import os
import unittest
import logging
from importlib import reload
from unittest.mock import patch

from app.utils import logger as logger_module

class TestAppLogger(unittest.TestCase):
    """AppLoggerの設定反映とレベル設定を確認するテスト。"""

    def tearDown(self):
        # reset configuration after each test
        logger_module.AppLogger._configured = False

    @patch.dict(os.environ, {"LOG_LEVEL": "DEBUG", "APP_ENV": "local"})
    def test_log_level_env(self):
        """環境変数によってログレベルが設定されることを検証する。"""
        logger_module.AppLogger._configured = False
        logger = logger_module.AppLogger.get_logger('test')
        self.assertEqual(logger.getEffectiveLevel(), logging.DEBUG)

    def test_json_format_requires_structlog(self):
        """JSON形式設定時にstructlogが無い場合は例外になることを確認する。"""
        logger_module.AppLogger._configured = False
        original_structlog = getattr(logger_module, "structlog", None)
        try:
            logger_module.structlog = None
            with patch.dict(os.environ, {"LOG_FORMAT": "json"}):
                with self.assertRaises(RuntimeError):
                    logger_module.AppLogger.get_logger("test")
        finally:
            logger_module.structlog = original_structlog

if __name__ == '__main__':
    unittest.main()
