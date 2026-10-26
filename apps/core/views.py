from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.conferences.models import Conference, Report
from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication
from apps.research.models import ResearchProject
from apps.staff.models import Teacher


@login_required
def home(request):
    year = timezone.localdate().year
    sections = [
        {
            'title': 'Преподаватели', 'url': reverse('staff:teacher_list'),
            'text': f'Работают на кафедре: {Teacher.objects.filter(is_active=True).count()}',
        },
        {
            'title': 'НИОКР', 'url': reverse('research:project_list'),
            'text': f'Всего: {ResearchProject.objects.count()}, выполняются: '
                    f'{ResearchProject.objects.filter(status=ResearchProject.Status.IN_PROGRESS).count()}',
        },
        {
            'title': 'Публикации', 'url': reverse('publications:publication_list'),
            'text': f'Всего: {Publication.objects.count()}, за {year} год: {Publication.objects.filter(year=year).count()}',
        },
        {
            'title': 'РИД', 'url': reverse('ip:ip_list'),
            'text': f'Патентов и свидетельств: {IntellectualProperty.objects.count()}',
        },
        {
            'title': 'Конференции', 'url': reverse('conferences:conference_list'),
            'text': f'Конференций: {Conference.objects.count()}, докладов: {Report.objects.count()}',
        },
    ]
    return render(request, 'core/home.html', {'sections': sections})


class StaffPermissionRequiredMixin(PermissionRequiredMixin):
    """Изменять данные могут только сотрудники (is_staff) с соответствующим правом Django.

    Анонимного пользователя перенаправляет на вход, вошедшему без прав возвращает 403.
    """

    def has_permission(self):
        return self.request.user.is_staff and super().has_permission()


class InlineFormSetMixin:
    """Сохраняет объект вместе с формсетом связанных записей (участников, авторов и т.п.).

    В подклассе задаются formset_class и success_message.
    """

    formset_class = None
    success_message = ''

    def get_formset(self, data=None):
        return self.formset_class(data, instance=self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'formset' not in context:
            context['formset'] = self.get_formset()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object() if 'pk' in self.kwargs else None
        form = self.get_form()
        formset = self.get_formset(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                formset.instance = self.object
                formset.save()
            messages.success(request, self.success_message)
            return HttpResponseRedirect(self.get_success_url())
        return self.render_to_response(self.get_context_data(form=form, formset=formset))
