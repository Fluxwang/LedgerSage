import logging
import logging.config

LOGGER_NAME = "beanbot"

DEFAULT_LOGGING_CONFIG = {
    "version": 1,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "WARNING",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        }
    },
    "loggers": {
        LOGGER_NAME: {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        }
    },
}


def merge_dicts(dict1, dict2):
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def init_logging(settings) -> logging.Logger:
    logging_conf = merge_dicts(DEFAULT_LOGGING_CONFIG, settings.get("logging", {}))
    logging.config.dictConfig(logging_conf)
    return logging.getLogger(LOGGER_NAME)
