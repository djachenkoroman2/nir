from django import forms

from apps.core.forms import BootstrapFormMixin

from .form16 import SECTION_CHOICES, person_kind

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
