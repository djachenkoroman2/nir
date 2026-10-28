"""Личный кабинет: преподаватель, адъюнкт и курсант видят только то, что касается их самих.

Правило проверяется в одном месте — в CabinetMiddleware — по белому списку имён URL своей роли (RULES).
- Страница, которой нет в списке роли (в том числе любая, добавленная потом), отвечает 403.
- Для страниц конкретной записи в списке указана проверка «запись своя»; если запись чужая — 404.
- Редирект на закрытую страницу (например, в общий список после удаления) заменяется переходом в кабинет.

Ограничения не касаются редакторов (is_staff), суперпользователя и пользователя без карточки человека.
Механизм ограничивает только видимость: права на действия по-прежнему проверяют представления
(apps.core.permissions, apps.adjuncts.access). Ссылки на закрытые записи шаблоны выводят текстом —
через тег {% record_link %} и фильтр openable (apps.core.templatetags.cabinet), которые спрашивают can_open.
"""
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.urls import Resolver404, resolve, reverse
from django.utils.functional import SimpleLazyObject

from apps.adjuncts.models import Adjunct, AdjunctAchievement, PlanStage, Task, TaskComment
from apps.conferences.models import Conference, Report
from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication
from apps.research.models import ResearchProject
from apps.schools.models import ScientificSchool
from apps.staff.models import Teacher
from apps.students.models import Student, StudentAchievement

from .permissions import get_person

TEACHER, ADJUNCT, STUDENT = 'teacher', 'adjunct', 'student'


def get_cabinet_person(user):
    """Человек, чей доступ ограничен кабинетом, или None (редактор, суперпользователь, пользователь без карточки)."""
    if not user.is_authenticated or user.is_staff or user.is_superuser:
        return None
    return get_person(user)


def role_of(person):
    return person._meta.model_name if person is not None else None


class Own:
    """Проверка «запись из адреса своя»: records(person) — записи, которые человек видит.

    test(person, obj) — та же проверка по уже загруженному объекту без запроса к базе (для ссылок в шаблонах).
    """

    def __init__(self, records, kwarg='pk', test=None):
        self.records, self.kwarg, self.test = records, kwarg, test

    def __call__(self, person, kwargs):
        return self.records(person).filter(pk=kwargs[self.kwarg]).exists()


def anything(person, kwargs):
    return True


def is_self(model):
    """Карточка самого человека (без запроса): одинаковый pk у людей разных видов — разные люди."""
    return Own(lambda person: model.objects.filter(pk=person.pk) if isinstance(person, model) else model.objects.none(),
               test=lambda person, obj: isinstance(person, model) and obj.pk == person.pk)


def self_in(kwarg):
    """Родительская запись из адреса (<adjunct_pk>, <student_pk>) — сам человек."""
    return lambda person, kwargs: kwargs[kwarg] == person.pk


def authored(model, relation):
    """Записи, где человек — автор (докладчик): relation — 'authors' или 'speakers'."""
    return lambda person: model.objects.filter(**{f'{relation}__{role_of(person)}': person})


# --- преподаватель: свои записи и записи подопечных ---

def supervised_students(teacher):
    return Student.objects.filter(supervisor=teacher)


def supervised_adjuncts(teacher):
    return Adjunct.objects.filter(supervisor=teacher)


def teacher_works(model, relation):
    """Записи преподавателя и его подопечных (свои он изменяет, записи подопечных — по существующим правам)."""
    def records(teacher):
        return model.objects.filter(
            Q(**{f'{relation}__teacher': teacher}) | Q(**{f'{relation}__student__supervisor': teacher})
            | Q(**{f'{relation}__adjunct__supervisor': teacher})
        ).distinct()
    return records


def teacher_tasks(teacher):
    return Task.objects.filter(Q(adjunct__supervisor=teacher) | Q(student__supervisor=teacher))


def supervised(model):
    return Own(lambda teacher: model.objects.filter(supervisor=teacher),
               test=lambda teacher, obj: obj.supervisor_id == teacher.pk)


def supervised_parent(model, kwarg):
    return lambda teacher, kwargs: model.objects.filter(pk=kwargs[kwarg], supervisor=teacher).exists()


