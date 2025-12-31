import gc
import sys
import traceback
from typing import Optional, Tuple

import bpy

from app.utils.logger import AppLogger

logger = AppLogger.get_logger(__name__)


def handle_blender_error(error_type, value, tb):
    """Blender実行中の未処理例外を捕捉し、ログ出力とシーン初期化を試みたうえで再送出する。"""
    error_msg = f"Blender error: {error_type.__name__}: {value}"
    logger.error(error_msg)
    logger.error("Traceback:")
    for line in traceback.format_tb(tb):
        logger.error(line.strip())

    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    except Exception:
        # If the reset itself fails, continue to surface the original exception.
        pass

    raise value


def clear_scene() -> Tuple[bool, Optional[str]]:
    """Blenderシーンを初期化し、オブジェクト/データブロックを削除してGCを実行する。(成功可否, メッセージ)を返す。"""
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)

        scene = bpy.context.scene
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.film_transparent = True

        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()

        for collection in [
            bpy.data.meshes,
            bpy.data.materials,
            bpy.data.textures,
            bpy.data.images,
            bpy.data.actions,
            bpy.data.armatures,
        ]:
            for item in collection:
                collection.remove(item)

        gc.collect()
        return True, None
    except Exception as exc:
        logger.error(f"Error clearing scene: {exc}")
        return False, f"Error clearing scene: {exc}"


def setup_vrm_addon() -> Tuple[bool, Optional[str]]:
    """VRMアドオンのパスを追加し、GLTFを先に有効化してVRMを登録する。(成功可否, メッセージ)を返す。"""
    try:
        addon_paths = [
            "/usr/local/blender/4.3/scripts/addons",
            "/usr/local/blender/4.3/scripts/addons/modules",
        ]
        for path in addon_paths:
            if path not in sys.path:
                sys.path.append(path)

        if not hasattr(bpy.ops.import_scene, "gltf"):
            logger.info("Enabling GLTF addon...")
            bpy.ops.preferences.addon_enable(module="io_scene_gltf2")

        import importlib
        import io_scene_vrm

        importlib.reload(io_scene_vrm)
        io_scene_vrm.register()

        if not hasattr(bpy.ops.import_scene, "vrm"):
            logger.error("VRM addon registration failed")
            return False, "VRM addon registration failed"

        logger.info("VRM addon setup completed successfully")
        return True, None
    except Exception as exc:
        logger.error(f"Error setting up VRM addon: {exc}")
        return False, f"Error setting up VRM addon: {exc}"


def setup_addons() -> Tuple[bool, Optional[str]]:
    """必須アドオン（FBX, glTF）が有効か確認し、足りなければ有効化する。(成功可否, メッセージ)を返す。"""
    try:
        logger.info("Setting up required addons...")
        required_addons = ["io_scene_fbx", "io_scene_gltf2"]

        for addon in required_addons:
            if not hasattr(bpy.ops.import_scene, addon.split("_")[-1]):
                try:
                    bpy.ops.preferences.addon_enable(module=addon)
                    logger.info(f"Enabled addon: {addon}")
                except Exception as exc:
                    logger.error(f"Failed to enable {addon}: {exc}")
                    return False, f"Failed to enable {addon}"

        return True, None
    except Exception as exc:
        logger.error(f"Error setting up addons: {exc}")
        return False, f"Error setting up addons: {exc}"


def initialize_blender() -> Tuple[bool, Optional[str]]:
    """ヘッドレス変換向けにBlenderを初期化する。エラーフック設定、アドオン有効化、シーン/データクリア、レンダー設定調整、VRM登録解除を行い、(成功可否, メッセージ)を返す。"""
    try:
        sys.excepthook = handle_blender_error

        bpy.ops.wm.read_factory_settings(use_empty=True)

        success, error = setup_addons()
        if not success:
            return False, error

        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()

        scene = bpy.context.scene
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.film_transparent = True
        scene.render.use_persistent_data = False

        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    for space in area.spaces:
                        if space.type == "VIEW_3D":
                            space.shading.type = "SOLID"
                            space.shading.use_scene_lights = False
                            space.shading.use_scene_world = False

        try:
            import io_scene_vrm

            io_scene_vrm.unregister()
        except Exception:
            # If VRM was not registered, continue without failing init.
            pass

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
            except Exception as exc:
                logger.warning(f"Error clearing {name}: {exc}")

        gc.collect()
        return True, None
    except Exception as exc:
        logger.error(f"Error initializing Blender: {exc}")
        return False, f"Error initializing Blender: {exc}"
    finally:
        sys.excepthook = sys.__excepthook__
