"""Кто может сформировать отчёт на человека кафедры: он сам, его научный руководитель, редактор."""
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


def form16_url_for(user, target):
    """Адрес формы 16 на target, если пользователю она доступна (для кнопки в карточке), иначе None."""
    return form16_url(target) if can_view_person_report(user, target) else None


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