COMMON = {
    'login': anything,
    'logout': anything,
    'core:home': anything,
    'tasks:my_tasks': anything,
    'publications:publication_create': anything,
    'conferences:report_choose': anything,
    'conferences:report_create': anything,
    'conferences:conference_create': anything,
}


def works_rules(publications, ips, reports, conferences):
    """Страницы трудов: publications(person) и т. д. — записи, которые человек видит."""
    return {
        'publications:publication_detail': Own(publications),
        'publications:publication_update': Own(publications),
        'publications:publication_delete': Own(publications),
        'ip:ip_detail': Own(ips),
        'conferences:report_update': Own(reports),
        'conferences:report_delete': Own(reports),
        'conferences:conference_detail': Own(conferences),
    }


def task_rules(tasks):
    return {
        'tasks:task_detail': Own(tasks),
        'tasks:task_update': Own(tasks),
        'tasks:task_delete': Own(tasks),
        'tasks:task_status': Own(tasks),
        'tasks:comment_delete': Own(lambda person: TaskComment.objects.filter(task__in=tasks(person))),
    }


RULES = {
    TEACHER: {
        **COMMON,
        **works_rules(
            teacher_works(Publication, 'authors'), teacher_works(IntellectualProperty, 'authors'),
            teacher_works(Report, 'speakers'),
            lambda teacher: Conference.objects.filter(
                Q(reports__speakers__teacher=teacher) | Q(reports__speakers__student__supervisor=teacher)
                | Q(reports__speakers__adjunct__supervisor=teacher)
            ).distinct(),
        ),
        **task_rules(teacher_tasks),
        'staff:teacher_detail': is_self(Teacher),
        'staff:teacher_update': is_self(Teacher),
        'ip:ip_create': anything,
        'ip:ip_update': Own(teacher_works(IntellectualProperty, 'authors')),
        'ip:ip_delete': Own(teacher_works(IntellectualProperty, 'authors')),
        'research:project_detail': Own(lambda teacher: ResearchProject.objects.filter(participants=teacher)),
        'schools:school_detail': Own(lambda teacher: ScientificSchool.objects.filter(leaders=teacher)),
        # Подопечные курсанты и адъюнкты: карточки и всё, что руководителю разрешено с ними делать.
        'students:student_detail': supervised(Student),
        'students:student_update': supervised(Student),
        'students:achievement_create': supervised_parent(Student, 'student_pk'),
        'students:achievement_update': Own(lambda t: StudentAchievement.objects.filter(student__supervisor=t)),
        'students:achievement_delete': Own(lambda t: StudentAchievement.objects.filter(student__supervisor=t)),
        'students:student_tasks': supervised_parent(Student, 'student_pk'),
        'students:task_create': supervised_parent(Student, 'student_pk'),
        'adjuncts:adjunct_detail': supervised(Adjunct),
        'adjuncts:adjunct_update': supervised(Adjunct),
        'adjuncts:stage_create': supervised_parent(Adjunct, 'adjunct_pk'),
        'adjuncts:stage_update': Own(lambda t: PlanStage.objects.filter(adjunct__supervisor=t)),
        'adjuncts:stage_delete': Own(lambda t: PlanStage.objects.filter(adjunct__supervisor=t)),
        'adjuncts:achievement_create': supervised_parent(Adjunct, 'adjunct_pk'),
        'adjuncts:achievement_update': Own(lambda t: AdjunctAchievement.objects.filter(adjunct__supervisor=t)),
        'adjuncts:achievement_delete': Own(lambda t: AdjunctAchievement.objects.filter(adjunct__supervisor=t)),
        'adjuncts:adjunct_tasks': supervised_parent(Adjunct, 'adjunct_pk'),
        'adjuncts:task_create': supervised_parent(Adjunct, 'adjunct_pk'),
    },
    ADJUNCT: {
        **COMMON,
        **works_rules(
            authored(Publication, 'authors'), authored(IntellectualProperty, 'authors'),
            authored(Report, 'speakers'),
            lambda adjunct: Conference.objects.filter(reports__speakers__adjunct=adjunct).distinct(),
        ),
        **task_rules(lambda adjunct: Task.objects.filter(adjunct=adjunct)),
        'adjuncts:adjunct_detail': is_self(Adjunct),
        'adjuncts:adjunct_contacts': is_self(Adjunct),
        'adjuncts:stage_start': Own(lambda adjunct: PlanStage.objects.filter(adjunct=adjunct)),
        'adjuncts:achievement_create': self_in('adjunct_pk'),
        'adjuncts:achievement_update': Own(lambda adjunct: AdjunctAchievement.objects.filter(adjunct=adjunct)),
        'adjuncts:achievement_delete': Own(lambda adjunct: AdjunctAchievement.objects.filter(adjunct=adjunct)),
        'adjuncts:adjunct_tasks': self_in('adjunct_pk'),
        'ip:ip_create': anything,
        'ip:ip_update': Own(authored(IntellectualProperty, 'authors')),
        'ip:ip_delete': Own(authored(IntellectualProperty, 'authors')),
        'schools:school_detail': Own(lambda adjunct: ScientificSchool.objects.filter(pk=adjunct.school_id),
                                     test=lambda adjunct, school: school.pk == adjunct.school_id),
    },
    STUDENT: {
        **COMMON,
        **works_rules(
            authored(Publication, 'authors'), authored(IntellectualProperty, 'authors'),
            authored(Report, 'speakers'),
            lambda student: Conference.objects.filter(reports__speakers__student=student).distinct(),
        ),
        **task_rules(lambda student: Task.objects.filter(student=student)),
        'students:student_detail': is_self(Student),
        'students:achievement_create': self_in('student_pk'),
        'students:achievement_update': Own(lambda student: StudentAchievement.objects.filter(student=student)),
        'students:achievement_delete': Own(lambda student: StudentAchievement.objects.filter(student=student)),
        'students:student_tasks': self_in('student_pk'),
    },
}
# Курсант задачи не изменяет и не удаляет, РИД только просматривает.
for name in ('tasks:task_update', 'tasks:task_delete'):
    del RULES[STUDENT][name]


