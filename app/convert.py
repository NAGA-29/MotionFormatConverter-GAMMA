import sys
import time
import traceback
import threading
from datetime import datetime
from functools import wraps

import redis
from flask import Flask, jsonify, request
from flasgger import Swagger, swag_from
from werkzeug.utils import secure_filename

from app.blender import clear_scene, initialize_blender, setup_addons
from app.blender.io import export_file, import_file
from app.config import get_settings
from app.services.conversion_service import (
    SUPPORTED_FORMATS,
    cache_conversion_result,
    cleanup_temp_files,
    conversion_doc,  # re-exported for tests
    convert_file,
    get_cached_conversion,
    process_conversion,
    run_conversion_with_timeout,
    validate_file_format,
    validate_file_size,
)
from app.utils.logger import AppLogger
from app.utils.memory_profiler import init_memory_profiling, log_memory_snapshot

app_settings = get_settings()

# Configure logging
logger = AppLogger.get_logger(__name__)
logger.debug("convert module loaded")

app = Flask(__name__)
swagger = Swagger(app)


def is_local_env() -> bool:
    """ローカル環境で動作している場合にTrueを返す。"""
    return app_settings.is_local()


# Redis connection for rate limiting and caching
redis_client = redis.Redis(
    host=app_settings.redis_host,
    port=int(app_settings.redis_port),
    db=0,
    decode_responses=True,
    socket_connect_timeout=5,
    retry_on_timeout=True,
)

# Configuration from environment variables
MAX_FILE_SIZE = app_settings.max_file_size
RATE_LIMIT_REQUESTS = app_settings.rate_limit_requests
RATE_LIMIT_WINDOW = app_settings.rate_limit_window
CONVERSION_TIMEOUT = app_settings.conversion_timeout
CACHE_DURATION = app_settings.cache_duration


