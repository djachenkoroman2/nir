from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Пользователь системы. Дополнительные поля (должность, учёная степень и т.п.) добавлять сюда."""

    class Meta:
        verbose_name = 'пользователь'
        verbose_name_plural = 'пользователи'
