from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput
from apps.staff.forms import teacher_choices

from .models import Participant, ResearchProject


class ResearchProjectForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ResearchProject
        fields = ['title', 'start_date', 'end_date', 'status']
        widgets = {
            'start_date': DateInput(),
            'end_date': DateInput(),
        }


class ParticipantForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Participant
        fields = ['teacher', 'role']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = teacher_choices(self.instance.teacher_id)


ParticipantFormSet = forms.inlineformset_factory(
    ResearchProject,
    Participant,
    form=ParticipantForm,
    extra=2,
    can_delete=True,
)
