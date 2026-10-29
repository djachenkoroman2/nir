"""Отчёт преподавателя о работе с подопечными курсантами и адъюнктами за период.

Данные собираются только здесь (build_supervision_report), страница и DOCX строятся из supervision_document.
Труды и достижения считаются за период (правила apps.reports.works); задачи и план — состояние на сегодня.
Каждая строка считается подзапросами в одном запросе на вид подопечных: число запросов не зависит от их числа.
"""
from dataclasses import dataclass

from django.db.models import Count, Q
from django.utils import timezone

from apps.adjuncts.models import Adjunct, PlanStage, Task
from apps.students.models import Student

from . import works
from .layout import Document, Section, Table, file_name, fit, signature
from .work import course_label

COLUMNS = ['Публикаций', 'Докладов', 'РИД', 'Достижений', 'Открытых задач', 'Просрочено задач']


@dataclass
class Supervisee:
    person: object
    description: str  # группа и курс курсанта, курс адъюнкта
    status: str
    values: list  # по COLUMNS
    plan: str = '—'  # «выполнено N из M, просрочено K» у адъюнкта


@dataclass
class SupervisionReport:
    teacher: object
    period: works.Period
    include_finished: bool
    students: list
    adjuncts: list

    @staticmethod
    def totals(rows):
        return [sum(row.values[index] for row in rows) for index in range(len(COLUMNS))]


def annotate_works(queryset, field, period, achievements):
    today = timezone.localdate()
    open_tasks = Q(tasks__status__in=Task.OPEN_STATUSES)
    return queryset.annotate(
        n_publications=works.count_for(works.publications(period), f'authors__{field}'),
        n_talks=works.count_for(works.talks(period), f'speakers__{field}'),
        n_ips=works.count_for(works.intellectual_properties(period), f'authors__{field}'),
        n_achievements=works.count_for(achievements, field),
        n_open_tasks=Count('tasks', filter=open_tasks, distinct=True),
        n_overdue_tasks=Count('tasks', filter=open_tasks & Q(tasks__due_date__lt=today), distinct=True),
    )


def values(person):
    return [person.n_publications, person.n_talks, person.n_ips, person.n_achievements, person.n_open_tasks,
            person.n_overdue_tasks]


def build_supervision_report(teacher, period, include_finished=False):
    students = teacher.supervised_students.all()
    adjuncts = teacher.supervised_adjuncts.all()
    if not include_finished:
        students = students.filter(status=Student.Status.STUDYING)
        adjuncts = adjuncts.exclude(status__in=Adjunct.FINISHED_STATUSES)
    students = annotate_works(students, 'student', period, works.student_achievements(period))
    today = timezone.localdate()
    adjuncts = annotate_works(adjuncts, 'adjunct', period, works.adjunct_achievements(period)).annotate(
        n_stages=works.count_for(PlanStage.objects.all(), 'adjunct'),
        n_done=works.count_for(PlanStage.objects.filter(status=PlanStage.Status.DONE), 'adjunct'),
        n_overdue_stages=works.count_for(
            PlanStage.objects.filter(status__in=[PlanStage.Status.PLANNED, PlanStage.Status.IN_PROGRESS],
                                     due_date__lt=today), 'adjunct'),
    )
    return SupervisionReport(
        teacher, period, include_finished,
        [Supervisee(student, f'группа {student.group}, {student.course} курс', student.get_status_display(),
                    values(student)) for student in students.order_by(*Student._meta.ordering)],
        [Supervisee(adjunct, f'{course_label(adjunct)} курс' if adjunct.course else '', adjunct.get_status_display(),
                    values(adjunct),
                    f'выполнено {adjunct.n_done} из {adjunct.n_stages}, просрочено {adjunct.n_overdue_stages}')
         for adjunct in adjuncts.order_by(*Adjunct._meta.ordering)],
    )


def supervision_document(report, author=''):
    teacher = report.teacher
    table = Table(['ФИО', 'Сведения', 'Статус', *(title.replace(' ', '\n') for title in COLUMNS), 'План работы'],
                  [3.8, 2.8, *fit([*([2.3] * len(COLUMNS)), 3.4], 25.7 - 6.6)],
                  centered=tuple(range(3, 3 + len(COLUMNS))), header_size=9)
    for title, rows in (('Курсанты', report.students), ('Адъюнкты', report.adjuncts)):
        table.group(title)
        if not rows:
            table.add('нет', '', '', *([''] * len(COLUMNS)), '')
            continue
        for row in rows:
            table.add(row.person.full_name, row.description, row.status, *row.values, row.plan)
        table.total(f'Итого: {title.lower()} ({len(rows)})', '', '', *report.totals(rows), '')
    table.total('Всего', '', '', *report.totals(report.students + report.adjuncts), '')

    shown = 'все подопечные, включая выпущенных и отчисленных' if report.include_finished \
        else 'обучающиеся подопечные (без выпущенных и отчисленных)'
    return Document(
        'Отчёт о работе с подопечными курсантами и адъюнктами',
        [f'Научный руководитель: {teacher.full_name}', f'Период: {report.period.label}'],
        sections=[Section('Подопечные', table)],
        notes=[f'В отчёте: {shown}. Публикации, доклады, РИД и достижения — за период; '
               'открытые и просроченные задачи и выполнение плана — на дату формирования.'],
        signatures=[f'Научный руководитель  _______________  {signature(teacher)}'],
        landscape=True, author=author,
    )


def supervision_filenames(report):
    teacher = report.teacher
    return (f'Подопечные_{file_name(teacher)}_{report.period.slug}.docx',
            f'supervision_teacher_{teacher.pk}_{report.period.slug}.docx')
