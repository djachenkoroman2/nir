from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput
from apps.staff.forms import teacher_choices

from .models import Student, StudentAchievement


class StudentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Student
        fields = ['last_name', 'first_name', 'middle_name', 'group', 'course', 'supervisor', 'status', 'note']
        widgets = {'note': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supervisor'].queryset = teacher_choices(self.instance.supervisor_id)


class StudentAchievementForm(BootstrapFormMixin, forms.ModelForm):
    """Достижение курсанта; сам курсант задаётся из адреса страницы и в форме не меняется."""

    class Meta:
        model = StudentAchievement
        fields = ['kind', 'level', 'title', 'result', 'date', 'supervisor', 'document']
        widgets = {'date': DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supervisor'].queryset = teacher_choices(self.instance.supervisor_id)
