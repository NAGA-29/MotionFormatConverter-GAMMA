# Blender Docker Error: ModuleNotFoundError: No module named 'flasgger'

When running a Blender-based Docker container for the Motion Format Converter API, you might encounter the following error:

```
Switching to fully guarded memory allocator.
Blender 4.3.0 (hash 2b18cad88b13 built 2024-11-19 10:50:58)
Color management: Using /usr/local/blender/4.3/datafiles/colormanagement/config.ocio as a configuration file
Traceback (most recent call last):
  File "/app/convert.py", line 9, in <module>
    from flasgger import Swagger, swag_from
ModuleNotFoundError: No module named 'flasgger'
time bl_operators 0.0574
time bl_ui 0.0000
time keyingsets_builtins 0.0008
time nodeitems_builtins 0.0006
Python Script Load Time 0.1035
bl_app_template_utils.reset('')
Extension version cache: no extensions, skipping cache data.
	addon_utils.enable io_anim_bvh
	addon_utils.enable io_curve_svg
	addon_utils.enable io_mesh_uv_layout
	addon_utils.enable io_scene_fbx
	addon_utils.enable io_scene_gltf2
	addon_utils.enable cycles
	addon_utils.enable pose_library
	addon_utils.enable bl_pkg
	addon_utils.disable io_anim_bvh
	addon_utils.disable io_curve_svg
	addon_utils.disable io_mesh_uv_layout
	addon_utils.disable io_scene_fbx
	addon_utils.disable io_scene_gltf2
	addon_utils.disable cycles
	addon_utils.disable pose_library
	addon_utils.disable bl_pkg
Blender quit
```

## 原因

このエラーは2つの問題が原因で発生していました:

1. **依存関係のインストール漏れ**: Dockerfileで個別にパッケージを指定してインストールしており、`requirements.txt`に記載されている`flasgger`などのパッケージがインストールされていなかった
2. **Blenderバージョンの不一致**: Blender 5.0.1をインストールしているにもかかわらず、一部のパスが4.3のまま残っていた

## 解決方法

### 1. requirements.txtを使用するように修正

Dockerfileの依存関係インストール部分を以下のように変更しました:

```dockerfile
# Copy requirements file
COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN ${BLENDER_PYTHON} -m ensurepip && \
    ${BLENDER_PYTHON} -m pip install --upgrade pip && \
    ${BLENDER_PYTHON} -m pip install --no-cache-dir -r /tmp/requirements.txt
```

### 2. Blenderバージョンを5.0に統一

以下のパスをすべて4.3から5.0に修正しました:
- アドオンディレクトリ: `/usr/local/blender/5.0/scripts/addons/`
- 設定スクリプト: `/usr/local/blender/5.0/config/scripts/addons/`
- 環境変数: `BLENDER_SYSTEM_SCRIPTS`, `BLENDER_SYSTEM_PYTHON`, `OCIO`

### 3. Docker イメージの再ビルド

修正後、以下のコマンドでDockerイメージを再ビルドします:

```bash
docker compose build --no-cache
docker compose up
```

`--no-cache`オプションを使用することで、依存関係が確実に再インストールされます