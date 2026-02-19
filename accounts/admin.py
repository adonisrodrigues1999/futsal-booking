from django.contrib import admin
from django.contrib.auth import get_user_model

User = get_user_model()

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'phone_number', 'role', 'email_verified')
    search_fields = ('email', 'phone_number', 'name')
    list_filter = ('role', 'email_verified')
