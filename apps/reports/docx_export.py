"""Форма № 16 в формате DOCX (python-docx). Данные — готовый результат build_form16."""
from io import BytesIO

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

HEADERS = ['№ п/п', 'Наименование работы, её вид', 'Форма работы', 'Выходные данные', 'Объём, п. л. или с.',
           'Соавторы']
# Ширина столбцов в сумме 16 см (A4 при полях 3 и 2 см): «Наименование» и «Выходные данные» шире остальных.
WIDTHS = [Cm(1.0), Cm(4.6), Cm(2.5), Cm(4.0), Cm(1.6), Cm(2.3)]
FONT = 'Times New Roman'


def set_font(document):
    style = document.styles['Normal']
    style.font.name = FONT
    style.font.size = Pt(12)
    # Для кириллицы Word берёт шрифт из атрибута eastAsia/cs — задаём его явно.
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attribute in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        fonts.set(qn(attribute), FONT)
    style.paragraph_format.space_after = Pt(0)


def setup_page(document):
    section = document.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = Cm(3)
    section.right_margin = section.top_margin = section.bottom_margin = Cm(2)


def repeat_header(row):
    """Строка заголовков повторяется на каждой странице."""
    properties = row._tr.get_or_add_trPr()
    element = OxmlElement('w:tblHeader')
    element.set(qn('w:val'), 'true')
    properties.append(element)


def paragraph(document, text, bold=False, center=False, space_after=0):
    p = document.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(space_after)
    return p


def fill_cell(cell, text, bold=False, center=False, size=11):
    cell.text = ''
    run = cell.paragraphs[0].add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if center:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER


def build_docx(report):
    document = Document()
    set_font(document)
    setup_page(document)

    paragraph(document, 'СПИСОК', bold=True, center=True)
    paragraph(document, 'научных и учебно-методических трудов', bold=True, center=True)
    paragraph(document, f'Автор: {report.person.full_name}', center=True)
    paragraph(document, report.position, center=True)
    if report.period:
        paragraph(document, f'Период: {report.period}', center=True)
    paragraph(document, '', space_after=6)

    table = document.add_table(rows=1, cols=len(HEADERS))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    header = table.rows[0]
    repeat_header(header)
    for cell, title in zip(header.cells, HEADERS):
        fill_cell(cell, title, bold=True, center=True)

    for section in report.sections:
        row = table.add_row()
        merged = row.cells[0].merge(row.cells[-1])
        fill_cell(merged, f'{section.number}. {section.title}', bold=True, center=True)
        if not section.rows:
            empty = table.add_row()
            fill_cell(empty.cells[0].merge(empty.cells[-1]), 'нет', center=True)
        for item in section.rows:
            cells = table.add_row().cells
            values = [f'{item.number}.', item.title, item.work_form, item.imprint, item.volume, item.coauthors]
            for index, (cell, value) in enumerate(zip(cells, values)):
                fill_cell(cell, value, center=index in (0, 2, 4))

    # Ширину задаём и сетке таблицы (её читает LibreOffice), и ячейкам (её читает Word).
    table.autofit = False
    for column, width in zip(table.columns, WIDTHS):
        column.width = width
    for row in table.rows:
        if len({cell._tc for cell in row.cells}) == len(WIDTHS):  # строки разделов объединены — пропускаем
            for cell, width in zip(row.cells, WIDTHS):
                cell.width = width

    paragraph(document, '', space_after=12)
    paragraph(document, f'Автор  _______________  {report.signature}', space_after=12)
    paragraph(document, 'Список верен:', space_after=6)
    paragraph(document, 'Заведующий кафедрой  _______________', space_after=12)
    paragraph(document, 'Учёный секретарь  _______________', space_after=12)
    paragraph(document, f'Дата формирования: {report.created:%d.%m.%Y}')

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
