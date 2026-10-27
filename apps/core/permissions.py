"""Кто может добавлять, изменять и удалять записи.

- Редактор — сотрудник (is_staff) с правом Django на действие: может всё.
- Преподаватель — пользователь с правом Django на действие и привязанной карточкой преподавателя:
  может добавлять записи, а изменять и удалять — только те, где сам указан автором
  (модель записи для этого определяет метод is_authored_by) или которые относятся к его подопечному
  курсанту (метод is_supervised_by). Записи без таких методов (НИОКР, конференции, преподаватели)
  изменяют только редакторы.
"""


def get_teacher(user):
    """Карточка преподавателя, привязанная к пользователю, или None."""
    return getattr(user, 'teacher', None) if user.is_authenticated else None


def is_editor(user, perm):
    return user.is_staff and user.has_perm(perm)


def can_manage(user, perm, obj=None):
    """Может ли пользователь выполнить действие perm (add/change/delete) над obj (None — добавление).

    При добавлении вложенной записи (например, достижения курсанта) в obj передаётся родительская запись.
    """
    if not user.is_authenticated or not user.has_perm(perm):
        return False
    if user.is_staff:
        return True
    teacher = get_teacher(user)
    if teacher is None:
        return False
    if obj is None:
        return True
    owned_by = getattr(obj, 'is_authored_by', None) or getattr(obj, 'is_supervised_by', None)
    return bool(owned_by and owned_by(teacher))
