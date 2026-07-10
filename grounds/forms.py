from django import forms

from .models import Tournament


class TournamentForm(forms.ModelForm):
    category_fees_text = forms.CharField(
        required=False,
        label='Categories and Fees',
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Men Open | 500\nWomen Open | 300'}),
        help_text='One category per line, using "Category | Fee".'
    )

    class Meta:
        model = Tournament
        fields = [
            'ground',
            'image',
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
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
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
        if owner is not None and getattr(owner, 'role', None) == 'owner':
            self.fields['ground'].queryset = self.fields['ground'].queryset.filter(owner=owner)

        if self.instance and self.instance.pk and self.instance.category_fees:
            lines = []
            for item in self.instance.category_fees:
                name = item.get('name', '').strip()
                fee = item.get('fee', '')
                if name:
                    lines.append(f'{name} | {fee}')
            self.fields['category_fees_text'].initial = '\n'.join(lines)

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

        category_fees_text = (cleaned_data.get('category_fees_text') or '').strip()
        category_fees = []
        if category_fees_text:
            for line in category_fees_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if '|' not in line:
                    self.add_error('category_fees_text', 'Use "Category | Fee" on each line.')
                    break
                name, fee = [part.strip() for part in line.split('|', 1)]
                if not name:
                    self.add_error('category_fees_text', 'Each category needs a name.')
                    break
                try:
                    fee_value = int(float(fee))
                except (TypeError, ValueError):
                    self.add_error('category_fees_text', 'Category fees must be numbers.')
                    break
                category_fees.append({'name': name, 'fee': fee_value})
        cleaned_data['category_fees'] = category_fees
        return cleaned_data

    def save(self, commit=True):
        tournament = super().save(commit=False)
        tournament.category_fees = self.cleaned_data.get('category_fees', [])
        if commit:
            tournament.save()
        return tournament
