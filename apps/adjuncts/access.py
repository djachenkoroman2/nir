"""Кто видит задачи адъюнкта и что может с ними делать.

Задачи не публичные: их видят только сам адъюнкт, его научный руководитель и редакторы.
- Руководитель и редактор создают, изменяют, удаляют задачи и переводят их в любой статус.
- Адъюнкт меняет статус только по цепочке «новая → в работе → на проверке» и может вернуть задачу
  с проверки в работу; «выполнена» ставит руководитель — это приёмка.
- Комментировать могут все, кто видит задачу.
"""
from django.db.models import Q

from apps.core.permissions import get_person, is_editor
from apps.staff.models import Teacher

from .models import Adjunct, Task


def is_task_editor(user):
    return is_editor(user, 'adjuncts.view_task')


def is_supervisor_of(user, adjunct):
    person = get_person(user)
    return isinstance(person, Teacher) and adjunct.supervisor_id == person.pk


def can_view_tasks(user, adjunct):
    if not user.is_authenticated or not user.has_perm('adjuncts.view_task'):
        return False
    if user.is_staff:
        return True
    person = get_person(user)
    return person is not None and (adjunct.is_authored_by(person) or is_supervisor_of(user, adjunct))


def can_manage_tasks(user, adjunct, perm='adjuncts.change_task'):
    """Создавать, изменять и удалять задачи адъюнкта: редактор или научный руководитель."""
    if not user.has_perm(perm):
        return False
    return user.is_staff or is_supervisor_of(user, adjunct)


def visible_tasks(user):
    """Задачи, которые видит пользователь (для списков)."""
    tasks = Task.objects.all()
    if not user.is_authenticated or not user.has_perm('adjuncts.view_task'):
        return tasks.none()
    if user.is_staff:
        return tasks
    return tasks.filter(Q(adjunct__user=user) | Q(adjunct__supervisor__user=user))


def allowed_transitions(user, task):
    """Статусы, в которые пользователь может перевести задачу."""
    if can_manage_tasks(user, task.adjunct):
        return [status for status in Task.Status if status != task.status]
    person = get_person(user)
    if person is not None and task.adjunct.is_authored_by(person):
        return list(Task.ADJUNCT_TRANSITIONS.get(task.status, []))
    return []


def attention_count(user):
    """Сколько задач ждут пользователя: адъюнкта — новые, руководителя — на проверке."""
    return Task.objects.filter(
        Q(adjunct__user=user, status=Task.Status.NEW)
        | Q(adjunct__supervisor__user=user, status=Task.Status.REVIEW)
    ).count()


def has_task_menu(user):
    """Показывать ли пункт «Мои задачи»: редактор, адъюнкт или руководитель адъюнктов."""
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return is_task_editor(user)
    return Adjunct.objects.filter(Q(user=user) | Q(supervisor__user=user)).exists()
