from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.adjuncts.access import is_task_editor
from apps.adjuncts.models import Adjunct, Task
from apps.conferences.models import Report
from apps.core.cabinet import get_cabinet_person
from apps.core.permissions import get_teacher
from apps.core.search import search
from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication
from apps.core.views import RecordPermissionRequiredMixin
from apps.students.models import Student, StudentAchievement

from .forms import TeacherForm
from .models import AUTHORS_PREFETCH, Teacher


class TeacherListView(LoginRequiredMixin, ListView):
    model = Teacher
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = search(queryset, ['last_name', 'first_name', 'middle_name'], self.request.GET.get('q', ''))
        active = self.request.GET.get('active', '')
        if active in ('1', '0'):
            queryset = queryset.filter(is_active=active == '1')
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['active'] = self.request.GET.get('active', '')
        return context


class TeacherDetailView(LoginRequiredMixin, DetailView):
    model = Teacher

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        teacher = self.object
        context['memberships'] = teacher.memberships.select_related('project').order_by('-project__start_date')
        context['publications'] = (
            Publication.objects.filter(authors__teacher=teacher).prefetch_related(*AUTHORS_PREFETCH)
        )
        context['intellectual_properties'] = (
            IntellectualProperty.objects.filter(authors__teacher=teacher).prefetch_related(*AUTHORS_PREFETCH)
        )
        context['reports'] = (
            Report.objects.filter(speakers__teacher=teacher)
            .select_related('conference').order_by('-conference__start_date')
        )
        # annotate с Count отменяет сортировку из Meta, поэтому задаём её явно.
        context['supervised_students'] = (
            teacher.supervised_students.annotate(
                achievement_count=Count('achievements', distinct=True),
                open_task_count=Count('tasks', filter=Q(tasks__status__in=Task.OPEN_STATUSES), distinct=True),
            ).order_by(*Student._meta.ordering)
        )
        context['supervised_achievements'] = (
            StudentAchievement.objects.filter(supervisor=teacher).select_related('student')
        )
        context['supervised_adjuncts'] = (
            teacher.supervised_adjuncts.annotate(
                review_task_count=Count('tasks', filter=Q(tasks__status=Task.Status.REVIEW))
            ).order_by(*Adjunct._meta.ordering)
        )
        # Задачи не публичные: число задач адъюнктов на проверке и открытых задач курсантов
        # видят сам руководитель и редакторы.
        user = self.request.user
        context['show_review_counts'] = is_task_editor(user) or get_teacher(user) == teacher
        # Преподаватель смотрит свою карточку — это его личный кабинет.
        context['is_cabinet'] = teacher.is_authored_by(get_cabinet_person(user))
        return context


class TeacherCreateView(RecordPermissionRequiredMixin, CreateView):
    model = Teacher
    form_class = TeacherForm
    permission_required = 'staff.add_teacher'

    def form_valid(self, form):
        messages.success(self.request, 'Преподаватель добавлен.')
        return super().form_valid(form)


class TeacherUpdateView(RecordPermissionRequiredMixin, UpdateView):
    model = Teacher
    form_class = TeacherForm
    permission_required = 'staff.change_teacher'

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class TeacherDeleteView(RecordPermissionRequiredMixin, DeleteView):
    model = Teacher
    permission_required = 'staff.delete_teacher'
    success_url = reverse_lazy('staff:teacher_list')

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
                'Нельзя удалить преподавателя, который участвует в НИОКР, публикациях, РИД или докладах '
                'либо руководит научной работой курсантов или адъюнктов. '
                'Снимите отметку «работает на кафедре» вместо удаления.',
            )
            return redirect(self.object)
        messages.success(self.request, 'Преподаватель удалён.')
        return response
