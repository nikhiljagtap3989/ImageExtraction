from django.apps import AppConfig


class Imageapp1Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ImageApp1"


    def ready(self):
        from ImageExtraction.logger import setup_logging
        setup_logging()
