from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.search import search
from apps.core.views import RecordPermissionRequiredMixin

from .forms import CooperationContractForm
from .models import CooperationContract

INDEFINITE = 'indefinite'
FILTER_CHOICES = [
    ('', 'Все договоры'),
    (CooperationContract.State.ACTIVE, 'Действующие'),
    (CooperationContract.State.FINISHED, 'Завершённые'),
    (INDEFINITE, 'Бессрочные'),
    (CooperationContract.State.UPCOMING, 'Ещё не начались'),
]


class CooperationContractListView(LoginRequiredMixin, ListView):
    model = CooperationContract
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = search(queryset, ['title', 'number', 'organization', 'subject'], self.request.GET.get('q', ''))
        state = self.request.GET.get('state', '')
        today = timezone.localdate()
        if state == CooperationContract.State.ACTIVE:
            queryset = queryset.filter(CooperationContract.active_filter(today))
        elif state == CooperationContract.State.FINISHED:
            queryset = queryset.filter(end_date__lt=today)
        elif state == CooperationContract.State.UPCOMING:
            queryset = queryset.filter(start_date__gt=today)
        elif state == INDEFINITE:
            queryset = queryset.filter(end_date__isnull=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state = self.request.GET.get('state', '')
        context.update({
            'query': self.request.GET.get('q', ''),
            'state': state if state in dict(FILTER_CHOICES) else '',
            'filter_choices': FILTER_CHOICES,
        })
        return context


class CooperationContractDetailView(LoginRequiredMixin, DetailView):
    model = CooperationContract


class CooperationContractCreateView(RecordPermissionRequiredMixin, CreateView):
    model = CooperationContract
    form_class = CooperationContractForm
    permission_required = 'cooperation.add_cooperationcontract'

    def form_valid(self, form):
        messages.success(self.request, 'Договор добавлен.')
        return super().form_valid(form)


class CooperationContractUpdateView(RecordPermissionRequiredMixin, UpdateView):
    model = CooperationContract
    form_class = CooperationContractForm
    permission_required = 'cooperation.change_cooperationcontract'

    def form_valid(self, form):
        messages.success(self.request, 'Изменения сохранены.')
        return super().form_valid(form)


class CooperationContractDeleteView(RecordPermissionRequiredMixin, DeleteView):
    model = CooperationContract
    permission_required = 'cooperation.delete_cooperationcontract'
    success_url = reverse_lazy('cooperation:contract_list')

    def form_valid(self, form):
        messages.success(self.request, 'Договор удалён.')
        return super().form_valid(form)
