from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone


class CooperationContract(models.Model):
    """Договор о научно-техническом сотрудничестве с другой организацией."""

    class State(models.TextChoices):
        ACTIVE = 'active', 'действует'
        FINISHED = 'finished', 'завершён'
        UPCOMING = 'upcoming', 'ещё не начался'

    STATE_BADGES = {
        State.ACTIVE: 'text-bg-success',
        State.FINISHED: 'text-bg-secondary',
        State.UPCOMING: 'text-bg-info',
    }

    title = models.CharField('название', max_length=500)
    number = models.CharField('номер договора', max_length=100, blank=True)
    organization = models.CharField('организация-контрагент', max_length=500)
    subject = models.TextField('предмет договора')
    start_date = models.DateField('дата начала действия')
    end_date = models.DateField(
        'дата окончания действия', null=True, blank=True,
        help_text='Оставьте пустым для бессрочного договора.',
    )

    class Meta:
        verbose_name = 'договор о научно-техническом сотрудничестве'
        verbose_name_plural = 'договоры о научно-техническом сотрудничестве'
        ordering = ['-start_date', 'title']

    def __str__(self):
        return f'{self.title} — {self.organization}'

    def get_absolute_url(self):
        return reverse('cooperation:contract_detail', args=[self.pk])

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'Дата окончания не может быть раньше даты начала.'})

    @staticmethod
    def active_filter(on_date):
        """Условие действующего договора на дату, в том числе бессрочного."""
        return Q(start_date__lte=on_date) & (Q(end_date__isnull=True) | Q(end_date__gte=on_date))

    @property
    def is_indefinite(self):
        return self.end_date is None

    @property
    def state(self):
        today = timezone.localdate()
        if self.start_date > today:
            return self.State.UPCOMING
        if self.end_date and self.end_date < today:
            return self.State.FINISHED
        return self.State.ACTIVE

    def get_state_display(self):
        return self.State(self.state).label

    @property
    def state_badge(self):
        return self.STATE_BADGES.get(self.state, 'text-bg-light')

    @property
    def term_display(self):
        if self.end_date:
            return f'{self.start_date:%d.%m.%Y} — {self.end_date:%d.%m.%Y}'
        return f'с {self.start_date:%d.%m.%Y}, бессрочно'
