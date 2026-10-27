from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from apps.research.models import ResearchProject
from apps.staff.models import AuthorBase, author_lookup


class IntellectualProperty(models.Model):
    """Результат интеллектуальной деятельности (РИД): патент или свидетельство о регистрации."""

    class Kind(models.TextChoices):
        INVENTION = 'invention', 'патент на изобретение'
        UTILITY_MODEL = 'utility_model', 'патент на полезную модель'
        INDUSTRIAL_DESIGN = 'industrial_design', 'патент на промышленный образец'
        SOFTWARE = 'software', 'свидетельство на программу для ЭВМ'
        DATABASE = 'database', 'свидетельство на базу данных'

    kind = models.CharField('вид', max_length=20, choices=Kind.choices)
    title = models.CharField('название', max_length=500)
    number = models.CharField('номер', max_length=50)
    application_date = models.DateField('дата подачи заявки', null=True, blank=True)
    registration_date = models.DateField('дата регистрации')
    holder = models.CharField(
        'правообладатель', max_length=300, blank=True, help_text='Например, наименование вуза.'
    )
    url = models.URLField('ссылка', max_length=500, blank=True, help_text='Например, на запись в реестре ФИПС.')
    schools = models.ManyToManyField(
        'schools.ScientificSchool', verbose_name='научные школы', blank=True, related_name='intellectual_properties',
        help_text='Научные направления, к которым относится РИД.',
    )
    project = models.ForeignKey(
        ResearchProject, verbose_name='НИОКР', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='intellectual_properties', help_text='Если РИД получен в рамках НИОКР.',
    )

    class Meta:
        verbose_name = 'РИД'
        verbose_name_plural = 'РИД'
        ordering = ['-registration_date', 'title']
        constraints = [
            models.UniqueConstraint(fields=['kind', 'number'], name='unique_ip_kind_number'),
        ]

    def __str__(self):
        return f'{self.title} (№ {self.number})'

    def get_absolute_url(self):
        return reverse('ip:ip_detail', args=[self.pk])

    def clean(self):
        if self.application_date and self.registration_date and self.registration_date < self.application_date:
            raise ValidationError({'registration_date': 'Дата регистрации не может быть раньше даты подачи заявки.'})

    def is_authored_by(self, person):
        return self.authors.filter(**author_lookup(person)).exists()

    @property
    def authors_display(self):
        return ', '.join(str(author) for author in self.authors.all())


class IntellectualPropertyAuthor(AuthorBase):
    intellectual_property = models.ForeignKey(
        IntellectualProperty, verbose_name='РИД', on_delete=models.CASCADE, related_name='authors'
    )

    class Meta(AuthorBase.Meta):
        verbose_name = 'автор РИД'
        verbose_name_plural = 'авторы РИД'
        constraints = [
            models.UniqueConstraint(
                fields=['intellectual_property', 'teacher'], condition=models.Q(teacher__isnull=False),
                name='unique_ip_teacher',
            ),
            models.UniqueConstraint(
                fields=['intellectual_property', 'student'], condition=models.Q(student__isnull=False),
                name='unique_ip_student',
            ),
            models.UniqueConstraint(
                fields=['intellectual_property', 'adjunct'], condition=models.Q(adjunct__isnull=False),
                name='unique_ip_adjunct',
            ),
        ]
