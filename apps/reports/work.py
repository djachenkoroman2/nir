"""Отчёт о научной работе курсанта, адъюнкта или преподавателя за период.

Данные собираются только здесь (build_work_report) и раскладываются в layout.Document (work_document):
из него строятся страница и DOCX. Записи отбираются по правилам apps.reports.works.
"""
from collections import Counter
from dataclasses import dataclass

from django.db.models import Prefetch

from apps.adjuncts.models import Adjunct
from apps.conferences.models import ReportSpeaker
from apps.ip.models import IntellectualPropertyAuthor
from apps.publications.models import Publication, PublicationAuthor
from apps.staff.models import Teacher
from apps.students.models import AchievementBase, Student

from . import works
from .form16 import authors_prefetch, coauthors, describe, ip_imprint, publication_imprint, volume
from .layout import Document, Section, Table, date, dash, file_name, fit, signature

TITLES = {
    'teacher': 'Отчёт о научной работе преподавателя',
    'adjunct': 'Отчёт о научной работе адъюнкта',
    'student': 'Отчёт о научной работе курсанта',
}
ROLE = {'teacher': 'Преподаватель', 'adjunct': 'Адъюнкт', 'student': 'Курсант'}


@dataclass
class WorkReport:
    person: object
    period: works.Period
    publications: list
    talks: list
    intellectual_properties: list
    achievements: list  # курсанта или адъюнкта; у преподавателя — пусто
    memberships: list  # участие преподавателя в НИОКР за период
    schools: list  # научные школы, где преподаватель — ведущий учёный
    defenses: list  # защиты под руководством преподавателя за период

    @property
    def kind(self):
        return self.person._meta.model_name

    @property
    def is_teacher(self):
        return isinstance(self.person, Teacher)

    @property
    def is_empty(self):
        return not (self.publications or self.talks or self.intellectual_properties or self.achievements
                    or self.memberships or self.defenses)

    def totals(self):
        """Итоги: число работ по видам."""
        kinds = Counter(publication.kind for publication in self.publications)
        rows = [('Публикации — всего', len(self.publications))]
        rows += [(f'в т. ч. {label}', kinds[value]) for value, label in Publication.Kind.choices if kinds[value]]
        rows += [
            ('из них ВАК', sum(bool(p.vak) for p in self.publications)),
            ('из них РИНЦ', sum(p.rinc or p.rinc_core for p in self.publications)),
            ('из них Scopus', sum(p.scopus for p in self.publications)),
            ('из них Web of Science', sum(p.wos for p in self.publications)),
            ('Доклады на конференциях', len(self.talks)),
            ('Результаты интеллектуальной деятельности', len(self.intellectual_properties)),
        ]
        if self.is_teacher:
            rows += [('Участие в НИОКР', len(self.memberships)), ('Защиты под руководством', len(self.defenses))]
        else:
            levels = Counter(achievement.level for achievement in self.achievements)
            rows.append(('Достижения — всего', len(self.achievements)))
            rows += [(f'в т. ч. {label} уровень', levels[value]) for value, label in AchievementBase.Level.choices
                     if levels[value]]
        return rows


def build_work_report(person, period):
    publications = works.by_person(works.publications(period), 'authors', person)
    talks = works.by_person(works.talks(period), 'speakers', person)
    ips = works.by_person(works.intellectual_properties(period), 'authors', person)
    report = WorkReport(
        person, period,
        list(publications.prefetch_related(authors_prefetch(PublicationAuthor)).order_by('year', 'title')),
        list(talks.select_related('conference').prefetch_related(Prefetch(
            'speakers', queryset=ReportSpeaker.objects.select_related('teacher', 'student', 'adjunct'),
        )).order_by('conference__start_date', 'title')),
        list(ips.prefetch_related(authors_prefetch(IntellectualPropertyAuthor)).order_by('registration_date', 'title')),
        [], [], [], [],
    )
    if isinstance(person, Teacher):
        report.memberships = list(
            person.memberships.filter(project__in=works.projects(period)).select_related('project')
            .order_by('project__start_date', 'project__title')
        )
        report.schools = list(person.led_schools.all())
        report.defenses = list(works.defenses(period).filter(supervisor=person).select_related('school')
                               .order_by('defense_date'))
    else:
        achievements = works.student_achievements(period) if isinstance(person, Student) \
            else works.adjunct_achievements(period)
        report.achievements = list(achievements.filter(**{person._meta.model_name: person}).order_by('date', 'title'))
    return report


def person_info(person):
    """Сведения о человеке в шапке отчёта."""
    if isinstance(person, Teacher):
        return [('Должность, степень, звание', describe(person))]
    supervisor = person.supervisor.full_name if person.supervisor_id else '—'
    if isinstance(person, Adjunct):
        return [
            ('Тема диссертации', person.dissertation_topic),
            ('Научная специальность', person.specialty),
            ('Курс', course_label(person)),
            ('Научный руководитель', supervisor),
        ]
    return [
        ('Учебная группа, курс', f'{person.group}, {person.course} курс'),
        ('Статус', person.get_status_display()),
        ('Научный руководитель', supervisor),
    ]


