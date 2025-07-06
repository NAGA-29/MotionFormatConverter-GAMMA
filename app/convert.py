import bpy
import os
import sys
import tempfile
import logging
from app.utils.logger import AppLogger
from flask import Flask, request, jsonify, send_file
import shutil
from werkzeug.utils import secure_filename
import mimetypes
from functools import wraps
import time
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib
import redis
import signal
import threading
import traceback
import io
import gc

# Configure logging
logger = AppLogger.get_logger(__name__)
logger.debug("convert module loaded")

app = Flask(__name__)

# Redis connection for rate limiting and caching
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=0,
    decode_responses=True,
    socket_connect_timeout=5,
    retry_on_timeout=True
)

# Configuration from environment variables
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 50 * 1024 * 1024))  # Default 50MB
RATE_LIMIT_REQUESTS = int(os.getenv('RATE_LIMIT_REQUESTS', 10))
RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', 60))  # seconds
CONVERSION_TIMEOUT = int(os.getenv('CONVERSION_TIMEOUT', 300))  # seconds
CACHE_DURATION = int(os.getenv('CACHE_DURATION', 3600))  # 1 hour

# Supported file formats and their MIME types
SUPPORTED_FORMATS = {
    'fbx': ['application/octet-stream', 'application/x-autodesk-fbx'],
    'obj': ['application/x-tgif', 'text/plain', 'application/octet-stream'],
    'gltf': ['model/gltf+json', 'application/json'],
    'glb': ['model/gltf-binary'],
    'vrm': ['application/octet-stream', 'model/gltf-binary']
}

def handle_blender_error(error_type, value, tb):
    """Global error handler for Blender operations"""
    error_msg = f"Blender error: {error_type.__name__}: {value}"
    logger.error(error_msg)
    logger.error("Traceback:")
    for line in traceback.format_tb(tb):
        logger.error(line.strip())
    
    # Try to recover from the error
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    except:
        pass
    
    # Re-raise the error to be caught by the conversion handler
    raise value

def rate_limit(f):
    """Decorator to apply rate limiting to a Flask route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get client IP
        ip = request.remote_addr
        
        # Get current timestamp
        now = int(time.time())
        key = f'rate_limit:{ip}'
        
        # Check rate limit
        try:
            # Use Redis to track requests
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, now - RATE_LIMIT_WINDOW)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, RATE_LIMIT_WINDOW)
            _, request_count, *_ = pipe.execute()
            
            if request_count >= RATE_LIMIT_REQUESTS:
                return jsonify({"error": "Rate limit exceeded"}), 429
                
        except redis.RedisError as e:
            logger.error(f"Redis error in rate limiting: {str(e)}")
            # Continue without rate limiting if Redis is unavailable
            pass
            
        return f(*args, **kwargs)
    return decorated_function

def timeout_handler(signum, frame):
    """Signal handler for conversion timeout"""
    raise TimeoutError("Operation timed out")

def calculate_file_hash(file_path):
    """Calculate SHA-256 hash of file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def convert_file_with_timeout(input_path, output_path, input_format, output_format):
    """Convert file from one format to another with timeout"""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(CONVERSION_TIMEOUT)
    try:
        result = convert_file(input_path, output_path, input_format, output_format)
        signal.alarm(0)  # Disable the alarm
        return result
    except TimeoutError:
        return False, "Conversion timed out"
    finally:
        signal.alarm(0)  # Ensure the alarm is disabled

def get_cached_conversion(input_path, output_format):
    """Try to get cached conversion result"""
    try:
        file_hash = calculate_file_hash(input_path)
        cache_key = f"conversion:{file_hash}:{output_format}"
        
        cached_path = redis_client.get(cache_key)
        if cached_path and os.path.exists(cached_path):
            return cached_path
            
    except (redis.RedisError, IOError) as e:
        logger.error(f"Error accessing cache: {str(e)}")
        
    return None

def cache_conversion_result(input_path, output_path, output_format):
    """Cache successful conversion result"""
    try:
        file_hash = calculate_file_hash(input_path)
        cache_key = f"conversion:{file_hash}:{output_format}"
        
        redis_client.setex(cache_key, CACHE_DURATION, output_path)
        
    except (redis.RedisError, IOError) as e:
        logger.error(f"Error caching result: {str(e)}")

