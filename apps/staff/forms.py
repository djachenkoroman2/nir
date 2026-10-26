from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import Teacher


class TeacherForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Teacher
        fields = [
            'last_name', 'first_name', 'middle_name', 'position', 'degree', 'academic_title',
            'email', 'phone', 'is_active', 'user',
        ]
