from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _sqlite_unicode_lower(sender, connection, **kwargs):
    # Встроенная LOWER в SQLite меняет регистр только у латиницы; заменяем её на str.lower,
    # чтобы поиск без учёта регистра работал и для русских букв.
    if connection.vendor == 'sqlite':
        connection.connection.create_function(
            'LOWER', 1, lambda value: value.lower() if isinstance(value, str) else value, deterministic=True
        )


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Основное'

    def ready(self):
        connection_created.connect(_sqlite_unicode_lower)
