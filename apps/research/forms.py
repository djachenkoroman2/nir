from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput
from apps.staff.models import Teacher

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
        # Новых участников выбираем из работающих; уже добавленный уволенный остаётся в списке.
        teachers = Teacher.objects.filter(is_active=True)
        if self.instance.pk:
            teachers = teachers | Teacher.objects.filter(pk=self.instance.teacher_id)
        self.fields['teacher'].queryset = teachers.distinct()


ParticipantFormSet = forms.inlineformset_factory(
    ResearchProject,
    Participant,
    form=ParticipantForm,
    extra=2,
    can_delete=True,
)
