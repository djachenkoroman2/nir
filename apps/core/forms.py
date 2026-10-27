from django import forms


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
