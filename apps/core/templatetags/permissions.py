from django import template

from apps.core.permissions import can_manage

register = template.Library()


@register.simple_tag
def can(user, perm, obj=None):
    """{% can user 'publications.change_publication' publication as allowed %}"""
    return can_manage(user, perm, obj)
