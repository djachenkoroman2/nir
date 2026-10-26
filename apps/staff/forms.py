from django import forms
from django.core.exceptions import ValidationError

from apps.core.forms import BootstrapFormMixin

from .models import Teacher


class TeacherForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Teacher
        fields = [
            'last_name', 'first_name', 'middle_name', 'position', 'degree', 'academic_title',
            'email', 'phone', 'is_active', 'user',
        ]


def teacher_choices(current_teacher_id=None):
    """Работающие преподаватели; уже выбранный (даже если уволен) остаётся в списке."""
    teachers = Teacher.objects.filter(is_active=True)
    if current_teacher_id:
        teachers = teachers | Teacher.objects.filter(pk=current_teacher_id)
    return teachers.distinct()


class AuthorForm(BootstrapFormMixin, forms.ModelForm):
    """Строка формсета авторов: преподаватель кафедры или внешний автор."""

    class Meta:
        fields = ['teacher', 'external_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = teacher_choices(self.instance.teacher_id)
        self.fields['teacher'].empty_label = '— внешний автор —'
        self.fields['external_name'].widget.attrs['placeholder'] = 'ФИО внешнего автора'


class BaseAuthorFormSet(forms.BaseInlineFormSet):
    """Проверяет, что указан хотя бы один автор и преподаватели не повторяются; сохраняет порядок строк."""

    empty_error = 'Укажите хотя бы одного автора.'

    def _kept_forms(self):
        for form in self.forms:
            if not form.has_changed() and not form.instance.pk:
                continue
            if self.can_delete and self._should_delete_form(form):
                continue
            yield form

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        forms_ = list(self._kept_forms())
        if not forms_:
            raise ValidationError(self.empty_error)
        teachers = [form.cleaned_data['teacher'] for form in forms_ if form.cleaned_data.get('teacher')]
        if len(teachers) != len(set(teachers)):
            raise ValidationError('Один и тот же преподаватель указан несколько раз.')

    def save(self, commit=True):
        saved = super().save(commit)
        if commit:
            for position, form in enumerate(self._kept_forms(), start=1):
                if form.instance.pk and form.instance.order != position:
                    type(form.instance).objects.filter(pk=form.instance.pk).update(order=position)
                    form.instance.order = position
        return saved


def author_formset_factory(parent_model, model, **kwargs):
    kwargs.setdefault('extra', 1)
    return forms.inlineformset_factory(
        parent_model, model, form=AuthorForm, formset=BaseAuthorFormSet, can_delete=True, **kwargs
    )
