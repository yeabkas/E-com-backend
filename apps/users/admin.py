from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Address


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0
    fields = ['label', 'street_line_1', 'city', 'state_province', 'postal_code', 'country_code', 'is_default']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'first_name', 'last_name', 'role', 'is_verified', 'is_suspended', 'created_at']
    list_filter = ['role', 'is_verified', 'is_suspended', 'is_staff']
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['-created_at']
    inlines = [AddressInline]

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Status', {'fields': ('role', 'is_verified', 'is_suspended')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login_at', 'created_at', 'updated_at')}),
    )
    readonly_fields = ['created_at', 'updated_at', 'last_login_at']

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2', 'role'),
        }),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ['user', 'label', 'city', 'country_code', 'is_default']
    list_filter = ['country_code', 'is_default']
    search_fields = ['user__email', 'city', 'street_line_1']
