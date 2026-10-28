"""Форма № 16 «Список научных и учебно-методических трудов».

Данные отчёта собираются только здесь (build_form16); страница в браузере и DOCX строятся из результата.
В форму входят опубликованные труды: доклад попадает в неё своими опубликованными тезисами
(Report.publication — это обычная публикация вида «тезисы»), доклады без тезисов не включаются.
"""
import re
from dataclasses import dataclass, field

from django.db.models import Prefetch
from django.http import Http404
from django.utils import timezone

from apps.adjuncts.models import Adjunct
from apps.ip.models import IntellectualProperty, IntellectualPropertyAuthor
from apps.publications.models import Publication, PublicationAuthor
from apps.staff.models import Teacher, author_lookup
from apps.students.models import Student

# Вид человека в адресе отчёта: pk преподавателя, адъюнкта и курсанта могут совпадать.
PERSON_KINDS = {'teacher': Teacher, 'adjunct': Adjunct, 'student': Student}

SCIENCE, STUDY, IP = 'science', 'study', 'ip'
K = Publication.Kind
SECTIONS = [
    (SCIENCE, 'Научные труды', [K.ARTICLE, K.THESES, K.MONOGRAPH, K.MONOGRAPH_CHAPTER]),
    (STUDY, 'Учебные и учебно-методические издания', [K.TEXTBOOK, K.STUDY_GUIDE]),
    (IP, 'Объекты интеллектуальной собственности', None),
]
SECTION_CHOICES = [(key, title) for key, title, _ in SECTIONS]
# Программы и базы данных регистрируются как электронные работы, патенты — как печатные (описание, формула).
ELECTRONIC_IP_KINDS = {IntellectualProperty.Kind.SOFTWARE, IntellectualProperty.Kind.DATABASE}
PAGE_RANGE = re.compile(r'^\s*(?:[сcСC]\.\s*)?(\d+)\s*[-–—]\s*(\d+)\s*$')


def get_report_person(kind, pk):
    """Человек кафедры по виду и pk из адреса отчёта или 404."""
    model = PERSON_KINDS.get(kind)
    if model is None:
        raise Http404
    person = model.objects.filter(pk=pk).first()
    if person is None:
        raise Http404
    return person


def person_kind(person):
    return person._meta.model_name


@dataclass
class Row:
    number: int
    title: str
    work_form: str
    imprint: str
    volume: str
    coauthors: str


@dataclass
class Section:
    number: int
    key: str
    title: str
    rows: list = field(default_factory=list)


@dataclass
class Form16:
    person: object
    position: str
    year_from: int | None
    year_to: int | None
    sections: list
    created: object

    @property
    def period(self):
        if self.year_from and self.year_to:
            return f'{self.year_from}–{self.year_to} гг.' if self.year_from != self.year_to else f'{self.year_from} г.'
        if self.year_from:
            return f'с {self.year_from} г.'
        if self.year_to:
            return f'по {self.year_to} г.'
        return ''

    @property
    def signature(self):
        """Подпись в форме: «И. О. Фамилия»."""
        initials = ' '.join(f'{part[0]}.' for part in (self.person.first_name, self.person.middle_name) if part)
        return f'{initials} {self.person.last_name}'.strip()

    @property
    def is_empty(self):
        return not any(section.rows for section in self.sections)


def describe(person):
    """Должность и степень преподавателя или категория адъюнкта и курсанта — для заголовка."""
    if isinstance(person, Teacher):
        parts = [person.get_position_display()]
        if person.degree != Teacher.Degree.NONE:
            parts.append(person.get_degree_display())
        if person.academic_title != Teacher.AcademicTitle.NONE:
            parts.append(person.get_academic_title_display())
        return ', '.join(parts)
    if isinstance(person, Adjunct):
        return f'адъюнкт, научная специальность {person.specialty}' if person.specialty else 'адъюнкт'
    return f'курсант, учебная группа {person.group}'


def volume(publication):
    """Объём: в печатных листах, если указан; иначе число страниц из диапазона или текст как есть."""
    if publication.print_sheets is not None:
        sheets = f'{publication.print_sheets.normalize():f}'.replace('.', ',')
        return f'{sheets}\u00a0п.\u00a0л.'  # неразрывные пробелы: объём не разрывается переносом
    match = PAGE_RANGE.match(publication.pages)
    if match:
        first, last = int(match[1]), int(match[2])
        if last >= first:
            return f'{last - first + 1}\u00a0с.'
    return publication.pages or '—'


def coauthors(record, person):
    """Все авторы, кроме самого человека, в порядке авторов; внешние — как записаны."""
    names = [str(author) for author in record.authors.all() if author.person != person]
    return ', '.join(names) or '—'


def publication_imprint(publication):
    imprint = publication.imprint
    if publication.doi:
        imprint = f'{imprint}. — DOI: {publication.doi}' if imprint else f'DOI: {publication.doi}'
    return imprint or '—'


def ip_imprint(ip):
    document = 'Свидетельство' if ip.kind in ELECTRONIC_IP_KINDS else 'Патент'
    parts = [f'{document} № {ip.number}', f'дата регистрации {ip.registration_date:%d.%m.%Y}']
    if ip.holder:
        parts.append(f'правообладатель: {ip.holder}')
    return ', '.join(parts)


def ip_work_form(ip):
    return 'электронная' if ip.kind in ELECTRONIC_IP_KINDS else 'печатная'


def authors_prefetch(author_model):
    return Prefetch('authors', queryset=author_model.objects.select_related('teacher', 'student', 'adjunct'))


def build_form16(person, year_from=None, year_to=None, sections=None):
    """Отчёт по форме № 16 на человека: разделы со строками, нумерация сквозная.

    Внутри раздела — по году, затем по названию, от ранних к поздним (хронологически, как принято в форме).
    sections — ключи разделов для включения (None — все).
    """
    lookup = {f'authors__{key}': value for key, value in author_lookup(person).items()}
    publications = Publication.objects.filter(**lookup).prefetch_related(authors_prefetch(PublicationAuthor))
    ips = IntellectualProperty.objects.filter(**lookup).prefetch_related(authors_prefetch(IntellectualPropertyAuthor))
    if year_from:
        publications = publications.filter(year__gte=year_from)
        ips = ips.filter(registration_date__year__gte=year_from)
    if year_to:
        publications = publications.filter(year__lte=year_to)
        ips = ips.filter(registration_date__year__lte=year_to)
    publications = list(publications.order_by('year', 'title').distinct())

    result, number = [], 0
    for section_number, (key, title, kinds) in enumerate(SECTIONS, start=1):
        if sections is not None and key not in sections:
            continue
        section = Section(section_number, key, title)
        if kinds is None:
            for ip in ips.order_by('registration_date', 'title').distinct():
                number += 1
                section.rows.append(Row(
                    number, f'{ip.title} ({ip.get_kind_display()})', ip_work_form(ip), ip_imprint(ip), '—',
                    coauthors(ip, person),
                ))
        else:
            for publication in publications:
                if publication.kind not in kinds:
                    continue
                number += 1
                section.rows.append(Row(
                    number, f'{publication.title} ({publication.get_kind_display()})',
                    publication.get_work_form_display(), publication_imprint(publication), volume(publication),
                    coauthors(publication, person),
                ))
        result.append(section)
    return Form16(person, describe(person), year_from, year_to, result, timezone.localdate())
