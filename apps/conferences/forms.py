from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput
from apps.publications.models import Publication
from apps.staff.forms import author_formset_factory
from apps.staff.models import author_lookup

from .models import Conference, Report, ReportSpeaker


class ConferenceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Conference
        fields = ['title', 'level', 'location', 'start_date', 'end_date', 'url']
        widgets = {
            'start_date': DateInput(),
            'end_date': DateInput(),
        }


class ReportForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Report
        fields = ['title', 'form', 'publication']

    def __init__(self, *args, own_publications_of=None, **kwargs):
        """own_publications_of — человек в личном кабинете: ему предлагаются только его публикации."""
        super().__init__(*args, **kwargs)
        # Публикацию можно связать только с одним докладом: предлагаем свободные и уже выбранную.
        publications = Publication.objects.filter(report__isnull=True)
        if own_publications_of is not None:
            publications = publications.filter(**{f'authors__{key}': person for key, person in
                                                  author_lookup(own_publications_of).items()})
        if self.instance.publication_id:
            publications = publications | Publication.objects.filter(pk=self.instance.publication_id)
        self.fields['publication'].queryset = publications.distinct()


class ReportSpeakerFormSet(author_formset_factory(Report, ReportSpeaker)):
    empty_error = 'Укажите хотя бы одного докладчика.'
    missing_teacher_error = 'Укажите среди докладчиков себя: иначе вы не сможете изменять этот доклад.'


class ConferenceChoiceForm(BootstrapFormMixin, forms.Form):
    conference = forms.ModelChoiceField(
        Conference.objects.all(), label='Конференция', empty_label='— выберите мероприятие —',
    )
