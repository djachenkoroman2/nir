"""Отчёт о выполнении индивидуального плана адъюнкта: за год обучения или за весь срок.

Данные собираются только здесь (build_plan_report), страница и DOCX строятся из plan_document.
Курс — по apps.adjuncts.study; «просрочен» — этап, не выполненный к плановому сроку (PlanStage.is_overdue).
"""
from dataclasses import dataclass

from apps.adjuncts.models import PlanStage

from .layout import Document, Section, Table, date, dash, file_name, fit, signature
from .work import course_label

S = PlanStage.Status


@dataclass
class PlanReport:
    adjunct: object
    study_year: int | None  # None — весь срок обучения
    stages: list

    @property
    def counts(self):
        """Итоги по статусам этапов: всего, выполнено, выполняется, запланировано, не выполнено, просрочено."""
        by_status = {status: sum(stage.status == status for stage in self.stages) for status in S}
        return {
            'total': len(self.stages), 'done': by_status[S.DONE], 'in_progress': by_status[S.IN_PROGRESS],
            'planned': by_status[S.PLANNED], 'failed': by_status[S.FAILED],
            'overdue': sum(stage.is_overdue for stage in self.stages),
        }

    @property
    def scope(self):
        if self.study_year:
            year = self.adjunct.admission_year + self.study_year - 1
            return f'{self.study_year}-й год обучения ({year}/{year + 1} уч. г.)'
        return f'весь срок обучения ({self.adjunct.study_years} г.)'


def build_plan_report(adjunct, study_year=None):
    stages = adjunct.plan_stages.all()
    if study_year:
        stages = stages.filter(study_year=study_year)
    return PlanReport(adjunct, study_year, list(stages))


def plan_document(report, author=''):
    adjunct = report.adjunct
    table = Table(
        ['№', 'Наименование этапа', 'Вид', 'Плановый срок', 'Статус', 'Дата выполнения', 'Отметка руководителя'],
        [1.0, *fit([3.6, 2.6, 3.4, 2.8, 5.6], 25.7 - 1.0)], centered=(0, 3, 5),
    )
    number, year = 0, None
    for stage in report.stages:
        if stage.study_year != year:
            year = stage.study_year
            table.group(f'{year}-й год обучения')
        number += 1
        status = stage.get_status_display() + (' (просрочен)' if stage.is_overdue else '')
        table.add(f'{number}.', stage.title, stage.get_kind_display(), date(stage.due_date), status,
                  date(stage.completed_date), dash(stage.supervisor_note))

    counts = report.counts
    percent = round(counts['done'] * 100 / counts['total']) if counts['total'] else 0
    totals = Table(['Показатель', 'Количество'], fit([4.0], 25.7), centered=(1,))
    for label, value in [
        ('Этапов всего', counts['total']), ('Выполнено', f'{counts["done"]} ({percent}%)'),
        ('Выполняется', counts['in_progress']), ('Запланировано', counts['planned']),
        ('Не выполнено', counts['failed']), ('Просрочено (не выполнены к плановому сроку)', counts['overdue']),
    ]:
        totals.add(label, value)

    info = [
        ('Тема диссертации', adjunct.dissertation_topic),
        ('Научная специальность', adjunct.specialty),
        ('Год поступления, курс', f'{adjunct.admission_year}, курс: {course_label(adjunct)}'),
        ('Форма обучения, срок', f'{adjunct.get_study_form_display()}, {adjunct.study_years} г.'),
        ('Научный руководитель', adjunct.supervisor.full_name),
        ('Планируемый год защиты', dash(adjunct.planned_defense_year)),
    ]
    return Document(
        'Отчёт о выполнении индивидуального плана работы адъюнкта',
        [adjunct.full_name, f'Период: {report.scope}'], info,
        [Section('Этапы индивидуального плана', table), Section('Итоги', totals)],
        signatures=[f'Адъюнкт  _______________  {signature(adjunct)}',
                    f'Научный руководитель  _______________  {signature(adjunct.supervisor)}'],
        landscape=True, author=author,
    )


def plan_filenames(report):
    adjunct, suffix = report.adjunct, f'_год_{report.study_year}' if report.study_year else ''
    return (f'План_{file_name(adjunct)}{suffix}.docx',
            f'plan_adjunct_{adjunct.pk}{f"_{report.study_year}" if report.study_year else ""}.docx')
