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
sys.modules['bpy'] = mock_bpy

mock_vrm_addon = types.ModuleType("io_scene_vrm")
mock_vrm_addon.register = Mock()
# Add spec to the mock module to satisfy importlib.reload
spec = Mock()
spec.name = "io_scene_vrm"
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
    def setUp(self):
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
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['status'], 'healthy')

    def test_no_file_provided(self):
        response = self.app.post('/convert?output_format=glb')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['error'], 'No file provided')

    def test_invalid_file_format(self):
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
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            data = {
                'file': (temp_file, 'empty.fbx')
            }
            response = self.app.post('/convert?output_format=glb', data=data, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 400)
            self.assertTrue('error' in response.json)

    def test_large_file(self):
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

@unittest.skipUnless(flask, "Flask is not installed in the test environment")
class TestIsLocalEnv(unittest.TestCase):
    def test_is_local_env_true(self):
        with patch.dict(os.environ, {"APP_ENV": "local"}):
            from app.config import get_settings
            get_settings.cache_clear()
            settings = get_settings()
            self.assertTrue(settings.is_local())

    def test_is_local_env_false(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            from app.config import get_settings
            get_settings.cache_clear()
            settings = get_settings()
            self.assertFalse(settings.is_local())

if __name__ == '__main__':
    unittest.main()
