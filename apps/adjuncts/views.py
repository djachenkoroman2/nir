from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.forms import ModelForm
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.permissions import can_manage, get_person, is_editor, is_owned_by
from apps.core.search import search
from apps.core.views import RecordPermissionRequiredMixin
from apps.reports.access import form16_url_for
from apps.staff.models import Teacher
from apps.students.models import Student
from apps.students.works import works_context

from .access import allowed_transitions, can_view_tasks, is_task_editor, visible_tasks
from .forms import (
    AdjunctAchievementForm, AdjunctContactsForm, AdjunctForm, PlanStageForm, SupervisorAdjunctForm, TaskCommentForm,
    TaskForm,
)
from .models import Adjunct, AdjunctAchievement, PlanStage, Task, TaskComment

ALL = 'all'


class AdjunctListView(LoginRequiredMixin, ListView):
    model = Adjunct
    paginate_by = 20

    def get_filters(self):
        get = self.request.GET
        status = get.get('status', Adjunct.Status.STUDYING)
        return {
            'query': get.get('q', ''),
            'supervisor': get.get('supervisor', ''),
            'admission_year': get.get('admission_year', ''),
            'study_form': get.get('study_form', ''),
            'status': status if status in Adjunct.Status.values else ALL,
        }

    def get_queryset(self):
        filters = self.get_filters()
        # annotate с Count отменяет сортировку из Meta, поэтому задаём её явно.
        queryset = (
            super().get_queryset()
            .select_related('supervisor')
            .annotate(
                publication_count=Count('publicationauthor', distinct=True),
                open_task_count=Count('tasks', filter=Q(tasks__status__in=Task.OPEN_STATUSES), distinct=True),
            )
            .order_by(*Adjunct._meta.ordering)
        )
        fields = ['last_name', 'first_name', 'middle_name', 'dissertation_topic']
        queryset = search(queryset, fields, filters['query'])
        if filters['supervisor'].isdigit():
            queryset = queryset.filter(supervisor_id=int(filters['supervisor']))
        if filters['admission_year'].isdigit():
            queryset = queryset.filter(admission_year=int(filters['admission_year']))
        if filters['study_form'] in Adjunct.StudyForm.values:
            queryset = queryset.filter(study_form=filters['study_form'])
        if filters['status'] != ALL:
            queryset = queryset.filter(status=filters['status'])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        # Число открытых задач показываем только тем, кому видны задачи этого адъюнкта.
        person = get_person(user)
        sees_all = is_task_editor(user)
        for adjunct in context['adjunct_list']:
            adjunct.show_tasks = sees_all or (
                person is not None and user.has_perm('adjuncts.view_task') and is_owned_by(adjunct, person)
            )
        context.update(self.get_filters())
        context.update({
            'all': ALL,
            'show_task_column': any(adjunct.show_tasks for adjunct in context['adjunct_list']),
            'status_choices': Adjunct.Status.choices,
            'study_form_choices': Adjunct.StudyForm.choices,
            'year_choices': Adjunct.objects.order_by('-admission_year')
                                   .values_list('admission_year', flat=True).distinct(),
            'supervisor_choices': Teacher.objects.filter(supervised_adjuncts__isnull=False).distinct(),
        })
        return context


class AdjunctDetailView(LoginRequiredMixin, DetailView):
    model = Adjunct

    def get_queryset(self):
        return super().get_queryset().select_related('supervisor', 'school', 'user')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        adjunct, user = self.object, self.request.user
        stages = list(adjunct.plan_stages.all())
        done = sum(stage.status == PlanStage.Status.DONE for stage in stages)
        person = get_person(user)
        context.update(works_context(adjunct, list(adjunct.achievements.all())))
        context.update({
            'plan_stages': stages,
            'plan_done': done,
            'plan_percent': round(done * 100 / len(stages)) if stages else 0,
            'is_own_card': person is not None and adjunct.is_authored_by(person),
            'form16_url': form16_url_for(user, adjunct),
            'defenses': adjunct.defenses.select_related('school'),
        })
        context.update(tasks_context(user, adjunct))
        return context


class AdjunctCreateView(RecordPermissionRequiredMixin, CreateView):
    model = Adjunct
    form_class = AdjunctForm
    permission_required = 'adjuncts.add_adjunct'

    def form_valid(self, form):
        messages.success(self.request, 'Адъюнкт добавлен.')
        return super().form_valid(form)


