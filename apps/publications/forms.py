from django import forms

from apps.core.forms import BootstrapFormMixin
from apps.schools.forms import school_choices
from apps.staff.forms import author_formset_factory

from .models import Publication, PublicationAuthor


class PublicationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Publication
        fields = [
            'kind', 'title', 'year', 'source', 'volume', 'issue', 'pages', 'print_sheets', 'work_form', 'doi', 'url',
            'vak', 'rinc', 'rinc_core', 'scopus', 'wos', 'quartile', 'project', 'schools',
        ]
        widgets = {'schools': forms.CheckboxSelectMultiple}

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('rinc_core'):
            cleaned_data['rinc'] = True
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['schools'].queryset = school_choices(self.instance)
        # Не указана форма работы — печатная (как у записей, внесённых до появления поля).
        self.fields['work_form'].required = False

    def clean_work_form(self):
        return self.cleaned_data['work_form'] or Publication.WorkForm.PRINTED


PublicationAuthorFormSet = author_formset_factory(Publication, PublicationAuthor)
