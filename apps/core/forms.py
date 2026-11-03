from django import forms
from django.db import transaction

from .permissions import get_person


class BootstrapFormMixin:
    """Добавляет полям формы CSS-классы Bootstrap."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                css_class = 'form-check-input'
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css_class = 'form-select'
            else:
                css_class = 'form-control'
            widget.attrs['class'] = f"{widget.attrs.get('class', '')} {css_class}".strip()


class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, attrs=None):
        super().__init__(attrs, format='%Y-%m-%d')


class ProfileForm(BootstrapFormMixin, forms.Form):
    """Личные сведения пользователя и привязанной карточки, без служебных полей и прав."""

    last_name = forms.CharField(label='Фамилия', max_length=100)
    first_name = forms.CharField(label='Имя', max_length=100)
    middle_name = forms.CharField(label='Отчество', max_length=100, required=False)
    email = forms.EmailField(label='E-mail', max_length=254, required=False)
    phone = forms.CharField(label='Телефон', max_length=30, required=False)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        self.person = get_person(user)
        person = self.person
        initial = {
            'last_name': person.last_name if person else user.last_name,
            'first_name': person.first_name if person else user.first_name,
            'email': getattr(person, 'email', user.email) if person else user.email,
        }
        if person is not None:
            initial['middle_name'] = person.middle_name
            if hasattr(person, 'phone'):
                initial['phone'] = person.phone
        kwargs.setdefault('initial', initial)
        super().__init__(*args, **kwargs)
        if person is None:
            del self.fields['middle_name']
        if person is None or not hasattr(person, 'phone'):
            del self.fields['phone']

    def save(self):
        data = self.cleaned_data
        person = self.person
        person_fields = []
        if person is not None:
            for field in ('last_name', 'first_name', 'middle_name'):
                if field in self.fields:
                    setattr(person, field, data[field])
                    person_fields.append(field)
            for field in ('email', 'phone'):
                if field in self.fields and hasattr(person, field):
                    setattr(person, field, data[field])
                    person_fields.append(field)
            person.full_clean()

        user = self.user
        user.last_name = data['last_name']
        user.first_name = data['first_name']
        user.email = data['email']
        user.full_clean()
        with transaction.atomic():
            if person is not None:
                person.save(update_fields=person_fields)
            user.save(update_fields=['last_name', 'first_name', 'email'])
        return user
