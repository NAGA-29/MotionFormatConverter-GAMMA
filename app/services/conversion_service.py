import hashlib
import io
import mimetypes
import os
import shutil
import sys
import tempfile
import traceback
from typing import Any, Callable, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import bpy

from flask import jsonify, send_file
from werkzeug.utils import secure_filename

from app.blender import clear_scene, handle_blender_error, import_file, setup_addons, export_file
from app.utils.logger import AppLogger

logger = AppLogger.get_logger(__name__)
PERSISTENT_CACHE_DIR = os.getenv("CONVERSION_CACHE_DIR", "/tmp/convert_cache")

SUPPORTED_FORMATS: Dict[str, list] = {
    "fbx": ["application/octet-stream", "application/x-autodesk-fbx"],
    "obj": ["application/x-tgif", "text/plain", "application/octet-stream"],
    "gltf": ["model/gltf+json", "application/json"],
    "glb": ["model/gltf-binary"],
    "vrm": ["application/octet-stream", "model/gltf-binary", "model/vrml"],
    "bvh": ["application/octet-stream"],
}


def conversion_doc(input_format: str, output_format: str) -> Dict[str, Any]:
    """Swagger用の基本的な辞書を生成する。"""
    return {
        "tags": ["conversion"],
        "consumes": ["multipart/form-data"],
        "parameters": [
            {
                "name": "file",
                "in": "formData",
                "type": "file",
                "required": True,
                "description": f"Input {input_format.upper()} file",
            }
        ],
        "responses": {
            200: {"description": f"Converted {output_format.upper()} file"},
            400: {"description": "Invalid input"},
            429: {"description": "Rate limit exceeded"},
            500: {"description": "Conversion error"},
        },
    }


def validate_file_format(file, format: str) -> Tuple[bool, Optional[str]]:
    """拡張子とMIMEタイプを検証する。"""
    if not file.filename.lower().endswith(f".{format}"):
        return False, f"File must have .{format} extension"

    mime_type = mimetypes.guess_type(file.filename)[0]
    if mime_type and format in SUPPORTED_FORMATS:
        if mime_type not in SUPPORTED_FORMATS[format]:
            return False, f"Invalid MIME type: {mime_type}"

    return True, None


def validate_file_size(file, max_file_size: int) -> Tuple[bool, Optional[str], bool]:
    """設定上限に対してファイルサイズを検証する。"""
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    if size > max_file_size:
        return (
            False,
            f"File size exceeds maximum limit of {max_file_size/1024/1024}MB",
            True,
        )
    elif size == 0:
        return False, "File is empty", False

    return True, None, False


