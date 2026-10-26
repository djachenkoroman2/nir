from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.search import search
from apps.core.views import InlineFormSetMixin, StaffPermissionRequiredMixin

from .forms import ConferenceForm, ReportForm, ReportSpeakerFormSet
from .models import Conference, Report


class ConferenceListView(LoginRequiredMixin, ListView):
    model = Conference
    paginate_by = 20

    def get_queryset(self):
        # annotate с Count отменяет сортировку из Meta, поэтому задаём её явно.
        queryset = (
            super().get_queryset()
            .annotate(report_count=Count('reports'))
            .order_by(*Conference._meta.ordering)
        )
        queryset = search(queryset, ['title', 'location'], self.request.GET.get('q', ''))
        level = self.request.GET.get('level', '')
        if level in Conference.Level.values:
            queryset = queryset.filter(level=level)
        year = self.request.GET.get('year', '')
        if year.isdigit():
            queryset = queryset.filter(start_date__year=int(year))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'query': self.request.GET.get('q', ''),
            'level': self.request.GET.get('level', ''),
            'year': self.request.GET.get('year', ''),
            'level_choices': Conference.Level.choices,
            'year_choices': [d.year for d in Conference.objects.dates('start_date', 'year', order='DESC')],
        })
        return context


class ConferenceDetailView(LoginRequiredMixin, DetailView):
    model = Conference

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reports'] = self.object.reports.select_related('publication').prefetch_related('speakers__teacher')
        return context


class ConferenceCreateView(StaffPermissionRequiredMixin, CreateView):
    model = Conference
    form_class = ConferenceForm
    permission_required = 'conferences.add_conference'

    def form_valid(self, form):
        messages.success(self.request, 'Конференция добавлена. Теперь можно добавить доклады.')
        return super().form_valid(form)


class ConferenceUpdateView(StaffPermissionRequiredMixin, UpdateView):
    model = Conference
    form_class = ConferenceForm
    permission_required = 'conferences.change_conference'

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class ConferenceDeleteView(StaffPermissionRequiredMixin, DeleteView):
    model = Conference
    permission_required = 'conferences.delete_conference'
    success_url = reverse_lazy('conferences:conference_list')

    def form_valid(self, form):
        messages.success(self.request, 'Конференция удалена.')
        return super().form_valid(form)


class ReportCreateView(StaffPermissionRequiredMixin, InlineFormSetMixin, CreateView):
    model = Report
    form_class = ReportForm
    formset_class = ReportSpeakerFormSet
    permission_required = 'conferences.add_report'
    success_message = 'Доклад добавлен.'

    def dispatch(self, request, *args, **kwargs):
        self.conference = get_object_or_404(Conference, pk=kwargs['conference_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.conference = self.conference
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['conference'] = self.conference
        return context


class ReportUpdateView(StaffPermissionRequiredMixin, InlineFormSetMixin, UpdateView):
    model = Report
    form_class = ReportForm
    formset_class = ReportSpeakerFormSet
    permission_required = 'conferences.change_report'
    success_message = 'Изменения сохранены.'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['conference'] = self.object.conference
        return context


class ReportDeleteView(StaffPermissionRequiredMixin, DeleteView):
    model = Report
    permission_required = 'conferences.delete_report'

    def get_success_url(self):
        return self.object.conference.get_absolute_url()

    def form_valid(self, form):
        messages.success(self.request, 'Доклад удалён.')
        return super().form_valid(form)
