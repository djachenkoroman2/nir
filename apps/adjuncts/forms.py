from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput
from apps.staff.forms import teacher_choices

from .models import Adjunct, AdjunctAchievement, PlanStage, Task, TaskComment


class AdjunctForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Adjunct
        fields = [
            'last_name', 'first_name', 'middle_name', 'dissertation_topic', 'specialty', 'admission_year',
            'study_form', 'study_years', 'supervisor', 'school', 'status', 'planned_defense_year',
            'email', 'phone', 'user',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supervisor'].queryset = teacher_choices(self.instance.supervisor_id)


class SupervisorAdjunctForm(AdjunctForm):
    """Карточка адъюнкта для научного руководителя: учётную запись привязывает только редактор."""

    class Meta(AdjunctForm.Meta):
        fields = [field for field in AdjunctForm.Meta.fields if field != 'user']


class AdjunctContactsForm(BootstrapFormMixin, forms.ModelForm):
    """Что адъюнкт может изменить в своей карточке сам."""

    class Meta:
        model = Adjunct
        fields = ['email', 'phone']


class AdjunctAchievementForm(BootstrapFormMixin, forms.ModelForm):
    """Достижение адъюнкта; сам адъюнкт задаётся из адреса страницы и в форме не меняется."""

    class Meta:
        model = AdjunctAchievement
        fields = ['kind', 'level', 'title', 'result', 'date', 'document']
        widgets = {'date': DateInput()}


class PlanStageForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PlanStage
        fields = ['study_year', 'kind', 'title', 'due_date', 'status', 'completed_date', 'supervisor_note']
        widgets = {
            'due_date': DateInput(),
            'completed_date': DateInput(),
            'supervisor_note': forms.Textarea(attrs={'rows': 2}),
        }


class TaskForm(BootstrapFormMixin, forms.ModelForm):
    """Задача; статус меняется отдельными кнопками на странице задачи, чтобы смена попадала в ленту."""

    class Meta:
        model = Task
        fields = ['title', 'description', 'due_date', 'priority', 'plan_stage']
        widgets = {'due_date': DateInput(), 'description': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, owner, **kwargs):
        """owner — исполнитель: адъюнкт или курсант (у курсанта нет плана работы)."""
        super().__init__(*args, **kwargs)
        if isinstance(owner, Adjunct):
            self.instance.adjunct = owner
            self.fields['plan_stage'].queryset = owner.plan_stages.all()
        else:
            self.instance.student = owner
            del self.fields['plan_stage']


class TaskCommentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ['text']
        widgets = {'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Комментарий'})}
        labels = {'text': 'Новый комментарий'}
