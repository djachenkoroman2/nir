from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.search import search
from apps.core.views import InlineFormSetMixin, StaffPermissionRequiredMixin

from .forms import ParticipantFormSet, ResearchProjectForm
from .models import ResearchProject


class ResearchProjectListView(LoginRequiredMixin, ListView):
    model = ResearchProject
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = search(queryset, ['title'], self.request.GET.get('q', ''))
        status = self.request.GET.get('status', '')
        if status in ResearchProject.Status.values:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['status'] = self.request.GET.get('status', '')
        context['status_choices'] = ResearchProject.Status.choices
        return context


class ResearchProjectDetailView(LoginRequiredMixin, DetailView):
    model = ResearchProject

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['memberships'] = self.object.memberships.select_related('teacher')
        return context


class ResearchProjectCreateView(StaffPermissionRequiredMixin, InlineFormSetMixin, CreateView):
    model = ResearchProject
    form_class = ResearchProjectForm
    formset_class = ParticipantFormSet
    permission_required = 'research.add_researchproject'
    success_message = 'НИОКР добавлена.'


class ResearchProjectUpdateView(StaffPermissionRequiredMixin, InlineFormSetMixin, UpdateView):
    model = ResearchProject
    form_class = ResearchProjectForm
    formset_class = ParticipantFormSet
    permission_required = 'research.change_researchproject'
    success_message = 'Изменения сохранены.'


class ResearchProjectDeleteView(StaffPermissionRequiredMixin, DeleteView):
    model = ResearchProject
    permission_required = 'research.delete_researchproject'
    success_url = reverse_lazy('research:project_list')

    def form_valid(self, form):
        messages.success(self.request, 'НИОКР удалена.')
        return super().form_valid(form)
