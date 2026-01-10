import os
import logging
import logging.config
from typing import TYPE_CHECKING, Union

try:
    import structlog
except ModuleNotFoundError:  # pragma: no cover - optional in local test runs
    structlog = None

if TYPE_CHECKING:
    import structlog as structlog_types


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

        handler_names = ["console"]
        if log_file:
            handler_names.append("file")

        if log_format == "json":
            if structlog is None:
                raise RuntimeError("structlog is required when LOG_FORMAT=json")
            # Configure structlog for JSON output
            structlog.configure(
                processors=[
                    structlog.stdlib.filter_by_level,
                    structlog.stdlib.add_logger_name,
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.PositionalArgumentsFormatter(),
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.stdlib.render_to_log_kwargs,
                ],
                context_class=dict,
                logger_factory=structlog.stdlib.LoggerFactory(),
                wrapper_class=structlog.stdlib.BoundLogger,
                cache_logger_on_first_use=True,
            )

            # Configure standard logging to use structlog's formatter
            log_config = {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "json": {
                        "()": structlog.stdlib.ProcessorFormatter,
                        "processor": structlog.processors.JSONRenderer(),
                        "foreign_pre_chain": [
                            structlog.stdlib.add_logger_name,
                            structlog.stdlib.add_log_level,
                            structlog.processors.TimeStamper(fmt="iso"),
                        ],
                    },
                },
                "handlers": {
                    "console": {
                        "class": "logging.StreamHandler",
                        "formatter": "json",
                    },
                },
                "root": {
                    "handlers": handler_names,
                    "level": log_level,
                },
            }
            if log_file:
                log_config["handlers"]["file"] = {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "json",
                    "filename": log_file,
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 5,
                }
            logging.config.dictConfig(log_config)
        else:
            # Plain text format configuration
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            log_config = {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {"default": {"format": fmt}},
                "handlers": {
                    "console": {
                        "class": "logging.StreamHandler",
                        "formatter": "default",
                    }
                },
                "root": {"level": log_level, "handlers": handler_names},
            }
            if log_file:
                log_config["handlers"]["file"] = {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "default",
                    "filename": log_file,
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 5,
                }
            logging.config.dictConfig(log_config)

        cls._configured = True
        logging.getLogger(__name__).debug("Logger configured")

    @classmethod
    def get_logger(cls, name: str = None) -> Union[logging.Logger, "structlog.stdlib.BoundLogger"]:
        if not cls._configured:
            cls.configure()

        log_format = os.getenv("LOG_FORMAT", "plain").lower()
        if log_format == "json":
            if structlog is None:
                raise RuntimeError("structlog is required when LOG_FORMAT=json")
            logger = structlog.get_logger(name)
        else:
            logger = logging.getLogger(name)

        logger.debug(f"Logger retrieved for {name}")
        return logger