def calculate_file_hash(file_path: str) -> str:
    """ファイルのSHA-256ハッシュを計算する。"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_cached_conversion(redis_client, input_path: str, output_format: str) -> Optional[str]:
    """キャッシュ済みの変換結果を取得する。"""
    try:
        file_hash = calculate_file_hash(input_path)
        cache_key = f"conversion:{file_hash}:{output_format}"

        cached_path = redis_client.get(cache_key)
        if cached_path and os.path.exists(cached_path):
            return cached_path

    except Exception as exc:
        logger.error(f"Error accessing cache: {exc}")

    return None


def cache_conversion_result(
    redis_client, input_path: str, output_path: str, output_format: str, cache_duration: int
) -> None:
    """成功した変換結果をキャッシュする。"""
    try:
        file_hash = calculate_file_hash(input_path)
        cache_key = f"conversion:{file_hash}:{output_format}"

        os.makedirs(PERSISTENT_CACHE_DIR, exist_ok=True)
        cached_copy_path = os.path.join(PERSISTENT_CACHE_DIR, f"{file_hash}.{output_format}")
        shutil.copy2(output_path, cached_copy_path)

        redis_client.setex(cache_key, cache_duration, cached_copy_path)

    except Exception as exc:
        logger.error(f"Error caching result: {exc}")


def cleanup_temp_files(temp_dir: str) -> bool:
    """一時ディレクトリを削除してクリーンアップする。"""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return True
    except Exception as exc:
        logger.error(f"Error cleaning up temporary files: {exc}")
        return False


def convert_file(
    input_path: str,
    output_path: str,
    input_format: str,
    output_format: str,
    *,
    importer: Callable = import_file,
    exporter: Callable = export_file,
    clear_scene_fn: Callable = clear_scene,
    setup_addons_fn: Callable = setup_addons,
):
    """Blenderを用いてファイルを別形式へ変換する。(成功可否, メッセージ)を返す。"""
    try:
        logger.info("=== Starting conversion process ===")
        logger.info(f"System info: {bpy.app.version_string}")  # type: ignore[name-defined]
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Input file exists: {os.path.exists(input_path)}")
        logger.info(f"Input file size: {os.path.getsize(input_path)}")

        sys.excepthook = handle_blender_error

        logger.info("Checking Blender addons...")
        success, error = setup_addons_fn()
        if not success:
            logger.error(f"Addon setup failed: {error}")
            return False, error

        if not os.path.exists(input_path):
            logger.error(f"Input file does not exist: {input_path}")
            return False, "Input file does not exist"

        if not os.access(input_path, os.R_OK):
            logger.error(f"Input file is not readable: {input_path}")
            return False, "Input file is not readable"

        logger.info(f"Input file exists and is readable: {input_path}")

        if os.path.getsize(input_path) == 0:
            logger.error(f"Input file is empty: {input_path}")
            return False, "Input file is empty"

        success, error = clear_scene_fn()
        if not success:
            logger.error(f"Failed to clear scene: {error}")
            return False, error
        logger.info("Scene cleared successfully")

        try:
            logger.info(f"Attempting to import file: {input_path}")
            logger.info(f"Current working directory: {os.getcwd()}")
            logger.info(f"File size: {os.path.getsize(input_path)} bytes")

            success, error = importer(input_path, input_format)
            if not success:
                logger.error(f"Failed to import file: {error}")
                return False, error

            logger.info("File imported successfully")
            logger.info(f"Number of objects in scene: {len(bpy.data.objects)}")  # type: ignore[name-defined]
            logger.info("Scene statistics:")
            logger.info(f"- Meshes: {len(bpy.data.meshes)}")  # type: ignore[name-defined]
            logger.info(f"- Materials: {len(bpy.data.materials)}")  # type: ignore[name-defined]
            logger.info(f"- Textures: {len(bpy.data.textures)}")  # type: ignore[name-defined]
            logger.info(f"- Images: {len(bpy.data.images)}")  # type: ignore[name-defined]

            for obj in bpy.data.objects:  # type: ignore[name-defined]
                logger.info(f"Object: {obj.name}, Type: {obj.type}")
        except Exception as exc:
            logger.error(f"Exception during import: {exc}")
            logger.error(traceback.format_exc())
            return False, f"Import error: {exc}"

        try:
            logger.info(f"Attempting to export to {output_format} at path: {output_path}")
            output_dir = os.path.dirname(output_path)
            if not os.path.exists(output_dir):
                logger.info(f"Creating output directory: {output_dir}")
                os.makedirs(output_dir, exist_ok=True)

            if not os.access(output_dir, os.W_OK):
                logger.error(f"Output directory is not writable: {output_dir}")
                return False, "Output directory is not writable"

            success, error = exporter(output_path, output_format)
            if not success:
                logger.error(f"Failed to export file: {error}")
                return False, error

            if not os.path.exists(output_path):
                logger.error(f"Export file was not created at {output_path}")
                return False, "Export file was not created"

            file_size = os.path.getsize(output_path)
            logger.info(f"File exported successfully to {output_path} (size: {file_size} bytes)")
            return True, "Conversion successful"

        except Exception as exc:
            logger.error(f"Exception during export: {exc}")
            logger.error(traceback.format_exc())
            return False, f"Export error: {exc}"
    except Exception as exc:
        logger.error(f"Error during conversion: {exc}")
        return False, f"Error during conversion: {exc}"
    finally:
        sys.excepthook = sys.__excepthook__


def run_conversion_with_timeout(convert_func: Callable, timeout_seconds: int) -> Tuple[bool, str]:
    """指定した変換関数をタイムアウト付きで実行する（スレッド実行でクロスプラットフォーム対応）。"""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(convert_func)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeout:
            future.cancel()
            return False, "Conversion timed out"


def process_conversion(
    request,
    input_format: str,
    output_format: str,
    *,
    settings,
    redis_client,
    convert_func: Callable,
    validate_format_fn: Callable,
    validate_size_fn: Callable,
    get_cached_fn: Callable,
    cache_result_fn: Callable,
    cleanup_fn: Callable,
    clear_scene_fn: Callable,
    supported_formats: Dict[str, list] = SUPPORTED_FORMATS,
):
    """検証・キャッシュ確認・変換実行・レスポンス生成までを統括する。"""
    temp_dir = None
    try:
        logger.info(f"Starting conversion request: {input_format} -> {output_format}")

        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400
        file_content = file.read()

        success, error = validate_format_fn(file, input_format)
        if not success:
            logger.error(f"File format validation failed: {error}")
            return jsonify({"error": error}), 400

        success, error, too_large = validate_size_fn(file)
        if not success:
            logger.error(f"File size validation failed: {error}")
            status_code = 413 if too_large else 400
            return jsonify({"error": error}), status_code

        temp_dir = tempfile.mkdtemp(prefix="convert_")
        logger.info(f"Created temporary directory: {temp_dir}")

        input_filename = secure_filename(f"input.{input_format}")
        input_path = os.path.join(temp_dir, input_filename)
        with open(input_path, "wb") as f:
            f.write(file_content)
        logger.info(f"Saved input file: {input_path}")

        cached_path = get_cached_fn(input_path, output_format)
        if cached_path:
            logger.info("Using cached conversion result")
            return send_file(
                cached_path,
                as_attachment=True,
                download_name=secure_filename(f"converted.{output_format}"),
                mimetype=supported_formats[output_format][0],
            )

        output_filename = secure_filename(f"converted.{output_format}")
        output_path = os.path.join(temp_dir, output_filename)
        logger.info(f"Will save converted file to: {output_path}")

        success, error = clear_scene_fn()
        if not success:
            logger.error(f"Failed to clear scene before conversion: {error}")
            cleanup_fn(temp_dir)
            return jsonify({"error": error}), 500

        success, message = convert_func(input_path, output_path, input_format, output_format)

        if not success:
            logger.error(f"Conversion failed: {message}")
            cleanup_fn(temp_dir)
            return jsonify({"error": message}), 500

        logger.info(f"Conversion successful: {input_format} -> {output_format}")

        cache_result_fn(input_path, output_path, output_format)

        try:
            if not os.path.exists(output_path):
                logger.error(f"Output file does not exist at {output_path}")
                return jsonify({"error": "Converted file not found"}), 500

            file_size = os.path.getsize(output_path)
            logger.info(f"Sending file {output_path} (size: {file_size} bytes)")

            try:
                with open(output_path, "rb") as f:
                    file_data = f.read()

                logger.info(f"File {output_path} read into memory (size: {len(file_data)} bytes)")
                cleanup_fn(temp_dir)
                logger.info("Temporary files cleaned up")

                return send_file(
                    io.BytesIO(file_data),
                    as_attachment=True,
                    download_name=secure_filename(f"converted.{output_format}"),
                    mimetype=supported_formats[output_format][0],
                    max_age=0,
                )
            except IOError as exc:
                logger.error(f"Error reading output file: {exc}")
                return jsonify({"error": "Error reading converted file"}), 500

        except Exception as exc:
            logger.error(f"Error sending file: {exc}")
            cleanup_fn(temp_dir)
            return jsonify({"error": "Error sending converted file"}), 500

    except Exception as exc:
        logger.error(f"Conversion handler error: {exc}")
        if temp_dir:
            cleanup_fn(temp_dir)
        return jsonify({"error": str(exc)}), 500