def rate_limit(f):
    """Flaskルートにレートリミットを適用するデコレーター。"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = request.remote_addr
        now = int(time.time())
        key = f"rate_limit:{ip}"

        try:
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, now - RATE_LIMIT_WINDOW)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, RATE_LIMIT_WINDOW)
            _, request_count, *_ = pipe.execute()

            if request_count >= RATE_LIMIT_REQUESTS:
                return jsonify({"error": "Rate limit exceeded"}), 429

        except redis.RedisError as exc:
            logger.error(f"Redis error in rate limiting: {exc}")
            # Continue without rate limiting if Redis is unavailable
            pass

        return f(*args, **kwargs)

    return decorated_function


def convert_file_with_timeout(input_path, output_path, input_format, output_format):
    """タイムアウト付きで変換を実行するラッパー。依存を注入して呼び出す。"""

    def conversion_callable():
        return convert_file(
            input_path,
            output_path,
            input_format,
            output_format,
            importer=import_file,
            exporter=export_file,
            clear_scene_fn=clear_scene,
            setup_addons_fn=setup_addons,
        )

    return run_conversion_with_timeout(conversion_callable, CONVERSION_TIMEOUT)


def _validate_file_size_with_limit(file):
    return validate_file_size(file, MAX_FILE_SIZE)


def handle_conversion(request, input_format, output_format):
    """変換リクエストを処理する共通ハンドラー。"""
    return process_conversion(
        request=request,
        input_format=input_format,
        output_format=output_format,
        settings=app_settings,
        redis_client=redis_client,
        convert_func=convert_file_with_timeout,
        validate_format_fn=validate_file_format,
        validate_size_fn=_validate_file_size_with_limit,
        get_cached_fn=lambda input_path, fmt: get_cached_conversion(
            redis_client, input_path, fmt
        ),
        cache_result_fn=lambda input_path, output_path, fmt: cache_conversion_result(
            redis_client, input_path, output_path, fmt, CACHE_DURATION
        ),
        cleanup_fn=cleanup_temp_files,
        clear_scene_fn=clear_scene,
        supported_formats=SUPPORTED_FORMATS,
    )


@app.errorhandler(413)
def request_entity_too_large(error):
    """ファイルサイズ上限超過エラーを処理する。"""
    return (
        jsonify(
            {
                "error": f"File size exceeds maximum limit of {MAX_FILE_SIZE/1024/1024}MB"
            }
        ),
        413,
    )


@app.errorhandler(429)
def too_many_requests(error):
    """レートリミット超過エラーを処理する。"""
    return jsonify({"error": "Rate limit exceeded"}), 429


# Apply rate limiting to all conversion endpoints
@app.route("/convert", methods=["POST"])
@rate_limit
@swag_from(
    {
        "tags": ["conversion"],
        "consumes": ["multipart/form-data"],
        "parameters": [
            {
                "name": "file",
                "in": "formData",
                "type": "file",
                "required": True,
                "description": "Input file to convert. The file extension determines the input format.",
            },
            {
                "name": "output_format",
                "in": "query",
                "type": "string",
                "required": True,
                "description": "The desired output format (e.g., glb, fbx, obj).",
            },
        ],
        "responses": {
            200: {"description": "Converted file"},
            400: {"description": "Invalid input"},
            429: {"description": "Rate limit exceeded"},
            500: {"description": "Conversion error"},
        },
    }
)
def convert_generic():
    """汎用的な変換エンドポイント。"""
    output_format = request.args.get("output_format")
    if not output_format:
        return jsonify({"error": "output_format query parameter is required"}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(file.filename)
    if "." not in filename:
        return jsonify({"error": "File has no extension"}), 400

    input_format = filename.rsplit(".", 1)[1].lower()

    if input_format not in SUPPORTED_FORMATS:
        return jsonify({"error": f"Unsupported input format: {input_format}"}), 400

    if output_format not in SUPPORTED_FORMATS:
        return jsonify({"error": f"Unsupported output format: {output_format}"}), 400

    return handle_conversion(request, input_format, output_format)


@app.route("/health", methods=["GET"])
def health_check():
    """ヘルスチェックとRedis疎通を返すエンドポイント。"""
    try:
        redis_client.ping()
        redis_status = "connected"
    except redis.RedisError:
        redis_status = "disconnected"

    return (
        jsonify(
            {
                "status": "healthy",
                "redis": redis_status,
                "timestamp": datetime.utcnow().isoformat(),
            }
        ),
        200,
    )


# Background task for memory profiling
stop_event = threading.Event()

def memory_profiling_task():
    """Periodically logs memory usage."""
    interval = app_settings.memory_profiling_interval
    while not stop_event.is_set():
        try:
            log_memory_snapshot()
        except Exception as e:
            logger.error(f"Error in memory profiling task: {e}")
        finally:
            # Wait for the interval before the next run, even if an error occurred.
            stop_event.wait(interval)

if __name__ == "__main__":
    profiling_thread = None
    if app_settings.enable_memory_profiling:
        init_memory_profiling()
        profiling_thread = threading.Thread(target=memory_profiling_task, daemon=True)
        profiling_thread.start()

    exit_code = 0
    try:
        success, error = initialize_blender()
        if not success:
            logger.error(f"Failed to initialize Blender: {error}")
            exit_code = 1

        if exit_code == 0:
            logger.info("Blender initialized successfully")
            success, error = setup_addons()
            if not success:
                logger.error(f"Failed to setup addons: {error}")
                exit_code = 1

        if exit_code == 0:
            logger.info("Initialization complete")
            app.run(host="0.0.0.0", port=5000, debug=False, threaded=False)

    except KeyboardInterrupt:
        logger.info("Application interrupted by user.")
        exit_code = 130
    except Exception as exc:
        logger.error(f"Fatal error: {exc}")
        logger.error(traceback.format_exc())
        exit_code = 1
    finally:
        # Stop the background thread if it was started
        if profiling_thread:
            stop_event.set()
            profiling_thread.join()
            logger.info("Memory profiling thread stopped.")

    sys.exit(exit_code)
