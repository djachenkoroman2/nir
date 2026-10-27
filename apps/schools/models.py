from django.db import models
from django.urls import reverse

from apps.staff.models import Teacher


class ScientificSchool(models.Model):
    """Научная школа кафедры (научное направление)."""

    name = models.CharField('наименование научного направления', max_length=500, unique=True)
    description = models.TextField('краткое описание', blank=True)
    leaders = models.ManyToManyField(Teacher, verbose_name='ведущие учёные', related_name='led_schools')
    is_active = models.BooleanField('действующая', default=True)

    class Meta:
        verbose_name = 'научная школа'
        verbose_name_plural = 'научные школы'
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('schools:school_detail', args=[self.pk])


class DissertationDefense(models.Model):
    """Защита диссертации по направлению научной школы."""

    class Kind(models.TextChoices):
        CANDIDATE = 'candidate', 'кандидатская'
        DOCTOR = 'doctor', 'докторская'

    full_name = models.CharField('ФИО защитившегося', max_length=200)
    teacher = models.ForeignKey(
        Teacher, verbose_name='сотрудник кафедры', on_delete=models.PROTECT, null=True, blank=True,
        related_name='dissertation_defenses', help_text='Если защитился преподаватель кафедры.',
    )
    kind = models.CharField('вид', max_length=20, choices=Kind.choices)
    title = models.CharField('тема диссертации', max_length=500)
    defense_date = models.DateField('дата защиты')
    school = models.ForeignKey(
        ScientificSchool, verbose_name='научная школа', on_delete=models.PROTECT, related_name='defenses'
    )
    supervisor = models.ForeignKey(
        Teacher, verbose_name='научный руководитель (консультант)', on_delete=models.PROTECT,
        null=True, blank=True, related_name='supervised_defenses',
    )

    class Meta:
        verbose_name = 'защита диссертации'
        verbose_name_plural = 'защиты диссертаций'
        ordering = ['-defense_date', 'full_name']

    def __str__(self):
        return f'{self.full_name}, {self.get_kind_display()} ({self.defense_date:%Y})'

    def get_absolute_url(self):
        return self.school.get_absolute_url()
