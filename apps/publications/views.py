from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.search import search
from apps.core.views import AuthorFormSetMixin, RecordPermissionRequiredMixin
from apps.staff.models import AUTHORS_PREFETCH

from .forms import PublicationAuthorFormSet, PublicationForm
from .models import Publication

INDEX_FILTERS = {
    'vak': ('ВАК', {'vak__gt': ''}),
    'rinc': ('РИНЦ', {'rinc': True}),
    'rinc_core': ('ядро РИНЦ', {'rinc_core': True}),
    'scopus': ('Scopus', {'scopus': True}),
    'wos': ('Web of Science', {'wos': True}),
}


class PublicationListView(LoginRequiredMixin, ListView):
    model = Publication
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related(*AUTHORS_PREFETCH)
        queryset = search(queryset, ['title', 'source'], self.request.GET.get('q', ''))
        kind = self.request.GET.get('kind', '')
        if kind in Publication.Kind.values:
            queryset = queryset.filter(kind=kind)
        year = self.request.GET.get('year', '')
        if year.isdigit():
            queryset = queryset.filter(year=int(year))
        index = self.request.GET.get('index', '')
        if index in INDEX_FILTERS:
            queryset = queryset.filter(**INDEX_FILTERS[index][1])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'query': self.request.GET.get('q', ''),
            'kind': self.request.GET.get('kind', ''),
            'year': self.request.GET.get('year', ''),
            'index': self.request.GET.get('index', ''),
            'kind_choices': Publication.Kind.choices,
            'year_choices': Publication.objects.order_by('-year').values_list('year', flat=True).distinct(),
            'index_choices': [(key, label) for key, (label, _) in INDEX_FILTERS.items()],
        })
        return context


class PublicationDetailView(LoginRequiredMixin, DetailView):
    model = Publication

    def get_queryset(self):
        return super().get_queryset().select_related('project').prefetch_related(*AUTHORS_PREFETCH)


class PublicationCreateView(RecordPermissionRequiredMixin, AuthorFormSetMixin, CreateView):
    model = Publication
    form_class = PublicationForm
    formset_class = PublicationAuthorFormSet
    permission_required = 'publications.add_publication'
    success_message = 'Публикация добавлена.'


class PublicationUpdateView(RecordPermissionRequiredMixin, AuthorFormSetMixin, UpdateView):
    model = Publication
    form_class = PublicationForm
    formset_class = PublicationAuthorFormSet
    permission_required = 'publications.change_publication'
    success_message = 'Изменения сохранены.'


class PublicationDeleteView(RecordPermissionRequiredMixin, DeleteView):
    model = Publication
    permission_required = 'publications.delete_publication'
    success_url = reverse_lazy('publications:publication_list')

    def form_valid(self, form):
        messages.success(self.request, 'Публикация удалена.')
        return super().form_valid(form)
