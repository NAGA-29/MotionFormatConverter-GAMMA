import os
import unittest
import logging
from importlib import reload

from app.utils import logger as logger_module

class TestAppLogger(unittest.TestCase):
    def tearDown(self):
        # reset configuration after each test
        logger_module.AppLogger._configured = False
        if 'LOG_LEVEL' in os.environ:
            del os.environ['LOG_LEVEL']
        if 'LOG_FILE' in os.environ:
            del os.environ['LOG_FILE']
        if 'LOG_FORMAT' in os.environ:
            del os.environ['LOG_FORMAT']

    def test_log_level_env(self):
        os.environ['LOG_LEVEL'] = 'DEBUG'
        logger_module.AppLogger._configured = False
        logger = logger_module.AppLogger.get_logger('test')
        self.assertEqual(logger.getEffectiveLevel(), logging.DEBUG)

if __name__ == '__main__':
    unittest.main()
