from django.apps import AppConfig

class ImageApp1Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ImageApp1'

    def ready(self):
        # Import and call setup_logging here
        from .logger import setup_logging
        setup_logging()
        # You can also set a default logger level for this app here
        # logging.getLogger('ImageExtraction').setLevel(logging.DEBUG)
        # logging.getLogger('ImageApp1').setLevel(logging.DEBUG)