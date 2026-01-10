import unittest
import os
import tempfile
from unittest.mock import patch, Mock
import sys
import types

try:
    import flask  # type: ignore
except ImportError:  # pragma: no cover - optional dependency in CI
    flask = None

# Stub bpy to avoid ImportError during tests
mock_bpy = Mock()
_bpy_objects = []
def _add_obj_side_effect(*args, **kwargs):
    # Simulate a successful import by adding a mock object
    _bpy_objects.clear()
    _bpy_objects.append(Mock())
def _clear_obj_side_effect(*args, **kwargs):
    # Simulate clearing objects
    _bpy_objects.clear()
def _export_side_effect(filepath, *args, **kwargs):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write("mock data")

mock_bpy.data.objects = _bpy_objects
mock_bpy.ops.import_scene.fbx.side_effect = _add_obj_side_effect
mock_bpy.ops.import_scene.obj.side_effect = _add_obj_side_effect
mock_bpy.ops.import_scene.gltf.side_effect = _add_obj_side_effect
mock_bpy.ops.import_scene.vrm.side_effect = _add_obj_side_effect
mock_bpy.ops.import_anim.bvh.side_effect = _add_obj_side_effect
mock_bpy.ops.object.delete.side_effect = _clear_obj_side_effect
mock_bpy.ops.wm.read_factory_settings = Mock()

mock_bpy.ops.export_scene.fbx.side_effect = _export_side_effect
mock_bpy.ops.export_scene.obj.side_effect = _export_side_effect
mock_bpy.ops.export_scene.gltf.side_effect = _export_side_effect
mock_bpy.ops.export_scene.vrm.side_effect = _export_side_effect
mock_bpy.ops.export_anim.bvh.side_effect = _export_side_effect

mock_bpy.data.meshes = []
mock_bpy.data.materials = []
mock_bpy.data.textures = []
mock_bpy.data.images = []
# For BVH export check, start with no actions
mock_bpy.data.actions = []
mock_bpy.data.armatures = []
mock_bpy.utils = Mock()
mock_bpy.utils.user_resource.return_value = None
sys.modules['bpy'] = mock_bpy

mock_vrm_addon = types.ModuleType("io_scene_vrm")
mock_vrm_addon.register = Mock()
# Add spec to the mock module to satisfy importlib.reload
spec = Mock()
spec.name = "io_scene_vrm"
spec.loader = Mock()
spec.loader.exec_module = Mock()
mock_vrm_addon.__spec__ = spec
sys.modules['io_scene_vrm'] = mock_vrm_addon

# Mock redis client and its methods
class MockRedisError(Exception):
    pass
mock_redis_client = Mock()
mock_pipeline = Mock()
mock_pipeline.execute.return_value = (None, 0, None, None)
mock_redis_client.pipeline.return_value = mock_pipeline
mock_redis_client.Redis.return_value = mock_redis_client
mock_redis_client.RedisError = MockRedisError
mock_redis_client.get.return_value = None
sys.modules['redis'] = mock_redis_client

if flask:
    from app.convert import app
else:
    app = None
import time

