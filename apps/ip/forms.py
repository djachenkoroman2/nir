from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput
from apps.schools.forms import school_choices
from apps.staff.forms import author_formset_factory

from .models import IntellectualProperty, IntellectualPropertyAuthor


class IntellectualPropertyForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = IntellectualProperty
        fields = [
            'kind', 'title', 'number', 'application_date', 'registration_date', 'holder', 'url', 'project',
            'schools',
        ]
        widgets = {
            'application_date': DateInput(),
            'registration_date': DateInput(),
            'schools': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['schools'].queryset = school_choices(self.instance)


IntellectualPropertyAuthorFormSet = author_formset_factory(IntellectualProperty, IntellectualPropertyAuthor)
