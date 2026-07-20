from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename
from pathlib import Path
import uuid
from .models import User
from grounds.models import Ground, GroundPricing


class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")

    class Meta:
        model = User
        fields = [
            'name',
            'email',
            'phone_number',
            'notify_price_drops',
            'notify_last_minute',
            'notify_nearby_tournaments',
            'email_alerts',
            'push_alerts',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '9999999999'}),
            'notify_price_drops': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_last_minute': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_nearby_tournaments': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_alerts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'push_alerts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone_number'].help_text = 'Enter your 10-digit mobile number without +91'

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        email = cleaned_data.get('email')
        phone = cleaned_data.get('phone_number')

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Passwords don't match")

        # Strip any +91 from phone if accidentally entered
        if phone:
            cleaned_data['phone_number'] = phone.lstrip('+').lstrip('91').strip()

        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.strip().lower()
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            phone = phone.strip()
            # Remove +91 or 91 prefix if accidentally entered
            if phone.startswith('+91'):
                phone = phone[3:]
            elif phone.startswith('91') and len(phone) > 10:
                phone = phone[2:]
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'customer'  # Default role for self-registration
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user
# Note: field order changed — name, email, phone_number (moved name to top)


class GroundOwnerCreationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")

    class Meta:
        model = User
        fields = ['email', 'phone_number', 'name']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Passwords don't match")

        return cleaned_data

    def clean_referral_code(self):
        referral_code = (self.cleaned_data.get('referral_code') or '').strip()
        if referral_code and not User.objects.filter(referral_code=referral_code).exists():
            raise forms.ValidationError("Referral code not found.")
        return referral_code

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'owner'  # Admin creates ground owners
        user.email_verified = True  # Admin-created accounts are pre-verified
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class GroundCreationForm(forms.ModelForm):
    image_upload = forms.ImageField(label="Ground Photo", required=False)

    for index in range(1, 5):
        locals()[f"slot_{index}_start"] = forms.TimeField(
            label=f"Rate {index} Start Time",
            required=False,
            widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        )
        locals()[f"slot_{index}_end"] = forms.TimeField(
            label=f"Rate {index} End Time",
            required=False,
            widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        )
        locals()[f"slot_{index}_price"] = forms.DecimalField(
            label=f"Rate {index} Price (₹)",
            required=False,
            max_digits=8,
            decimal_places=2,
            min_value=1,
        )
    del index

    class Meta:
        model = Ground
        fields = ['name', 'location', 'opening_time', 'closing_time']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'opening_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'closing_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.owner = kwargs.pop('owner', None)
        super().__init__(*args, **kwargs)
        self.fields['opening_time'].initial = '06:00'
        self.fields['closing_time'].initial = '02:00'
        self.fields['slot_1_start'].initial = '06:00'
        self.fields['slot_1_end'].initial = '02:00'
        self.fields['slot_1_price'].initial = 1000
        self.fields['image_upload'].widget.attrs.update({'class': 'form-control', 'accept': 'image/*'})
        for index in range(1, 5):
            self.fields[f'slot_{index}_price'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Example: 1000',
                'step': '1',
            })

    @staticmethod
    def _minutes_from_opening(value, opening_time):
        minutes = value.hour * 60 + value.minute
        opening_minutes = opening_time.hour * 60 + opening_time.minute
        if minutes < opening_minutes:
            minutes += 24 * 60
        return minutes

    def _rate_blocks_from_cleaned_data(self):
        blocks = []
        opening_time = self.cleaned_data.get('opening_time')
        closing_time = self.cleaned_data.get('closing_time')
        if not opening_time or not closing_time:
            return blocks

        open_minute = self._minutes_from_opening(opening_time, opening_time)
        close_minute = self._minutes_from_opening(closing_time, opening_time)
        if close_minute <= open_minute:
            close_minute += 24 * 60

        for index in range(1, 5):
            start = self.cleaned_data.get(f'slot_{index}_start')
            end = self.cleaned_data.get(f'slot_{index}_end')
            price = self.cleaned_data.get(f'slot_{index}_price')
            provided = [start is not None, end is not None, price is not None]
            if any(provided) and not all(provided):
                raise forms.ValidationError(f'Complete start, end, and price for rate {index}, or leave it blank.')
            if not all(provided):
                continue

            start_minute = self._minutes_from_opening(start, opening_time)
            end_minute = self._minutes_from_opening(end, opening_time)
            if end_minute <= start_minute:
                end_minute += 24 * 60
            if start_minute < open_minute or end_minute > close_minute:
                raise forms.ValidationError(f'Rate {index} must stay within the ground operating hours.')
            blocks.append({
                'index': index,
                'start': start,
                'end': end,
                'price': int(price),
                'start_minute': start_minute,
                'end_minute': end_minute,
            })

        if not blocks:
            raise forms.ValidationError('Add at least one rate block for this ground.')

        sorted_blocks = sorted(blocks, key=lambda block: block['start_minute'])
        if sorted_blocks[0]['start_minute'] != open_minute:
            raise forms.ValidationError('The first rate block must start at the opening time.')
        if sorted_blocks[-1]['end_minute'] != close_minute:
            raise forms.ValidationError('The last rate block must end at the closing time.')
        previous = None
        for block in sorted_blocks:
            if previous and block['start_minute'] != previous['end_minute']:
                if block['start_minute'] < previous['end_minute']:
                    raise forms.ValidationError('Rate blocks cannot overlap.')
                raise forms.ValidationError('Rate blocks must connect without gaps.')
            if previous and block['start_minute'] < previous['end_minute']:
                raise forms.ValidationError('Rate blocks cannot overlap.')
            previous = block
        return sorted_blocks

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('opening_time') and cleaned_data.get('closing_time'):
            self.pricing_blocks = self._rate_blocks_from_cleaned_data()
        return cleaned_data

    def save(self, commit=True):
        ground = super().save(commit=False)
        if self.owner:
            ground.owner = self.owner
        pricing_blocks = getattr(self, 'pricing_blocks', [])
        base_price = pricing_blocks[0]['price'] if pricing_blocks else 1
        night_block = next((block for block in pricing_blocks if block['start'].hour >= 18 or block['start'].hour < 6), None)
        ground.day_price = base_price
        ground.night_price = night_block['price'] if night_block else base_price
        if commit:
            ground.save()
            self.save_image(ground)
            self.save_pricing_blocks(ground)
        return ground

    def save_image(self, ground):
        image = self.cleaned_data.get('image_upload')
        if not image:
            return
        filename = get_valid_filename(Path(image.name).name)
        path = default_storage.save(f'grounds/{uuid.uuid4().hex}_{filename}', image)
        ground.image = f'{settings.MEDIA_URL}{path}'
        ground.save(update_fields=['image'])

    def save_pricing_blocks(self, ground):
        GroundPricing.objects.filter(ground=ground).delete()
        GroundPricing.objects.bulk_create([
            GroundPricing(
                ground=ground,
                start_time=block['start'],
                end_time=block['end'],
                price_per_hour=block['price'],
            )
            for block in getattr(self, 'pricing_blocks', [])
        ])


class UserLoginForm(forms.Form):
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'placeholder': 'Enter your email', 'class': 'form-control'})
    )
    phone = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Enter your phone number', 'class': 'form-control'})
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        phone = cleaned_data.get('phone')

        if not email and not phone:
            raise forms.ValidationError("Please enter either email or phone number")

        if email and phone:
            raise forms.ValidationError("Please enter either email or phone number, not both")

        return cleaned_data


class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'notify_price_drops',
            'notify_last_minute',
            'notify_nearby_tournaments',
            'email_alerts',
            'push_alerts',
        ]
        widgets = {
            'notify_price_drops': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_last_minute': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_nearby_tournaments': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_alerts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'push_alerts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