@unittest.skipUnless(flask, "Flask is not installed in the test environment")
class TestFileConversion(unittest.TestCase):
    """ファイル変換APIの入力検証・正常系・異常系を網羅するテスト群。"""

    def setUp(self):
        """モックの初期化とFlaskテストクライアントの準備を行う。"""
        # Reset mocks for test isolation
        mock_pipeline.execute.side_effect = None
        mock_pipeline.execute.return_value = (None, 0, None, None)
        _bpy_objects.clear()
        mock_bpy.data.actions = []

        os.makedirs('/tmp/convert', exist_ok=True)
        with patch.dict(os.environ, {"APP_ENV": "local"}):
            from app.convert import app
            self.app = app.test_client()
            self.app.testing = True
        
    def test_health_check(self):
        """ヘルスチェックが200とhealthyを返すことを確認する。"""
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['status'], 'healthy')

    def test_no_file_provided(self):
        """ファイル未指定時に400が返ることを確認する。"""
        response = self.app.post('/convert?output_format=glb')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['error'], 'No file provided')

    def test_invalid_file_format(self):
        """未対応拡張子で400となることを確認する。"""
        temp = tempfile.NamedTemporaryFile(suffix='.txt')
        temp.write(b'data')
        temp.seek(0)
        data = {
            'file': (temp, 'test.txt')
        }
        response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)
        self.assertTrue('error' in response.json)

    def test_empty_file(self):
        """空ファイルで400となることを確認する。"""
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            data = {
                'file': (temp_file, 'empty.fbx')
            }
            response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 400)
            self.assertTrue('error' in response.json)

    def test_large_file(self):
        """上限超過ファイルで413となることを確認する。"""
        # Create a large temporary file (100MB)
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            temp_file.write(b'0' * 100 * 1024 * 1024)
            temp_file.seek(0)
            data = {
                'file': (temp_file, 'large.fbx')
            }
            response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 413)
            self.assertTrue('error' in response.json)

    @patch('app.convert.import_file', return_value=(False, "Import error"))
    def test_malformed_file(self, mock_import):
        """インポート失敗時に500が返ることを確認する。"""
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            temp_file.write(b'malformed content')
            temp_file.seek(0)
            data = {
                'file': (temp_file, 'malformed.fbx')
            }
            response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 500)
            self.assertTrue('error' in response.json)

    @patch('app.convert.convert_file_with_timeout')
    def test_successful_conversion(self, mock_convert):
        """正常な変換で200が返ることを確認する。"""
        # Mock successful conversion
        def side_effect(input_path, output_path, input_format, output_format):
            with open(output_path, "w") as f:
                f.write("mock data")
            return (True, "Conversion successful")
        mock_convert.side_effect = side_effect
        
        # Create a temporary FBX file
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            temp_file.write(b'data')
            temp_file.seek(0)
            data = {
                'file': (temp_file, 'test.fbx')
            }
            response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 200)


    @patch('app.convert.convert_file_with_timeout')
    def test_conversion_error(self, mock_convert):
        """変換失敗時に500が返ることを確認する。"""
        # Mock conversion error
        mock_convert.return_value = (False, "Error during conversion")

        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            temp_file.write(b'data')
            temp_file.seek(0)
            data = {
                'file': (temp_file, 'test.fbx')
            }
            response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json['error'], "Error during conversion")

    def test_rate_limit(self):
        """レートリミットが適用されることを確認する。"""
        from app.config import get_settings
        settings = get_settings()

        counts = list(range(settings.rate_limit_requests + 5))

        def mock_execute(*args, **kwargs):
            return (None, counts.pop(0), None, None)

        mock_pipeline.execute.side_effect = mock_execute

        # Test rate limiting by making multiple requests
        responses = []
        for _ in range(settings.rate_limit_requests + 5):
            with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
                temp_file.write(b'data')
                temp_file.seek(0)
                data = {
                    'file': (temp_file, 'test.fbx')
                }
                responses.append(self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data'))
        
        # Check if any requests were rate limited
        rate_limited = any(r.status_code == 429 for r in responses)
        self.assertTrue(rate_limited)

    @patch('app.convert.convert_file_with_timeout')
    def test_timeout_handling(self, mock_convert):
        """タイムアウト時に500と適切なエラーが返ることを確認する。"""
        # Mock a timeout during conversion
        mock_convert.return_value = (False, "Conversion timed out")

        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            temp_file.write(b'data')
            temp_file.seek(0)
            data = {
                'file': (temp_file, 'test.fbx')
            }

            response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 500)
            self.assertTrue('error' in response.json)
            self.assertEqual(response.json['error'], "Conversion timed out")

    def test_concurrent_requests(self):
        """複数スレッドからの同時リクエストをハンドリングできることを確認する。"""
        import threading
        import queue
        
        results = queue.Queue()
        def make_request():
            with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
                temp_file.write(b'data')
                temp_file.seek(0)
                data = {
                    'file': (temp_file, 'test.fbx')
                }
                response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
                results.put(response.status_code)

        # Create multiple threads to simulate concurrent requests
        threads = []
        for _ in range(20):
            t = threading.Thread(target=make_request)
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Check results
        status_codes = []
        while not results.empty():
            status_codes.append(results.get())

        # Verify that all requests were handled
        self.assertEqual(len(status_codes), 20)
        # Some requests might be rate limited (429) or successful (200)
        self.assertTrue(all(code in [200, 429, 500] for code in status_codes))

    def test_conversion_doc(self):
        """Swagger用ドキュメント定義が期待通りであることを確認する。"""
        from app.convert import conversion_doc
        doc = conversion_doc('fbx', 'glb')
        self.assertEqual(doc['tags'], ['conversion'])
        self.assertEqual(doc['consumes'], ['multipart/form-data'])
        self.assertEqual(doc['parameters'][0]['name'], 'file')
        self.assertEqual(doc['parameters'][0]['in'], 'formData')
        self.assertEqual(doc['parameters'][0]['type'], 'file')
        self.assertTrue(doc['parameters'][0]['required'])
        self.assertEqual(doc['parameters'][0]['description'], 'Input FBX file')
        self.assertEqual(doc['responses'][200]['description'], 'Converted GLB file')

    @patch('app.convert.convert_file_with_timeout')
    def test_cleanup_after_error(self, mock_convert):
        """Test that temporary files are cleaned up after an error"""
        mock_convert.return_value = (False, "Simulated error")

        temp_dir = tempfile.mkdtemp()
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            temp_file.write(b'data')
            temp_file.seek(0)
            data = {
                'file': (temp_file, 'test.fbx')
            }
            with patch('tempfile.mkdtemp', return_value=temp_dir):
                response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
        
        self.assertEqual(response.status_code, 500)
        self.assertFalse(os.path.exists(temp_dir))


    def test_all_format_conversions(self):
        """Test all supported format conversion combinations"""
        formats = ['fbx', 'obj', 'gltf', 'glb', 'vrm', 'bvh']
        
        for input_format in formats:
            for output_format in formats:
                if input_format != output_format:
                    with self.subTest(f"{input_format} to {output_format}"):
                        with tempfile.NamedTemporaryFile(suffix=f'.{input_format}') as temp_file:
                            temp_file.write(b'data')
                            temp_file.seek(0)
                            data = {
                                'file': (temp_file, f'test.{input_format}')
                            }
                            endpoint = f'/convert?output_format={output_format}'
                            response = self.app.post(endpoint, data=data, content_type='multipart/form-data')
                            self.assertIn(response.status_code, [200, 400, 500])

    def test_bvh_conversion_no_animation(self):
        # No animation data in mock_bpy.data.actions, so this should fail
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            temp_file.write(b'data')
            temp_file.seek(0)
            data = {
                'file': (temp_file, 'test.fbx')
            }
            response = self.app.post('/convert?output_format=bvh', data=data, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json['error'], "No animation data found to export to BVH.")

    def test_successful_bvh_conversion(self):
        # Add a mock action to pass the BVH export check
        mock_bpy.data.actions.append(Mock())

        with tempfile.NamedTemporaryFile(suffix='.bvh') as temp_file:
            temp_file.write(b'data')
            temp_file.seek(0)
            data = {
                'file': (temp_file, 'test.bvh')
            }
            response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 200)


