"""Правила отбора записей для отчётов: к какому периоду относится запись и чья она.

Отчёты о человеке и отчёт по кафедре берут записи только отсюда, поэтому их итоги согласованы.
Период — годы «с — по»: у публикации есть только год издания, поэтому точнее года период не задаётся.
- Публикация относится к периоду по году издания, доклад — по дате начала конференции, РИД — по дате регистрации,
  защита — по дате защиты, достижение — по дате.
- НИОКР и договоры входят в период, если сроки пересекаются с ним (запись без даты окончания продолжается).
"""
from dataclasses import dataclass

from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.adjuncts.models import AdjunctAchievement
from apps.conferences.models import Report
from apps.cooperation.models import CooperationContract
from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication
from apps.research.models import ResearchProject
from apps.schools.models import DissertationDefense
from apps.staff.models import author_lookup
from apps.students.models import StudentAchievement

# Категории людей кафедры: ключ — имя поля автора (AuthorBase.teacher / adjunct / student).
TEACHERS, ADJUNCTS, STUDENTS = 'teacher', 'adjunct', 'student'
PEOPLE_CATEGORIES = [(TEACHERS, 'Преподаватели'), (ADJUNCTS, 'Адъюнкты'), (STUDENTS, 'Курсанты')]
ALL_PEOPLE = [key for key, _ in PEOPLE_CATEGORIES]


@dataclass(frozen=True)
class Period:
    year_from: int
    year_to: int

    @classmethod
    def current(cls):
        """По умолчанию — текущий календарный год."""
        year = timezone.localdate().year
        return cls(year, year)

    @property
    def years(self):
        return list(range(self.year_from, self.year_to + 1))

    @property
    def label(self):
        if self.year_from == self.year_to:
            return f'{self.year_from} г.'
        return f'{self.year_from}–{self.year_to} гг.'

    @property
    def slug(self):
        """Для имени файла: «2026» или «2022-2026»."""
        return str(self.year_from) if self.year_from == self.year_to else f'{self.year_from}-{self.year_to}'

    def as_tuple(self):
        """Период в виде, который принимают показатели научных школ (apps.schools.indicators)."""
        return self.year_from, self.year_to


def years(lookup, period):
    return {f'{lookup}__gte': period.year_from, f'{lookup}__lte': period.year_to}


def publications(period):
    return Publication.objects.filter(**years('year', period))


def intellectual_properties(period):
    return IntellectualProperty.objects.filter(**years('registration_date__year', period))


def talks(period):
    """Доклады на конференциях за период."""
    return Report.objects.filter(**years('conference__start_date__year', period))


def project_overlaps(year_from, year_to):
    return Q(start_date__year__lte=year_to) & (Q(end_date__isnull=True) | Q(end_date__year__gte=year_from))


def projects(period):
    return ResearchProject.objects.filter(project_overlaps(period.year_from, period.year_to))


def contract_overlaps(year_from, year_to):
    return Q(start_date__year__lte=year_to) & (Q(end_date__isnull=True) | Q(end_date__year__gte=year_from))


def contracts(period):
    return CooperationContract.objects.filter(contract_overlaps(period.year_from, period.year_to))


def defenses(period):
    return DissertationDefense.objects.filter(**years('defense_date__year', period))


def student_achievements(period):
    return StudentAchievement.objects.filter(**years('date__year', period))


def adjunct_achievements(period):
    return AdjunctAchievement.objects.filter(**years('date__year', period))


def authors_exist(model, relation, condition):
    """Условие «у записи есть автор (докладчик), подходящий под condition» — без JOIN и повторов строк."""
    rel = model._meta.get_field(relation)
    return Exists(rel.related_model.objects.filter(condition, **{rel.field.name: OuterRef('pk')}))


def department_authors(categories=None):
    """Автор — человек кафедры выбранных категорий (None — любой); внешние авторы не подходят."""
    condition = Q()
    for key in categories or ALL_PEOPLE:
        condition |= Q(**{f'{key}__isnull': False})
    return condition


def by_department(queryset, relation, categories=None):
    """Записи кафедры: хотя бы один автор — человек кафедры. Записи только с внешними авторами не входят."""
    return queryset.filter(authors_exist(queryset.model, relation, department_authors(categories)))


def by_person(queryset, relation, person):
    """Записи, где человек указан автором (докладчиком)."""
    return queryset.filter(authors_exist(queryset.model, relation, Q(**author_lookup(person))))


def count_for(queryset, lookup):
    """Число записей queryset, связанных с человеком через lookup, — подзапрос для annotate.

    Так строки по людям считаются одним запросом, а не запросом на каждого (как показатели научных школ).
    """
    counts = (queryset.filter(**{lookup: OuterRef('pk')}).order_by().values(lookup)
              .annotate(count=Count('pk', distinct=True)).values('count'))
    return Coalesce(Subquery(counts, output_field=IntegerField()), 0)
