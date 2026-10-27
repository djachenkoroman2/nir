from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

from apps.staff.models import ProtectedRelationsMixin, Teacher


class Student(ProtectedRelationsMixin, models.Model):
    """Курсант (студент), который занимается научной работой на кафедре."""

    class Status(models.TextChoices):
        STUDYING = 'studying', 'обучается'
        GRADUATED = 'graduated', 'выпущен'
        EXPELLED = 'expelled', 'отчислен'

    STATUS_BADGES = {
        Status.STUDYING: 'text-bg-success',
        Status.GRADUATED: 'text-bg-secondary',
        Status.EXPELLED: 'text-bg-danger',
    }

    last_name = models.CharField('фамилия', max_length=100)
    first_name = models.CharField('имя', max_length=100)
    middle_name = models.CharField('отчество', max_length=100, blank=True)
    group = models.CharField('учебная группа', max_length=30, help_text='Например: ИБ-21.')
    course = models.PositiveSmallIntegerField('курс', validators=[MinValueValidator(1), MaxValueValidator(6)])
    supervisor = models.ForeignKey(
        Teacher, verbose_name='научный руководитель', on_delete=models.PROTECT, null=True, blank=True,
        related_name='supervised_students',
    )
    status = models.CharField('статус', max_length=20, choices=Status.choices, default=Status.STUDYING)
    note = models.TextField('примечание', blank=True)

    class Meta:
        verbose_name = 'курсант'
        verbose_name_plural = 'курсанты'
        ordering = ['course', 'group', 'last_name', 'first_name', 'middle_name']

    def __str__(self):
        return self.short_name

    def get_absolute_url(self):
        return reverse('students:student_detail', args=[self.pk])

    def get_tasks_url(self):
        return reverse('students:student_tasks', args=[self.pk])

    def is_supervised_by(self, teacher):
        return self.supervisor_id == teacher.pk

    @property
    def status_badge(self):
        return self.STATUS_BADGES.get(self.status, 'text-bg-light')

    @property
    def full_name(self):
        return ' '.join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    @property
    def short_name(self):
        initials = ' '.join(f'{part[0]}.' for part in (self.first_name, self.middle_name) if part)
        return f'{self.last_name} {initials}'.strip()


class AchievementBase(models.Model):
    """Общие поля персонального достижения (курсанта, адъюнкта)."""

    class Kind(models.TextChoices):
        OLYMPIAD = 'olympiad', 'олимпиада'
        CONTEST = 'contest', 'конкурс научных работ'
        GRANT = 'grant', 'грант'
        SCHOLARSHIP = 'scholarship', 'именная стипендия'
        EXHIBITION = 'exhibition', 'выставка'
        OTHER = 'other', 'другое'

    class Level(models.TextChoices):
        # Те же значения, что у уровня конференции (Conference.Level), но в мужском роде.
        UNIVERSITY = 'university', 'вузовский'
        REGIONAL = 'regional', 'региональный'
        NATIONAL = 'national', 'всероссийский'
        INTERNATIONAL = 'international', 'международный'

    kind = models.CharField('вид', max_length=20, choices=Kind.choices)
    level = models.CharField('уровень', max_length=20, choices=Level.choices)
    title = models.CharField('мероприятие или награда', max_length=500)
    result = models.CharField(
        'результат', max_length=200, help_text='Например: диплом I степени, победитель, участник.'
    )
    date = models.DateField('дата')
    document = models.CharField(
        'подтверждающий документ', max_length=500, blank=True, help_text='Ссылка или реквизиты документа.'
    )

    class Meta:
        abstract = True
        ordering = ['-date', 'title']

    def __str__(self):
        return f'{self.title}: {self.result}'

    @property
    def document_is_link(self):
        return self.document.startswith(('http://', 'https://'))


class StudentAchievement(AchievementBase):
    """Персональное достижение курсанта в научной работе."""

    student = models.ForeignKey(
        Student, verbose_name='курсант', on_delete=models.CASCADE, related_name='achievements'
    )
    supervisor = models.ForeignKey(
        Teacher, verbose_name='руководитель', on_delete=models.PROTECT, null=True, blank=True,
        related_name='supervised_achievements',
    )

    class Meta(AchievementBase.Meta):
        verbose_name = 'достижение курсанта'
        verbose_name_plural = 'достижения курсантов'

    def get_absolute_url(self):
        return self.student.get_absolute_url()

    def is_supervised_by(self, teacher):
        return self.student.is_supervised_by(teacher)
