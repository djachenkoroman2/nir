from django.conf import settings
from django.core.exceptions import ValidationError
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

    def has_protected_relations(self):
        """Участвует ли преподаватель в НИОКР, публикациях, РИД или докладах (тогда удалять нельзя)."""
        return any(
            relation.related_model._default_manager.filter(**{relation.field.name: self}).exists()
            for relation in self._meta.related_objects
            if relation.on_delete is models.PROTECT
        )

    @property
    def full_name(self):
        return ' '.join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    @property
    def short_name(self):
        initials = ' '.join(f'{part[0]}.' for part in (self.first_name, self.middle_name) if part)
        return f'{self.last_name} {initials}'.strip()


class AuthorBase(models.Model):
    """Автор (соавтор, докладчик): преподаватель кафедры или внешний человек, указанный текстом.

    Используется в публикациях, РИД и докладах; порядок авторов хранится в поле order.
    """

    teacher = models.ForeignKey(
        Teacher, verbose_name='преподаватель кафедры', on_delete=models.PROTECT, null=True, blank=True
    )
    external_name = models.CharField(
        'внешний автор', max_length=200, blank=True, help_text='ФИО, если автор не работает на кафедре.'
    )
    order = models.PositiveSmallIntegerField('порядок', default=0)

    class Meta:
        abstract = True
        ordering = ['order', 'pk']

    def __str__(self):
        return self.teacher.short_name if self.teacher_id else self.external_name

    def clean(self):
        if bool(self.teacher_id) == bool(self.external_name.strip()):
            raise ValidationError('Выберите преподавателя кафедры или укажите ФИО внешнего автора (что-то одно).')
