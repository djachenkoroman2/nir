from django import forms
from django.core.exceptions import ValidationError

from apps.core.forms import BootstrapFormMixin
from apps.students.models import Student

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


def student_choices(current_student_id=None):
    """Курсанты, кроме отчисленных; уже выбранный (даже если отчислен) остаётся в списке."""
    students = Student.objects.exclude(status=Student.Status.EXPELLED)
    if current_student_id:
        students = students | Student.objects.filter(pk=current_student_id)
    return students.distinct()


class AuthorForm(BootstrapFormMixin, forms.ModelForm):
    """Строка формсета авторов: преподаватель кафедры, курсант или внешний автор."""

    class Meta:
        fields = ['teacher', 'student', 'external_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = teacher_choices(self.instance.teacher_id)
        self.fields['teacher'].empty_label = '— преподаватель —'
        self.fields['student'].queryset = student_choices(self.instance.student_id)
        self.fields['student'].empty_label = '— курсант —'
        self.fields['external_name'].widget.attrs['placeholder'] = 'или ФИО внешнего автора'

    def has_changed(self):
        # Новая строка заполнена, если выбран преподаватель или курсант или вписано ФИО. Сравнение
        # с initial не подходит: строку, заранее заполненную текущим преподавателем, Django счёл бы пустой.
        if self.instance.pk or not self.is_bound:
            return super().has_changed()
        return bool(
            self['teacher'].value() or self['student'].value() or (self['external_name'].value() or '').strip()
        )


class BaseAuthorFormSet(forms.BaseInlineFormSet):
    """Проверяет, что указан хотя бы один автор, а преподаватели и курсанты не повторяются; сохраняет порядок строк."""

    empty_error = 'Укажите хотя бы одного автора.'
    missing_teacher_error = 'Укажите среди авторов себя: иначе вы не сможете изменять эту запись.'

    def __init__(self, *args, required_teacher=None, **kwargs):
        # required_teacher — преподаватель, который обязан остаться среди авторов (не редактор).
        self.required_teacher = required_teacher
        if required_teacher is not None and not getattr(kwargs.get('instance'), 'pk', None):
            kwargs.setdefault('initial', [{'teacher': required_teacher.pk}])
        super().__init__(*args, **kwargs)

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
        students = [form.cleaned_data['student'] for form in forms_ if form.cleaned_data.get('student')]
        if len(students) != len(set(students)):
            raise ValidationError('Один и тот же курсант указан несколько раз.')
        if self.required_teacher is not None and self.required_teacher not in teachers:
            raise ValidationError(self.missing_teacher_error)

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
