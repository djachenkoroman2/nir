from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.search import search
from apps.core.views import StaffPermissionRequiredMixin

from .forms import TeacherForm
from .models import Teacher


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
        context['memberships'] = self.object.memberships.select_related('project').order_by('-project__start_date')
        return context


class TeacherCreateView(StaffPermissionRequiredMixin, CreateView):
    model = Teacher
    form_class = TeacherForm
    permission_required = 'staff.add_teacher'

    def form_valid(self, form):
        messages.success(self.request, 'Преподаватель добавлен.')
        return super().form_valid(form)


class TeacherUpdateView(StaffPermissionRequiredMixin, UpdateView):
    model = Teacher
    form_class = TeacherForm
    permission_required = 'staff.change_teacher'

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class TeacherDeleteView(StaffPermissionRequiredMixin, DeleteView):
    model = Teacher
    permission_required = 'staff.delete_teacher'
    success_url = reverse_lazy('staff:teacher_list')

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                'Нельзя удалить преподавателя, который участвует в НИОКР. '
                'Снимите отметку «работает на кафедре» вместо удаления.',
            )
            return redirect(self.object)
        messages.success(self.request, 'Преподаватель удалён.')
        return response
