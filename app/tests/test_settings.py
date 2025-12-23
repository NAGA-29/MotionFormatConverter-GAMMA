import os
import unittest
from importlib import reload
from unittest import mock


class TestSettings(unittest.TestCase):
    def test_settings_defaults_use_env(self):
        with mock.patch.dict(os.environ, {
            "REDIS_HOST": "example",
            "REDIS_PORT": "1234",
            "APP_ENV": "local",
            "LOG_FORMAT": "json",
        }):
            from app.config import settings as settings_module
            reload(settings_module)
            settings = settings_module.get_settings()

            self.assertEqual(settings.redis_host, "example")
            self.assertEqual(settings.redis_port, 1234)
            self.assertEqual(settings.app_env, "local")
            self.assertEqual(settings.log_format, "json")

    def test_settings_has_expected_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from app.config import settings as settings_module
            reload(settings_module)
            settings = settings_module.get_settings()

            self.assertEqual(settings.max_file_size, 50 * 1024 * 1024)
            self.assertEqual(settings.rate_limit_requests, 10)
            self.assertEqual(settings.rate_limit_window, 60)
            self.assertEqual(settings.conversion_timeout, 300)
            self.assertEqual(settings.cache_duration, 3600)
            self.assertEqual(settings.log_level, "INFO")
            self.assertEqual(settings.log_format, "plain")


if __name__ == "__main__":
    unittest.main()