class AdjunctUpdateView(RecordPermissionRequiredMixin, UpdateView):
    model = Adjunct
    permission_required = 'adjuncts.change_adjunct'

    def get_form_class(self):
        return AdjunctForm if is_editor(self.request.user, 'adjuncts.change_adjunct') else SupervisorAdjunctForm

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class AdjunctContactsView(LoginRequiredMixin, UpdateView):
    """Адъюнкт сам изменяет в своей карточке только контакты."""

    model = Adjunct
    form_class = AdjunctContactsForm
    template_name = 'adjuncts/adjunct_contacts_form.html'

    def get_object(self, queryset=None):
        adjunct = super().get_object(queryset)
        person = get_person(self.request.user)
        if person is None or not adjunct.is_authored_by(person):
            raise PermissionDenied
        return adjunct

    def form_valid(self, form):
        messages.success(self.request, 'Контакты сохранены.')
        return super().form_valid(form)


class AdjunctDeleteView(RecordPermissionRequiredMixin, DeleteView):
    model = Adjunct
    permission_required = 'adjuncts.delete_adjunct'
    success_url = reverse_lazy('adjuncts:adjunct_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['delete_blocked'] = self.object.has_protected_relations()
        return context

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                'Нельзя удалить адъюнкта, который указан автором публикаций, РИД или докладов либо связан '
                'с защитой диссертации. Сначала уберите эти связи или измените статус адъюнкта.',
            )
            return redirect(self.object)
        messages.success(self.request, 'Адъюнкт удалён.')
        return response


class AdjunctChildMixin:
    """Запись, вложенная в карточку адъюнкта (этап плана, достижение): адъюнкт берётся из адреса или записи."""

    success_message = ''

    def dispatch(self, request, *args, **kwargs):
        if 'adjunct_pk' in kwargs:
            self.adjunct = get_object_or_404(Adjunct, pk=kwargs['adjunct_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_permission_object(self):
        # При добавлении права проверяются на самого адъюнкта: своего или подопечного.
        return self.adjunct if 'adjunct_pk' in self.kwargs else self.get_object()

    def get_adjunct(self):
        return self.adjunct if 'adjunct_pk' in self.kwargs else self.get_object().adjunct

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['adjunct'] = self.get_adjunct()
        return context

    def form_valid(self, form):
        if isinstance(form, ModelForm):  # у страницы удаления форма без записи
            form.instance.adjunct = self.get_adjunct()
        messages.success(self.request, self.success_message)
        return super().form_valid(form)

    def get_success_url(self):
        return self.get_adjunct().get_absolute_url()


class PlanStageCreateView(AdjunctChildMixin, RecordPermissionRequiredMixin, CreateView):
    model = PlanStage
    form_class = PlanStageForm
    permission_required = 'adjuncts.add_planstage'
    success_message = 'Этап плана добавлен.'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.adjunct = self.adjunct  # нужен для проверки года обучения
        return form


class PlanStageUpdateView(AdjunctChildMixin, RecordPermissionRequiredMixin, UpdateView):
    model = PlanStage
    form_class = PlanStageForm
    permission_required = 'adjuncts.change_planstage'
    success_message = 'Изменения сохранены.'


class PlanStageDeleteView(AdjunctChildMixin, RecordPermissionRequiredMixin, DeleteView):
    model = PlanStage
    permission_required = 'adjuncts.delete_planstage'
    success_message = 'Этап плана удалён.'


class PlanStageStartView(LoginRequiredMixin, View):
    """Адъюнкт отмечает запланированный этап своего плана как «выполняется»."""

    def post(self, request, pk):
        stage = get_object_or_404(PlanStage.objects.select_related('adjunct'), pk=pk)
        person = get_person(request.user)
        if person is None or not stage.adjunct.is_authored_by(person) or stage.status != PlanStage.Status.PLANNED:
            raise PermissionDenied
        stage.status = PlanStage.Status.IN_PROGRESS
        stage.save(update_fields=['status'])
        messages.success(request, f'Этап «{stage.title}» отмечен как выполняемый.')
        return redirect(stage.adjunct.get_absolute_url() + '#plan')


class AchievementCreateView(AdjunctChildMixin, RecordPermissionRequiredMixin, CreateView):
    model = AdjunctAchievement
    form_class = AdjunctAchievementForm
    permission_required = 'adjuncts.add_adjunctachievement'
    success_message = 'Достижение добавлено.'


class AchievementUpdateView(AdjunctChildMixin, RecordPermissionRequiredMixin, UpdateView):
    model = AdjunctAchievement
    form_class = AdjunctAchievementForm
    permission_required = 'adjuncts.change_adjunctachievement'
    success_message = 'Изменения сохранены.'


class AchievementDeleteView(AdjunctChildMixin, RecordPermissionRequiredMixin, DeleteView):
    model = AdjunctAchievement
    permission_required = 'adjuncts.delete_adjunctachievement'
    success_message = 'Достижение удалено.'


# Раздел исполнителя задач: заголовок и адрес раздела, подпись, имя адреса «Поставить задачу».
OWNER_SECTIONS = {
    Adjunct: ('Адъюнктура', 'adjuncts:adjunct_list', 'Адъюнкт', 'adjuncts:task_create'),
    Student: ('Курсанты', 'students:student_list', 'Курсант', 'students:task_create'),
}


def owner_context(owner):
    """Исполнитель задач и раздел, к которому он относится (для заголовков, хлебных крошек и ссылок)."""
    section_title, section_url, owner_label, add_task_url = OWNER_SECTIONS[type(owner)]
    return {
        'owner': owner,
        'section_title': section_title,
        'section_url': reverse(section_url),
        'owner_label': owner_label,
        'tasks_url': owner.get_tasks_url(),
        'add_task_url': reverse(add_task_url, args=[owner.pk]),
    }


def tasks_context(user, owner):
    """Блок задач в карточке адъюнкта или курсанта: открытые задачи — только тем, кому они видны."""
    if not can_view_tasks(user, owner):
        return {'show_tasks': False}
    return {
        **owner_context(owner),
        'show_tasks': True,
        'tasks': owner.tasks.filter(status__in=Task.OPEN_STATUSES).select_related('plan_stage'),
        'closed_task_count': owner.tasks.exclude(status__in=Task.OPEN_STATUSES).count(),
        'can_add_task': can_manage(user, 'adjuncts.add_task', owner),
    }


def get_visible_owner(user, model, pk):
    """Адъюнкт или курсант, чьи задачи видит пользователь; для остальных задач как будто нет (404)."""
    owner = get_object_or_404(model.objects.select_related('supervisor'), pk=pk)
    if not can_view_tasks(user, owner):
        raise Http404
    return owner


class TaskOwnerMixin:
    """Исполнитель задач берётся из адреса: <adjunct_pk> или <student_pk>."""

    owner_model = Adjunct

    def dispatch(self, request, *args, **kwargs):
        self.owner = self.get_owner()
        return super().dispatch(request, *args, **kwargs)

    def get_owner_pk(self):
        return self.kwargs['adjunct_pk' if self.owner_model is Adjunct else 'student_pk']

    def get_owner(self):
        return get_object_or_404(self.owner_model.objects.select_related('supervisor'), pk=self.get_owner_pk())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(owner_context(self.owner))
        return context


OPEN = 'open'
ADJUNCTS, STUDENTS = 'adjuncts', 'students'


class TaskFilterMixin:
    """Фильтр списка задач по статусу: по умолчанию — открытые."""

    paginate_by = 30
    statuses = tuple(Task.Status)

    def get_status_filter(self):
        status = self.request.GET.get('status', OPEN)
        return status if status in (OPEN, ALL, *self.statuses) else OPEN

    def filter_status(self, tasks):
        status = self.get_status_filter()
        if status == OPEN:
            return tasks.filter(status__in=Task.OPEN_STATUSES)
        if status != ALL:
            return tasks.filter(status=status)
        return tasks

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'status': self.get_status_filter(),
            'status_choices': [
                (OPEN, 'Открытые'), *((status.value, status.label.capitalize()) for status in self.statuses),
                (ALL, 'Все'),
            ],
        })
        return context


