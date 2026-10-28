from django.apps import AppConfig


class ActivityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.activity'
    verbose_name = 'Журнал активности'

    def ready(self):
        from . import signals  # noqa: F401 — подключает обработчики сигналов
