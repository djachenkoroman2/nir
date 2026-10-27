from collections import Counter

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.conferences.models import Report
from apps.core.search import search
from apps.core.views import RecordPermissionRequiredMixin
from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication
from apps.staff.models import AUTHORS_PREFETCH, SPEAKERS_PREFETCH, Teacher

from .forms import StudentAchievementForm, StudentForm
from .models import Student, StudentAchievement

ALL_STATUSES = 'all'


class StudentListView(LoginRequiredMixin, ListView):
    model = Student
    paginate_by = 20

    def get_filters(self):
        get = self.request.GET
        status = get.get('status', Student.Status.STUDYING)
        return {
            'query': get.get('q', ''),
            'course': get.get('course', ''),
            'group': get.get('group', ''),
            'supervisor': get.get('supervisor', ''),
            'status': status if status in Student.Status.values else ALL_STATUSES,
        }

    def get_queryset(self):
        filters = self.get_filters()
        # annotate с Count отменяет сортировку из Meta, поэтому задаём её явно.
        queryset = (
            super().get_queryset()
            .select_related('supervisor')
            .annotate(
                publication_count=Count('publicationauthor', distinct=True),
                achievement_count=Count('achievements', distinct=True),
            )
            .order_by(*Student._meta.ordering)
        )
        queryset = search(queryset, ['last_name', 'first_name', 'middle_name', 'group'], filters['query'])
        if filters['course'].isdigit():
            queryset = queryset.filter(course=int(filters['course']))
        if filters['group']:
            queryset = queryset.filter(group=filters['group'])
        if filters['supervisor'].isdigit():
            queryset = queryset.filter(supervisor_id=int(filters['supervisor']))
        if filters['status'] != ALL_STATUSES:
            queryset = queryset.filter(status=filters['status'])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_filters())
        context.update({
            'all_statuses': ALL_STATUSES,
            'status_choices': Student.Status.choices,
            'course_choices': range(1, 7),
            'group_choices': Student.objects.order_by('group').values_list('group', flat=True).distinct(),
            'supervisor_choices': Teacher.objects.filter(supervised_students__isnull=False).distinct(),
        })
        return context


class StudentDetailView(LoginRequiredMixin, DetailView):
    model = Student

    def get_queryset(self):
        return super().get_queryset().select_related('supervisor')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.object
        achievements = list(student.achievements.select_related('supervisor'))
        publications = Publication.objects.filter(authors__student=student)
        level_counts = Counter(achievement.level for achievement in achievements)
        context.update({
            'achievements': achievements,
            'publications': publications.prefetch_related(*AUTHORS_PREFETCH),
            'publication_stats': publications.aggregate(
                total=Count('pk'),
                vak=Count('pk', filter=~Q(vak='')),
                rinc=Count('pk', filter=Q(rinc=True) | Q(rinc_core=True)),
                scopus=Count('pk', filter=Q(scopus=True)),
                wos=Count('pk', filter=Q(wos=True)),
            ),
            'achievement_levels': [
                (label, level_counts[value]) for value, label in StudentAchievement.Level.choices
            ],
            'intellectual_properties': (
                IntellectualProperty.objects.filter(authors__student=student).prefetch_related(*AUTHORS_PREFETCH)
            ),
            'reports': (
                Report.objects.filter(speakers__student=student).select_related('conference')
                .prefetch_related(*SPEAKERS_PREFETCH).order_by('-conference__start_date')
            ),
        })
        return context


class StudentCreateView(RecordPermissionRequiredMixin, CreateView):
    model = Student
    form_class = StudentForm
    permission_required = 'students.add_student'

    def form_valid(self, form):
        messages.success(self.request, 'Курсант добавлен.')
        return super().form_valid(form)


class StudentUpdateView(RecordPermissionRequiredMixin, UpdateView):
    model = Student
    form_class = StudentForm
    permission_required = 'students.change_student'

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class StudentDeleteView(RecordPermissionRequiredMixin, DeleteView):
    model = Student
    permission_required = 'students.delete_student'
    success_url = reverse_lazy('students:student_list')

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
                'Нельзя удалить курсанта, который указан автором публикаций, РИД или докладов. '
                'Сначала уберите его из авторов или отметьте статус «выпущен» либо «отчислен».',
            )
            return redirect(self.object)
        messages.success(self.request, 'Курсант удалён.')
        return response


class AchievementCreateView(RecordPermissionRequiredMixin, CreateView):
    model = StudentAchievement
    form_class = StudentAchievementForm
    permission_required = 'students.add_studentachievement'

    def dispatch(self, request, *args, **kwargs):
        self.student = get_object_or_404(Student, pk=kwargs['student_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_permission_object(self):
        # Преподаватель добавляет достижения только своим подопечным.
        return self.student

    def get_initial(self):
        return {'supervisor': self.student.supervisor}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['student'] = self.student
        return context

    def form_valid(self, form):
        form.instance.student = self.student
        messages.success(self.request, 'Достижение добавлено.')
        return super().form_valid(form)


class AchievementUpdateView(RecordPermissionRequiredMixin, UpdateView):
    model = StudentAchievement
    form_class = StudentAchievementForm
    permission_required = 'students.change_studentachievement'

    def get_queryset(self):
        return super().get_queryset().select_related('student')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['student'] = self.object.student
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class AchievementDeleteView(RecordPermissionRequiredMixin, DeleteView):
    model = StudentAchievement
    permission_required = 'students.delete_studentachievement'

    def get_queryset(self):
        return super().get_queryset().select_related('student')

    def get_success_url(self):
        return self.object.student.get_absolute_url()

    def form_valid(self, form):
        messages.success(self.request, 'Достижение удалено.')
        return super().form_valid(form)
