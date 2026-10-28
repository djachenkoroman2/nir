"""Кто видит задачи адъюнктов и курсантов и что может с ними делать.

Исполнитель задачи (owner) — адъюнкт или курсант. Задачи не публичные: их видят только научный руководитель
исполнителя, редакторы и сам исполнитель, если у него есть учётная запись.
- Руководитель и редактор создают, изменяют, удаляют задачи и переводят их в любой допустимый статус.
- Исполнитель меняет статус только по цепочке «новая → в работе → на проверке» и может вернуть задачу
  с проверки в работу; «выполнена» ставит руководитель — это приёмка.
- Задачи курсанта без учётной записи ведут только руководитель и редакторы; статуса «на проверке» у них нет.
- Комментировать могут все, кто видит задачу.
"""
from django.contrib.auth import get_user_model
from django.db.models import Exists, Q
from django.utils import timezone

from apps.core.permissions import get_person, is_editor, is_owned_by
from apps.staff.models import Teacher
from apps.students.models import Student

from .models import Adjunct, Task


def is_task_editor(user):
    return is_editor(user, 'adjuncts.view_task')


def is_supervisor_of(user, owner):
    person = get_person(user)
    return isinstance(person, Teacher) and owner.supervisor_id == person.pk


def can_view_tasks(user, owner):
    """Видит ли пользователь задачи адъюнкта или курсанта owner."""
    if not user.is_authenticated or not user.has_perm('adjuncts.view_task'):
        return False
    if user.is_staff:
        return True
    person = get_person(user)
    return person is not None and is_owned_by(owner, person)


def can_manage_tasks(user, owner, perm='adjuncts.change_task'):
    """Создавать, изменять и удалять задачи адъюнкта или курсанта: редактор или научный руководитель."""
    if not user.has_perm(perm):
        return False
    return user.is_staff or is_supervisor_of(user, owner)


def visible_tasks(user):
    """Задачи, которые видит пользователь (для списков)."""
    tasks = Task.objects.all()
    if not user.is_authenticated or not user.has_perm('adjuncts.view_task'):
        return tasks.none()
    if user.is_staff:
        return tasks
    return tasks.filter(
        Q(adjunct__user=user) | Q(adjunct__supervisor__user=user)
        | Q(student__user=user) | Q(student__supervisor__user=user)
    )


def allowed_transitions(user, task):
    """Статусы, в которые пользователь может перевести задачу."""
    if can_manage_tasks(user, task.person):
        return [status for status in task.statuses if status != task.status]
    person = get_person(user)
    if person is not None and task.is_authored_by(person):
        return list(Task.ADJUNCT_TRANSITIONS.get(task.status, []))
    return []


def attention_count(user):
    """Сколько задач ждут пользователя.

    Адъюнкту и курсанту — новые; руководителю — задачи на проверке и просроченные открытые задачи курсантов
    без учётной записи (такой курсант сам статус не меняет, поэтому руководителю важен срок).
    """
    return Task.objects.filter(
        Q(adjunct__user=user, status=Task.Status.NEW)
        | Q(student__user=user, status=Task.Status.NEW)
        | Q(adjunct__supervisor__user=user, status=Task.Status.REVIEW)
        | Q(student__supervisor__user=user, status=Task.Status.REVIEW)
        | Q(student__supervisor__user=user, student__user__isnull=True, status__in=Task.OPEN_STATUSES,
            due_date__lt=timezone.localdate())
    ).count()


def attention_title(user):
    """Подсказка к счётчику в шапке: что именно он считает."""
    if isinstance(get_person(user), (Adjunct, Student)):
        return 'Новые задачи'
    return 'Задачи на проверке и просроченные задачи курсантов без учётной записи'


def has_task_menu(user):
    """Показывать ли пункт «Мои задачи»: редактор, адъюнкт, курсант или руководитель адъюнктов либо курсантов."""
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return is_task_editor(user)
    # Один запрос вместо двух: меню проверяется на каждой странице.
    return get_user_model().objects.filter(
        Exists(Adjunct.objects.filter(Q(user=user) | Q(supervisor__user=user)))
        | Exists(Student.objects.filter(Q(user=user) | Q(supervisor__user=user))),
        pk=user.pk,
    ).exists()
