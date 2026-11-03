"""Отчёт о НИР кафедры: консолидированный (показатели) и подробный (перечни записей) вид.

Данные собираются только здесь (build_department_report) и раскладываются в layout.Document (department_document).
Оба вида берут записи одной функцией раздела (Spec.records) по правилам apps.reports.works, поэтому строка
«Итого» подробного вида совпадает с показателем «всего» консолидированного.

Правила подсчёта:
- в итогах кафедры запись считается один раз, сколько бы людей кафедры ни было среди её авторов;
- в таблице по людям запись засчитывается каждому автору, поэтому сумма по людям может быть больше итога;
- записи только с внешними авторами в отчёт не входят;
- категории людей отбирают публикации, РИД, доклады (есть автор выбранной категории), достижения, кадровый состав
  и таблицу по людям; НИОКР, договоры, защиты и научные школы — показатели кафедры в целом.
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone

from apps.adjuncts.models import Adjunct
from apps.conferences.models import Conference, Report, ReportSpeaker
from apps.ip.models import IntellectualProperty, IntellectualPropertyAuthor
from apps.publications.models import Publication, PublicationAuthor
from apps.research.models import Participant, ResearchProject
from apps.schools.indicators import INDICATORS, annotate_indicators, indicator_totals
from apps.schools.models import DissertationDefense, ScientificSchool
from apps.staff.models import Teacher
from apps.students.models import AchievementBase, Student

from . import works
from .form16 import authors_prefetch, ip_imprint, publication_imprint
from .layout import Document, Section, Table, Text, date, fit
from .works import ADJUNCTS, ALL_PEOPLE, PEOPLE_CATEGORIES, STUDENTS, TEACHERS

SUMMARY, DETAILED = 'summary', 'detailed'
VIEWS = [(SUMMARY, 'Консолидированный'), (DETAILED, 'Подробный')]
VIEW_TITLES = {SUMMARY: 'консолидированный', DETAILED: 'подробный'}

STAFF, PUBLICATIONS, IPS, TALKS, PROJECTS, CONTRACTS, DEFENSES, STUDENT_ACHIEVEMENTS, ADJUNCT_ACHIEVEMENTS, SCHOOLS, PEOPLE = (
    'staff', 'publications', 'ips', 'talks', 'projects', 'contracts', 'defenses', 'student_achievements',
    'adjunct_achievements', 'schools', 'people',
)
SECTION_CHOICES = [
    (STAFF, 'Кадровый состав'),
    (PUBLICATIONS, 'Публикации'),
    (IPS, 'Результаты интеллектуальной деятельности'),
    (TALKS, 'Доклады на конференциях'),
    (PROJECTS, 'НИОКР'),
    (CONTRACTS, 'Договоры о научно-техническом сотрудничестве'),
    (DEFENSES, 'Защиты диссертаций'),
    (STUDENT_ACHIEVEMENTS, 'Достижения курсантов'),
    (ADJUNCT_ACHIEVEMENTS, 'Достижения адъюнктов'),
    (SCHOOLS, 'Научные школы'),
    (PEOPLE, 'Показатели по людям (консолидированный вид)'),
]
SECTION_TITLES = dict(SECTION_CHOICES)
CATEGORY_TITLES = dict(PEOPLE_CATEGORIES)
# Кто сейчас работает (обучается): остальные попадают в кадровый состав и таблицу по людям только по флажку.
ACTIVE = {
    TEACHERS: Q(is_active=True),
    ADJUNCTS: ~Q(status__in=Adjunct.FINISHED_STATUSES),
    STUDENTS: Q(status=Student.Status.STUDYING),
}
PEOPLE_MODELS = {TEACHERS: Teacher, ADJUNCTS: Adjunct, STUDENTS: Student}


@dataclass(frozen=True)
class Metric:
    """Показатель раздела: число записей, подходящих под condition (или сумма поля)."""

    label: str
    condition: object = None  # Q или Exists; None — все записи раздела
    field: str = 'pk'
    function: type = Count

    def expression(self, extra=None):
        condition = self.condition
        if extra is not None:
            condition = extra if condition is None else Q(condition) & extra
        if self.function is Sum:
            return Sum(self.field, filter=condition)
        return Count(self.field, filter=condition, distinct=True)


@dataclass(frozen=True)
class Spec:
    """Раздел с записями: как их отобрать, отнести к году, посчитать и перечислить."""

    key: str
    records: Callable  # (period, categories) -> QuerySet
    in_year: Callable  # (year) -> Q: запись относится к году
    metrics: list  # первый показатель — «всего»: он совпадает с числом записей подробного вида
    entries: Callable  # (queryset) -> list[Text]
    category: str | None = None  # раздел только при выбранной категории людей


# --- описание записей для подробного вида ---

def names(authors):
    """Авторы через запятую, люди кафедры — полужирным; в конце — разделитель перед описанием записи."""
    parts = []
    for index, author in enumerate(authors):
        if index:
            parts.append((', ', False))
        parts.append((str(author), author.person is not None))
    # «Иванов И. И.» уже кончается точкой — вторая не нужна.
    parts.append((' ' if parts and parts[-1][0].endswith('.') else '. ', False))
    return parts


def publication_entries(queryset):
    kinds = [value for value, _ in Publication.Kind.choices]
    items = sorted(queryset.prefetch_related(authors_prefetch(PublicationAuthor)),
                   key=lambda p: (kinds.index(p.kind), p.year, p.title))
    result = []
    for item in items:
        text = f'{item.title} ({item.get_kind_display()}) // {publication_imprint(item)}'
        if item.indexing:
            text += f'. Индексация: {", ".join(item.indexing)}'
        result.append(Text([*names(item.authors.all()), (text + '.', False)]))
    return result


def ip_entries(queryset):
    items = queryset.prefetch_related(authors_prefetch(IntellectualPropertyAuthor)).order_by('registration_date', 'title')
    return [Text([*names(item.authors.all()), (f'{item.title} ({item.get_kind_display()}). {ip_imprint(item)}.',
                                               False)]) for item in items]


def talk_entries(queryset):
    speakers = Prefetch('speakers', queryset=ReportSpeaker.objects.select_related('teacher', 'student', 'adjunct'))
    items = queryset.select_related('conference').prefetch_related(speakers).order_by('conference__start_date', 'title')
    result = []
    for talk in items:
        conference = talk.conference
        dates = date(conference.start_date)
        if conference.end_date and conference.end_date != conference.start_date:
            dates += f' — {date(conference.end_date)}'
        place = f', {conference.location}' if conference.location else ''
        result.append(Text([*names(talk.speakers.all()), (
            f'{talk.title} ({talk.get_form_display()} доклад) // {conference.title} '
            f'({conference.get_level_display()}){place}, {dates}.', False)]))
    return result


def project_entries(queryset):
    members = Prefetch('memberships', queryset=Participant.objects.select_related('teacher'))
    result = []
    for project in queryset.prefetch_related(members).order_by('start_date', 'title'):
        memberships = list(project.memberships.all())
        leaders = [m.teacher.short_name for m in memberships if m.role == Participant.Role.LEADER]
        others = [m.teacher.short_name for m in memberships if m.role != Participant.Role.LEADER]
        end = date(project.end_date) if project.end_date else 'н. в.'
        text = f'{project.title}. Сроки: {date(project.start_date)} — {end}. Статус: {project.get_status_display()}.'
        if leaders:
            text += f' Руководитель: {", ".join(leaders)}.'
        if others:
            text += f' Исполнители: {", ".join(others)}.'
        result.append(Text([(text, False)]))
    return result


def contract_entries(queryset):
    result = []
    for contract in queryset.order_by('start_date', 'title'):
        number = f' № {contract.number}' if contract.number else ''
        end = date(contract.end_date) if contract.end_date else 'бессрочно'
        text = (f'{contract.title}{number}. Организация: {contract.organization}. '
                f'Предмет: {contract.subject}. Срок действия: {date(contract.start_date)} — {end}.')
        result.append(Text([(text, False)]))
    return result


def defense_entries(queryset):
    result = []
    for defense in queryset.select_related('school', 'supervisor').order_by('defense_date', 'full_name'):
        text = (f' — {defense.get_kind_display()} диссертация «{defense.title}», {date(defense.defense_date)}, '
                f'научная школа «{defense.school.name}»')
        if defense.supervisor_id:
            text += f', научный руководитель (консультант) {defense.supervisor.short_name}'
        is_ours = defense.teacher_id is not None or defense.adjunct_id is not None
        result.append(Text([(defense.full_name, is_ours), (text + '.', False)]))
    return result


def achievement_entries(owner):
    def entries(queryset):
        result = []
        for item in queryset.select_related(owner).order_by('date', 'title'):
            person = getattr(item, owner)
            text = (f' — {item.title}: {item.result} ({item.get_kind_display()}, {item.get_level_display()} уровень), '
                    f'{date(item.date)}.')
            if item.document:
                text += f' Документ: {item.document}.'
            result.append(Text([(person.full_name, True), (text, False)]))
        return result
    return entries


# --- разделы ---

def kind_metrics(choices, field_name, prefix):
    return [Metric(f'{prefix}: {label}', Q(**{field_name: value})) for value, label in choices if value]


P = Publication
SPECS = [
    Spec(
        PUBLICATIONS,
        lambda period, categories: works.by_department(works.publications(period), 'authors', categories),
        lambda year: Q(year=year),
        [
            Metric('Публикации — всего'),
            *kind_metrics(P.Kind.choices, 'kind', 'вид'),
            Metric('индексация: ВАК (всего)', ~Q(vak='')),
            *kind_metrics(P.VakCategory.choices, 'vak', 'индексация: ВАК, категория'),
            Metric('индексация: РИНЦ', Q(rinc=True) | Q(rinc_core=True)),
            Metric('индексация: ядро РИНЦ', Q(rinc_core=True)),
            Metric('индексация: Scopus', Q(scopus=True)),
            Metric('индексация: Web of Science', Q(wos=True)),
            *kind_metrics(P.Quartile.choices, 'quartile', 'квартиль'),
            *kind_metrics(P.WorkForm.choices, 'work_form', 'форма работы'),
            Metric('объём, п. л. (сумма, где указан)', field='print_sheets', function=Sum),
            Metric('с участием курсантов', works.authors_exist(P, 'authors', Q(student__isnull=False))),
            Metric('с участием адъюнктов', works.authors_exist(P, 'authors', Q(adjunct__isnull=False))),
        ],
        publication_entries,
    ),
    Spec(
        IPS,
        lambda period, categories: works.by_department(works.intellectual_properties(period), 'authors', categories),
        lambda year: Q(registration_date__year=year),
        [Metric('РИД — всего'), *kind_metrics(IntellectualProperty.Kind.choices, 'kind', 'вид')],
        ip_entries,
    ),
    Spec(
        TALKS,
        lambda period, categories: works.by_department(works.talks(period), 'speakers', categories),
        lambda year: Q(conference__start_date__year=year),
        [
            Metric('Доклады — всего'),
            *kind_metrics(Conference.Level.choices, 'conference__level', 'уровень конференции'),
            *kind_metrics(Report.Form.choices, 'form', 'форма доклада'),
            Metric('конференций с докладами кафедры', field='conference'),
        ],
        talk_entries,
    ),
    Spec(
        PROJECTS,
        lambda period, categories: works.projects(period),
        lambda year: works.project_overlaps(year, year),
        [
            Metric('НИОКР — всего (выполнялись в периоде)'),
            *kind_metrics(ResearchProject.Status.choices, 'status', 'статус на сегодня'),
            Metric('участников (преподавателей кафедры)', field='memberships__teacher'),
        ],
        project_entries,
    ),
    Spec(
        CONTRACTS,
        lambda period, categories: works.contracts(period),
        lambda year: works.contract_overlaps(year, year),
        [
            Metric('Договоры — всего'),
            Metric('Из них бессрочные', Q(end_date__isnull=True)),
        ],
        contract_entries,
    ),
    Spec(
        DEFENSES,
        lambda period, categories: works.defenses(period),
        lambda year: Q(defense_date__year=year),
        [Metric('Защиты диссертаций — всего'), *kind_metrics(DissertationDefense.Kind.choices, 'kind', 'вид')],
        defense_entries,
    ),
    Spec(
        STUDENT_ACHIEVEMENTS,
        lambda period, categories: works.student_achievements(period),
        lambda year: Q(date__year=year),
        [
            Metric('Достижения курсантов — всего'),
            *kind_metrics(AchievementBase.Level.choices, 'level', 'уровень'),
            *kind_metrics(AchievementBase.Kind.choices, 'kind', 'вид'),
        ],
        achievement_entries('student'),
        category=STUDENTS,
    ),
    Spec(
        ADJUNCT_ACHIEVEMENTS,
        lambda period, categories: works.adjunct_achievements(period),
        lambda year: Q(date__year=year),
        [
            Metric('Достижения адъюнктов — всего'),
            *kind_metrics(AchievementBase.Level.choices, 'level', 'уровень'),
            *kind_metrics(AchievementBase.Kind.choices, 'kind', 'вид'),
        ],
        achievement_entries('adjunct'),
        category=ADJUNCTS,
    ),
]
SPECS_BY_KEY = {spec.key: spec for spec in SPECS}


# --- результат ---

@dataclass
class MetricRow:
    label: str
    by_year: list  # значения по годам периода (пусто, если период — один год)
    total: object


@dataclass
class Block:
    """Раздел с записями: показатели (консолидированный вид) или перечень (подробный)."""

    key: str
    title: str
    metrics: list = field(default_factory=list)
    entries: list = field(default_factory=list)

    @property
    def total(self):
        return self.metrics[0].total if self.metrics else len(self.entries)


@dataclass
class PersonRow:
    person: object
    values: list  # по PEOPLE_COLUMNS; None — показатель к категории не относится


@dataclass
class PeopleBlock:
    key: str
    title: str
    rows: list
    totals: list  # итог категории без повторов


@dataclass
class DepartmentReport:
    period: works.Period
    view: str
    sections: list
    categories: list
    include_inactive: bool
    staff: list | None = None  # кадровый состав: (подпись, значение, итоговая строка)
    staff_people: list | None = None  # подробный вид: (категория, [строки о людях])
    blocks: list = field(default_factory=list)
    schools: list | None = None
    school_totals: dict | None = None
    people: list | None = None
    people_totals: list | None = None
    created: object = field(default_factory=timezone.now)

    @property
    def by_year(self):
        return len(self.period.years) > 1


def summarize(spec, period, categories):
    """Показатели раздела одним агрегирующим запросом: по годам (если их несколько) и за весь период."""
    aggregates = {}
    by_year = len(period.years) > 1
    for index, metric in enumerate(spec.metrics):
        aggregates[f'm{index}'] = metric.expression()
        if by_year:
            for year in period.years:
                aggregates[f'm{index}_{year}'] = metric.expression(spec.in_year(year))
    values = spec.records(period, categories).aggregate(**aggregates)
    return [
        MetricRow(metric.label, [number(values[f'm{index}_{year}']) for year in period.years] if by_year else [],
                  number(values[f'm{index}']))
        for index, metric in enumerate(spec.metrics)
    ]


def number(value):
    """Число для таблицы: сумма объёма — десятичная с запятой, пустая сумма — 0."""
    if value is None:
        return 0
    if hasattr(value, 'normalize'):
        return f'{value.normalize():f}'.replace('.', ',')
    return value


def staff_summary(categories):
    """Кадровый состав на дату формирования: работающие преподаватели, обучающиеся адъюнкты и курсанты."""
    rows = []
    if TEACHERS in categories:
        T = Teacher
        counts = T.objects.filter(ACTIVE[TEACHERS]).aggregate(
            total=Count('pk'),
            **{f'p_{value}': Count('pk', filter=Q(position=value)) for value, _ in T.Position.choices},
            candidates=Count('pk', filter=Q(degree=T.Degree.CANDIDATE)),
            doctors=Count('pk', filter=Q(degree=T.Degree.DOCTOR)),
            docents=Count('pk', filter=Q(academic_title=T.AcademicTitle.DOCENT)),
            professors=Count('pk', filter=Q(academic_title=T.AcademicTitle.PROFESSOR)),
        )
        rows.append(('Преподаватели (работают на кафедре) — всего', counts['total'], True))
        rows += [(f'должность: {label}', counts[f'p_{value}'], False) for value, label in T.Position.choices]
        rows += [('кандидаты наук', counts['candidates'], False), ('доктора наук', counts['doctors'], False),
                 ('учёное звание доцента', counts['docents'], False),
                 ('учёное звание профессора', counts['professors'], False)]
    if ADJUNCTS in categories:
        adjuncts = list(Adjunct.objects.filter(ACTIVE[ADJUNCTS]).only('admission_year', 'status', 'study_years'))
        courses = Counter(adjunct.course for adjunct in adjuncts)
        rows.append(('Адъюнкты (обучаются) — всего', len(adjuncts), True))
        rows += [(f'{course} курс', courses[course], False) for course in sorted(courses)]
        rows.append(('в академическом отпуске',
                     sum(adjunct.status == Adjunct.Status.ACADEMIC_LEAVE for adjunct in adjuncts), False))
    if STUDENTS in categories:
        courses = dict(Student.objects.filter(ACTIVE[STUDENTS]).values_list('course').annotate(n=Count('pk')))
        rows.append(('Курсанты, занимающиеся НИР (обучаются) — всего', sum(courses.values()), True))
        rows += [(f'{course} курс', courses[course], False) for course in sorted(courses)]
    return rows


def staff_details(categories):
    """Подробный кадровый состав: те же люди, что в консолидированном виде."""
    result = []
    if TEACHERS in categories:
        result.append((CATEGORY_TITLES[TEACHERS], [
            f'{t.full_name} — {t.get_position_display()}'
            + ''.join(f', {label}' for label in (t.get_degree_display(), t.get_academic_title_display())
                      if label != 'нет')
            for t in Teacher.objects.filter(ACTIVE[TEACHERS])
        ]))
    if ADJUNCTS in categories:
        result.append((CATEGORY_TITLES[ADJUNCTS], [
            f'{a.full_name} — {a.course} курс, {a.get_status_display()}; руководитель {a.supervisor.short_name}'
            for a in Adjunct.objects.filter(ACTIVE[ADJUNCTS]).select_related('supervisor')
        ]))
    if STUDENTS in categories:
        result.append((CATEGORY_TITLES[STUDENTS], [
            f'{s.full_name} — группа {s.group}, {s.course} курс'
            + (f'; руководитель {s.supervisor.short_name}' if s.supervisor_id else '')
            for s in Student.objects.filter(ACTIVE[STUDENTS]).select_related('supervisor')
        ]))
    return result


PEOPLE_COLUMNS = ['Публикаций', 'из них ВАК', 'Scopus', 'WoS', 'РИД', 'Докладов', 'НИОКР', 'Достижений']


def achievements_of(key):
    return {STUDENTS: works.student_achievements, ADJUNCTS: works.adjunct_achievements}.get(key)


def people_rows(key, period, include_inactive):
    """Люди категории с показателями: каждому автору засчитываются все его записи (один запрос на категорию)."""
    publications = works.publications(period)
    annotations = {
        'n0': works.count_for(publications, f'authors__{key}'),
        'n1': works.count_for(publications.exclude(vak=''), f'authors__{key}'),
        'n2': works.count_for(publications.filter(scopus=True), f'authors__{key}'),
        'n3': works.count_for(publications.filter(wos=True), f'authors__{key}'),
        'n4': works.count_for(works.intellectual_properties(period), f'authors__{key}'),
        'n5': works.count_for(works.talks(period), f'speakers__{key}'),
    }
    if key == TEACHERS:
        annotations['n6'] = works.count_for(works.projects(period), 'memberships__teacher')
    else:
        annotations['n7'] = works.count_for(achievements_of(key)(period), key)
    people = PEOPLE_MODELS[key].objects.all()
    if not include_inactive:
        people = people.filter(ACTIVE[key])
    people = people.annotate(**annotations).order_by('last_name', 'first_name', 'middle_name')
    return [PersonRow(person, [getattr(person, f'n{index}', None) for index in range(len(PEOPLE_COLUMNS))])
            for person in people]


def people_totals(period, categories, whole_department=False):
    """Итог без повторов: запись с несколькими авторами выбранных категорий считается один раз.

    whole_department — строка «по кафедре»: НИОКР — все работы периода (как в консолидированном виде),
    иначе — работы с участием преподавателей кафедры.
    """
    publications = works.by_department(works.publications(period), 'authors', categories).aggregate(
        total=Count('pk'), vak=Count('pk', filter=~Q(vak='')), scopus=Count('pk', filter=Q(scopus=True)),
        wos=Count('pk', filter=Q(wos=True)),
    )
    values = [
        publications['total'], publications['vak'], publications['scopus'], publications['wos'],
        works.by_department(works.intellectual_properties(period), 'authors', categories).count(),
        works.by_department(works.talks(period), 'speakers', categories).count(),
        None, None,
    ]
    if whole_department:
        values[6] = works.projects(period).count()
    elif TEACHERS in categories:
        values[6] = works.projects(period).filter(memberships__isnull=False).distinct().count()
    achievements = [achievements_of(key)(period).count() for key in (STUDENTS, ADJUNCTS) if key in categories]
    if achievements:
        values[7] = sum(achievements)
    return values


def build_department_report(period, view=SUMMARY, sections=None, categories=None, include_inactive=False):
    sections = sections or [key for key, _ in SECTION_CHOICES]
    categories = [key for key in ALL_PEOPLE if key in (categories or ALL_PEOPLE)]
    report = DepartmentReport(period, view, sections, categories, include_inactive)
    if STAFF in sections:
        if view == SUMMARY:
            report.staff = staff_summary(categories)
        else:
            report.staff_people = staff_details(categories)
    for spec in SPECS:
        if spec.key not in sections or (spec.category and spec.category not in categories):
            continue
        block = Block(spec.key, SECTION_TITLES[spec.key])
        if view == SUMMARY:
            block.metrics = summarize(spec, period, categories)
        else:
            block.entries = spec.entries(spec.records(period, categories))
        report.blocks.append(block)
    if SCHOOLS in sections:
        schools = ScientificSchool.objects.filter(is_active=True)
        report.schools = list(annotate_indicators(schools, period.as_tuple()).prefetch_related('leaders'))
        if view == SUMMARY:
            report.school_totals = indicator_totals(schools, period.as_tuple())
    if PEOPLE in sections and view == SUMMARY:
        report.people = [
            PeopleBlock(key, CATEGORY_TITLES[key], people_rows(key, period, include_inactive),
                        people_totals(period, [key]))
            for key in categories
        ]
        report.people_totals = people_totals(period, categories, whole_department=True)
    return report


# --- вид документа ---

NOTES = [
    'В итогах кафедры запись считается один раз, сколько бы людей кафедры ни было среди её авторов. '
    'В таблице по людям запись засчитывается каждому автору, поэтому сумма строк может быть больше итога.',
    'Публикация относится к периоду по году издания, доклад — по дате начала конференции, РИД — по дате регистрации, '
    'защита — по дате защиты, достижение — по дате. НИОКР и договоры входят в каждый год, который пересекается '
    'со сроком работы или действия, поэтому их сумма по годам может быть больше итога за период.',
    'Записи только с внешними авторами в отчёт не входят. Категории людей отбирают публикации, РИД и доклады '
    '(есть автор выбранной категории), достижения, кадровый состав и таблицу по людям; НИОКР, договоры, защиты '
    'и научные школы — показатели кафедры в целом.',
]


def cell(value):
    return '—' if value is None else str(value)


def summary_sections(report):
    sections = []
    width = 25.7
    if report.staff is not None:
        staff = Table(['Показатель', 'Значение'], fit([3.0], width), centered=(1,))
        for label, value, is_total in report.staff:
            (staff.total if is_total else staff.add)(label, value)
        sections.append(Section(f'Кадровый состав на {date(timezone.localdate())}', staff))
    if report.blocks:
        years = report.period.years if report.by_year else []
        year_width = min(2.0, 14.0 / max(len(years), 1))
        table = Table(['Показатель', *map(str, years), 'Всего за период'],
                      fit([*([year_width] * len(years)), 2.6], width),
                      centered=tuple(range(1, len(years) + 2)))
        for block in report.blocks:
            table.group(block.title)
            for index, row in enumerate(block.metrics):
                (table.total if index == 0 else table.add)(row.label, *row.by_year, row.total)
        sections.append(Section('Показатели научно-исследовательской работы', table))
    if report.schools is not None:
        sections.append(Section('Научные школы (действующие)', schools_table(report, width)))
    if report.people is not None:
        sections.append(Section('Показатели по людям', people_table(report, width),
                                note='Строки «Итого» — без повторов: совместная запись считается один раз; '
                                     'сумма строк по людям может быть больше итога.'))
    return sections


def schools_table(report, width):
    labels = [indicator.label for indicator in INDICATORS]
    table = Table(['Научная школа', *(label.replace(' ', '\n') for label in labels)],
                  fit([2.7] * len(labels), width), centered=tuple(range(1, len(labels) + 1)),
                  empty='действующих научных школ нет', header_size=9)
    for school in report.schools:
        table.add(school.name, *(getattr(school, indicator.key) for indicator in INDICATORS))
    if report.schools:
        table.total('Итого (без повторов)', *(report.school_totals[indicator.key] for indicator in INDICATORS))
    return table


def people_table(report, width):
    table = Table(['ФИО', *(title.replace(' ', '\n') for title in PEOPLE_COLUMNS)],
                  fit([2.4] * len(PEOPLE_COLUMNS), width), centered=tuple(range(1, len(PEOPLE_COLUMNS) + 1)),
                  header_size=9)
    for block in report.people:
        table.group(block.title)
        for row in block.rows:
            table.add(row.person.full_name, *map(cell, row.values))
        table.total(f'Итого: {block.title.lower()}', *map(cell, block.totals))
    table.total('Итого по кафедре', *map(cell, report.people_totals))
    return table


def detailed_sections(report):
    sections = []
    if report.staff_people is not None:
        table = Table(['ФИО и сведения'], [16.0])
        count = 0
        for title, people in report.staff_people:
            table.group(f'{title} ({len(people)})')
            for line in people:
                table.add(line)
            count += len(people)
        sections.append(Section(f'Кадровый состав на {date(timezone.localdate())}', table,
                                total=f'Итого: {count} чел.'))
    for block in report.blocks:
        sections.append(Section(block.title, entries=block.entries, total=f'Итого: {len(block.entries)}'))
    if report.schools is not None:
        entries = [
            Text([(school.name, True), (f'. Ведущие учёные: {", ".join(t.short_name for t in school.leaders.all())}.',
                                        False)])
            for school in report.schools
        ]
        sections.append(Section('Научные школы (действующие)', entries=entries, total=f'Итого: {len(entries)}'))
    return sections


def department_document(report, author=''):
    summary = report.view == SUMMARY
    sections = summary_sections(report) if summary else detailed_sections(report)
    for number, section in enumerate(sections, start=1):
        section.title = f'{number}. {section.title}'
    chosen = [SECTION_TITLES[key] for key, _ in SECTION_CHOICES if key in report.sections
              and (summary or key != PEOPLE)]
    subtitle = [
        f'Вид отчёта: {VIEW_TITLES[report.view]}',
        f'Период: {report.period.label}',
        f'Разделы: {", ".join(chosen)}',
        f'Категории людей: {", ".join(CATEGORY_TITLES[key] for key in report.categories).lower()}'
        + ('' if report.include_inactive else ' (в таблице по людям — без неработающих, выпущенных и отчисленных)'
           if summary and report.people is not None else ''),
    ]
    return Document(
        'Отчёт о научно-исследовательской работе кафедры', subtitle, sections=sections, notes=NOTES,
        signatures=['Заведующий кафедрой  _______________', 'Учёный секретарь  _______________'],
        landscape=summary, author=author, created=report.created,
    )


def department_filenames(report):
    years = f'{report.period.year_from}-{report.period.year_to}'
    kind = 'сводный' if report.view == SUMMARY else 'подробный'
    fallback = 'summary' if report.view == SUMMARY else 'detailed'
    return f'НИР_кафедры_{kind}_{years}.docx', f'department_{fallback}_{years}.docx'
