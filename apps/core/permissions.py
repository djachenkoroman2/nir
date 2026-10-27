"""Кто может добавлять, изменять и удалять записи.

- Редактор — сотрудник (is_staff) с правом Django на действие: может всё.
- Преподаватель или адъюнкт — пользователь с правом Django на действие и привязанной карточкой
  преподавателя или адъюнкта («человек пользователя», get_person). Он может добавлять записи, а изменять
  и удалять — только свои:
  - где сам указан автором (модель записи для этого определяет метод is_authored_by(person));
  - для преподавателя — ещё и записи его подопечных курсантов и адъюнктов (метод is_supervised_by(teacher)).
  Записи без таких методов (НИОКР, конференции, преподаватели) изменяют только редакторы.
"""
from apps.staff.models import Teacher


def get_person(user):
    """Карточка преподавателя или адъюнкта, привязанная к пользователю, или None."""
    if not user.is_authenticated:
        return None
    return getattr(user, 'teacher', None) or getattr(user, 'adjunct', None)


def get_teacher(user):
    """Карточка преподавателя, привязанная к пользователю, или None."""
    person = get_person(user)
    return person if isinstance(person, Teacher) else None


def is_editor(user, perm):
    return user.is_staff and user.has_perm(perm)


def is_owned_by(obj, person):
    """Своя ли запись obj для человека person (автор или научный руководитель)."""
    is_authored_by = getattr(obj, 'is_authored_by', None)
    if is_authored_by and is_authored_by(person):
        return True
    is_supervised_by = getattr(obj, 'is_supervised_by', None)
    return bool(is_supervised_by and isinstance(person, Teacher) and is_supervised_by(person))


def can_manage(user, perm, obj=None):
    """Может ли пользователь выполнить действие perm (add/change/delete) над obj (None — добавление).

    При добавлении вложенной записи (например, достижения курсанта) в obj передаётся родительская запись.
    """
    if not user.is_authenticated or not user.has_perm(perm):
        return False
    if user.is_staff:
        return True
    person = get_person(user)
    if person is None:
        return False
    return obj is None or is_owned_by(obj, person)
