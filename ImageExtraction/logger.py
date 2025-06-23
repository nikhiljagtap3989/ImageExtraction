import logging
import logging.config
import traceback
import configparser
from datetime import datetime


def setup_logging():
    # config = configparser.ConfigParser()
    # config.read("config.properties")  # Ensure this file exists

    # current_date = datetime.now().strftime('%Y-%m-%d')
    # logs_dir = config['Input']['logs_dir']  # Must match section/key in your properties file
    # log_file = f"{logs_dir}/Log_ADP_{current_date}.log"

    config = configparser.ConfigParser()
    config.read("config.properties")

    try:
        logs_dir = config['Input']['logs_dir']
    except KeyError:
        logs_dir = "logs"  # fallback to default
        print("⚠️ 'Input' section or 'logs_dir' key missing in config.properties. Using 'logs/' as default.")

    current_date = datetime.now().strftime('%Y-%m-%d')
    log_file = f"{logs_dir}/Log_ADP_{current_date}.log"



    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": (
                    "%(asctime)s | %(levelname)-8s | %(name)15s | "
                    "%(funcName)-20s | Line %(lineno)-4d | %(message)s"
                )
            },
            "simple": {
                "format": "%(levelname)-8s %(message)s"
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "detailed",
                "level": "DEBUG"
            },
            "file": {
                "class": "logging.FileHandler",
                "filename": log_file,
                "formatter": "detailed",
                "level": "DEBUG"
            }
        },
        "loggers": {
            "": {  # root logger
                "handlers": ["console", "file"],
                "level": "DEBUG",
                "propagate": True
            }
        }
    })


def log_exception(logger):
    exc_type, exc_value, exc_tb = traceback.sys.exc_info()
    tb_details = traceback.extract_tb(exc_tb)
    for tb in tb_details:
        logger.error(
            f"Exception occurred in {tb.filename}, line {tb.lineno}: {tb.line.strip()}"
        )
