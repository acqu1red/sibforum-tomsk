from django.apps import AppConfig


class ForumsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'forums'
    verbose_name = 'Форумы и программа'

    def ready(self):
        from . import signals  # noqa: F401
