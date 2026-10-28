from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from apps.core.permissions import get_person

from .access import can_view_person_report, form16_url, is_report_editor, report_people
from .docx_export import build_docx
from .form16 import SECTION_CHOICES, build_form16, get_report_person, person_kind
from .forms import Form16Form
from .registry import available_reports

DOCX_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


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


def docx_response(report):
    filename = docx_filename(report.person)
    response = HttpResponse(build_docx(report), content_type=DOCX_TYPE)
    fallback = f'form16_{person_kind(report.person)}_{report.person.pk}.docx'
    response['Content-Disposition'] = f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename)}'
    return response


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
            return docx_response(report)
    return render(request, 'reports/form16.html', {'form': form, 'report': report, 'person': person})
