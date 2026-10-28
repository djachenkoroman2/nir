"""Общее оформление отчётов в DOCX (python-docx): шрифт, страница, таблица с повтором заголовков, ответ HTTP."""
from io import BytesIO
from urllib.parse import quote

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from django.http import HttpResponse

DOCX_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
FONT = 'Times New Roman'


def new_document(landscape=False, left_margin=Cm(3), margin=Cm(2)):
    """Документ A4: шрифт Times New Roman 12 пт, книжная (поля слева 3 см) или альбомная ориентация."""
    document = Document()
    style = document.styles['Normal']
    style.font.name = FONT
    style.font.size = Pt(12)
    # Для кириллицы Word берёт шрифт из атрибута eastAsia/cs — задаём его явно.
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attribute in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        fonts.set(qn(attribute), FONT)
    style.paragraph_format.space_after = Pt(0)

    section = document.sections[0]
    if landscape:
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = Cm(29.7), Cm(21)
    else:
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = left_margin
    section.right_margin = section.top_margin = section.bottom_margin = margin
    return document


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


def add_table(document, headers, size=11):
    """Таблица с границами; строка заголовков повторяется на каждой странице."""
    table = document.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    header = table.rows[0]
    properties = header._tr.get_or_add_trPr()
    repeat = OxmlElement('w:tblHeader')
    repeat.set(qn('w:val'), 'true')
    properties.append(repeat)
    for cell, title in zip(header.cells, headers):
        fill_cell(cell, title, bold=True, center=True, size=size)
    return table


def add_row(table, values, bold=False, centered=(), size=11):
    cells = table.add_row().cells
    for index, (cell, value) in enumerate(zip(cells, values)):
        fill_cell(cell, value, bold=bold, center=index in centered, size=size)


def add_merged_row(table, text, bold=False, size=11):
    """Строка на всю ширину таблицы (заголовок раздела, «нет»)."""
    row = table.add_row()
    fill_cell(row.cells[0].merge(row.cells[-1]), text, bold=bold, center=True, size=size)


def set_widths(table, widths):
    """Ширину задаём и сетке таблицы (её читает LibreOffice), и ячейкам (её читает Word)."""
    table.autofit = False
    for column, width in zip(table.columns, widths):
        column.width = width
    for row in table.rows:
        if len({cell._tc for cell in row.cells}) == len(widths):  # объединённые строки пропускаем
            for cell, width in zip(row.cells, widths):
                cell.width = width


def docx_response(document, filename, fallback):
    """Ответ с файлом: имя в UTF-8 (filename*) и ASCII-запасное (filename) для старых клиентов."""
    buffer = BytesIO()
    document.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type=DOCX_TYPE)
    response['Content-Disposition'] = f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename)}'
    return response
