from django import forms

from .models import Tournament


class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = [
            'ground',
            'title',
            'description',
            'start_date',
            'end_date',
            'start_time',
            'registration_deadline',
            'entry_fee',
            'prize_details',
            'max_teams',
            'contact_name',
            'contact_phone',
            'rules',
            'status',
            'is_published',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'registration_deadline': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'rules': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop('owner', None)
        super().__init__(*args, **kwargs)
        if owner is not None:
            self.fields['ground'].queryset = self.fields['ground'].queryset.filter(owner=owner)

        for field in self.fields.values():
            css_class = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-control'
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} {css_class}'.strip()
        self.fields['ground'].widget.attrs['class'] = 'form-select'
        self.fields['status'].widget.attrs['class'] = 'form-select'

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        registration_deadline = cleaned_data.get('registration_deadline')

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'End date cannot be before start date.')
        if registration_deadline and start_date and registration_deadline > start_date:
            self.add_error('registration_deadline', 'Registration deadline cannot be after the tournament start date.')
        return cleaned_data
