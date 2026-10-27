"""Показатели научных школ за отчётный период.

Каждый показатель описан один раз: какие записи считаются и через какое поле они связаны со школой.
Из этого описания строятся и числа в сводной таблице, и списки записей в карточке школы.
"""
from dataclasses import dataclass
from typing import Callable

from django.db.models import Count, IntegerField, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce

from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication

from .models import DissertationDefense


@dataclass(frozen=True)
class Indicator:
    key: str
    label: str
    records: Callable[[tuple[int, int]], QuerySet]  # записи за период, без отбора по школе
    school_lookup: str  # поле записи, связывающее её со школой

    def for_school(self, school, period):
        return self.records(period).filter(**{self.school_lookup: school})

    def count_subquery(self, period):
        """Число записей школы — подзапрос для annotate, чтобы вся таблица считалась одним запросом."""
        counts = (
            self.records(period)
            .filter(**{self.school_lookup: OuterRef('pk')})
            .order_by()
            .values(self.school_lookup)
            .annotate(count=Count('pk', distinct=True))
            .values('count')
        )
        return Coalesce(Subquery(counts, output_field=IntegerField()), 0)

    def total(self, schools, period):
        """Число записей по набору школ; запись нескольких школ считается один раз."""
        return self.records(period).filter(**{f'{self.school_lookup}__in': schools}).distinct().count()


def _defenses(period):
    return DissertationDefense.objects.filter(defense_date__year__gte=period[0], defense_date__year__lte=period[1])


def _publications(period):
    return Publication.objects.filter(year__gte=period[0], year__lte=period[1])


def _intellectual_properties(period):
    return IntellectualProperty.objects.filter(
        registration_date__year__gte=period[0], registration_date__year__lte=period[1]
    )


VAK_CATEGORIES = [Publication.VakCategory.K1, Publication.VakCategory.K2, Publication.VakCategory.K3]

INDICATORS = [
    Indicator('candidate_defenses', 'кандидатские',
              lambda p: _defenses(p).filter(kind=DissertationDefense.Kind.CANDIDATE), 'school'),
    Indicator('doctor_defenses', 'докторские',
              lambda p: _defenses(p).filter(kind=DissertationDefense.Kind.DOCTOR), 'school'),
    Indicator('defenses_total', 'всего защит', _defenses, 'school'),
    Indicator('monographs', 'монографии',
              lambda p: _publications(p).filter(kind=Publication.Kind.MONOGRAPH), 'schools'),
    Indicator('monograph_chapters', 'главы в монографиях',
              lambda p: _publications(p).filter(kind=Publication.Kind.MONOGRAPH_CHAPTER), 'schools'),
    Indicator('vak_publications', 'публикации ВАК',
              lambda p: _publications(p).filter(vak__in=VAK_CATEGORIES), 'schools'),
    Indicator('ip_total', 'РИД', _intellectual_properties, 'schools'),
]
INDICATORS_BY_KEY = {indicator.key: indicator for indicator in INDICATORS}


def annotate_indicators(schools, period):
    return schools.annotate(**{indicator.key: indicator.count_subquery(period) for indicator in INDICATORS})


def indicator_totals(schools, period):
    return {indicator.key: indicator.total(schools, period) for indicator in INDICATORS}
