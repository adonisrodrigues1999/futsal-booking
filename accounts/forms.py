from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User
from grounds.models import Ground


class UserRegistrationForm(forms.ModelForm):
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

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'customer'  # Default role for self-registration
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


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
        widget=forms.EmailInput(attrs={'placeholder': 'Enter your email'})
    )
    phone = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Enter your phone number'})
    )
    password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        phone = cleaned_data.get('phone')

        if not email and not phone:
            raise forms.ValidationError("Please enter either email or phone number")

        if email and phone:
            raise forms.ValidationError("Please enter either email or phone number, not both")

        return cleaned_data
