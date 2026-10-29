"""Карточки для печати: карточка человека кафедры и карточка учётной записи.

Данные карточки собираются только здесь и раскладываются в layout.Document: из него строятся страница для печати
и DOCX. Сводка трудов — за всё время, по тем же правилам, что отчёты (apps.reports.works).
Контакты (телефон, e-mail) выводятся: печатать карточку могут только те, кто видит её страницу с контактами.
Логин учётной записи — только редактору и самому человеку: на странице карточки руководитель его не видит.
"""
from django.db.models import Count, Q
from django.utils import timezone

from apps.adjuncts.models import Adjunct, PlanStage
from apps.conferences.models import Report
from apps.core.permissions import get_person
from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication
from apps.staff.models import Teacher, author_lookup
from apps.students.models import AchievementBase, Student

from .activity import ADJUNCTS, ADMINS, EDITORS, OTHERS, STUDENTS, TEACHERS, user_category
from .form16 import describe
from .layout import Document, Section, Table, date, dash, file_name, fit
from .work import course_label

CARD_TITLES = {
    'teacher': 'Карточка преподавателя',
    'adjunct': 'Карточка адъюнкта',
    'student': 'Карточка курсанта',
}
# Роль в карточке учётной записи — по той же категории, что в отчёте об активности (apps.reports.activity).
ROLE_TITLES = {
    ADMINS: 'администратор (суперпользователь)',
    EDITORS: 'редактор',
    TEACHERS: 'преподаватель',
    ADJUNCTS: 'адъюнкт',
    STUDENTS: 'курсант',
    OTHERS: 'пользователь без карточки человека',
}
PERSON_KINDS_GENITIVE = {'teacher': 'преподавателя', 'adjunct': 'адъюнкта', 'student': 'курсанта'}


def works_summary(person):
    """Сводка трудов человека за всё время: публикации по видам и индексации, доклады, РИД."""
    [(field, _)] = author_lookup(person).items()
    stats = Publication.objects.filter(**{f'authors__{field}': person}).aggregate(
        total=Count('pk', distinct=True),
        vak=Count('pk', filter=~Q(vak=''), distinct=True),
        rinc=Count('pk', filter=Q(rinc=True) | Q(rinc_core=True), distinct=True),
        scopus=Count('pk', filter=Q(scopus=True), distinct=True),
        wos=Count('pk', filter=Q(wos=True), distinct=True),
        **{f'k_{value}': Count('pk', filter=Q(kind=value), distinct=True) for value, _ in Publication.Kind.choices},
    )
    rows = [('Публикации — всего', stats['total'])]
    rows += [(f'вид: {label}', stats[f'k_{value}']) for value, label in Publication.Kind.choices
             if stats[f'k_{value}']]
    rows += [('из них ВАК', stats['vak']), ('из них РИНЦ', stats['rinc']), ('из них Scopus', stats['scopus']),
             ('из них Web of Science', stats['wos']),
             ('Доклады на конференциях', Report.objects.filter(**{f'speakers__{field}': person}).distinct().count()),
             ('Результаты интеллектуальной деятельности',
              IntellectualProperty.objects.filter(**{f'authors__{field}': person}).distinct().count())]
    return rows


def summary_section(rows, title='Сводка трудов (за всё время)'):
    table = Table(['Показатель', 'Количество'], fit([3.0], 16.0), centered=(1,))
    for label, value in rows:
        table.add(label, value)
    return Section(title, table)


def achievements_rows(person):
    levels = dict(person.achievements.values_list('level').annotate(n=Count('pk')))
    rows = [('Достижения — всего', sum(levels.values()))]
    rows += [(f'{label} уровень', levels[value]) for value, label in AchievementBase.Level.choices if value in levels]
    return rows


def account_line(person, show_account):
    if not show_account:
        return []
    return [('Учётная запись (логин)', person.user.username if person.user_id else 'не привязана')]


