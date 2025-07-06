import os
import logging
import logging.config
from logging.handlers import RotatingFileHandler


class AppLogger:
    """Application-wide logger configuration"""

    _configured = False

    @classmethod
    def configure(cls):
        if cls._configured:
            return

        logging.getLogger(__name__).debug("Configuring application logger")

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        log_format = os.getenv("LOG_FORMAT", "plain").lower()
        log_file = os.getenv("LOG_FILE")

        if log_format == "json":
            fmt = (
                '{"timestamp": "%(asctime)s", "logger": "%(name)s", '
                '"level": "%(levelname)s", "message": "%(message)s"}'
            )
        else:
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        handlers = {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": log_level,
            }
        }

        if log_file:
            handlers["file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "level": log_level,
                "filename": log_file,
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
            }

        logging.config.dictConfig(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {"default": {"format": fmt}},
                "handlers": handlers,
                "root": {"level": log_level, "handlers": list(handlers.keys())},
            }
        )

        cls._configured = True
        logging.getLogger(__name__).debug("Logger configured")

    @classmethod
    def get_logger(cls, name: str = None) -> logging.Logger:
        if not cls._configured:
            cls.configure()
        logger = logging.getLogger(name)
        logger.debug("Logger retrieved for %s", name)
        return logger
