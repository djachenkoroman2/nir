from django.utils.functional import SimpleLazyObject

from .access import attention_count, attention_title, has_task_menu


def task_menu(request):
    """Пункт «Мои задачи» в шапке и число задач, требующих внимания (считается, только если пункт виден)."""

    def build():
        user = request.user
        if not has_task_menu(user):
            return {'show': False, 'attention': 0}
        return {'show': True, 'attention': attention_count(user), 'title': attention_title(user)}

    return {'task_menu': SimpleLazyObject(build)}