def teacher_card(teacher, show_account):
    info = [
        ('Должность', teacher.get_position_display()),
        ('Учёная степень', teacher.get_degree_display()),
        ('Учёное звание', teacher.get_academic_title_display()),
        ('Работает на кафедре', 'да' if teacher.is_active else 'нет'),
        ('E-mail', dash(teacher.email)),
        ('Телефон', dash(teacher.phone)),
        ('Ведущий учёный научных школ', dash(', '.join(school.name for school in teacher.led_schools.all()))),
        *account_line(teacher, show_account),
    ]
    projects = Table(['НИОКР', 'Роль', 'Сроки', 'Статус'], fit([2.4, 3.6, 2.6], 16.0), centered=(2,))
    for membership in teacher.memberships.select_related('project').order_by('-project__start_date'):
        project = membership.project
        end = date(project.end_date) if project.end_date else 'н. в.'
        projects.add(project.title, membership.get_role_display(), f'{date(project.start_date)} — {end}',
                     project.get_status_display())
    supervised = Table(['ФИО', 'Категория', 'Статус'], fit([5.0, 3.0], 16.0))
    for adjunct in teacher.supervised_adjuncts.order_by(*Adjunct._meta.ordering):
        supervised.add(adjunct.full_name, f'адъюнкт, курс: {course_label(adjunct)}', adjunct.get_status_display())
    for student in teacher.supervised_students.order_by(*Student._meta.ordering):
        supervised.add(student.full_name, f'курсант, группа {student.group}, {student.course} курс',
                       student.get_status_display())
    return info, [
        Section('Участие в НИОКР', projects),
        Section('Научное руководство курсантами и адъюнктами', supervised),
        summary_section(works_summary(teacher)),
    ]


def adjunct_card(adjunct, show_account):
    stages = list(adjunct.plan_stages.all())
    done = sum(stage.status == PlanStage.Status.DONE for stage in stages)
    info = [
        ('Тема диссертации', adjunct.dissertation_topic),
        ('Научная специальность', adjunct.specialty),
        ('Год поступления', adjunct.admission_year),
        ('Курс', course_label(adjunct)),
        ('Форма обучения, срок', f'{adjunct.get_study_form_display()}, {adjunct.study_years} г.'),
        ('Статус', adjunct.get_status_display()),
        ('Планируемый год защиты', dash(adjunct.planned_defense_year)),
        ('Научный руководитель', adjunct.supervisor.full_name),
        ('Научная школа', adjunct.school.name if adjunct.school_id else '—'),
        *[('Защита диссертации', f'{defense.get_kind_display()}, {date(defense.defense_date)}')
          for defense in adjunct.defenses.all()],
        ('E-mail', dash(adjunct.email)),
        ('Телефон', dash(adjunct.phone)),
        *account_line(adjunct, show_account),
    ]
    plan = [('Этапов плана всего', len(stages)), ('Выполнено', done),
            ('Просрочено', sum(stage.is_overdue for stage in stages))]
    return info, [
        summary_section(plan, 'Индивидуальный план работы'),
        summary_section(works_summary(adjunct) + achievements_rows(adjunct)),
    ]


def student_card(student, show_account):
    info = [
        ('Учебная группа', student.group),
        ('Курс', student.course),
        ('Статус', student.get_status_display()),
        ('Научный руководитель', student.supervisor.full_name if student.supervisor_id else '—'),
        ('Примечание', dash(student.note)),
        *account_line(student, show_account),
    ]
    return info, [summary_section(works_summary(student) + achievements_rows(student))]


BUILDERS = {Teacher: teacher_card, Adjunct: adjunct_card, Student: student_card}


def person_card(person, show_account, author=''):
    """Карточка человека кафедры для печати."""
    info, sections = BUILDERS[type(person)](person, show_account)
    subtitle = [person.full_name]
    if isinstance(person, Teacher):
        subtitle.append(describe(person))
    return Document(CARD_TITLES[person._meta.model_name], subtitle, info, sections, author=author)


def card_filenames(person):
    kind = person._meta.model_name
    return f'Карточка_{file_name(person)}.docx', f'card_{kind}_{person.pk}.docx'


def account_card(account, author=''):
    """Карточка учётной записи: для всех пользователей, в том числе без карточки человека."""
    person = get_person(account)
    linked = '—'
    if person is not None:
        linked = f'{person.full_name} (карточка {PERSON_KINDS_GENITIVE[person._meta.model_name]})'
    groups = ', '.join(account.groups.order_by('name').values_list('name', flat=True))
    info = [
        ('Логин', account.get_username()),
        ('ФИО', dash(account.get_full_name())),
        ('E-mail', dash(account.email)),
        ('Роль', ROLE_TITLES[user_category(account)]),
        ('Группы', dash(groups)),
        ('Учётная запись активна', 'да' if account.is_active else 'нет (вход запрещён)'),
        ('Дата создания', date(account.date_joined.date()) if account.date_joined else '—'),
        ('Последний вход', last_login(account)),
        ('Привязанная карточка человека', linked),
    ]
    return Document('Карточка учётной записи', [account.get_username()], info, author=author)


def last_login(account):
    if not account.last_login:
        return 'не входил'
    return f'{timezone.localtime(account.last_login):%d.%m.%Y %H:%M}'


def account_filenames(account):
    return f'Учётная_запись_{account.get_username()}.docx', f'account_{account.pk}.docx'
