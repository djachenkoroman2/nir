"""Вид отчётного документа: заголовок, сведения, разделы с таблицами или перечнями, подписи.

Отчёты о человеке, отчёт по кафедре и карточки собирают данные в своих модулях и раскладывают их в Document.
Из одного Document строятся страница (шаблон reports/document.html) и DOCX (docx_common.build_document_docx),
поэтому в браузере, при печати и в файле одно и то же содержимое.
"""
from dataclasses import dataclass, field

from django.utils import timezone

ROW, GROUP, TOTAL = 'row', 'group', 'total'


@dataclass
class Text:
    """Текст с выделенными фрагментами: parts — пары (текст, полужирный)."""

    parts: list

    def __str__(self):
        return ''.join(text for text, _ in self.parts)


@dataclass
class Row:
    cells: list
    kind: str = ROW  # GROUP — строка на всю ширину (заголовок блока), TOTAL — итоговая (полужирная)


@dataclass
class Table:
    headers: list
    widths: list  # ширина столбцов в см; в сумме — ширина текста страницы
    rows: list = field(default_factory=list)
    centered: tuple = ()  # номера столбцов, выровненных по центру (числа, даты)
    empty: str = 'нет'
    header_size: int | None = None  # заголовки узких числовых столбцов — мельче, чтобы слова не разрывались

    def add(self, *cells):
        self.rows.append(Row([value if isinstance(value, Text) else str(value) for value in cells]))

    def group(self, title):
        self.rows.append(Row([title], GROUP))

    def total(self, *cells):
        self.rows.append(Row([str(value) for value in cells], TOTAL))


@dataclass
class Section:
    title: str
    table: Table | None = None
    entries: list | None = None  # нумерованный перечень (Text или строки) вместо таблицы
    total: str = ''  # строка «Итого: N» под разделом
    note: str = ''


@dataclass
class Document:
    title: str
    subtitle: list = field(default_factory=list)  # строки под заголовком: ФИО, должность, период
    info: list = field(default_factory=list)  # сведения: пары (подпись, значение)
    sections: list = field(default_factory=list)
    notes: list = field(default_factory=list)  # пояснения после разделов
    signatures: list = field(default_factory=list)  # строки подписей: «Адъюнкт ____ И. О. Фамилия»
    landscape: bool = False
    font_size: int = 10  # размер шрифта таблиц в DOCX
    created: object = field(default_factory=timezone.now)
    author: str = ''  # кто сформировал (логин)

    @property
    def text_width(self):
        """Ширина текста страницы в см: A4 книжная при полях 3 и 2 см, альбомная при полях 2 см."""
        return 25.7 if self.landscape else 16.0


def signature(person):
    """Подпись: «И. О. Фамилия»."""
    initials = ' '.join(f'{part[0]}.' for part in (person.first_name, person.middle_name) if part)
    return f'{initials} {person.last_name}'.strip()


def file_name(person):
    """Часть имени файла: «Иванов_С_П»."""
    initials = '_'.join(part[0] for part in (person.first_name, person.middle_name) if part)
    return f'{person.last_name}_{initials}'.rstrip('_')


def fit(widths, total):
    """Ширины столбцов в см: первый (текстовый) столбец забирает остаток до ширины текста total."""
    return [round(total - sum(widths), 2), *widths]


def dash(value):
    return value if value not in (None, '') else '—'


def date(value):
    return f'{value:%d.%m.%Y}' if value else '—'
