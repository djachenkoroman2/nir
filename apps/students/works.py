"""Труды и сводка человека кафедры (курсанта, адъюнкта) для его карточки."""
from collections import Counter

from django.db.models import Count, Q

from apps.conferences.models import Report
from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication
from apps.staff.models import AUTHORS_PREFETCH, SPEAKERS_PREFETCH, author_lookup

from .models import AchievementBase


def works_context(person, achievements):
    """Публикации, доклады и РИД, где person указан автором, и сводка по ним и по достижениям."""
    [(field, _)] = author_lookup(person).items()
    publications = Publication.objects.filter(**{f'authors__{field}': person})
    level_counts = Counter(achievement.level for achievement in achievements)
    return {
        'achievements': achievements,
        'publications': publications.prefetch_related(*AUTHORS_PREFETCH),
        'publication_stats': publications.aggregate(
            total=Count('pk'),
            vak=Count('pk', filter=~Q(vak='')),
            rinc=Count('pk', filter=Q(rinc=True) | Q(rinc_core=True)),
            scopus=Count('pk', filter=Q(scopus=True)),
            wos=Count('pk', filter=Q(wos=True)),
        ),
        'achievement_levels': [(label, level_counts[value]) for value, label in AchievementBase.Level.choices],
        'intellectual_properties': (
            IntellectualProperty.objects.filter(**{f'authors__{field}': person}).prefetch_related(*AUTHORS_PREFETCH)
        ),
        'reports': (
            Report.objects.filter(**{f'speakers__{field}': person}).select_related('conference')
            .prefetch_related(*SPEAKERS_PREFETCH).order_by('-conference__start_date')
        ),
    }
