"""Общее оформление отчётов в DOCX (python-docx): шрифт, страница, таблица с повтором заголовков, ответ HTTP.

Здесь же — повторяющиеся части документов (заголовок, подписи, дата формирования) и build_document_docx,
который строит DOCX из вида документа apps.reports.layout.Document.
"""
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
from django.utils import timezone

from .layout import GROUP, TOTAL

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


def add_runs(p, value, bold=False, size=None):
    """Текст в абзац: строка или layout.Text (фрагменты с выделением полужирным)."""
    for text, strong in getattr(value, 'parts', [(str(value), False)]):
        run = p.add_run(text)
        run.bold = bold or strong
        if size:
            run.font.size = Pt(size)


def fill_cell(cell, text, bold=False, center=False, size=11):
    cell.text = ''
    add_runs(cell.paragraphs[0], text, bold, size)
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


def heading(document, bold_lines, lines=()):
    """Заголовок документа: строки по центру (первые — полужирные) и отступ перед содержимым."""
    for line in bold_lines:
        paragraph(document, line, bold=True, center=True)
    for line in lines:
        paragraph(document, line, center=True)
    paragraph(document, '', space_after=6)


def signatures(document, lines):
    """Строки подписей; строка — текст или пара (текст, отступ после в пт), по умолчанию отступ 12 пт."""
    paragraph(document, '', space_after=12)
    for line in lines:
        text, space_after = line if isinstance(line, tuple) else (line, 12)
        paragraph(document, text, space_after=space_after)


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


def build_document_docx(doc):
    """DOCX из вида документа layout.Document: те же заголовок, сведения, разделы и подписи, что на странице."""
    landscape_margin = {'left_margin': Cm(2)} if doc.landscape else {}
    document = new_document(landscape=doc.landscape, **landscape_margin)
    heading(document, [doc.title], doc.subtitle)
    size = doc.font_size
    if doc.info:
        info = document.add_table(rows=0, cols=2)
        for label, value in doc.info:
            cells = info.add_row().cells
            fill_cell(cells[0], label, bold=True, size=size + 1)
            fill_cell(cells[1], value, size=size + 1)
        set_widths(info, [Cm(doc.text_width * 0.35), Cm(doc.text_width * 0.65)])
        paragraph(document, '', space_after=6)

    for section in doc.sections:
        p = paragraph(document, section.title, bold=True, space_after=4)
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.keep_with_next = True
        if section.table is not None:
            write_table(document, section.table, size)
        elif section.entries is not None:
            for number, entry in enumerate(section.entries, start=1):
                p = document.add_paragraph()
                add_runs(p, f'{number}. ', size=size + 1)
                add_runs(p, entry, size=size + 1)
                p.paragraph_format.space_after = Pt(3)
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if not section.entries:
                paragraph(document, 'нет')
        if section.total:
            paragraph(document, section.total, bold=True).paragraph_format.space_before = Pt(3)
        if section.note:
            add_runs(document.add_paragraph(), section.note, size=size)

    for note in doc.notes:
        p = document.add_paragraph()
        add_runs(p, note, size=size)
        p.paragraph_format.space_before = Pt(6)
    if doc.signatures:
        signatures(document, doc.signatures)
    else:
        paragraph(document, '', space_after=6)
    created = f'Дата формирования: {timezone.localtime(doc.created):%d.%m.%Y %H:%M}'
    paragraph(document, f'{created}, пользователь {doc.author}' if doc.author else created)
    return document


def write_table(document, spec, size):
    """Таблица из layout.Table: заголовки повторяются на страницах, блоки — строки на всю ширину, итоги полужирные."""
    table = add_table(document, spec.headers, size=spec.header_size or size)
    if not spec.rows:
        add_merged_row(table, spec.empty, size=size)
    for row in spec.rows:
        if row.kind == GROUP:
            add_merged_row(table, row.cells[0], bold=True, size=size)
        else:
            add_row(table, row.cells, bold=row.kind == TOTAL, centered=spec.centered, size=size)
    set_widths(table, [Cm(width) for width in spec.widths])
    return table
