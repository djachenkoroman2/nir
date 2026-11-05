"""Роль для справки определяется тем же классификатором, что и категория отчёта активности."""
from apps.reports.activity import ADMINS, ADJUNCTS, EDITORS, OTHERS, STUDENTS, TEACHERS, user_category

from .content import GUIDES

CATEGORY_ROLES = {
    ADMINS: 'admin',
    EDITORS: 'editor',
    TEACHERS: 'teacher',
    ADJUNCTS: 'adjunct',
    STUDENTS: 'student',
    OTHERS: 'reader',
}


def role_for_user(user):
    return CATEGORY_ROLES[user_category(user)]


def can_view_role(user, role):
    if not user.is_authenticated or role not in GUIDES:
        return False
    return user.is_staff or user.is_superuser or role_for_user(user) == role


def accessible_guides(user):
    return [guide for slug, guide in GUIDES.items() if can_view_role(user, slug)]