def course_label(adjunct):
    if adjunct.course is None:
        return adjunct.get_status_display()
    return f'{adjunct.course}' + (' (срок обучения истёк)' if adjunct.term_expired else '')


def supervisor_signatures(person):
    lines = [f'{ROLE[person._meta.model_name]}  _______________  {signature(person)}']
    if isinstance(person, Teacher):
        lines.append('Заведующий кафедрой  _______________')
    elif person.supervisor_id:
        lines.append(f'Научный руководитель  _______________  {signature(person.supervisor)}')
    return lines


def work_document(report, author=''):
    person, width = report.person, 16.0
    publications = Table(['№', 'Наименование, вид', 'Выходные данные', 'Объём', 'Индексация', 'Соавторы'],
                         [1.0, *fit([3.9, 1.5, 2.3, 2.8], width - 1.0)], centered=(0, 3), header_size=9)
    for number, item in enumerate(report.publications, start=1):
        publications.add(f'{number}.', f'{item.title} ({item.get_kind_display()})', publication_imprint(item),
                         volume(item), dash(', '.join(item.indexing)), coauthors(item, person))

    talks = Table(['№', 'Тема доклада, форма', 'Конференция, уровень', 'Дата', 'Содокладчики'],
                  [1.0, *fit([4.6, 2.2, 3.2], width - 1.0)], centered=(0, 3))
    for number, talk in enumerate(report.talks, start=1):
        conference = talk.conference
        talks.add(f'{number}.', f'{talk.title} ({talk.get_form_display()})',
                  f'{conference.title} ({conference.get_level_display()})', date(conference.start_date),
                  dash(', '.join(str(s) for s in talk.speakers.all() if s.person != person)))

    ips = Table(['№', 'Наименование, вид', 'Документ', 'Соавторы'], [1.0, *fit([6.0, 3.2], width - 1.0)],
                centered=(0,))
    for number, item in enumerate(report.intellectual_properties, start=1):
        ips.add(f'{number}.', f'{item.title} ({item.get_kind_display()})', ip_imprint(item), coauthors(item, person))

    sections = [
        Section('Публикации', publications),
        Section('Доклады на конференциях', talks),
        Section('Результаты интеллектуальной деятельности', ips),
    ]
    if report.is_teacher:
        projects = Table(['№', 'НИОКР', 'Роль', 'Сроки', 'Статус'], [1.0, *fit([2.6, 3.4, 2.6], width - 1.0)],
                         centered=(0, 3))
        for number, membership in enumerate(report.memberships, start=1):
            project = membership.project
            projects.add(f'{number}.', project.title, membership.get_role_display(),
                         f'{date(project.start_date)} — {date(project.end_date) if project.end_date else "н. в."}',
                         project.get_status_display())
        defenses = Table(['№', 'Защитившийся, тема', 'Вид', 'Дата', 'Научная школа'],
                         [1.0, *fit([2.6, 2.2, 4.2], width - 1.0)], centered=(0, 3))
        for number, defense in enumerate(report.defenses, start=1):
            defenses.add(f'{number}.', f'{defense.full_name}. {defense.title}', defense.get_kind_display(),
                         date(defense.defense_date), defense.school.name)
        sections += [
            Section('Участие в НИОКР', projects),
            Section('Защиты диссертаций под научным руководством', defenses),
            Section('Научные школы (ведущий учёный)', entries=[school.name for school in report.schools]),
        ]
    else:
        achievements = Table(['№', 'Мероприятие или награда', 'Вид', 'Уровень', 'Результат', 'Дата'],
                             [1.0, *fit([2.6, 2.4, 3.0, 2.2], width - 1.0)], centered=(0, 5))
        for number, item in enumerate(report.achievements, start=1):
            achievements.add(f'{number}.', item.title, item.get_kind_display(), item.get_level_display(),
                             item.result, date(item.date))
        sections.append(Section('Достижения', achievements))

    totals = Table(['Показатель', 'Количество'], fit([3.0], width), centered=(1,))
    for label, value in report.totals():
        totals.add(label, value)
    sections.append(Section('Итоги', totals))

    return Document(
        TITLES[report.kind], [person.full_name, f'Период: {report.period.label}'], person_info(person), sections,
        signatures=supervisor_signatures(person), author=author,
    )


def work_filenames(report):
    person = report.person
    return (f'Научная_работа_{file_name(person)}_{report.period.slug}.docx',
            f'work_{report.kind}_{person.pk}_{report.period.slug}.docx')
