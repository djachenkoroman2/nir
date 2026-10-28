"""Форма № 16 в формате DOCX. Данные — готовый результат build_form16, оформление — docx_common."""
from docx.shared import Cm

from .docx_common import add_merged_row, add_row, add_table, new_document, paragraph, set_widths

HEADERS = ['№ п/п', 'Наименование работы, её вид', 'Форма работы', 'Выходные данные', 'Объём, п. л. или с.',
           'Соавторы']
# Ширина столбцов в сумме 16 см (A4 при полях 3 и 2 см): «Наименование» и «Выходные данные» шире остальных.
WIDTHS = [Cm(1.0), Cm(4.6), Cm(2.5), Cm(4.0), Cm(1.6), Cm(2.3)]


def build_docx(report):
    document = new_document()

    paragraph(document, 'СПИСОК', bold=True, center=True)
    paragraph(document, 'научных и учебно-методических трудов', bold=True, center=True)
    paragraph(document, f'Автор: {report.person.full_name}', center=True)
    paragraph(document, report.position, center=True)
    if report.period:
        paragraph(document, f'Период: {report.period}', center=True)
    paragraph(document, '', space_after=6)

    table = add_table(document, HEADERS)
    for section in report.sections:
        add_merged_row(table, f'{section.number}. {section.title}', bold=True)
        if not section.rows:
            add_merged_row(table, 'нет')
        for item in section.rows:
            values = [f'{item.number}.', item.title, item.work_form, item.imprint, item.volume, item.coauthors]
            add_row(table, values, centered=(0, 2, 4))
    set_widths(table, WIDTHS)

    paragraph(document, '', space_after=12)
    paragraph(document, f'Автор  _______________  {report.signature}', space_after=12)
    paragraph(document, 'Список верен:', space_after=6)
    paragraph(document, 'Заведующий кафедрой  _______________', space_after=12)
    paragraph(document, 'Учёный секретарь  _______________', space_after=12)
    paragraph(document, f'Дата формирования: {report.created:%d.%m.%Y}')
    return document
