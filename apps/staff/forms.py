from django import forms
from django.core.exceptions import ValidationError

from apps.adjuncts.models import Adjunct
from apps.core.forms import BootstrapFormMixin
from apps.students.models import Student

from .models import Teacher, author_lookup


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


def adjunct_choices(current_adjunct_id=None):
    """Адъюнкты, кроме отчисленных; уже выбранный (даже если отчислен) остаётся в списке."""
    adjuncts = Adjunct.objects.exclude(status=Adjunct.Status.EXPELLED)
    if current_adjunct_id:
        adjuncts = adjuncts | Adjunct.objects.filter(pk=current_adjunct_id)
    return adjuncts.distinct()


# Поля строки автора, которые выбирают человека кафедры, и сообщения о его повторе.
PERSON_FIELDS = {
    'teacher': 'Один и тот же преподаватель указан несколько раз.',
    'student': 'Один и тот же курсант указан несколько раз.',
    'adjunct': 'Один и тот же адъюнкт указан несколько раз.',
}


class AuthorForm(BootstrapFormMixin, forms.ModelForm):
    """Строка формсета авторов: преподаватель кафедры, курсант, адъюнкт или внешний автор."""

    class Meta:
        fields = ['teacher', 'student', 'adjunct', 'external_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = teacher_choices(self.instance.teacher_id)
        self.fields['teacher'].empty_label = '— преподаватель —'
        self.fields['student'].queryset = student_choices(self.instance.student_id)
        self.fields['student'].empty_label = '— курсант —'
        self.fields['adjunct'].queryset = adjunct_choices(self.instance.adjunct_id)
        self.fields['adjunct'].empty_label = '— адъюнкт —'
        self.fields['external_name'].widget.attrs['placeholder'] = 'или ФИО внешнего автора'

    def has_changed(self):
        # Новая строка заполнена, если выбран человек кафедры или вписано ФИО. Сравнение с initial
        # не подходит: строку, заранее заполненную текущим пользователем, Django счёл бы пустой.
        if self.instance.pk or not self.is_bound:
            return super().has_changed()
        external_name = (self['external_name'].value() or '').strip()
        return any(self[field].value() for field in PERSON_FIELDS) or bool(external_name)


class BaseAuthorFormSet(forms.BaseInlineFormSet):
    """Проверяет, что указан хотя бы один автор, а люди кафедры не повторяются; сохраняет порядок строк."""

    empty_error = 'Укажите хотя бы одного автора.'
    missing_author_error = 'Укажите среди авторов себя: иначе вы не сможете изменять эту запись.'

    def __init__(self, *args, required_author=None, **kwargs):
        # required_author — преподаватель или адъюнкт, который обязан остаться среди авторов (не редактор).
        self.required_author = required_author
        if required_author is not None and not getattr(kwargs.get('instance'), 'pk', None):
            [(field, person)] = author_lookup(required_author).items()
            kwargs.setdefault('initial', [{field: person.pk}])
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
        people = set()
        for field, duplicate_error in PERSON_FIELDS.items():
            chosen = [form.cleaned_data[field] for form in forms_ if form.cleaned_data.get(field)]
            if len(chosen) != len(set(chosen)):
                raise ValidationError(duplicate_error)
            people.update(chosen)
        if self.required_author is not None and self.required_author not in people:
            raise ValidationError(self.missing_author_error)

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
