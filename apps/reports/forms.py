from django import forms

from apps.activity.models import ActivityLog
from apps.core.forms import BootstrapFormMixin

from .activity import CATEGORIES
from .department import SECTION_CHOICES as DEPARTMENT_SECTIONS
from .department import VIEWS as DEPARTMENT_VIEWS
from .form16 import SECTION_CHOICES, person_kind
from .works import PEOPLE_CATEGORIES, Period

YEAR = {'min_value': 1900, 'max_value': 2100, 'required': False}


class Form16Form(BootstrapFormMixin, forms.Form):
    """Параметры формы № 16. Пустой период — все годы; по умолчанию включены все разделы."""

    person = forms.ChoiceField(label='На кого', required=False)
    year_from = forms.IntegerField(label='Год с', **YEAR)
    year_to = forms.IntegerField(label='Год по', **YEAR)
    sections = forms.MultipleChoiceField(
        label='Разделы', choices=SECTION_CHOICES, required=False, widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, people=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person'].choices = [(self.person_value(person), str(person.full_name)) for person in people]
        if len(people) < 2:
            del self.fields['person']

    @staticmethod
    def person_value(person):
        return f'{person_kind(person)}-{person.pk}'

    def clean(self):
        data = super().clean()
        if data.get('year_from') and data.get('year_to') and data['year_from'] > data['year_to']:
            raise forms.ValidationError('Год «с» не может быть больше года «по».')
        if not data.get('sections'):
            raise forms.ValidationError('Выберите хотя бы один раздел.')
        return data


class DateTimeInput(forms.DateTimeInput):
    input_type = 'datetime-local'

    def __init__(self, attrs=None):
        super().__init__(attrs, format='%Y-%m-%dT%H:%M')


class ActivityReportForm(BootstrapFormMixin, forms.Form):
    """Параметры отчёта об активности: период с точностью до минуты, категории, пользователи без активности."""

    start = forms.DateTimeField(label='С', widget=DateTimeInput(), input_formats=['%Y-%m-%dT%H:%M'])
    end = forms.DateTimeField(label='По', widget=DateTimeInput(), input_formats=['%Y-%m-%dT%H:%M'])
    categories = forms.MultipleChoiceField(
        label='Категории', choices=CATEGORIES, required=False, widget=forms.CheckboxSelectMultiple,
    )
    show_inactive = forms.BooleanField(label='Показывать пользователей без активности', required=False)

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('Начало периода не может быть позже конца.')
        if not data.get('categories'):
            data['categories'] = [key for key, _ in CATEGORIES]  # ничего не выбрано — все категории
        return data


class UserLogForm(BootstrapFormMixin, forms.Form):
    start = forms.DateTimeField(label='С', widget=DateTimeInput(), input_formats=['%Y-%m-%dT%H:%M'])
    end = forms.DateTimeField(label='По', widget=DateTimeInput(), input_formats=['%Y-%m-%dT%H:%M'])
    action = forms.ChoiceField(label='Действие', required=False,
                               choices=[('', 'Все действия'), *ActivityLog.Action.choices])


KIND_TITLES = {'teacher': 'преподаватель', 'adjunct': 'адъюнкт', 'student': 'курсант'}


class PersonReportForm(BootstrapFormMixin, forms.Form):
    """Параметры отчёта о человеке: выбор человека — только тем, кому доступны отчёты на нескольких людей."""

    person = forms.ChoiceField(label='На кого', required=False)

    def __init__(self, *args, people=(), require_person=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['person'].choices = [
            *([('', '— выберите —')] if require_person else []),
            *((Form16Form.person_value(person), f'{person.full_name} ({KIND_TITLES[person_kind(person)]})')
              for person in people),
        ]
        self.fields['person'].required = require_person
        if len(people) < 2 and not require_person:
            del self.fields['person']



class PeriodFormMixin(forms.Form):
    """Период «год с — по»: у публикаций есть только год издания, поэтому период задаётся годами."""

    year_from = forms.IntegerField(label='Год с', min_value=1900, max_value=2100)
    year_to = forms.IntegerField(label='Год по', min_value=1900, max_value=2100)

    def clean(self):
        data = super().clean()
        if data.get('year_from') and data.get('year_to') and data['year_from'] > data['year_to']:
            raise forms.ValidationError('Год «с» не может быть больше года «по».')
        return data

    @property
    def period(self):
        return Period(self.cleaned_data['year_from'], self.cleaned_data['year_to'])


class WorkReportForm(PeriodFormMixin, PersonReportForm):
    field_order = ['person', 'year_from', 'year_to']


class SupervisionReportForm(PeriodFormMixin, PersonReportForm):
    include_finished = forms.BooleanField(label='Включать выпущенных и отчисленных подопечных', required=False)
    field_order = ['person', 'year_from', 'year_to', 'include_finished']


class PlanReportForm(PersonReportForm):
    study_year = forms.TypedChoiceField(label='Год обучения', required=False, coerce=int, empty_value=None)

    def __init__(self, *args, adjunct=None, **kwargs):
        super().__init__(*args, **kwargs)
        years = adjunct.study_years if adjunct is not None else 6
        self.fields['study_year'].choices = [('', 'весь срок обучения'),
                                             *((year, f'{year}-й год') for year in range(1, years + 1))]


class DepartmentReportForm(PeriodFormMixin, BootstrapFormMixin, forms.Form):
    view = forms.ChoiceField(label='Вид отчёта', choices=DEPARTMENT_VIEWS, widget=forms.RadioSelect)
    sections = forms.MultipleChoiceField(
        label='Разделы', choices=DEPARTMENT_SECTIONS, required=False, widget=forms.CheckboxSelectMultiple,
    )
    categories = forms.MultipleChoiceField(
        label='Категории людей', choices=PEOPLE_CATEGORIES, required=False, widget=forms.CheckboxSelectMultiple,
        help_text='Ничего не выбрано — все категории.',
    )
    include_inactive = forms.BooleanField(
        label='Учитывать неработающих, выпущенных и отчисленных (в таблице по людям)', required=False,
    )
    field_order = ['view', 'year_from', 'year_to', 'sections', 'categories', 'include_inactive']

    def clean(self):
        data = super().clean()
        if not data.get('sections'):
            raise forms.ValidationError('Выберите хотя бы один раздел.')
        if not data.get('categories'):
            data['categories'] = [key for key, _ in PEOPLE_CATEGORIES]  # ничего не выбрано — все категории
        return data
