"""Отчёт о договорах научно-технического сотрудничества за период.

Записи отбираются общим правилом apps.reports.works; страница, печать и DOCX строятся из одного Document.
"""
from dataclasses import dataclass

from . import works
from .layout import Document, Section, Table, date


@dataclass
class CooperationReport:
    period: works.Period
    contracts: list

    @property
    def indefinite_count(self):
        return sum(contract.is_indefinite for contract in self.contracts)


def build_cooperation_report(period):
    return CooperationReport(
        period,
        list(works.contracts(period).order_by('start_date', 'title')),
    )


def cooperation_document(report, author=''):
    table = Table(
        ['№', 'Название', 'Номер', 'Организация', 'Предмет договора', 'Дата начала', 'Дата окончания'],
        [1.0, 4.3, 2.8, 4.4, 5.8, 3.7, 3.7],
        centered=(0, 5, 6),
        empty='Договоры за выбранный период не найдены',
        header_size=9,
    )
    for number, contract in enumerate(report.contracts, start=1):
        table.add(
            f'{number}.', contract.title, contract.number or '—', contract.organization, contract.subject,
            date(contract.start_date), date(contract.end_date) if contract.end_date else 'бессрочно',
        )
    total = f'Итого: {len(report.contracts)} (из них бессрочных: {report.indefinite_count})'
    return Document(
        'Договоры о научно-техническом сотрудничестве',
        [f'Период: {report.period.label}'],
        sections=[Section('Реестр договоров', table, total=total)],
        notes=[
            'В отчёт входят договоры, срок действия которых пересекается с выбранным периодом. '
            'Бессрочный договор учитывается во всех периодах начиная с даты его начала.',
        ],
        signatures=['Заведующий кафедрой  _______________', 'Учёный секретарь  _______________'],
        landscape=True,
        author=author,
    )


def cooperation_filenames(report):
    return (f'Договоры_сотрудничество_{report.period.slug}.docx',
            f'cooperation_contracts_{report.period.slug}.docx')
