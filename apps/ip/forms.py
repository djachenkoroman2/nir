from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput
from apps.staff.forms import author_formset_factory

from .models import IntellectualProperty, IntellectualPropertyAuthor


class IntellectualPropertyForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = IntellectualProperty
        fields = ['kind', 'title', 'number', 'application_date', 'registration_date', 'holder', 'url', 'project']
        widgets = {
            'application_date': DateInput(),
            'registration_date': DateInput(),
        }


IntellectualPropertyAuthorFormSet = author_formset_factory(IntellectualProperty, IntellectualPropertyAuthor)
