"""Реестр отчётов раздела «Отчёты».

Новый отчёт: модуль с построением данных (как form16.py), представление и адрес в urls.py, запись в REPORTS
и, если отчёт доступен преподавателям, адъюнктам или курсантам, — страницы в белых списках apps/core/cabinet.py.
"""
from dataclasses import dataclass
from typing import Callable

from django.urls import reverse

from apps.core.permissions import get_person

from .access import is_report_editor


@dataclass(frozen=True)
class ReportType:
    slug: str
    title: str
    description: str
    url_name: str
    is_available: Callable  # (user) -> bool

    @property
    def url(self):
        return reverse(self.url_name)


def has_works(user):
    """Отчёт о трудах: у пользователя есть карточка человека кафедры или он редактор."""
    return is_report_editor(user) or get_person(user) is not None


REPORTS = [
    ReportType(
        slug='form16',
        title='Форма № 16 — список научных и учебно-методических трудов',
        description='Научные труды, учебные издания и объекты интеллектуальной собственности за выбранный период: '
                    'просмотр, печать и скачивание в DOCX.',
        url_name='reports:form16_own',
        is_available=has_works,
    ),
    ReportType(
        slug='activity',
        title='Активность пользователей',
        description='Входы, просмотры страниц, добавление, изменение и удаление записей, выгрузки отчётов '
                    'по пользователям и категориям за выбранный период; выгрузка в DOCX.',
        url_name='reports:activity',
        # Только администратору и тем, кому право выдано вручную: журнал содержит персональные данные.
        is_available=lambda user: user.has_perm('activity.view_activity_report'),
    ),
]


def available_reports(user):
    return [report for report in REPORTS if report.is_available(user)]