def validate_file_format(file, format):
    """Validate file format and MIME type"""
    if not file.filename.lower().endswith(f'.{format}'):
        return False, f"File must have .{format} extension"
    
    mime_type = mimetypes.guess_type(file.filename)[0]
    if mime_type and format in SUPPORTED_FORMATS:
        if mime_type not in SUPPORTED_FORMATS[format]:
            return False, f"Invalid MIME type: {mime_type}"
    
    return True, None

def validate_file_size(file):
    """Validate file size"""
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    
    if size > MAX_FILE_SIZE:
        return False, f"File size exceeds maximum limit of {MAX_FILE_SIZE/1024/1024}MB"
    elif size == 0:
        return False, "File is empty"
        
    return True, None

def clear_scene():
    """Clear the current scene"""
    try:
        # Force Load Factory Settings
        bpy.ops.wm.read_factory_settings(use_empty=True)
        
        # Set default scene settings
        scene = bpy.context.scene
        scene.render.engine = 'BLENDER_WORKBENCH'
        scene.render.film_transparent = True
        
        # Clear all objects
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()
        
        # データブロックのクリーンアップ
        for collection in [bpy.data.meshes, bpy.data.materials, 
                         bpy.data.textures, bpy.data.images,
                         bpy.data.actions, bpy.data.armatures]:
            for item in collection:
                collection.remove(item)  # do_unlink=True を削除
        
        # Force garbage collection
        gc.collect()
            
        return True, None
    except Exception as e:
        logger.error(f"Error clearing scene: {str(e)}")
        return False, f"Error clearing scene: {str(e)}"

def setup_vrm_addon():
    """Enable VRM addon if not already enabled"""
    try:
        # Add addon paths to sys.path if not already there
        addon_paths = [
            "/usr/local/blender/4.3/scripts/addons",
            "/usr/local/blender/4.3/scripts/addons/modules"
        ]
        for path in addon_paths:
            if path not in sys.path:
                sys.path.append(path)

        # Ensure GLTF addon is enabled first
        if not hasattr(bpy.ops.import_scene, 'gltf'):
            logger.info("Enabling GLTF addon...")
            bpy.ops.preferences.addon_enable(module='io_scene_gltf2')
            
        # Import and reload the VRM addon module
        import importlib
        import io_scene_vrm
        importlib.reload(io_scene_vrm)
        
        # Register the addon
        io_scene_vrm.register()
        
        # Verify registration
        if not hasattr(bpy.ops.import_scene, 'vrm'):
            logger.error("VRM addon registration failed")
            return False, "VRM addon registration failed"
            
        logger.info("VRM addon setup completed successfully")
        return True, None
    except Exception as e:
        logger.error(f"Error setting up VRM addon: {str(e)}")
        return False, f"Error setting up VRM addon: {str(e)}"

def import_file(input_path, file_format):
    """Import file based on format"""
    try:
        logger.info(f"Importing {file_format} file: {input_path}")

        # 既存のデータをクリーンアップ
        bpy.ops.wm.read_factory_settings(use_empty=True)
        for obj in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
            
        # メモリを明示的に解放
        gc.collect()

        if file_format == 'fbx':
            # bpy.ops.import_scene.fbx(filepath=input_path)
            bpy.ops.import_scene.fbx(
                filepath=input_path,
                use_custom_props=False,  # カスタムプロパティを無視
                use_image_search=False,  # テクスチャ検索を無効化
                use_anim=False,         # アニメーションを無視
                global_scale=1.0,       # スケールを維持
                use_manual_orientation=True  # 手動方向設定
            )
        elif file_format == 'obj':
            bpy.ops.import_scene.obj(filepath=input_path)
        elif file_format == 'gltf':
            bpy.ops.import_scene.gltf(filepath=input_path)
        elif file_format == 'glb':
            bpy.ops.import_scene.gltf(filepath=input_path)
        elif file_format == 'vrm':
            success, error = setup_vrm_addon()
            if not success:
                return False, error
            bpy.ops.import_scene.vrm(filepath=input_path)
        else:
            return False, f"Unsupported input format: {file_format}"
        
        # Verify import was successful
        if len(bpy.data.objects) == 0:
            logger.error("Import resulted in no objects")
            return False, "Import resulted in no objects"
            
        logger.info(f"Successfully imported {len(bpy.data.objects)} objects")
        return True, None
    except Exception as e:
        logger.error(f"Error importing file: {str(e)}")
        return False, f"Error importing file: {str(e)}"

