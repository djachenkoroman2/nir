"""Форма № 16 в формате DOCX. Данные — готовый результат build_form16, оформление — docx_common."""
from docx.shared import Cm

from .docx_common import add_merged_row, add_row, add_table, heading, new_document, paragraph, set_widths, signatures

HEADERS = ['№ п/п', 'Наименование работы, её вид', 'Форма работы', 'Выходные данные', 'Объём, п. л. или с.',
           'Соавторы']
# Ширина столбцов в сумме 16 см (A4 при полях 3 и 2 см): «Наименование» и «Выходные данные» шире остальных.
WIDTHS = [Cm(1.0), Cm(4.6), Cm(2.5), Cm(4.0), Cm(1.6), Cm(2.3)]


def build_docx(report):
    document = new_document()

    lines = [f'Автор: {report.person.full_name}', report.position]
    if report.period:
        lines.append(f'Период: {report.period}')
    heading(document, ['СПИСОК', 'научных и учебно-методических трудов'], lines)

    table = add_table(document, HEADERS)
    for section in report.sections:
        add_merged_row(table, f'{section.number}. {section.title}', bold=True)
        if not section.rows:
            add_merged_row(table, 'нет')
        for item in section.rows:
            values = [f'{item.number}.', item.title, item.work_form, item.imprint, item.volume, item.coauthors]
            add_row(table, values, centered=(0, 2, 4))
    set_widths(table, WIDTHS)

    signatures(document, [
        f'Автор  _______________  {report.signature}', ('Список верен:', 6),
        'Заведующий кафедрой  _______________', 'Учёный секретарь  _______________',
    ])
    paragraph(document, f'Дата формирования: {report.created:%d.%m.%Y}')
    return document
