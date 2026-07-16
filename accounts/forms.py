from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User
from grounds.models import Ground


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
    # Optional slot configuration fields (two ranges)
    slot_1_start = forms.TimeField(label="Slot 1 Start Time", required=False,
                                   widget=forms.TimeInput(attrs={'type': 'time'}),
                                   initial="06:00")
    slot_1_end = forms.TimeField(label="Slot 1 End Time", required=False,
                                 widget=forms.TimeInput(attrs={'type': 'time'}),
                                 initial="18:00")
    slot_1_price = forms.DecimalField(label="Slot 1 Price (₹)", required=False,
                                      max_digits=8, decimal_places=2, initial=500.00)

    slot_2_start = forms.TimeField(label="Slot 2 Start Time", required=False,
                                   widget=forms.TimeInput(attrs={'type': 'time'}),
                                   initial="18:00")
    slot_2_end = forms.TimeField(label="Slot 2 End Time", required=False,
                                 widget=forms.TimeInput(attrs={'type': 'time'}),
                                 initial="01:00")
    slot_2_price = forms.DecimalField(label="Slot 2 Price (₹)", required=False,
                                      max_digits=8, decimal_places=2, initial=1000.00)

    class Meta:
        model = Ground
        fields = ['name', 'location', 'day_price', 'night_price', 'opening_time', 'closing_time']
        widgets = {
            'opening_time': forms.TimeInput(attrs={'type': 'time'}),
            'closing_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        self.owner = kwargs.pop('owner', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        ground = super().save(commit=False)
        if self.owner:
            ground.owner = self.owner
        if commit:
            ground.save()
        return ground


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
