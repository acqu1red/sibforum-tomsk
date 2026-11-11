from django.contrib import admin
from django.conf import settings
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied

from .models import Admin2FAProfile
from .forms import StaffCreationForm
from .roles import assign_role


class OwnerOnlyAdmin:
    """Account privileges cannot be delegated through Django permissions."""

    def is_owner(self, request):
        return (request.user.is_active and request.user.is_superuser
                and request.user.get_username() == settings.ADMIN_OWNER_USERNAME)

    def has_module_permission(self, request):
        return self.is_owner(request)

    def has_view_permission(self, request, obj=None):
        return self.is_owner(request)

    def has_add_permission(self, request):
        return self.is_owner(request)

    def has_change_permission(self, request, obj=None):
        return self.is_owner(request)

    def has_delete_permission(self, request, obj=None):
        return self.is_owner(request)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name in ('permissions', 'user_permissions') and field:
            def label(permission):
                model = permission.content_type.model_class()
                title = model._meta.verbose_name_plural if model else permission.content_type.name
                action = {'add': 'добавление', 'change': 'изменение', 'delete': 'удаление', 'view': 'просмотр'}.get(permission.codename.split('_', 1)[0], permission.name)
                return f'{title} — {action}'
            field.label_from_instance = label
        return field


class DirectorUserAdmin(OwnerOnlyAdmin, UserAdmin):
    add_form = StaffCreationForm
    add_fieldsets = (
        ('Сотрудник', {'fields': ('username', 'first_name', 'last_name', 'email', 'role')}),
        ('Пароль для входа', {'fields': ('password1', 'password2')}),
    )
    list_display = ('username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff')

    def response_add(self, request, obj, post_url_continue=None):
        # Role and access are already set: honour the selected Save action.
        return admin.ModelAdmin.response_add(self, request, obj, post_url_continue)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.is_staff = True
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not change:
            assign_role(form.instance, form.cleaned_data.get('role'))

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and obj.get_username() == settings.ADMIN_OWNER_USERNAME:
            return (*fields, 'username', 'is_active', 'is_staff', 'is_superuser')
        return fields

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and not (
            obj and obj.get_username() == settings.ADMIN_OWNER_USERNAME)

    def delete_queryset(self, request, queryset):
        if not self.is_owner(request) or queryset.filter(username=settings.ADMIN_OWNER_USERNAME).exists():
            raise PermissionDenied('Аккаунт руководителя нельзя удалить.')
        return super().delete_queryset(request, queryset)


class DirectorGroupAdmin(OwnerOnlyAdmin, GroupAdmin):
    pass


admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, DirectorUserAdmin)
admin.site.register(Group, DirectorGroupAdmin)


@admin.register(Admin2FAProfile)
class Admin2FAProfileAdmin(OwnerOnlyAdmin, admin.ModelAdmin):
    list_display = ('user', 'confirmed_at', 'last_counter', 'updated_at')
    readonly_fields = ('user', 'confirmed_at', 'last_counter', 'created_at', 'updated_at')
    exclude = ('secret_ciphertext',)

    def has_add_permission(self, request):
        return False

    def has_module_permission(self, request):
        return settings.ADMIN_TOTP_REQUIRED and super().has_module_permission(request)
