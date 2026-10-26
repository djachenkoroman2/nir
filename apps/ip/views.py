from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.search import search
from apps.core.views import AuthorFormSetMixin, RecordPermissionRequiredMixin

from .forms import IntellectualPropertyAuthorFormSet, IntellectualPropertyForm
from .models import IntellectualProperty


class IntellectualPropertyListView(LoginRequiredMixin, ListView):
    model = IntellectualProperty
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('authors__teacher')
        queryset = search(queryset, ['title', 'number'], self.request.GET.get('q', ''))
        kind = self.request.GET.get('kind', '')
        if kind in IntellectualProperty.Kind.values:
            queryset = queryset.filter(kind=kind)
        year = self.request.GET.get('year', '')
        if year.isdigit():
            queryset = queryset.filter(registration_date__year=int(year))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'query': self.request.GET.get('q', ''),
            'kind': self.request.GET.get('kind', ''),
            'year': self.request.GET.get('year', ''),
            'kind_choices': IntellectualProperty.Kind.choices,
            'year_choices': [
                d.year for d in IntellectualProperty.objects.dates('registration_date', 'year', order='DESC')
            ],
        })
        return context


class IntellectualPropertyDetailView(LoginRequiredMixin, DetailView):
    model = IntellectualProperty

    def get_queryset(self):
        return super().get_queryset().select_related('project').prefetch_related('authors__teacher')


class IntellectualPropertyCreateView(RecordPermissionRequiredMixin, AuthorFormSetMixin, CreateView):
    model = IntellectualProperty
    form_class = IntellectualPropertyForm
    formset_class = IntellectualPropertyAuthorFormSet
    permission_required = 'ip.add_intellectualproperty'
    success_message = 'РИД добавлен.'


class IntellectualPropertyUpdateView(RecordPermissionRequiredMixin, AuthorFormSetMixin, UpdateView):
    model = IntellectualProperty
    form_class = IntellectualPropertyForm
    formset_class = IntellectualPropertyAuthorFormSet
    permission_required = 'ip.change_intellectualproperty'
    success_message = 'Изменения сохранены.'


class IntellectualPropertyDeleteView(RecordPermissionRequiredMixin, DeleteView):
    model = IntellectualProperty
    permission_required = 'ip.delete_intellectualproperty'
    success_url = reverse_lazy('ip:ip_list')

    def form_valid(self, form):
        messages.success(self.request, 'РИД удалён.')
        return super().form_valid(form)
