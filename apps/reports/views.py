from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.core.permissions import get_person

from .access import (
    PERSON_REPORTS, can_view_person_report, form16_url, is_report_editor, person_report_url, report_people,
    report_people_of,
)
from .activity import CATEGORIES, COUNTERS, build_activity_report, default_period, user_log
from .activity_docx import build_activity_docx
from .cards import account_card, account_filenames, card_filenames, person_card
from .department import SUMMARY, build_department_report, department_document, department_filenames
from .department import SECTION_CHOICES as DEPARTMENT_SECTIONS
from .docx_common import DOCX_TYPE, build_document_docx, docx_response  # noqa: F401 — DOCX_TYPE нужен тестам
from .docx_export import build_docx
from .form16 import SECTION_CHOICES, build_form16, get_report_person, person_kind
from .forms import (
    ActivityReportForm, DepartmentReportForm, Form16Form, PlanReportForm, SupervisionReportForm, UserLogForm,
    WorkReportForm,
)
from .plan import build_plan_report, plan_document, plan_filenames
from .registry import report_groups
from .supervision import build_supervision_report, supervision_document, supervision_filenames
from .work import build_work_report, work_document, work_filenames
from .works import PEOPLE_CATEGORIES, Period


class ReportListView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/report_list.html'

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'groups': report_groups(self.request.user)}


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


class DocumentPageMixin:
    """Страница отчёта из layout.Document: просмотр, версия для печати (кнопка) и DOCX (?format=docx)."""

    template_name = 'reports/document.html'
    page_title = ''
    intro = ''

    def render_document(self, document, filenames, **context):
        if document is not None and self.request.GET.get('format') == 'docx':
            return docx_response(build_document_docx(document), *filenames)
        return render(self.request, self.template_name, {
            'page_title': self.page_title, 'intro': self.intro, 'document': document, **context,
        })


class PersonReportView(LoginRequiredMixin, DocumentPageMixin, View):
    """Отчёт о человеке (научная работа, план адъюнкта, подопечные) по правилам доступа формы 16.

    /reports/<name>/ — свой отчёт; редактору без подходящей карточки — выбор человека.
    Отчёт на человека — по адресу из person_report_url; чужой человек и неподходящий вид — 404.
    """

    name = ''  # имя URL отчёта и ключ PERSON_REPORTS
    form_class = WorkReportForm

    @property
    def kinds(self):
        return PERSON_REPORTS[self.name][1]

    def initial(self):
        year = Period.current().year_from
        return {'year_from': year, 'year_to': year}

    def get_form(self, data, people, person=None, require_person=False):
        return self.form_class(data, people=people, require_person=require_person)

    def get(self, request, kind=None, pk=None):
        if pk is None:
            return self.own(request)
        person = get_report_person(kind, pk)
        if kind not in self.kinds or not can_view_person_report(request.user, person):
            raise Http404
        people = report_people_of(request.user, self.kinds)
        if person not in people:
            people = [person, *people]
        current = Form16Form.person_value(person)
        data = request.GET if 'submitted' in request.GET else {'person': current, **self.initial()}
        form = self.get_form(data, people, person)
        if not form.is_valid():
            return self.render_document(None, None, form=form, person=person)
        chosen = form.cleaned_data.get('person') or current
        if chosen != current:
            # Выбран другой человек — тот же отчёт с теми же параметрами на него.
            return self.redirect_to(get_report_person(*chosen.rsplit('-', 1)), request.GET)
        report = self.build(person, form)
        return self.render_document(self.document(report, request.user), self.filenames(report),
                                    form=form, person=person)

    def own(self, request):
        person = get_person(request.user)
        if person is not None and person_kind(person) in self.kinds:
            return self.redirect_to(person, request.GET)
        if not is_report_editor(request.user):
            raise Http404
        people = report_people_of(request.user, self.kinds)
        data = request.GET if 'submitted' in request.GET else None
        form = self.get_form(data, people, require_person=True)
        if data is None:
            form.initial = self.initial()
        elif form.is_valid():
            return self.redirect_to(get_report_person(*form.cleaned_data['person'].rsplit('-', 1)), request.GET)
        return self.render_document(None, None, form=form, choose=True)

    def redirect_to(self, person, params):
        params = params.copy()
        params.pop('person', None)
        url = person_report_url(self.name, person)
        return redirect(f'{url}?{params.urlencode()}' if params else url)

    def build(self, person, form):
        raise NotImplementedError

    def document(self, report, user):
        raise NotImplementedError

    def filenames(self, report):
        raise NotImplementedError


