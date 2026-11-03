from django import forms

from apps.core.forms import BootstrapFormMixin, DateInput

from .models import CooperationContract


class CooperationContractForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CooperationContract
        fields = ['title', 'number', 'organization', 'subject', 'start_date', 'end_date']
        widgets = {
            'subject': forms.Textarea(attrs={'rows': 5}),
            'start_date': DateInput(),
            'end_date': DateInput(),
        }