def export_file(output_path, file_format):
    """Export file based on format"""
    try:
        logger.info(f"Exporting to {file_format}: {output_path}")
        
        if file_format == 'fbx':
            bpy.ops.export_scene.fbx(filepath=output_path, use_selection=False)
        elif file_format == 'obj':
            bpy.ops.export_scene.obj(filepath=output_path, use_selection=False)
        elif file_format == 'gltf':
            bpy.ops.export_scene.gltf(filepath=output_path, export_format='GLTF_SEPARATE')
        elif file_format == 'glb':
            bpy.ops.export_scene.gltf(filepath=output_path, export_format='GLB')
        elif file_format == 'vrm':
            success, error = setup_vrm_addon()
            if not success:
                return False, error
            bpy.ops.export_scene.vrm(filepath=output_path)
        else:
            return False, f"Unsupported output format: {file_format}"
            
        # Verify export was successful
        if not os.path.exists(output_path):
            logger.error("Export file was not created")
            return False, "Export file was not created"
            
        logger.info(f"Successfully exported to {output_path}")
        return True, None
    except Exception as e:
        logger.error(f"Error exporting file: {str(e)}")
        return False, f"Error exporting file: {str(e)}"

def convert_file(input_path, output_path, input_format, output_format):
    """Convert file from one format to another"""
    try:
        logger.info("=== Starting conversion process ===")
        logger.info(f"System info: {bpy.app.version_string}")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Input file exists: {os.path.exists(input_path)}")
        logger.info(f"Input file size: {os.path.getsize(input_path)}")
        # logger.info(f"Starting conversion from {input_format} to {output_format}")
        # logger.info(f"Input path: {input_path}")
        # logger.info(f"Output path: {output_path}")
        
        # Set up error handling
        sys.excepthook = handle_blender_error
        
        # Verify Blender addons
        logger.info("Checking Blender addons...")
        for addon_name in ['io_scene_gltf2', 'io_scene_fbx', 'io_scene_obj']:
            if hasattr(bpy.ops.import_scene, addon_name.split('_')[-1]):
                logger.info(f"Addon {addon_name} is available")
            else:
                logger.warning(f"Addon {addon_name} is not available")
                try:
                    bpy.ops.preferences.addon_enable(module=addon_name)
                    logger.info(f"Enabled addon {addon_name}")
                except Exception as e:
                    logger.error(f"Failed to enable addon {addon_name}: {str(e)}")
        
        # Verify input file exists and is readable
        if not os.path.exists(input_path):
            logger.error(f"Input file does not exist: {input_path}")
            return False, "Input file does not exist"
        
        if not os.access(input_path, os.R_OK):
            logger.error(f"Input file is not readable: {input_path}")
            return False, "Input file is not readable"
            
        logger.info(f"Input file exists and is readable: {input_path}")
            
        # Verify input file is not empty
        if os.path.getsize(input_path) == 0:
            logger.error(f"Input file is empty: {input_path}")
            return False, "Input file is empty"
            
        # Clear existing scene
        success, error = clear_scene()
        if not success:
            logger.error(f"Failed to clear scene: {error}")
            return False, error
        logger.info("Scene cleared successfully")
        
        # Import the file
        try:
            logger.info(f"Attempting to import file: {input_path}")
            logger.info(f"Current working directory: {os.getcwd()}")
            logger.info(f"File size: {os.path.getsize(input_path)} bytes")
            
            success, error = import_file(input_path, input_format)
            if not success:
                logger.error(f"Failed to import file: {error}")
                return False, error
                
            logger.info("File imported successfully")
            logger.info(f"Number of objects in scene: {len(bpy.data.objects)}")
            logger.info(f"Scene statistics:")
            logger.info(f"- Meshes: {len(bpy.data.meshes)}")
            logger.info(f"- Materials: {len(bpy.data.materials)}")
            logger.info(f"- Textures: {len(bpy.data.textures)}")
            logger.info(f"- Images: {len(bpy.data.images)}")
            
            # Log object details for debugging
            for obj in bpy.data.objects:
                logger.info(f"Object: {obj.name}, Type: {obj.type}")
        except Exception as e:
            logger.error(f"Exception during import: {str(e)}")
            logger.error(traceback.format_exc())
            return False, f"Import error: {str(e)}"
        
        # Export to the desired format
        try:
            logger.info(f"Attempting to export to {output_format} at path: {output_path}")
            # Verify output directory exists and is writable
            output_dir = os.path.dirname(output_path)
            if not os.path.exists(output_dir):
                logger.info(f"Creating output directory: {output_dir}")
                os.makedirs(output_dir, exist_ok=True)
            
            if not os.access(output_dir, os.W_OK):
                logger.error(f"Output directory is not writable: {output_dir}")
                return False, "Output directory is not writable"
            
            success, error = export_file(output_path, output_format)
            if not success:
                logger.error(f"Failed to export file: {error}")
                return False, error
                
            if not os.path.exists(output_path):
                logger.error(f"Export file was not created at {output_path}")
                return False, "Export file was not created"
                
            file_size = os.path.getsize(output_path)
            logger.info(f"File exported successfully to {output_path} (size: {file_size} bytes)")
            return True, "Conversion successful"
            
        except Exception as e:
            logger.error(f"Exception during export: {str(e)}")
            logger.error(traceback.format_exc())
            return False, f"Export error: {str(e)}"
    except Exception as e:
        logger.error(f"Error during conversion: {str(e)}")
        return False, f"Error during conversion: {str(e)}"
    finally:
        # Reset error handler
        sys.excepthook = sys.__excepthook__

