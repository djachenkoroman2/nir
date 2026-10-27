from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.views import RecordPermissionRequiredMixin
from apps.staff.models import AUTHORS_PREFETCH

from .forms import DissertationDefenseForm, SchoolForm
from .indicators import INDICATORS_BY_KEY, annotate_indicators, indicator_totals
from .models import DissertationDefense, ScientificSchool
from .period import period_label, report_period


class PeriodMixin:
    def get_period(self):
        if not hasattr(self, '_period'):
            self._period = report_period()
        return self._period

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['period'] = period_label(self.get_period())
        return context


class SchoolListView(LoginRequiredMixin, PeriodMixin, ListView):
    """Сводная таблица научных школ с показателями за последние 5 лет."""

    model = ScientificSchool
    template_name = 'schools/school_list.html'
    context_object_name = 'school_list'

    def show_all(self):
        return self.request.GET.get('all') == '1'

    def get_base_queryset(self):
        schools = ScientificSchool.objects.all()
        return schools if self.show_all() else schools.filter(is_active=True)

    def get_queryset(self):
        return annotate_indicators(self.get_base_queryset(), self.get_period()).prefetch_related('leaders')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show_all'] = self.show_all()
        context['totals'] = indicator_totals(self.get_base_queryset(), self.get_period())
        return context


class SchoolDetailView(LoginRequiredMixin, PeriodMixin, DetailView):
    model = ScientificSchool

    def get_queryset(self):
        return super().get_queryset().prefetch_related('leaders')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school, period = self.object, self.get_period()

        def records(key):
            return INDICATORS_BY_KEY[key].for_school(school, period)

        context.update({
            'defenses': records('defenses_total').select_related('teacher', 'supervisor'),
            'monographs': records('monographs').prefetch_related(*AUTHORS_PREFETCH),
            'monograph_chapters': records('monograph_chapters').prefetch_related(*AUTHORS_PREFETCH),
            'vak_publications': records('vak_publications').prefetch_related(*AUTHORS_PREFETCH),
            'intellectual_properties': records('ip_total').prefetch_related(*AUTHORS_PREFETCH),
            'earlier_defenses': school.defenses.exclude(pk__in=records('defenses_total')).select_related('supervisor'),
        })
        return context


class SchoolCreateView(RecordPermissionRequiredMixin, CreateView):
    model = ScientificSchool
    form_class = SchoolForm
    permission_required = 'schools.add_scientificschool'

    def form_valid(self, form):
        messages.success(self.request, 'Научная школа добавлена.')
        return super().form_valid(form)


class SchoolUpdateView(RecordPermissionRequiredMixin, UpdateView):
    model = ScientificSchool
    form_class = SchoolForm
    permission_required = 'schools.change_scientificschool'

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class SchoolDeleteView(RecordPermissionRequiredMixin, DeleteView):
    model = ScientificSchool
    permission_required = 'schools.delete_scientificschool'
    success_url = reverse_lazy('schools:school_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['delete_blocked'] = self.object.defenses.exists()
        return context

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                'Нельзя удалить научную школу, к которой относятся защиты диссертаций. '
                'Сначала удалите защиты или перенесите их в другую школу.',
            )
            return redirect(self.object)
        messages.success(self.request, 'Научная школа удалена.')
        return response


class DefenseCreateView(RecordPermissionRequiredMixin, CreateView):
    model = DissertationDefense
    form_class = DissertationDefenseForm
    permission_required = 'schools.add_dissertationdefense'

    def dispatch(self, request, *args, **kwargs):
        self.school = get_object_or_404(ScientificSchool, pk=kwargs['school_pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {'school': self.school}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['school'] = self.school
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Защита добавлена.')
        return super().form_valid(form)


class DefenseUpdateView(RecordPermissionRequiredMixin, UpdateView):
    model = DissertationDefense
    form_class = DissertationDefenseForm
    permission_required = 'schools.change_dissertationdefense'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['school'] = self.object.school
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class DefenseDeleteView(RecordPermissionRequiredMixin, DeleteView):
    model = DissertationDefense
    permission_required = 'schools.delete_dissertationdefense'

    def get_success_url(self):
        return self.object.school.get_absolute_url()

    def form_valid(self, form):
        messages.success(self.request, 'Защита удалена.')
        return super().form_valid(form)
