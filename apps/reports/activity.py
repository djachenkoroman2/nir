"""Отчёт об активности пользователей: данные собираются только здесь (страница и DOCX строятся из результата).

Подсчёт — агрегирующими запросами по журналу (apps.activity), число запросов не зависит от числа пользователей.
"""
import datetime
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Min, Q
from django.utils import timezone

from apps.activity.models import ActivityLog

A = ActivityLog.Action
# Столбцы-счётчики отчёта: ключ — действие журнала.
COUNTERS = [
    (A.LOGIN, 'Входов'), (A.LOGIN_FAILED, 'Неудачных входов'), (A.VIEW, 'Просмотров страниц'),
    (A.CREATE, 'Добавлено'), (A.UPDATE, 'Изменено'), (A.DELETE, 'Удалено'), (A.EXPORT, 'Выгрузок отчётов'),
]

ADMINS, EDITORS, TEACHERS, ADJUNCTS, STUDENTS, OTHERS, UNKNOWN = (
    'admins', 'editors', 'teachers', 'adjuncts', 'students', 'others', 'unknown',
)
# Категории в порядке приоритета: у пользователя ровно одна — первая подходящая.
CATEGORIES = [
    (ADMINS, 'Администраторы'),
    (EDITORS, 'Редакторы'),
    (TEACHERS, 'Преподаватели'),
    (ADJUNCTS, 'Адъюнкты'),
    (STUDENTS, 'Курсанты'),
    (OTHERS, 'Прочие пользователи'),
    (UNKNOWN, 'Неудачные входы с несуществующими логинами и удалённые пользователи'),
]
CATEGORY_TITLES = dict(CATEGORIES)


def user_category(user):
    """Категория пользователя: администратор → редактор → преподаватель → адъюнкт → курсант → прочие."""
    if user.is_superuser:
        return ADMINS
    if user.is_staff:
        return EDITORS
    for relation, category in (('teacher', TEACHERS), ('adjunct', ADJUNCTS), ('student', STUDENTS)):
        if getattr(user, relation, None) is not None:
            return category
    return OTHERS


def default_period(now=None):
    """По умолчанию — последние 7 суток до текущего момента."""
    now = now or timezone.now()
    return now - datetime.timedelta(days=7), now


@dataclass
class Row:
    username: str
    full_name: str
    counts: dict
    first: object = None
    last: object = None
    user_id: int | None = None

    @property
    def values(self):
        return [self.counts.get(action, 0) for action, _ in COUNTERS]


@dataclass
class Category:
    key: str
    title: str
    rows: list = field(default_factory=list)

    @property
    def totals(self):
        return [sum(row.values[index] for row in self.rows) for index in range(len(COUNTERS))]


@dataclass
class ActivityReport:
    start: object
    end: object
    categories: list
    selected: list
    created: object

    @property
    def totals(self):
        return [sum(category.totals[index] for category in self.categories) for index in range(len(COUNTERS))]

    @property
    def selected_titles(self):
        return ', '.join(CATEGORY_TITLES[key] for key in self.selected)


def counters():
    """Аннотации: число записей каждого действия, первая и последняя активность."""
    return {
        **{f'n_{action.value}': Count('pk', filter=Q(action=action)) for action, _ in COUNTERS},
        'first': Min('created_at'),
        'last': Max('created_at'),
    }


def stats_row(stats, username, full_name='', user_id=None):
    return Row(username, full_name, {action: stats.get(f'n_{action.value}', 0) for action, _ in COUNTERS},
               stats.get('first'), stats.get('last'), user_id)


def build_activity_report(start, end, categories=None, show_inactive=False):
    """Активность за период [start, end] по категориям; categories — ключи категорий (None — все)."""
    selected = [key for key, _ in CATEGORIES if categories is None or key in categories]
    logs = ActivityLog.objects.filter(created_at__gte=start, created_at__lte=end)
    by_user = {item['user']: item for item in logs.filter(user__isnull=False).values('user').annotate(**counters())}

    users = get_user_model().objects.select_related('teacher', 'adjunct', 'student')
    users = users if show_inactive else users.filter(pk__in=by_user)
    result = {key: Category(key, title) for key, title in CATEGORIES if key in selected}
    for user in users:
        category = result.get(user_category(user))
        if category is not None:
            category.rows.append(stats_row(by_user.get(user.pk, {}), user.username, user.get_full_name(), user.pk))
    if UNKNOWN in result:
        # Записи без пользователя: неудачные входы с несуществующим логином и записи удалённых пользователей.
        unknown = logs.filter(user__isnull=True).values('username').annotate(**counters())
        result[UNKNOWN].rows = [stats_row(item, item['username'] or '—') for item in unknown]

    epoch = datetime.datetime.min.replace(tzinfo=datetime.UTC)
    for category in result.values():
        # Сначала недавно активные; без активности — в конце, по логину.
        category.rows.sort(key=lambda row: row.username)
        category.rows.sort(key=lambda row: row.last or epoch, reverse=True)
    return ActivityReport(start, end, list(result.values()), selected, timezone.now())


def user_log(start, end, user=None, username=None, action=None):
    """Подробный журнал пользователя (или записей без пользователя с таким логином) за период."""
    logs = ActivityLog.objects.filter(created_at__gte=start, created_at__lte=end).select_related('content_type')
    logs = logs.filter(user=user) if user is not None else logs.filter(user__isnull=True, username=username)
    if action:
        logs = logs.filter(action=action)
    return logs.order_by('created_at', 'pk')