class WorkReportView(PersonReportView):
    name = 'work'
    page_title = 'Отчёт о научной работе'
    intro = ('Публикации — по году издания, доклады — по дате конференции, РИД — по дате регистрации, '
             'достижения и защиты — по дате, НИОКР — если сроки работы пересекаются с периодом.')

    def build(self, person, form):
        return build_work_report(person, form.period)

    def document(self, report, user):
        return work_document(report, user.get_username())

    def filenames(self, report):
        return work_filenames(report)


class PlanReportView(PersonReportView):
    name = 'plan'
    form_class = PlanReportForm
    page_title = 'Отчёт о выполнении индивидуального плана'
    intro = 'Просроченный этап — запланированный или выполняемый этап, плановый срок которого прошёл.'

    def initial(self):
        return {}  # весь срок обучения

    def get_form(self, data, people, person=None, require_person=False):
        return self.form_class(data, people=people, require_person=require_person, adjunct=person)

    def build(self, person, form):
        return build_plan_report(person, form.cleaned_data['study_year'])

    def document(self, report, user):
        return plan_document(report, user.get_username())

    def filenames(self, report):
        return plan_filenames(report)


class SupervisionReportView(PersonReportView):
    name = 'supervision'
    form_class = SupervisionReportForm
    page_title = 'Отчёт о работе с подопечными'
    intro = ('Труды и достижения подопечных — за период; открытые и просроченные задачи и выполнение плана '
             'адъюнктов — на сегодня.')

    def build(self, person, form):
        return build_supervision_report(person, form.period, form.cleaned_data['include_finished'])

    def document(self, report, user):
        return supervision_document(report, user.get_username())

    def filenames(self, report):
        return supervision_filenames(report)


class DepartmentReportView(LoginRequiredMixin, DocumentPageMixin, View):
    """Отчёт о НИР кафедры: редакторам и суперпользователю, остальным — 403."""

    page_title = 'Отчёт о НИР кафедры'
    intro = ('Консолидированный вид — показатели по разделам, годам и людям; подробный — перечни записей, '
             'из которых показатели получены. Правила подсчёта — в конце отчёта.')

    def get(self, request):
        if not is_report_editor(request.user):
            raise PermissionDenied
        year = Period.current().year_from
        data = request.GET if 'submitted' in request.GET else {
            'view': SUMMARY, 'year_from': year, 'year_to': year,
            'sections': [key for key, _ in DEPARTMENT_SECTIONS],
            'categories': [key for key, _ in PEOPLE_CATEGORIES],
        }
        form = DepartmentReportForm(data)
        if not form.is_valid():
            return self.render_document(None, None, form=form)
        data = form.cleaned_data
        report = build_department_report(form.period, data['view'], data['sections'], data['categories'],
                                         data['include_inactive'])
        return self.render_document(department_document(report, request.user.get_username()),
                                    department_filenames(report), form=form)


class PersonCardView(LoginRequiredMixin, DocumentPageMixin, View):
    """Карточка человека для печати: сам человек, его научный руководитель, редактор; остальным — 404."""

    page_title = 'Карточка для печати'

    def get(self, request, kind, pk):
        person = get_report_person(kind, pk)
        if not can_view_person_report(request.user, person):
            raise Http404
        own = get_person(request.user) == person
        document = person_card(person, show_account=is_report_editor(request.user) or own,
                               author=request.user.get_username())
        return self.render_document(document, card_filenames(person), person=person)


class AccountCardView(LoginRequiredMixin, DocumentPageMixin, View):
    """Карточка учётной записи: своя — любому вошедшему, чужая — только суперпользователю (иначе 404)."""

    page_title = 'Моя учётная запись'

    def get(self, request, pk=None):
        account = request.user
        if pk is not None and pk != request.user.pk:
            if not request.user.is_superuser:
                raise Http404
            account = get_object_or_404(get_user_model(), pk=pk)
            self.page_title = 'Карточка учётной записи'
        document = account_card(account, author=request.user.get_username())
        return self.render_document(document, account_filenames(account), account=account)
