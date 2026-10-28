from django import template

from apps.core.permissions import get_person

register = template.Library()


@register.filter
def person_name(user):
    """Как подписывать пользователя: «Иванов С. П.» по карточке человека кафедры, иначе имя или логин."""
    if user is None:
        return 'пользователь удалён'
    person = get_person(user)
    return person.short_name if person else (user.get_full_name() or user.username)
