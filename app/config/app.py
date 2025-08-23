"""Application configuration placeholder."""

import os

from app.utils.logger import AppLogger
from app.convert import is_local_env

logger = AppLogger.get_logger(__name__)
logger.debug("Loading configuration module")

# Example of reading a configuration value
logger.debug("IS_LOCAL=%s", is_local_env())