class OwnerTaskListView(LoginRequiredMixin, TaskOwnerMixin, TaskFilterMixin, ListView):
    """Задачи одного адъюнкта или курсанта."""

    template_name = 'adjuncts/owner_tasks.html'
    context_object_name = 'tasks'

    def get_owner(self):
        return get_visible_owner(self.request.user, self.owner_model, self.get_owner_pk())

    @property
    def statuses(self):
        return Task.statuses_for(self.owner)

    def get_queryset(self):
        return self.filter_status(self.owner.tasks.select_related('plan_stage'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_add_task'] = can_manage(self.request.user, 'adjuncts.add_task', self.owner)
        return context


class AdjunctTaskListView(OwnerTaskListView):
    owner_model = Adjunct


class StudentTaskListView(OwnerTaskListView):
    owner_model = Student


class MyTaskListView(LoginRequiredMixin, TaskFilterMixin, ListView):
    """«Мои задачи»: адъюнкту — его задачи, руководителю — задачи его адъюнктов и курсантов, редактору — все."""

    template_name = 'adjuncts/my_tasks.html'
    context_object_name = 'tasks'

    def get_filters(self):
        get = self.request.GET
        kind = get.get('kind', ALL)
        return {
            'kind': kind if kind in (ADJUNCTS, STUDENTS) else ALL,
            'adjunct': get.get('adjunct', ''),
            'student': get.get('student', ''),
        }

    def get_base_queryset(self):
        return visible_tasks(self.request.user)

    def get_queryset(self):
        filters = self.get_filters()
        tasks = self.filter_status(self.get_base_queryset().select_related('adjunct', 'student', 'plan_stage'))
        if filters['kind'] == ADJUNCTS:
            tasks = tasks.filter(adjunct__isnull=False)
        elif filters['kind'] == STUDENTS:
            tasks = tasks.filter(student__isnull=False)
        if filters['adjunct'].isdigit():
            tasks = tasks.filter(adjunct_id=int(filters['adjunct']))
        if filters['student'].isdigit():
            tasks = tasks.filter(student_id=int(filters['student']))
        return tasks

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = self.get_base_queryset()
        context.update(self.get_filters())
        context.update({
            'kind_choices': [(ALL, 'Все исполнители'), (ADJUNCTS, 'Адъюнкты'), (STUDENTS, 'Курсанты')],
            'adjunct_choices': Adjunct.objects.filter(tasks__in=base).distinct(),
            'student_choices': Student.objects.filter(tasks__in=base).distinct(),
        })
        return context


class VisibleTaskMixin(LoginRequiredMixin):
    """Задачу видят только руководитель исполнителя, редакторы и сам адъюнкт; остальным — 404."""

    def get_queryset(self):
        return visible_tasks(self.request.user).select_related(
            'adjunct__supervisor', 'student__supervisor', 'created_by', 'plan_stage'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(owner_context(self.object.person))
        return context


class TaskDetailView(VisibleTaskMixin, DetailView):
    model = Task

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task, user = self.object, self.request.user
        comments = list(task.comments.select_related('author__teacher', 'author__adjunct', 'author__student'))
        for comment in comments:
            comment.deletable = comment.can_be_deleted_by(user) and user.has_perm('adjuncts.delete_taskcomment')
        context.update({
            'comments': comments,
            'transitions': [(status, status.label) for status in allowed_transitions(user, task)],
            'comment_form': kwargs.get('comment_form') or TaskCommentForm(),
            'can_comment': user.has_perm('adjuncts.add_taskcomment'),
        })
        return context

    def post(self, request, *args, **kwargs):
        """Новый комментарий."""
        self.object = self.get_object()
        if not request.user.has_perm('adjuncts.add_taskcomment'):
            raise PermissionDenied
        form = TaskCommentForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(comment_form=form))
        form.instance.task = self.object
        form.instance.author = request.user
        form.save()
        return redirect(self.object.get_absolute_url() + '#comments')


class TaskCreateView(TaskOwnerMixin, RecordPermissionRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    permission_required = 'adjuncts.add_task'

    def handle_no_permission(self):
        if self.request.user.is_authenticated and not can_view_tasks(self.request.user, self.owner):
            raise Http404
        return super().handle_no_permission()

    def get_permission_object(self):
        # Задачи ставят только руководитель исполнителя и редакторы.
        return self.owner

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'owner': self.owner}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Задача поставлена.')
        return super().form_valid(form)


class AdjunctTaskCreateView(TaskCreateView):
    owner_model = Adjunct


class StudentTaskCreateView(TaskCreateView):
    owner_model = Student


class TaskUpdateView(VisibleTaskMixin, RecordPermissionRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    permission_required = 'adjuncts.change_task'

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'owner': self.object.person}

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class TaskDeleteView(VisibleTaskMixin, RecordPermissionRequiredMixin, DeleteView):
    model = Task
    permission_required = 'adjuncts.delete_task'

    def get_success_url(self):
        return self.object.person.get_tasks_url()

    def form_valid(self, form):
        messages.success(self.request, 'Задача удалена.')
        return super().form_valid(form)


class TaskStatusView(VisibleTaskMixin, View):
    """Смена статуса задачи; в ленту комментариев добавляется служебная запись."""

    def post(self, request, pk):
        task = get_object_or_404(self.get_queryset(), pk=pk)
        new_status = request.POST.get('status', '')
        allowed = allowed_transitions(request.user, task)
        if new_status not in allowed:
            raise PermissionDenied
        old_label = task.get_status_display()
        with transaction.atomic():
            task.set_status(new_status)
            task.save(update_fields=['status', 'completed_at'])
            TaskComment.objects.create(
                task=task, author=request.user, is_system=True,
                text=f'Смена статуса: {old_label} → {task.get_status_display()}',
            )
        messages.success(request, f'Статус задачи: {task.get_status_display()}.')
        return redirect(task.get_absolute_url())


class TaskCommentDeleteView(LoginRequiredMixin, View):
    """Автор удаляет свой комментарий в течение 15 минут после публикации."""

    def post(self, request, pk):
        comment = get_object_or_404(
            TaskComment.objects.select_related('task'), pk=pk, task__in=visible_tasks(request.user)
        )
        if not (request.user.has_perm('adjuncts.delete_taskcomment') and comment.can_be_deleted_by(request.user)):
            raise PermissionDenied
        comment.delete()
        messages.success(request, 'Комментарий удалён.')
        return redirect(comment.task.get_absolute_url() + '#comments')