def cleanup_temp_files(temp_dir):
    """Clean up temporary files"""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return True
    except Exception as e:
        logger.error(f"Error cleaning up temporary files: {str(e)}")
        return False

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file size limit exceeded error"""
    return jsonify({"error": f"File size exceeds maximum limit of {MAX_FILE_SIZE/1024/1024}MB"}), 413

@app.errorhandler(429)
def too_many_requests(error):
    """Handle rate limit exceeded error"""
    return jsonify({"error": "Rate limit exceeded"}), 429

def handle_conversion(request, input_format, output_format):
    """Generic handler for file conversion requests"""
    temp_dir = None
    try:
        logger.info(f"Starting conversion request: {input_format} -> {output_format}")

        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        file_content = file.read()
        
        # Validate file format
        success, error = validate_file_format(file, input_format)
        if not success:
            logger.error(f"File format validation failed: {error}")
            return jsonify({"error": error}), 400
            
        # Validate file size
        success, error = validate_file_size(file)
        if not success:
            logger.error(f"File size validation failed: {error}")
            return jsonify({"error": error}), 400
        
        # Create output directory if it doesn't exist
        output_dir = '/app/output'
        os.makedirs(output_dir, exist_ok=True)
        
        # Create temporary directory with a unique name
        temp_dir = tempfile.mkdtemp(prefix='convert_', dir='/tmp/convert')
        logger.info(f"Created temporary directory: {temp_dir}")
        
        # Save input file with secure filename
        input_filename = secure_filename(f"input.{input_format}")
        input_path = os.path.join(temp_dir, input_filename)
        # file.save(input_path)
        with open(input_path, 'wb') as f:
            f.write(file_content)
        logger.info(f"Saved input file: {input_path}")
        
        # Check cache
        cached_path = get_cached_conversion(input_path, output_format)
        if cached_path:
            logger.info("Using cached conversion result")
            return send_file(
                cached_path,
                as_attachment=True,
                download_name=secure_filename(f"converted.{output_format}"),
                mimetype=SUPPORTED_FORMATS[output_format][0]
            )
        
        # Set output path in the mounted output directory
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = secure_filename(f"{timestamp}_converted.{output_format}")
        output_path = os.path.join(output_dir, output_filename)
        logger.info(f"Will save converted file to: {output_path}")
        
        # Clear Blender scene before conversion
        success, error = clear_scene()
        if not success:
            logger.error(f"Failed to clear scene before conversion: {error}")
            cleanup_temp_files(temp_dir)
            return jsonify({"error": error}), 500
        
        # Perform conversion
        success, message = convert_file_with_timeout(input_path, output_path, input_format, output_format)
        
        if not success:
            logger.error(f"Conversion failed: {message}")
            cleanup_temp_files(temp_dir)
            return jsonify({"error": message}), 500
        
        logger.info(f"Conversion successful: {input_format} -> {output_format}")
        
        # Cache successful conversion
        cache_conversion_result(input_path, output_path, output_format)
        
        # Return the converted file
        try:
            if not os.path.exists(output_path):
                logger.error(f"Output file does not exist at {output_path}")
                return jsonify({"error": "Converted file not found"}), 500
            
            file_size = os.path.getsize(output_path)
            logger.info(f"Sending file {output_path} (size: {file_size} bytes)")
            
            try:
                # ファイルを読み込んでメモリにコピー
                with open(output_path, 'rb') as f:
                    file_data = f.read()
                
                logger.info(f"File {output_path} read into memory (size: {len(file_data)} bytes)")
                
                # クリーンアップを実行
                cleanup_temp_files(temp_dir)
                logger.info("Temporary files cleaned up")
                
                # メモリ内のデータを送信
                return send_file(
                    io.BytesIO(file_data),
                    as_attachment=True,
                    download_name=secure_filename(f"converted.{output_format}"),
                    mimetype=SUPPORTED_FORMATS[output_format][0],
                    max_age=0
                )
            except IOError as e:
                logger.error(f"Error reading output file: {str(e)}")
                return jsonify({"error": "Error reading converted file"}), 500
            
        except Exception as e:
            logger.error(f"Error sending file: {str(e)}")
            cleanup_temp_files(temp_dir)
            return jsonify({"error": "Error sending converted file"}), 500
            
    except Exception as e:
        logger.error(f"Conversion handler error: {str(e)}")
        if temp_dir:
            cleanup_temp_files(temp_dir)
        return jsonify({"error": str(e)}), 500

def setup_addons():
    """Initialize required Blender addons"""
    try:
        logger.info("Setting up required addons...")
        
        # Required addons
        required_addons = [
            'io_scene_fbx',
            'io_scene_gltf2'
        ]
        
        # Ensure addons are enabled and stay enabled
        for addon in required_addons:
            if not hasattr(bpy.ops.import_scene, addon.split('_')[-1]):
                try:
                    bpy.ops.preferences.addon_enable(module=addon)
                    logger.info(f"Enabled addon: {addon}")
                except Exception as e:
                    logger.error(f"Failed to enable {addon}: {str(e)}")
                    return False, f"Failed to enable {addon}"
        
        return True, None
    except Exception as e:
        logger.error(f"Error setting up addons: {str(e)}")
        return False, f"Error setting up addons: {str(e)}"

def initialize_blender():
    """Initialize Blender environment"""
    try:
        # Set up error handling
        sys.excepthook = handle_blender_error
        
        # Force Load Factory Settings with empty scene
        bpy.ops.wm.read_factory_settings(use_empty=True)
        
        # Set up required addons
        success, error = setup_addons()
        if not success:
            return False, error
        
        # Clear default scene
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()
        
        # Set default scene settings
        scene = bpy.context.scene
        scene.render.engine = 'BLENDER_WORKBENCH'  # CYCLES, BLENDER_EEVEE, BLENDER_WORKBENCH
        scene.render.film_transparent = True
        
        # メモリ使用量の最適化
        scene.render.use_persistent_data = False
        
        # Set up viewport for headless mode
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'SOLID'
                            space.shading.use_scene_lights = False
                            space.shading.use_scene_world = False
        
        # Unregister any existing VRM addon
        try:
            import io_scene_vrm
            io_scene_vrm.unregister()
        except:
            pass
        
        # Clear all data
        data_to_clear = [
            (bpy.data.objects, "objects"),
            (bpy.data.meshes, "meshes"),
            (bpy.data.materials, "materials"),
            (bpy.data.textures, "textures"),
            (bpy.data.images, "images"),
            (bpy.data.lights, "lights"),
            (bpy.data.cameras, "cameras"),
            (bpy.data.actions, "actions"),
            (bpy.data.armatures, "armatures"),
            (bpy.data.particles, "particles"),
            (bpy.data.node_groups, "node groups"),
        ]
        
        for data_collection, name in data_to_clear:
            try:
                for item in data_collection:
                    data_collection.remove(item, do_unlink=True)
                logger.info(f"Cleared {name}")
            except Exception as e:
                logger.warning(f"Error clearing {name}: {str(e)}")
        
        # Force garbage collection
        import gc
        gc.collect()
                
        return True, None
    except Exception as e:
        logger.error(f"Error initializing Blender: {str(e)}")
        return False, f"Error initializing Blender: {str(e)}"
    finally:
        # Reset error handler
        sys.excepthook = sys.__excepthook__

# Apply rate limiting to all conversion endpoints
@app.route('/convert/fbx-to-glb', methods=['POST'])
@rate_limit
def convert_fbx_to_glb():
    """Convert FBX to GLB"""
    return handle_conversion(request, 'fbx', 'glb')

@app.route('/convert/fbx-to-obj', methods=['POST'])
@rate_limit
def convert_fbx_to_obj():
    """Convert FBX to OBJ"""
    return handle_conversion(request, 'fbx', 'obj')

@app.route('/convert/fbx-to-gltf', methods=['POST'])
@rate_limit
def convert_fbx_to_gltf():
    """Convert FBX to GLTF"""
    return handle_conversion(request, 'fbx', 'gltf')

@app.route('/convert/fbx-to-vrm', methods=['POST'])
@rate_limit
def convert_fbx_to_vrm():
    """Convert FBX to VRM"""
    return handle_conversion(request, 'fbx', 'vrm')

@app.route('/convert/vrm-to-glb', methods=['POST'])
@rate_limit
def convert_vrm_to_glb():
    """Convert VRM to GLB"""
    return handle_conversion(request, 'vrm', 'glb')

@app.route('/convert/vrm-to-fbx', methods=['POST'])
@rate_limit
def convert_vrm_to_fbx():
    """Convert VRM to FBX"""
    return handle_conversion(request, 'vrm', 'fbx')

@app.route('/convert/vrm-to-obj', methods=['POST'])
@rate_limit
def convert_vrm_to_obj():
    """Convert VRM to OBJ"""
    return handle_conversion(request, 'vrm', 'obj')

@app.route('/convert/gltf-to-obj', methods=['POST'])
@rate_limit
def convert_gltf_to_obj():
    """Convert GLTF to OBJ"""
    return handle_conversion(request, 'gltf', 'obj')

@app.route('/convert/gltf-to-fbx', methods=['POST'])
@rate_limit
def convert_gltf_to_fbx():
    """Convert GLTF to FBX"""
    return handle_conversion(request, 'gltf', 'fbx')

@app.route('/convert/gltf-to-vrm', methods=['POST'])
@rate_limit
def convert_gltf_to_vrm():
    """Convert GLTF to VRM"""
    return handle_conversion(request, 'gltf', 'vrm')

@app.route('/convert/glb-to-obj', methods=['POST'])
@rate_limit
def convert_glb_to_obj():
    """Convert GLB to OBJ"""
    return handle_conversion(request, 'glb', 'obj')

@app.route('/convert/glb-to-fbx', methods=['POST'])
@rate_limit
def convert_glb_to_fbx():
    """Convert GLB to FBX"""
    return handle_conversion(request, 'glb', 'fbx')

@app.route('/convert/glb-to-vrm', methods=['POST'])
@rate_limit
def convert_glb_to_vrm():
    """Convert GLB to VRM"""
    return handle_conversion(request, 'glb', 'vrm')

@app.route('/convert/obj-to-glb', methods=['POST'])
@rate_limit
def convert_obj_to_glb():
    """Convert OBJ to GLB"""
    return handle_conversion(request, 'obj', 'glb')

@app.route('/convert/obj-to-fbx', methods=['POST'])
@rate_limit
def convert_obj_to_fbx():
    """Convert OBJ to FBX"""
    return handle_conversion(request, 'obj', 'fbx')

@app.route('/convert/obj-to-gltf', methods=['POST'])
@rate_limit
def convert_obj_to_gltf():
    """Convert OBJ to GLTF"""
    return handle_conversion(request, 'obj', 'gltf')

@app.route('/convert/obj-to-vrm', methods=['POST'])
@rate_limit
def convert_obj_to_vrm():
    """Convert OBJ to VRM"""
    return handle_conversion(request, 'obj', 'vrm')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint that also verifies Redis connection"""
    try:
        redis_client.ping()
        redis_status = "connected"
    except redis.RedisError:
        redis_status = "disconnected"
    
    return jsonify({
        "status": "healthy",
        "redis": redis_status,
        "timestamp": datetime.utcnow().isoformat()
    }), 200

if __name__ == '__main__':
    try:
        # Initialize Blender on startup
        success, error = initialize_blender()
        if not success:
            logger.error(f"Failed to initialize Blender: {error}")
            sys.exit(1)
        logger.info("Blender initialized successfully")
        
        # # Initialize VRM addon
        # success, error = setup_vrm_addon()
        # if not success:
        #     logger.error(f"Failed to setup VRM addon: {error}")
        #     sys.exit(1)
        # logger.info("VRM addon initialized successfully")
        
        # app.run(host='0.0.0.0', port=5000, debug=False)
        success, error = setup_addons()
        if not success:
            logger.error(f"Failed to setup addons: {error}")
            sys.exit(1)
            
        logger.info("Initialization complete")
        
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=False)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)
