from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from apps.publications.models import Publication
from apps.staff.models import AuthorBase


class Conference(models.Model):
    """Научная конференция (семинар, симпозиум, форум)."""

    class Level(models.TextChoices):
        INTERNATIONAL = 'international', 'международная'
        NATIONAL = 'national', 'всероссийская'
        REGIONAL = 'regional', 'региональная'
        UNIVERSITY = 'university', 'вузовская'

    LEVEL_BADGES = {
        Level.INTERNATIONAL: 'text-bg-primary',
        Level.NATIONAL: 'text-bg-info',
        Level.REGIONAL: 'text-bg-secondary',
        Level.UNIVERSITY: 'text-bg-light',
    }

    title = models.CharField('название', max_length=500)
    level = models.CharField('уровень', max_length=20, choices=Level.choices)
    location = models.CharField('место проведения', max_length=300, blank=True, help_text='Город или «онлайн».')
    start_date = models.DateField('дата начала')
    end_date = models.DateField('дата окончания', null=True, blank=True)
    url = models.URLField('сайт', max_length=500, blank=True)

    class Meta:
        verbose_name = 'конференция'
        verbose_name_plural = 'конференции'
        ordering = ['-start_date', 'title']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('conferences:conference_detail', args=[self.pk])

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'Дата окончания не может быть раньше даты начала.'})

    @property
    def level_badge(self):
        return self.LEVEL_BADGES.get(self.level, 'text-bg-light')


class Report(models.Model):
    """Доклад на конференции."""

    class Form(models.TextChoices):
        PLENARY = 'plenary', 'пленарный'
        SECTION = 'section', 'секционный'
        POSTER = 'poster', 'стендовый'

    conference = models.ForeignKey(
        Conference, verbose_name='конференция', on_delete=models.CASCADE, related_name='reports'
    )
    title = models.CharField('тема доклада', max_length=500)
    form = models.CharField('форма', max_length=20, choices=Form.choices, default=Form.SECTION)
    publication = models.OneToOneField(
        Publication, verbose_name='опубликованные тезисы', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='report', help_text='Если по докладу опубликованы тезисы или статья.',
    )

    class Meta:
        verbose_name = 'доклад'
        verbose_name_plural = 'доклады'
        ordering = ['conference', 'title']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return self.conference.get_absolute_url()

    @property
    def speakers_display(self):
        return ', '.join(str(speaker) for speaker in self.speakers.all())


class ReportSpeaker(AuthorBase):
    report = models.ForeignKey(Report, verbose_name='доклад', on_delete=models.CASCADE, related_name='speakers')

    class Meta(AuthorBase.Meta):
        verbose_name = 'докладчик'
        verbose_name_plural = 'докладчики'
        constraints = [
            models.UniqueConstraint(
                fields=['report', 'teacher'], condition=models.Q(teacher__isnull=False),
                name='unique_report_teacher',
            ),
        ]