class TestVrmAddonSetup(unittest.TestCase):
    """VRMアドオンのセットアップ処理を検証するテスト群。"""

    def setUp(self):
        """テスト用のモック状態を初期化する。"""
        mock_bpy.utils.user_resource.return_value = None
        self._bpy_patcher = patch("app.blender.setup.bpy", mock_bpy)
        self._bpy_patcher.start()
        self._vrm_module_patcher = patch.dict(sys.modules, {"io_scene_vrm": mock_vrm_addon})
        self._vrm_module_patcher.start()

    def tearDown(self):
        """セットアップしたパッチを解除する。"""
        self._vrm_module_patcher.stop()
        self._bpy_patcher.stop()

    def test_setup_vrm_addon_uses_env_scripts_path(self):
        """環境変数で指定されたスクリプトパスが利用されることを確認する。"""
        from app.blender.setup import setup_vrm_addon

        original_sys_path = list(sys.path)
        try:
            with patch.dict(os.environ, {"BLENDER_USER_SCRIPTS": "/custom/scripts"}):
                setup_vrm_addon()
                self.assertIn("/custom/scripts/addons", sys.path)
                self.assertIn("/custom/scripts/addons/modules", sys.path)
        finally:
            sys.path[:] = original_sys_path

    def test_setup_vrm_addon_uses_bpy_resource_path(self):
        """環境変数がない場合にbpyのリソースパスが利用されることを確認する。"""
        from app.blender.setup import setup_vrm_addon

        original_sys_path = list(sys.path)
        try:
            with patch.dict(os.environ, {}, clear=True):
                mock_bpy.utils.user_resource.return_value = "/resource/scripts"
                setup_vrm_addon()
                self.assertIn("/resource/scripts/addons", sys.path)
                self.assertIn("/resource/scripts/addons/modules", sys.path)
        finally:
            sys.path[:] = original_sys_path


class TestFactoryResetToggle(unittest.TestCase):
    """ファクトリーリセットの環境変数制御を検証するテスト群。"""

    def setUp(self):
        """ファクトリーリセット関連のモックを初期化する。"""
        mock_bpy.ops.wm.read_factory_settings.reset_mock()

    def test_clear_scene_skips_factory_reset_by_default(self):
        """既定値ではファクトリーリセットが呼ばれないことを確認する。"""
        from app.blender.setup import clear_scene

        with patch.dict(os.environ, {}, clear=True):
            success, error = clear_scene()
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertFalse(mock_bpy.ops.wm.read_factory_settings.called)

    def test_clear_scene_calls_factory_reset_when_enabled(self):
        """環境変数指定時にファクトリーリセットが呼ばれることを確認する。"""
        from app.blender.setup import clear_scene

        with patch.dict(os.environ, {"BLENDER_FACTORY_RESET": "1"}):
            success, error = clear_scene()
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(mock_bpy.ops.wm.read_factory_settings.called)

@unittest.skipUnless(flask, "Flask is not installed in the test environment")
class TestIsLocalEnv(unittest.TestCase):
    """is_localの判定を検証するテスト。"""

    def test_is_local_env_true(self):
        """APP_ENV=localでTrueになることを確認する。"""
        with patch.dict(os.environ, {"APP_ENV": "local"}):
            from app.config import get_settings
            get_settings.cache_clear()
            settings = get_settings()
            self.assertTrue(settings.is_local())

    def test_is_local_env_false(self):
        """APP_ENV=productionでFalseになることを確認する。"""
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            from app.config import get_settings
            get_settings.cache_clear()
            settings = get_settings()
            self.assertFalse(settings.is_local())

if __name__ == '__main__':
    unittest.main()
