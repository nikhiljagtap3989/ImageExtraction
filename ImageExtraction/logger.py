import logging
import logging.config
import traceback
import configparser
import os # Import os for path manipulation
from datetime import datetime


def setup_logging():
    config = configparser.ConfigParser()
    # It's better to provide a full path to config.properties, especially in a Django project.
    # Assuming config.properties is in the same directory as logger.py, or you adjust the path.
    # Example: config_path = os.path.join(os.path.dirname(__file__), "config.properties")
    # For a Django project, you might store logs_dir directly in Django settings.py or .env
    config_file_path = "config.properties" # Adjust this path if config.properties is elsewhere
    if not os.path.exists(config_file_path):
        print(f"⚠️ Config file '{config_file_path}' not found. Using default log directory.")
        logs_dir = "logs"
    else:
        config.read(config_file_path)
        try:
            logs_dir = config['Input']['logs_dir']
            # Ensure the logs_dir is an absolute path or relative to your project root
            # If logs_dir from config can be relative, consider os.path.join(settings.BASE_DIR, logs_dir)
        except KeyError:
            logs_dir = "logs"  # fallback to default
            print("⚠️ 'Input' section or 'logs_dir' key missing in config.properties. Using 'logs/' as default.")

    # --- Ensure the log directory exists ---
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
            print(f"Created log directory: {logs_dir}")
        except OSError as e:
            print(f"Error creating log directory {logs_dir}: {e}")
            # Fallback to current directory if logs_dir cannot be created
            logs_dir = "." # Fallback
            print("Using current directory for logs due to creation error.")

    current_date = datetime.now().strftime('%Y-%m-%d')
    log_file = os.path.join(logs_dir, f"Log_ADP_{current_date}.log") # Use os.path.join for paths


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
                "level": "DEBUG", # Set to DEBUG during development for full visibility
                "encoding": "utf-8" # --- FIX: Specify UTF-8 encoding for console output ---
            },
            "file": {
                "class": "logging.FileHandler",
                "filename": log_file,
                "formatter": "detailed",
                "level": "DEBUG", # Set to DEBUG during development for full visibility
                "encoding": "utf-8" # --- FIX: Specify UTF-8 encoding for file output ---
            }
        },
        "loggers": {
            "": {  # root logger
                "handlers": ["console", "file"],
                "level": "INFO", # Typically INFO for root, DEBUG for specific modules
                "propagate": True
            },
            # You might want to add specific loggers for your Django apps/modules here
            # For example:
            # "ImageApp1": {
            #     "handlers": ["console", "file"],
            #     "level": "DEBUG",
            #     "propagate": False
            # },
            # "ImageExtraction": {
            #     "handlers": ["console", "file"],
            #     "level": "DEBUG",
            #     "propagate": False
            # }
        }
    })


def log_exception(logger_instance: logging.Logger): # Use type hint for clarity
    """
    Logs the current exception's full traceback details using logger.exception().
    This method should be called from within an 'except' block.

    Args:
        logger_instance: The logger object to use for logging the exception.
    """
    # --- IMPROVEMENT: Use logger.exception() for full traceback ---
    # logger.exception() automatically gets exc_info=True and logs at ERROR level.
    # It also handles the traceback formatting correctly.
    logger_instance.exception("An unhandled exception occurred.")
    # The previous loop for traceback.extract_tb is generally not needed
    # when using logger.exception() as it handles the full stack trace.