from django.conf import settings
from django.db import models
from django.urls import reverse


class Teacher(models.Model):
    """Преподаватель кафедры (профессорско-преподавательский состав)."""

    class Position(models.TextChoices):
        ASSISTANT = 'assistant', 'ассистент'
        LECTURER = 'lecturer', 'преподаватель'
        SENIOR_LECTURER = 'senior_lecturer', 'старший преподаватель'
        ASSOCIATE_PROFESSOR = 'associate_professor', 'доцент'
        PROFESSOR = 'professor', 'профессор'
        HEAD = 'head', 'заведующий кафедрой'

    class Degree(models.TextChoices):
        NONE = 'none', 'нет'
        CANDIDATE = 'candidate', 'кандидат наук'
        DOCTOR = 'doctor', 'доктор наук'

    class AcademicTitle(models.TextChoices):
        NONE = 'none', 'нет'
        DOCENT = 'docent', 'доцент'
        PROFESSOR = 'professor', 'профессор'

    last_name = models.CharField('фамилия', max_length=100)
    first_name = models.CharField('имя', max_length=100)
    middle_name = models.CharField('отчество', max_length=100, blank=True)
    position = models.CharField('должность', max_length=30, choices=Position.choices)
    degree = models.CharField('учёная степень', max_length=20, choices=Degree.choices, default=Degree.NONE)
    academic_title = models.CharField(
        'учёное звание', max_length=20, choices=AcademicTitle.choices, default=AcademicTitle.NONE
    )
    email = models.EmailField('e-mail', blank=True)
    phone = models.CharField('телефон', max_length=30, blank=True)
    is_active = models.BooleanField(
        'работает на кафедре',
        default=True,
        help_text='Снимите отметку вместо удаления, чтобы сохранить историю участия в НИОКР.',
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name='учётная запись',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teacher',
    )

    class Meta:
        verbose_name = 'преподаватель'
        verbose_name_plural = 'преподаватели'
        ordering = ['last_name', 'first_name', 'middle_name']

    def __str__(self):
        return self.short_name

    def get_absolute_url(self):
        return reverse('staff:teacher_detail', args=[self.pk])

    @property
    def full_name(self):
        return ' '.join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    @property
    def short_name(self):
        initials = ' '.join(f'{part[0]}.' for part in (self.first_name, self.middle_name) if part)
        return f'{self.last_name} {initials}'.strip()
