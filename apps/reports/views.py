from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from apps.core.permissions import get_person

from .access import can_view_person_report, form16_url, is_report_editor, report_people
from .activity import CATEGORIES, COUNTERS, build_activity_report, default_period, user_log
from .activity_docx import build_activity_docx
from .docx_common import DOCX_TYPE, docx_response  # noqa: F401 — DOCX_TYPE нужен тестам
from .docx_export import build_docx
from .form16 import SECTION_CHOICES, build_form16, get_report_person, person_kind
from .forms import ActivityReportForm, Form16Form, UserLogForm
from .registry import available_reports


class ReportListView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/report_list.html'

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'reports': available_reports(self.request.user)}


@login_required
def form16_own(request):
    """Своя форма 16; редактору без карточки — выбор человека."""
    person = get_person(request.user)
    if person is not None:
        url = form16_url(person)
        return redirect(f'{url}?{request.GET.urlencode()}' if request.GET else url)
    if not is_report_editor(request.user):
        raise Http404
    form = Form16Form(request.GET or None, people=report_people(request.user))
    if form.is_bound and form.is_valid() and form.cleaned_data.get('person'):
        params = request.GET.copy()
        params.pop('person')
        target = get_report_person(*form.cleaned_data['person'].rsplit('-', 1))
        return redirect(f'{form16_url(target)}?{params.urlencode()}')
    return render(request, 'reports/form16.html', {'form': form, 'report': None})


def docx_filename(person):
    initials = '_'.join(part[0] for part in (person.first_name, person.middle_name) if part)
    return f'Форма_16_{person.last_name}_{initials}.docx'.replace('__', '_')


def form16_docx(report):
    person = report.person
    return docx_response(build_docx(report), docx_filename(person), f'form16_{person_kind(person)}_{person.pk}.docx')


@login_required
def form16(request, kind, pk):
    """Форма 16 на человека: страница, версия для печати (кнопка) и DOCX (?format=docx)."""
    person = get_report_person(kind, pk)
    if not can_view_person_report(request.user, person):
        raise Http404
    people = report_people(request.user)
    current = Form16Form.person_value(person)
    if person not in people:
        people = [person, *people]
    data = request.GET if 'submitted' in request.GET else {
        'person': current, 'sections': [key for key, _ in SECTION_CHOICES],
    }
    form = Form16Form(data, people=people)
    report = None
    if form.is_valid():
        chosen = form.cleaned_data.get('person') or current
        if chosen != current:
            # Выбран другой человек — тот же отчёт с теми же параметрами на него.
            target = get_report_person(*chosen.rsplit('-', 1))
            params = request.GET.copy()
            params.pop('person', None)
            return redirect(f'{form16_url(target)}?{params.urlencode()}')
        report = build_form16(
            person, form.cleaned_data['year_from'], form.cleaned_data['year_to'], form.cleaned_data['sections'],
        )
        if request.GET.get('format') == 'docx':
            return form16_docx(report)
    return render(request, 'reports/form16.html', {'form': form, 'report': report, 'person': person})


ACTIVITY_PERMISSION = 'activity.view_activity_report'
DATETIME_FORMAT = '%Y-%m-%dT%H:%M'


def local_input(value):
    return timezone.localtime(value).strftime(DATETIME_FORMAT)


def period_defaults():
    start, end = default_period()
    return {'start': local_input(start), 'end': local_input(end)}


class ActivityReportView(PermissionRequiredMixin, TemplateView):
    """Отчёт об активности: суперпользователь или обладатель права activity.view_activity_report."""

    permission_required = ACTIVITY_PERMISSION
    template_name = 'reports/activity.html'

    def get(self, request, *args, **kwargs):
        data = request.GET if 'submitted' in request.GET else {
            **period_defaults(), 'categories': [key for key, _ in CATEGORIES],
        }
        form = ActivityReportForm(data)
        report = None
        if form.is_valid():
            report = build_activity_report(
                form.cleaned_data['start'], form.cleaned_data['end'], form.cleaned_data['categories'],
                form.cleaned_data['show_inactive'],
            )
            if request.GET.get('format') == 'docx':
                start, end = (timezone.localtime(value) for value in (report.start, report.end))
                return docx_response(
                    build_activity_docx(report, request.user),
                    f'Активность_пользователей_{start:%d.%m.%Y}-{end:%d.%m.%Y}.docx',
                    f'activity_{start:%Y%m%d}-{end:%Y%m%d}.docx',
                )
        period = {'start': data.get('start', ''), 'end': data.get('end', '')}
        return self.render_to_response(self.get_context_data(
            form=form, report=report, counters=COUNTERS, period=period,
        ))


class UserActivityView(PermissionRequiredMixin, ListView):
    """Подробный журнал пользователя (или записей без пользователя с логином) за период."""

    permission_required = ACTIVITY_PERMISSION
    template_name = 'reports/activity_user.html'
    context_object_name = 'records'
    paginate_by = 50

    def get_form(self):
        data = self.request.GET if 'start' in self.request.GET else period_defaults()
        return UserLogForm(data)

    def get_queryset(self):
        self.form = self.get_form()
        if 'pk' in self.kwargs:
            self.subject = get_object_or_404(get_user_model(), pk=self.kwargs['pk'])
            user, username = self.subject, None
        else:
            self.subject, user, username = None, None, self.kwargs['username']
        if not self.form.is_valid():
            return []
        data = self.form.cleaned_data
        return user_log(data['start'], data['end'], user=user, username=username, action=data['action'] or None)

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs), 'form': self.form, 'subject': self.subject,
            'username': self.subject.get_username() if self.subject else self.kwargs['username'],
            'period_query': urlencode({key: self.form.data.get(key, '') for key in ('start', 'end')}),
        }
