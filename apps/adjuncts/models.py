import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.staff.models import ProtectedRelationsMixin, Teacher
from apps.students.models import AchievementBase, Student

from .study import academic_course


class Adjunct(ProtectedRelationsMixin, models.Model):
    """Адъюнкт (аспирант) кафедры."""

    class StudyForm(models.TextChoices):
        FULL_TIME = 'full_time', 'очная'
        PART_TIME = 'part_time', 'заочная'

    class Status(models.TextChoices):
        STUDYING = 'studying', 'обучается'
        ACADEMIC_LEAVE = 'academic_leave', 'академический отпуск'
        GRADUATED = 'graduated', 'окончил'
        DEFENDED = 'defended', 'защитился'
        EXPELLED = 'expelled', 'отчислен'

    # Для этих статусов курс не показывается: обучение закончено.
    FINISHED_STATUSES = (Status.GRADUATED, Status.DEFENDED, Status.EXPELLED)
    STATUS_BADGES = {
        Status.STUDYING: 'text-bg-success',
        Status.ACADEMIC_LEAVE: 'text-bg-warning',
        Status.GRADUATED: 'text-bg-secondary',
        Status.DEFENDED: 'text-bg-primary',
        Status.EXPELLED: 'text-bg-danger',
    }

    last_name = models.CharField('фамилия', max_length=100)
    first_name = models.CharField('имя', max_length=100)
    middle_name = models.CharField('отчество', max_length=100, blank=True)
    dissertation_topic = models.CharField('тема диссертации', max_length=500)
    specialty = models.CharField(
        'научная специальность', max_length=300, help_text='Например: 2.3.6. Методы и системы защиты информации.'
    )
    admission_year = models.PositiveSmallIntegerField(
        'год поступления', validators=[MinValueValidator(1990), MaxValueValidator(2100)]
    )
    study_form = models.CharField('форма обучения', max_length=20, choices=StudyForm.choices,
                                  default=StudyForm.FULL_TIME)
    study_years = models.PositiveSmallIntegerField(
        'нормативный срок обучения, лет', default=3, validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    supervisor = models.ForeignKey(
        Teacher, verbose_name='научный руководитель', on_delete=models.PROTECT, related_name='supervised_adjuncts'
    )
    school = models.ForeignKey(
        'schools.ScientificSchool', verbose_name='научная школа', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='adjuncts',
    )
    status = models.CharField('статус', max_length=20, choices=Status.choices, default=Status.STUDYING)
    planned_defense_year = models.PositiveSmallIntegerField(
        'планируемый год защиты', null=True, blank=True, validators=[MinValueValidator(1990), MaxValueValidator(2100)]
    )
    email = models.EmailField('e-mail', blank=True)
    phone = models.CharField('телефон', max_length=30, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name='учётная запись', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='adjunct',
    )

    class Meta:
        verbose_name = 'адъюнкт'
        verbose_name_plural = 'адъюнкты'
        ordering = ['last_name', 'first_name', 'middle_name']

    def __str__(self):
        return self.short_name

    def get_absolute_url(self):
        return reverse('adjuncts:adjunct_detail', args=[self.pk])

    def get_tasks_url(self):
        return reverse('adjuncts:adjunct_tasks', args=[self.pk])

    def clean(self):
        if self.user_id and Teacher.objects.filter(user_id=self.user_id).exists():
            raise ValidationError({'user': 'Эта учётная запись уже привязана к карточке преподавателя.'})

    def is_supervised_by(self, teacher):
        return self.supervisor_id == teacher.pk

    def is_authored_by(self, person):
        """Своя запись адъюнкта (используется для вложенных записей: достижений)."""
        return isinstance(person, Adjunct) and person.pk == self.pk

    @property
    def course(self):
        """Курс в текущем учебном году; None, если обучение закончено."""
        if self.status in self.FINISHED_STATUSES:
            return None
        return academic_course(self.admission_year)

    @property
    def term_expired(self):
        course = self.course
        return course is not None and course > self.study_years

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


class AdjunctOwnedMixin:
    """Права на запись, вложенную в карточку адъюнкта: её ведут сам адъюнкт и его руководитель."""

    def get_absolute_url(self):
        return self.adjunct.get_absolute_url()

    def is_supervised_by(self, teacher):
        return self.adjunct.is_supervised_by(teacher)

    def is_authored_by(self, person):
        return self.adjunct.is_authored_by(person)


class AdjunctAchievement(AdjunctOwnedMixin, AchievementBase):
    """Персональное достижение адъюнкта."""

    adjunct = models.ForeignKey(
        Adjunct, verbose_name='адъюнкт', on_delete=models.CASCADE, related_name='achievements'
    )

    class Meta(AchievementBase.Meta):
        verbose_name = 'достижение адъюнкта'
        verbose_name_plural = 'достижения адъюнктов'


class PlanStage(AdjunctOwnedMixin, models.Model):
    """Этап индивидуального плана работы адъюнкта."""

    class Kind(models.TextChoices):
        EXAM = 'exam', 'кандидатский экзамен'
        PUBLICATION = 'publication', 'публикация'
        CHAPTER = 'chapter', 'глава диссертации'
        APPROBATION = 'approbation', 'апробация (доклад)'
        PRE_DEFENSE = 'pre_defense', 'предзащита'
        OTHER = 'other', 'другое'

    class Status(models.TextChoices):
        PLANNED = 'planned', 'запланирован'
        IN_PROGRESS = 'in_progress', 'выполняется'
        DONE = 'done', 'выполнен'
        FAILED = 'failed', 'не выполнен'

    STATUS_BADGES = {
        Status.PLANNED: 'text-bg-light border',
        Status.IN_PROGRESS: 'text-bg-info',
        Status.DONE: 'text-bg-success',
        Status.FAILED: 'text-bg-danger',
    }

    adjunct = models.ForeignKey(Adjunct, verbose_name='адъюнкт', on_delete=models.CASCADE, related_name='plan_stages')
    study_year = models.PositiveSmallIntegerField('год обучения', validators=[MinValueValidator(1)])
    title = models.CharField('наименование этапа', max_length=500)
    kind = models.CharField('вид', max_length=20, choices=Kind.choices)
    due_date = models.DateField('плановый срок')
    status = models.CharField('статус', max_length=20, choices=Status.choices, default=Status.PLANNED)
    completed_date = models.DateField('дата выполнения', null=True, blank=True)
    supervisor_note = models.TextField('отметка руководителя', blank=True)

    class Meta:
        verbose_name = 'этап плана'
        verbose_name_plural = 'этапы плана'
        ordering = ['study_year', 'due_date', 'pk']

    def __str__(self):
        return f'{self.study_year} год: {self.title}'

    def clean(self):
        if self.adjunct_id and self.study_year and self.study_year > self.adjunct.study_years:
            raise ValidationError({
                'study_year': f'Год обучения не может быть больше срока обучения ({self.adjunct.study_years}).'
            })

    @property
    def status_badge(self):
        return self.STATUS_BADGES.get(self.status, 'text-bg-light')

    @property
    def is_overdue(self):
        return self.status in (self.Status.PLANNED, self.Status.IN_PROGRESS) and self.due_date < timezone.localdate()


class Task(models.Model):
    """Задача, которую научный руководитель ставит адъюнкту или курсанту (исполнитель — ровно один из них)."""

    class Priority(models.IntegerChoices):
        LOW = 1, 'низкий'
        NORMAL = 2, 'обычный'
        HIGH = 3, 'высокий'

    class Status(models.TextChoices):
        NEW = 'new', 'новая'
        IN_PROGRESS = 'in_progress', 'в работе'
        REVIEW = 'review', 'на проверке'
        DONE = 'done', 'выполнена'
        CANCELLED = 'cancelled', 'отменена'

    OPEN_STATUSES = (Status.NEW, Status.IN_PROGRESS, Status.REVIEW)
    # У курсанта нет учётной записи: задачу ведёт руководитель, поэтому «на проверке» не нужна.
    STUDENT_STATUSES = (Status.NEW, Status.IN_PROGRESS, Status.DONE, Status.CANCELLED)
    # Переходы, доступные самому адъюнкту; руководитель и редактор переводят задачу в любой статус.
    ADJUNCT_TRANSITIONS = {
        Status.NEW: [Status.IN_PROGRESS],
        Status.IN_PROGRESS: [Status.REVIEW],
        Status.REVIEW: [Status.IN_PROGRESS],
    }
    STATUS_BADGES = {
        Status.NEW: 'text-bg-primary',
        Status.IN_PROGRESS: 'text-bg-info',
        Status.REVIEW: 'text-bg-warning',
        Status.DONE: 'text-bg-success',
        Status.CANCELLED: 'text-bg-secondary',
    }
    PRIORITY_BADGES = {Priority.LOW: 'text-bg-light border', Priority.NORMAL: 'text-bg-light border',
                       Priority.HIGH: 'text-bg-danger'}

    adjunct = models.ForeignKey(
        Adjunct, verbose_name='адъюнкт', on_delete=models.CASCADE, null=True, blank=True, related_name='tasks'
    )
    student = models.ForeignKey(
        Student, verbose_name='курсант', on_delete=models.CASCADE, null=True, blank=True, related_name='tasks'
    )
    title = models.CharField('заголовок', max_length=300)
    description = models.TextField('описание', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='поставил', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_tasks',
    )
    created_at = models.DateTimeField('создана', default=timezone.now)
    due_date = models.DateField('срок', null=True, blank=True)
    priority = models.PositiveSmallIntegerField('приоритет', choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField('статус', max_length=20, choices=Status.choices, default=Status.NEW)
    plan_stage = models.ForeignKey(
        PlanStage, verbose_name='этап плана', on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks'
    )
    completed_at = models.DateTimeField('выполнена', null=True, blank=True)

    class Meta:
        verbose_name = 'задача'
        verbose_name_plural = 'задачи'
        ordering = [models.F('due_date').asc(nulls_last=True), '-priority', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=Q(adjunct__isnull=False, student__isnull=True)
                | Q(adjunct__isnull=True, student__isnull=False),
                name='task_single_assignee',
                violation_error_message='У задачи должен быть ровно один исполнитель: адъюнкт или курсант.',
            ),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('tasks:task_detail', args=[self.pk])

    def clean(self):
        if (self.adjunct_id is None) == (self.student_id is None):
            raise ValidationError('У задачи должен быть ровно один исполнитель: адъюнкт или курсант.')
        if self.plan_stage_id:
            if self.student_id:
                raise ValidationError({'plan_stage': 'У задачи курсанта не бывает этапа плана.'})
            if self.plan_stage.adjunct_id != self.adjunct_id:
                raise ValidationError({'plan_stage': 'Этап относится к плану другого адъюнкта.'})
        if self.status not in self.statuses:
            raise ValidationError({'status': f'Статус «{self.get_status_display()}» недоступен для этой задачи.'})

    @property
    def person(self):
        """Исполнитель: адъюнкт или курсант."""
        return self.adjunct if self.adjunct_id else self.student

    @property
    def statuses(self):
        """Статусы, допустимые для задачи этого исполнителя."""
        return self.STUDENT_STATUSES if self.student_id else tuple(self.Status)

    def is_supervised_by(self, teacher):
        return self.person.is_supervised_by(teacher)

    def is_authored_by(self, person):
        # Сам с задачей работает только адъюнкт: у курсанта нет учётной записи.
        return self.adjunct_id is not None and self.adjunct.is_authored_by(person)

    def set_status(self, status):
        """Меняет статус; дата завершения заполняется при переходе в «выполнена» и сбрасывается иначе."""
        self.status = status
        self.completed_at = timezone.now() if status == self.Status.DONE else None

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_overdue(self):
        return self.is_open and self.due_date is not None and self.due_date < timezone.localdate()

    @property
    def status_badge(self):
        return self.STATUS_BADGES.get(self.status, 'text-bg-light')

    @property
    def priority_badge(self):
        return self.PRIORITY_BADGES.get(self.priority, 'text-bg-light')


class TaskComment(models.Model):
    """Комментарий к задаче или служебная запись о смене статуса."""

    # Сколько времени после публикации автор может удалить свой комментарий.
    DELETE_WINDOW = datetime.timedelta(minutes=15)

    task = models.ForeignKey(Task, verbose_name='задача', on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='автор', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='task_comments',
    )
    text = models.TextField('текст')
    created_at = models.DateTimeField('дата и время', default=timezone.now)
    is_system = models.BooleanField('служебная запись', default=False)

    class Meta:
        verbose_name = 'комментарий к задаче'
        verbose_name_plural = 'комментарии к задачам'
        ordering = ['created_at', 'pk']

    def __str__(self):
        return self.text[:60]

    def can_be_deleted_by(self, user):
        return (
            not self.is_system and self.author_id == user.pk
            and timezone.now() - self.created_at <= self.DELETE_WINDOW
        )
