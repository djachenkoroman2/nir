"""Реестр отчётов раздела «Отчёты».

Новый отчёт: модуль с построением данных (как form16.py или work.py), представление и адрес в urls.py, запись
в REPORTS и, если отчёт доступен преподавателям, адъюнктам или курсантам, — страницы в белых списках
apps/core/cabinet.py.

Список /reports/ сгруппирован по назначению: группа отчёта может зависеть от пользователя (например, форма 16
для курсанта — «мой отчёт», для редактора — отчёт кафедры на любого человека).
"""
from dataclasses import dataclass
from typing import Callable

from django.urls import reverse

from apps.adjuncts.models import Adjunct
from apps.core.permissions import get_person
from apps.staff.models import Teacher

from .access import is_report_editor

OWN, SUPERVISION, DEPARTMENT, ADMINISTRATION = 'own', 'supervision', 'department', 'administration'
GROUPS = [
    (OWN, 'Мои отчёты'),
    (SUPERVISION, 'Отчёты по подопечным'),
    (DEPARTMENT, 'Отчёты кафедры'),
    (ADMINISTRATION, 'Администрирование'),
]


@dataclass(frozen=True)
class ReportType:
    slug: str
    title: str
    description: str
    url_name: str
    is_available: Callable  # (user) -> bool
    group: Callable = lambda user: DEPARTMENT  # (user) -> ключ группы в списке

    @property
    def url(self):
        return reverse(self.url_name)


def has_works(user):
    """Отчёт о трудах: у пользователя есть карточка человека кафедры или он редактор."""
    return is_report_editor(user) or get_person(user) is not None


def own_or_department(user):
    """Свой отчёт у человека кафедры; у редактора без карточки — отчёт кафедры на любого человека."""
    return OWN if get_person(user) is not None else DEPARTMENT


def of_kind(model):
    """Отчёт на людей одного вида: человеку этого вида — свой, редактору — на любого."""
    return lambda user: is_report_editor(user) or isinstance(get_person(user), model)


def own_kind_or_department(model):
    return lambda user: OWN if isinstance(get_person(user), model) else DEPARTMENT


REPORTS = [
    ReportType(
        slug='form16',
        title='Форма № 16 — список научных и учебно-методических трудов',
        description='Научные труды, учебные издания и объекты интеллектуальной собственности за выбранный период: '
                    'просмотр, печать и скачивание в DOCX.',
        url_name='reports:form16_own',
        is_available=has_works,
        group=own_or_department,
    ),
    ReportType(
        slug='work',
        title='Отчёт о научной работе',
        description='Публикации, доклады, РИД и достижения (у преподавателя — НИОКР, защиты подопечных и научные '
                    'школы) за период с итогами по видам: просмотр, печать и DOCX.',
        url_name='reports:work_own',
        is_available=has_works,
        group=own_or_department,
    ),
    ReportType(
        slug='plan',
        title='Отчёт о выполнении индивидуального плана адъюнкта',
        description='Этапы плана по годам обучения со статусами и отметками руководителя, итоги выполнения: '
                    'просмотр, печать и DOCX.',
        url_name='reports:plan_own',
        is_available=of_kind(Adjunct),
        group=own_kind_or_department(Adjunct),
    ),
    ReportType(
        slug='supervision',
        title='Отчёт о работе с подопечными',
        description='Труды и достижения подопечных курсантов и адъюнктов за период, их открытые задачи '
                    'и выполнение планов: просмотр, печать и DOCX.',
        url_name='reports:supervision_own',
        is_available=of_kind(Teacher),
        group=lambda user: SUPERVISION if isinstance(get_person(user), Teacher) else DEPARTMENT,
    ),
    ReportType(
        slug='cooperation',
        title='Договоры о научно-техническом сотрудничестве',
        description='Договоры с организациями, действовавшие в выбранном периоде: просмотр, печать и DOCX.',
        url_name='reports:cooperation',
        is_available=is_report_editor,
    ),
    ReportType(
        slug='department',
        title='Отчёт о НИР кафедры',
        description='Консолидированный (показатели по разделам, годам и людям) и подробный (перечни записей) вид '
                    'за период: просмотр, печать и DOCX.',
        url_name='reports:department',
        is_available=is_report_editor,
    ),
    ReportType(
        slug='activity',
        title='Активность пользователей',
        description='Входы, просмотры страниц, добавление, изменение и удаление записей, выгрузки отчётов '
                    'по пользователям и категориям за выбранный период; выгрузка в DOCX.',
        url_name='reports:activity',
        # Только администратору и тем, кому право выдано вручную: журнал содержит персональные данные.
        is_available=lambda user: user.has_perm('activity.view_activity_report'),
        group=lambda user: ADMINISTRATION,
    ),
]


def available_reports(user):
    return [report for report in REPORTS if report.is_available(user)]


def report_groups(user):
    """Доступные отчёты по группам: [(название группы, [отчёты])], только непустые группы."""
    reports = available_reports(user)
    groups = [(title, [report for report in reports if report.group(user) == key]) for key, title in GROUPS]
    return [(title, items) for title, items in groups if items]
