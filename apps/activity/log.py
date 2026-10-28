"""Запись в журнал активности: единственное место, где создаются записи (кроме демо-данных seed_demo).

Текущий запрос передаётся сигналам изменения данных через contextvar, который выставляет ActivityMiddleware.
Изменения без запроса (seed_demo, clear_data, миграции, shell) в журнал не попадают.
"""
import contextvars
import logging

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction

from .models import ActivityLog

logger = logging.getLogger(__name__)
current_request = contextvars.ContextVar('activity_request', default=None)


def client_ip(request):
    """IP клиента: REMOTE_ADDR; заголовку прокси доверяем, только если это включено настройкой (иначе его подделают)."""
    if settings.ACTIVITY_TRUST_PROXY_HEADER:
        forwarded = request.META.get('HTTP_X_REAL_IP') or request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def write(action, request=None, user=None, username='', obj=None, isolate=True):
    """Пишет запись; ошибка записи не прерывает запрос пользователя, а попадает в лог приложения.

    isolate=False — без точки сохранения: для записей после ответа представления (просмотр, выгрузка),
    когда транзакции представления уже нет.
    """
    try:
        if user is None and request is not None and request.user.is_authenticated:
            user = request.user
        record = ActivityLog(action=action, user=user, username=username or (user.get_username() if user else ''))
        if obj is not None:
            record.content_type = ContentType.objects.get_for_model(obj)
            record.object_id = obj.pk
            record.object_repr = str(obj)[:200]
        if request is not None:
            record.path = request.path[:500]
            match = getattr(request, 'resolver_match', None)
            record.url_name = (match.view_name if match else '')[:100]
            record.ip = client_ip(request)
        if isolate and connection.in_atomic_block:
            # Внутри транзакции представления сбой записи не должен откатить сохранение данных.
            with transaction.atomic():
                record.save()
        else:
            record.save()
    except Exception:
        logger.exception('Не удалось записать событие «%s» в журнал активности', action)