def is_allowed(person, view_name, kwargs):
    """Доступна ли человеку страница: None — страницы нет в белом списке его роли, False — запись чужая."""
    check = RULES[role_of(person)].get(view_name)
    if check is None:
        return None
    return check(person, kwargs)


def can_open(request, obj):
    """Может ли пользователь открыть страницу записи obj (для ссылок в шаблонах). Результаты кэшируются на запрос."""
    person = getattr(request, 'cabinet_person', None)
    if person is None:
        return True
    try:
        match = resolve(obj.get_absolute_url())
    except Resolver404:
        return False
    check = RULES[role_of(person)].get(match.view_name)
    if check is None:
        return False
    if not isinstance(check, Own):
        return check(person, match.kwargs)
    if check.test is not None:
        return check.test(person, obj)
    # Видимые записи правила загружаются один раз за запрос: ссылок на странице может быть много.
    cache = request.__dict__.setdefault('_cabinet_cache', {})
    if match.view_name not in cache:
        cache[match.view_name] = set(check.records(person).values_list('pk', flat=True))
    return match.kwargs[check.kwarg] in cache[match.view_name]


class CabinetMiddleware:
    """Ограничивает преподавателя, адъюнкта и курсанта их личным кабинетом (см. описание модуля)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        person = getattr(request, 'cabinet_person', None)
        if person is not None and isinstance(response, HttpResponseRedirect):
            # После удаления или сохранения записи представления ведут в общий список раздела,
            # который закрыт, — отправляем в кабинет.
            try:
                match = resolve(response.url.split('?')[0].split('#')[0])
            except Resolver404:
                return response
            if not is_allowed(person, match.view_name, match.kwargs):
                return HttpResponseRedirect(reverse('core:home'))
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        person = get_cabinet_person(request.user)
        request.cabinet_person = person
        if person is None:
            return None
        allowed = is_allowed(person, request.resolver_match.view_name, view_kwargs)
        if allowed is None:
            raise PermissionDenied
        if not allowed:
            raise Http404
        return None


def cabinet(request):
    """Контекст шаблонов: cabinet_person — человек в своём кабинете (или None), cabinet_role — его роль."""
    person = SimpleLazyObject(lambda: get_cabinet_person(request.user))
    return {'cabinet_person': person, 'cabinet_role': SimpleLazyObject(lambda: role_of(person or None))}
