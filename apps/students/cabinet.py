"""Что доступно курсанту с учётной записью: только его личный кабинет и его собственные записи.

Правило проверяется в одном месте — в StudentCabinetMiddleware — по белому списку имён URL. Страница, которой
нет в списке (в том числе любая, добавленная потом), отвечает курсанту 403. Для страниц конкретной записи
в списке указана проверка «запись своя»; если запись чужая, курсант получает 404, как будто её нет.
Права на действия (добавить, изменить, удалить) по-прежнему проверяют представления (apps.core.permissions).
"""
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.urls import Resolver404, resolve, reverse
from django.utils.functional import SimpleLazyObject

from apps.adjuncts.models import Task, TaskComment
from apps.conferences.models import Conference, Report
from apps.core.permissions import get_person
from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication

from .models import Student, StudentAchievement


def get_cabinet_student(user):
    """Курсант, привязанный к пользователю, или None (тогда ограничения кабинета не действуют)."""
    person = get_person(user)
    return person if isinstance(person, Student) else None


def own_student(kwarg):
    return lambda student, kwargs: kwargs[kwarg] == student.pk


def own(queryset_for):
    """Проверка «запись <pk> своя»: queryset_for(student) — записи курсанта."""
    return lambda student, kwargs: queryset_for(student).filter(pk=kwargs['pk']).exists()


def any_record(student, kwargs):
    return True


# Имя URL → проверка, что запись (или родительская запись) принадлежит курсанту.
ALLOWED_URLS = {
    'login': any_record,
    'logout': any_record,
    'core:home': any_record,
    # Своя карточка (личный кабинет) и свои достижения.
    'students:student_detail': own_student('pk'),
    'students:achievement_create': own_student('student_pk'),
    'students:achievement_update': own(lambda s: StudentAchievement.objects.filter(student=s)),
    'students:achievement_delete': own(lambda s: StudentAchievement.objects.filter(student=s)),
    # Свои задачи: «Мои задачи» и страницы задачи дополнительно фильтруют задачи по видимости.
    'students:student_tasks': own_student('student_pk'),
    'tasks:my_tasks': any_record,
    'tasks:task_detail': own(lambda s: Task.objects.filter(student=s)),
    'tasks:task_status': own(lambda s: Task.objects.filter(student=s)),
    'tasks:comment_delete': own(lambda s: TaskComment.objects.filter(task__student=s)),
    # Публикации и доклады, где курсант указан автором; добавлять — новые.
    'publications:publication_create': any_record,
    'publications:publication_detail': own(lambda s: Publication.objects.filter(authors__student=s)),
    'publications:publication_update': own(lambda s: Publication.objects.filter(authors__student=s)),
    'publications:publication_delete': own(lambda s: Publication.objects.filter(authors__student=s)),
    'conferences:report_choose': any_record,
    'conferences:report_create': any_record,
    'conferences:report_update': own(lambda s: Report.objects.filter(speakers__student=s)),
    'conferences:report_delete': own(lambda s: Report.objects.filter(speakers__student=s)),
    'conferences:conference_create': any_record,
    'conferences:conference_detail': own(lambda s: Conference.objects.filter(reports__speakers__student=s)),
    # РИД, где курсант соавтор, — только просмотр.
    'ip:ip_detail': own(lambda s: IntellectualProperty.objects.filter(authors__student=s)),
}


def is_allowed(student, url_name, kwargs):
    """Доступна ли курсанту страница: None — страницы нет в белом списке, False — запись чужая."""
    check = ALLOWED_URLS.get(url_name)
    if check is None:
        return None
    return check(student, kwargs)


class StudentCabinetMiddleware:
    """Ограничивает курсанта его личным кабинетом (см. описание модуля)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        student = getattr(request, 'cabinet_student', None)
        if student is not None and isinstance(response, HttpResponseRedirect):
            # После удаления или сохранения записи представления ведут в общий список раздела, который курсанту
            # закрыт, — отправляем его в кабинет.
            try:
                match = resolve(response.url.split('?')[0].split('#')[0])
            except Resolver404:
                return response
            if not is_allowed(student, match.view_name, match.kwargs):
                return HttpResponseRedirect(reverse('core:home'))
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        student = get_cabinet_student(request.user)
        request.cabinet_student = student
        if student is None:
            return None
        allowed = is_allowed(student, request.resolver_match.view_name, view_kwargs)
        if allowed is None:
            raise PermissionDenied
        if not allowed:
            raise Http404
        return None


def cabinet(request):
    """Контекст шаблонов: cabinet_student — курсант, вошедший в свой кабинет (для меню и ссылок)."""
    return {'cabinet_student': SimpleLazyObject(lambda: get_cabinet_student(request.user))}
