from django import forms

from apps.core.forms import BootstrapFormMixin
from apps.staff.forms import author_formset_factory

from .models import Publication, PublicationAuthor


class PublicationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Publication
        fields = [
            'kind', 'title', 'year', 'source', 'volume', 'issue', 'pages', 'doi', 'url',
            'vak', 'rinc', 'rinc_core', 'scopus', 'wos', 'quartile', 'project',
        ]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('rinc_core'):
            cleaned_data['rinc'] = True
        return cleaned_data


PublicationAuthorFormSet = author_formset_factory(Publication, PublicationAuthor)
