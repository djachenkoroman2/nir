from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput
from apps.staff.forms import teacher_choices
from apps.staff.models import Teacher

from .models import DissertationDefense, ScientificSchool


class SchoolForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ScientificSchool
        fields = ['name', 'description', 'leaders', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'leaders': forms.SelectMultiple(attrs={'size': 8}),
        }
        help_texts = {
            'leaders': 'Удерживайте Ctrl (на Mac — Cmd), чтобы выбрать несколько.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        leaders = Teacher.objects.filter(is_active=True)
        if self.instance.pk:
            leaders = leaders | self.instance.leaders.all()
        self.fields['leaders'].queryset = leaders.distinct()


class DissertationDefenseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DissertationDefense
        fields = ['full_name', 'teacher', 'adjunct', 'kind', 'title', 'defense_date', 'school', 'supervisor']
        widgets = {'defense_date': DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supervisor'].queryset = teacher_choices(self.instance.supervisor_id)


def school_choices(instance):
    """Действующие школы для поля «научные школы»; уже выбранные (даже если не действуют) остаются."""
    schools = ScientificSchool.objects.filter(is_active=True)
    if instance.pk:
        schools = schools | instance.schools.all()
    return schools.distinct()
