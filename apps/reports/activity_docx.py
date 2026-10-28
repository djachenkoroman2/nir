"""Отчёт об активности пользователей в DOCX: A4 альбомная, данные — результат build_activity_report."""
from django.utils import timezone
from docx.shared import Cm

from .activity import COUNTERS
from .docx_common import add_merged_row, add_row, add_table, new_document, paragraph, set_widths

# Слова заголовков — с новой строки: в узких столбцах длинное слово иначе разрывается посередине.
HEADERS = ['Пользователь', *(title.replace(' ', '\n') for _, title in COUNTERS), 'Первая\nактивность',
           'Последняя\nактивность']
# В сумме 25,7 см — ширина текста альбомного A4 при полях 2 см.
WIDTHS = [Cm(3.9), *([Cm(2.2)] * len(COUNTERS)), Cm(3.2), Cm(3.2)]
SIZE = 10
HEADER_SIZE = 9  # заголовки узких числовых столбцов — мельче, чтобы слова не разрывались
NUMBERS = tuple(range(1, len(HEADERS)))


def moment(value):
    return timezone.localtime(value).strftime('%d.%m.%Y %H:%M') if value else '—'


def build_activity_docx(report, author):
    document = new_document(landscape=True, left_margin=Cm(2))
    paragraph(document, 'Отчёт об активности пользователей', bold=True, center=True)
    paragraph(document, f'Период: с {moment(report.start)} по {moment(report.end)}', center=True)
    paragraph(document, f'Категории: {report.selected_titles}', center=True, space_after=6)

    table = add_table(document, HEADERS, size=HEADER_SIZE)
    for category in report.categories:
        add_merged_row(table, category.title, bold=True, size=SIZE)
        if not category.rows:
            add_merged_row(table, 'нет активности', size=SIZE)
            continue
        for row in category.rows:
            name = f'{row.username} ({row.full_name})' if row.full_name else row.username
            add_row(table, [name, *map(str, row.values), moment(row.first), moment(row.last)],
                    centered=NUMBERS, size=SIZE)
        add_row(table, [f'Итого: {category.title.lower()}', *map(str, category.totals), '', ''],
                bold=True, centered=NUMBERS, size=SIZE)
    add_row(table, ['Всего', *map(str, report.totals), '', ''], bold=True, centered=NUMBERS, size=SIZE)
    set_widths(table, WIDTHS)

    paragraph(document, '', space_after=6)
    paragraph(document, f'Сформирован: {moment(report.created)}, пользователь {author.get_username()}')
    return document
