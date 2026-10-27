"""Общее для команд seed_demo и clear_data (модуль с «_» Django командой не считает)."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.conferences.models import Conference, Report, ReportSpeaker
from apps.ip.models import IntellectualProperty, IntellectualPropertyAuthor
from apps.publications.models import Publication, PublicationAuthor
from apps.research.models import Participant, ResearchProject
from apps.schools.models import DissertationDefense, ScientificSchool
from apps.staff.models import Teacher
from apps.students.models import Student, StudentAchievement

# Предметные модели в порядке удаления: сначала зависимые записи, потом те, на которые они
# ссылаются с on_delete=PROTECT (авторы → преподаватели и курсанты, защиты → школы и т.д.).
DOMAIN_MODELS = [
    ReportSpeaker, Report, Conference,
    PublicationAuthor, Publication,
    IntellectualPropertyAuthor, IntellectualProperty,
    DissertationDefense, ScientificSchool,
    Participant, ResearchProject,
    StudentAchievement, Student,
    Teacher,
]


def has_domain_data():
    return any(model.objects.exists() for model in DOMAIN_MODELS)


def domain_counts():
    return [(model._meta.verbose_name_plural, model.objects.count()) for model in DOMAIN_MODELS]


class DevOnlyCommand(BaseCommand):
    """Команда только для разработки: при DEBUG=False работает лишь с --force."""

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Выполнить, даже если DJANGO_DEBUG=False (рабочий сервер).',
        )

    def check_environment(self, options):
        if not settings.DEBUG and not options['force']:
            raise CommandError(
                'DJANGO_DEBUG=False: похоже, это рабочий сервер. Команда предназначена только для разработки '
                'и меняет данные в базе. Если вы уверены, повторите с параметром --force.'
            )

    def print_counts(self, title, counts):
        self.stdout.write(title)
        for name, count in counts:
            if count:
                self.stdout.write(f'  {name}: {count}')
