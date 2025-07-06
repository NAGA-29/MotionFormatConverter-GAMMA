import unittest
import os
import tempfile
from unittest.mock import patch, Mock
import sys

# Stub bpy to avoid ImportError during tests
sys.modules.setdefault('bpy', Mock())

from app.convert import app
import time

class TestFileConversion(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        
    def test_health_check(self):
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['status'], 'healthy')

    def test_no_file_provided(self):
        response = self.app.post('/convert/fbx-to-glb')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['error'], 'No file provided')

    def test_invalid_file_format(self):
        data = {
            'file': (tempfile.NamedTemporaryFile(suffix='.txt'), 'test.txt')
        }
        response = self.app.post('/convert/fbx-to-glb', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertTrue('error' in response.json)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            data = {
                'file': (temp_file, 'empty.fbx')
            }
            response = self.app.post('/convert/fbx-to-glb', data=data)
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
            response = self.app.post('/convert/fbx-to-glb', data=data)
            self.assertEqual(response.status_code, 413)
            self.assertTrue('error' in response.json)

    def test_malformed_file(self):
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            temp_file.write(b'malformed content')
            temp_file.seek(0)
            data = {
                'file': (temp_file, 'malformed.fbx')
            }
            response = self.app.post('/convert/fbx-to-glb', data=data)
            self.assertEqual(response.status_code, 400)
            self.assertTrue('error' in response.json)

    @patch('app.convert.convert_file')
    def test_successful_conversion(self, mock_convert):
        # Mock successful conversion
        mock_convert.return_value = (True, "Conversion successful")
        
        # Create a temporary FBX file
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            data = {
                'file': (temp_file, 'test.fbx')
            }
            response = self.app.post('/convert/fbx-to-glb', data=data)
            self.assertEqual(response.status_code, 200)

    @patch('app.convert.convert_file')
    def test_conversion_error(self, mock_convert):
        # Mock conversion error
        mock_convert.return_value = (False, "Error during conversion")
        
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            data = {
                'file': (temp_file, 'test.fbx')
            }
            response = self.app.post('/convert/fbx-to-glb', data=data)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json['error'], "Error during conversion")

    def test_rate_limit(self):
        # Test rate limiting by making multiple requests
        responses = []
        for _ in range(10):  # Adjust based on your rate limit
            with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
                data = {
                    'file': (temp_file, 'test.fbx')
                }
                responses.append(self.app.post('/convert/fbx-to-glb', data=data))
                time.sleep(0.1)  # Small delay between requests
        
        # Check if any requests were rate limited
        rate_limited = any(r.status_code == 429 for r in responses)
        self.assertTrue(rate_limited)

    @patch('app.convert.convert_file')
    def test_timeout_handling(self, mock_convert):
        # Mock a timeout during conversion
        def timeout_side_effect(*args, **kwargs):
            time.sleep(2)  # Simulate long processing
            return (True, "Conversion successful")
        
        mock_convert.side_effect = timeout_side_effect
        
        with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
            data = {
                'file': (temp_file, 'test.fbx')
            }
            response = self.app.post('/convert/fbx-to-glb', data=data)
            self.assertEqual(response.status_code, 408)
            self.assertTrue('error' in response.json)

    def test_concurrent_requests(self):
        import threading
        import queue
        
        results = queue.Queue()
        def make_request():
            with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
                data = {
                    'file': (temp_file, 'test.fbx')
                }
                response = self.app.post('/convert/fbx-to-glb', data=data)
                results.put(response.status_code)

        # Create multiple threads to simulate concurrent requests
        threads = []
        for _ in range(5):
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
        self.assertEqual(len(status_codes), 5)
        # Some requests might be rate limited (429) or successful (200)
        self.assertTrue(all(code in [200, 429] for code in status_codes))

    def test_cleanup_after_error(self):
        """Test that temporary files are cleaned up after an error"""
        temp_dir = None
        
        @patch('app.convert.convert_file')
        def mock_conversion(mock_convert):
            mock_convert.return_value = (False, "Simulated error")
            
            with tempfile.NamedTemporaryFile(suffix='.fbx') as temp_file:
                data = {
                    'file': (temp_file, 'test.fbx')
                }
                response = self.app.post('/convert/fbx-to-glb', data=data)
                
                # Get the temp directory path from the mock
                nonlocal temp_dir
                if mock_convert.call_args:
                    temp_dir = os.path.dirname(mock_convert.call_args[0][0])
                
                return response

        response = mock_conversion()
        self.assertEqual(response.status_code, 500)
        
        # Verify temp directory was cleaned up
        if temp_dir:
            self.assertFalse(os.path.exists(temp_dir))

    def test_all_format_conversions(self):
        """Test all supported format conversion combinations"""
        formats = ['fbx', 'obj', 'gltf', 'glb', 'vrm']
        
        for input_format in formats:
            for output_format in formats:
                if input_format != output_format:
                    with self.subTest(f"{input_format} to {output_format}"):
                        with tempfile.NamedTemporaryFile(suffix=f'.{input_format}') as temp_file:
                            data = {
                                'file': (temp_file, f'test.{input_format}')
                            }
                            endpoint = f'/convert/{input_format}-to-{output_format}'
                            response = self.app.post(endpoint, data=data)
                            self.assertIn(response.status_code, [200, 500])  # Either success or handled error

if __name__ == '__main__':
    unittest.main()
