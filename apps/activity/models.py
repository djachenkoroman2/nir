from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class ActivityLog(models.Model):
    """Запись журнала активности. Пароли, содержимое форм и значения полей не сохраняются."""

    class Action(models.TextChoices):
        LOGIN = 'login', 'вход'
        LOGOUT = 'logout', 'выход'
        LOGIN_FAILED = 'login_failed', 'неудачный вход'
        VIEW = 'view', 'просмотр страницы'
        CREATE = 'create', 'добавление'
        UPDATE = 'update', 'изменение'
        DELETE = 'delete', 'удаление'
        EXPORT = 'export', 'выгрузка отчёта'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='пользователь', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='activity',
    )
    # Логин текстом: остаётся после удаления пользователя и сохраняется для неудачных входов.
    username = models.CharField('имя пользователя', max_length=150, blank=True)
    created_at = models.DateTimeField('дата и время', default=timezone.now, db_index=True)
    action = models.CharField('действие', max_length=20, choices=Action.choices)
    content_type = models.ForeignKey(
        ContentType, verbose_name='тип объекта', on_delete=models.SET_NULL, null=True, blank=True,
    )
    object_id = models.PositiveBigIntegerField('id объекта', null=True, blank=True)
    object_repr = models.CharField('объект', max_length=200, blank=True)
    path = models.CharField('адрес', max_length=500, blank=True)
    url_name = models.CharField('имя URL', max_length=100, blank=True)
    ip = models.GenericIPAddressField('IP-адрес', null=True, blank=True)

    class Meta:
        verbose_name = 'запись журнала активности'
        verbose_name_plural = 'журнал активности'
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['user', 'created_at'])]
        permissions = [('view_activity_report', 'Может смотреть отчёт об активности пользователей')]

    def __str__(self):
        return f'{self.created_at:%d.%m.%Y %H:%M} {self.username} — {self.get_action_display()}'
