"""Ссылки на записи с учётом личного кабинета: на закрытую для пользователя запись — текст без ссылки."""
from django import template
from django.utils.html import conditional_escape, format_html

from apps.core.cabinet import can_open

register = template.Library()


@register.filter
def openable(obj, request):
    """{% if record|openable:request %} — может ли пользователь открыть страницу записи."""
    return obj is not None and can_open(request, obj)


@register.simple_tag(takes_context=True)
def record_link(context, obj, text=None):
    """{% record_link record %} или {% record_link record 'подпись' %}: ссылка, если запись открыта, иначе текст."""
    label = obj if text is None else text
    if can_open(context['request'], obj):
        return format_html('<a href="{}">{}</a>', obj.get_absolute_url(), label)
    return conditional_escape(label)
