from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from apps.staff.models import Teacher


class ResearchProject(models.Model):
    """Научно-исследовательская и опытно-конструкторская работа (НИОКР)."""

    class Status(models.TextChoices):
        PLANNED = 'planned', 'планируется'
        IN_PROGRESS = 'in_progress', 'выполняется'
        COMPLETED = 'completed', 'завершена'
        SUSPENDED = 'suspended', 'приостановлена'
        CANCELLED = 'cancelled', 'отменена'

    STATUS_BADGES = {
        Status.PLANNED: 'text-bg-info',
        Status.IN_PROGRESS: 'text-bg-primary',
        Status.COMPLETED: 'text-bg-success',
        Status.SUSPENDED: 'text-bg-warning',
        Status.CANCELLED: 'text-bg-secondary',
    }

    title = models.CharField('название', max_length=500)
    start_date = models.DateField('дата начала')
    end_date = models.DateField(
        'дата окончания', null=True, blank=True, help_text='Можно не заполнять для незавершённых работ.'
    )
    status = models.CharField('статус', max_length=20, choices=Status.choices, default=Status.PLANNED)
    participants = models.ManyToManyField(
        Teacher, through='Participant', related_name='research_projects', verbose_name='участники'
    )

    class Meta:
        verbose_name = 'НИОКР'
        verbose_name_plural = 'НИОКР'
        ordering = ['-start_date', 'title']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('research:project_detail', args=[self.pk])

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'Дата окончания не может быть раньше даты начала.'})

    @property
    def status_badge(self):
        return self.STATUS_BADGES.get(self.status, 'text-bg-light')


class Participant(models.Model):
    """Участие преподавателя в НИОКР с указанием роли."""

    class Role(models.IntegerChoices):
        # Порядок значений задаёт порядок вывода: руководитель первым.
        LEADER = 1, 'руководитель'
        MEMBER = 2, 'исполнитель'

    project = models.ForeignKey(
        ResearchProject, verbose_name='НИОКР', on_delete=models.CASCADE, related_name='memberships'
    )
    teacher = models.ForeignKey(
        Teacher, verbose_name='преподаватель', on_delete=models.PROTECT, related_name='memberships'
    )
    role = models.PositiveSmallIntegerField('роль', choices=Role.choices, default=Role.MEMBER)

    class Meta:
        verbose_name = 'участник НИОКР'
        verbose_name_plural = 'участники НИОКР'
        ordering = ['role', 'teacher__last_name', 'teacher__first_name']
        constraints = [
            models.UniqueConstraint(fields=['project', 'teacher'], name='unique_project_teacher'),
        ]

    def __str__(self):
        return f'{self.teacher} — {self.get_role_display()}'
