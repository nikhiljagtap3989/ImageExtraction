import logging.config
import traceback
import configparser
import os
from datetime import datetime


def setup_logging():
    config = configparser.ConfigParser()
    config_file_path = os.path.join(os.path.dirname(__file__), "config.properties")
    
    if not os.path.exists(config_file_path):
        print(f"⚠️ Config file '{config_file_path}' not found. Using default log directory.")
        logs_dir = "logs"
    else:
        config.read(config_file_path)
        try:
            logs_dir = config['Input']['logs_dir']
        except KeyError:
            logs_dir = "logs"
            print("⚠️ 'Input' section or 'logs_dir' key missing in config.properties. Using 'logs/' as default.")

    current_date = datetime.now().strftime('%Y-%m-%d')
    log_file = os.path.join(logs_dir, f"Log_ADP_{current_date}.log")

    # Ensure log directory exists
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
            print(f"Created log directory: {logs_dir}")
        except OSError as e:
            print(f"Error creating log directory {logs_dir}: {e}")
            logs_dir = "."
            print("Using current directory for logs due to creation error.")

    # Create log directory if it doesn't exist
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
        except OSError as e:
            print(f"Error creating log directory {logs_dir}: {e}")
            logs_dir = os.path.dirname(os.path.abspath(__file__))
            print(f"Using alternative log directory: {logs_dir}")

    # Create log file path
    log_file = os.path.join(logs_dir, f"Log_ADP_{current_date}.log")

    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'detailed': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'detailed',
                'level': 'DEBUG'
            },
            'file': {
                'class': 'logging.FileHandler',
                'filename': log_file,
                'formatter': 'detailed',
                'level': 'DEBUG',
                'encoding': 'utf-8'
            }
        },
        'loggers': {
            '': {
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': True
            },
            'ImageApp1': {
                'handlers': ['console', 'file'],
                'level': 'DEBUG',
                'propagate': False
            }
        }
    })

def log_exception(logger_instance: logging.Logger):
    """
    Logs the current exception's full traceback details using logger.exception().
    This method should be called from within an 'except' block.

    Args:
        logger_instance: The logger object to use for logging the exception.
    """
    logger_instance.exception("An unhandled exception occurred.")
