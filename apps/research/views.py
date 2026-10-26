from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.search import search
from apps.core.views import StaffPermissionRequiredMixin

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


class ParticipantFormSetMixin:
    """Сохраняет НИОКР вместе с формсетом участников."""

    success_message = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'formset' not in context:
            context['formset'] = ParticipantFormSet(instance=self.object)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object() if 'pk' in self.kwargs else None
        form = self.get_form()
        formset = ParticipantFormSet(request.POST, instance=self.object)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                formset.instance = self.object
                formset.save()
            messages.success(request, self.success_message)
            return HttpResponseRedirect(self.get_success_url())
        return self.render_to_response(self.get_context_data(form=form, formset=formset))


class ResearchProjectCreateView(StaffPermissionRequiredMixin, ParticipantFormSetMixin, CreateView):
    model = ResearchProject
    form_class = ResearchProjectForm
    permission_required = 'research.add_researchproject'
    success_message = 'НИОКР добавлена.'


class ResearchProjectUpdateView(StaffPermissionRequiredMixin, ParticipantFormSetMixin, UpdateView):
    model = ResearchProject
    form_class = ResearchProjectForm
    permission_required = 'research.change_researchproject'
    success_message = 'Изменения сохранены.'


class ResearchProjectDeleteView(StaffPermissionRequiredMixin, DeleteView):
    model = ResearchProject
    permission_required = 'research.delete_researchproject'
    success_url = reverse_lazy('research:project_list')

    def form_valid(self, form):
        messages.success(self.request, 'НИОКР удалена.')
        return super().form_valid(form)
