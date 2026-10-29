"""Кто может сформировать отчёт на человека кафедры: он сам, его научный руководитель, редактор.

Те же правила — для отчёта о научной работе, отчёта о выполнении плана адъюнкта, отчёта о работе с подопечными
(преподаватель — только сам, подопечных у него руководителя нет) и для печати карточки человека.
"""
from django.urls import reverse

from apps.adjuncts.models import Adjunct
from apps.core.permissions import get_person, is_owned_by
from apps.staff.models import Teacher
from apps.students.models import Student

from .form16 import get_report_person, person_kind


def is_report_editor(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def can_view_person_report(user, target):
    """Сам человек, его научный руководитель (для курсанта и адъюнкта) или редактор."""
    if is_report_editor(user):
        return True
    person = get_person(user)
    return person is not None and is_owned_by(target, person)


def person_report_rule(person, kwargs):
    """Проверка «запись своя» для белых списков личного кабинета (apps.core.cabinet)."""
    return is_owned_by(get_report_person(kwargs['kind'], kwargs['pk']), person)


def form16_url(person):
    return reverse('reports:form16', args=[person_kind(person), person.pk])


def report_people(user):
    """Люди, на которых пользователь может сформировать отчёт (для выбора в форме)."""
    if is_report_editor(user):
        return [*Teacher.objects.all(), *Adjunct.objects.all(), *Student.objects.all()]
    person = get_person(user)
    if person is None:
        return []
    people = [person]
    if isinstance(person, Teacher):
        people += [*person.supervised_adjuncts.all(), *person.supervised_students.all()]
    return people


# Отчёты о человеке: имя URL → (название, виды людей, на которых отчёт формируется).
PERSON_REPORTS = {
    'form16': ('Форма № 16', ('teacher', 'adjunct', 'student')),
    'work': ('Отчёт о научной работе', ('teacher', 'adjunct', 'student')),
    'plan': ('Отчёт о выполнении индивидуального плана', ('adjunct',)),
    'supervision': ('Отчёт о работе с подопечными', ('teacher',)),
    'card': ('Карточка для печати', ('teacher', 'adjunct', 'student')),
}


def person_report_url(name, person):
    """Адрес отчёта name на человека: у отчётов одного вида людей в адресе только pk."""
    kind = person_kind(person)
    if len(PERSON_REPORTS[name][1]) == 1:
        return reverse(f'reports:{name}', args=[person.pk])
    return reverse(f'reports:{name}', args=[kind, person.pk])


def person_report_links(user, person):
    """Отчёты на person, доступные пользователю, — для блока «Отчёты» в карточке: [(название, адрес)]."""
    if not user.is_authenticated or not can_view_person_report(user, person):
        return []
    kind = person_kind(person)
    return [(title, person_report_url(name, person)) for name, (title, kinds) in PERSON_REPORTS.items()
            if kind in kinds]


def report_people_of(user, kinds):
    """Люди выбранных видов, на которых пользователь может сформировать отчёт."""
    return [person for person in report_people(user) if person_kind(person) in kinds]
