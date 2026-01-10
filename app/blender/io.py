import gc
import os

import bpy
from typing import Optional, Tuple

from app.utils.logger import AppLogger
from app.blender.setup import reset_factory_settings, setup_vrm_addon

logger = AppLogger.get_logger(__name__)


def import_file(input_path: str, file_format: str) -> Tuple[bool, Optional[str]]:
    """
    指定された形式に応じてBlenderへインポートし、(成功可否, メッセージ)を返す。

    Args:
        input_path (str): インポート対象ファイルのパス。
        file_format (str): インポートするファイル形式。
            サポートされている値は "fbx", "obj", "gltf", "glb", "vrm", "bvh"。
            それ以外の値が指定された場合は未対応形式として失敗を返す。

    Returns:
        Tuple[bool, Optional[str]]: (処理が成功したかどうか, エラーメッセージまたはNone)。
    """
    try:
        logger.info(f"Importing {file_format} file: {input_path}")

        reset_factory_settings()
        for obj in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)

        gc.collect()

        if file_format == "fbx":
            bpy.ops.import_scene.fbx(
                filepath=input_path,
                use_custom_props=False,
                use_image_search=False,
                use_anim=False,
                global_scale=1.0,
                use_manual_orientation=True,
            )
        elif file_format == "obj":
            bpy.ops.import_scene.obj(filepath=input_path)
        elif file_format in ("gltf", "glb"):
            bpy.ops.import_scene.gltf(filepath=input_path)
        elif file_format == "vrm":
            success, error = setup_vrm_addon()
            if not success:
                return False, error
            bpy.ops.import_scene.vrm(filepath=input_path)
        elif file_format == "bvh":
            bpy.ops.import_anim.bvh(filepath=input_path)
        else:
            return False, f"Unsupported input format: {file_format}"

        if len(bpy.data.objects) == 0:
            logger.error("Import resulted in no objects")
            return False, "Import resulted in no objects"

        logger.info(f"Successfully imported {len(bpy.data.objects)} objects")
        return True, None
    except Exception as exc:
        logger.error(f"Error importing file: {exc}")
        return False, f"Error importing file: {exc}"


def export_file(output_path: str, file_format: str) -> Tuple[bool, Optional[str]]:
    """
    現在のシーンを指定フォーマットでエクスポートし、(成功可否, メッセージ)を返す。

    Args:
        output_path: エクスポート先のファイルパス。拡張子も含めた出力ファイルのフルパスを指定する。
        file_format: 出力するファイルフォーマットを表す文字列。
            サポートされている値は以下の通り:

            - "fbx": FBX 形式
            - "obj": OBJ 形式
            - "gltf": glTF (GLTF_SEPARATE) 形式
            - "glb": GLB (バイナリ glTF) 形式
            - "vrm": VRM 形式
            - "bvh": BVH アニメーション形式

    Returns:
        Tuple[bool, Optional[str]]: (成功可否, メッセージ) のタプル。
            成功時は (True, None)、失敗時は (False, エラーメッセージ) を返す。
    """
    try:
        logger.info(f"Exporting to {file_format}: {output_path}")

        if file_format == "fbx":
            bpy.ops.export_scene.fbx(filepath=output_path, use_selection=False)
        elif file_format == "obj":
            bpy.ops.export_scene.obj(filepath=output_path, use_selection=False)
        elif file_format == "gltf":
            bpy.ops.export_scene.gltf(filepath=output_path, export_format="GLTF_SEPARATE")
        elif file_format == "glb":
            bpy.ops.export_scene.gltf(filepath=output_path, export_format="GLB")
        elif file_format == "vrm":
            success, error = setup_vrm_addon()
            if not success:
                return False, error
            bpy.ops.export_scene.vrm(filepath=output_path)
        elif file_format == "bvh":
            if not bpy.data.actions:
                return False, "No animation data found to export to BVH."
            bpy.ops.export_anim.bvh(filepath=output_path)
        else:
            return False, f"Unsupported output format: {file_format}"

        if not os.path.exists(output_path):
            logger.error("Export file was not created")
            return False, "Export file was not created"

        logger.info(f"Successfully exported to {output_path}")
        return True, None
    except Exception as exc:
        logger.error(f"Error exporting file: {exc}")
        return False, f"Error exporting file: {exc}"
