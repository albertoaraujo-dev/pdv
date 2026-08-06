from django.contrib import admin
from django.contrib.auth import logout
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserCreationForm
from django import forms
from unfold.admin import ModelAdmin

from apps.accounts.models import AuthEvent, record_auth_event
from apps.accounts.policies import (
    SUBORDINATE_ROLES,
    can_access_admin,
    get_allowed_stores,
    get_manageable_profiles,
    get_manageable_users,
    get_user_organization,
    get_visible_stores,
    is_inactive_for_login,
    can_manage_organization_settings,
    is_manager,
)

from .models import Organization, Store, UserProfile, UserStoreAccess


User = get_user_model()


def admin_has_permission(request):
    if request.user.is_authenticated and is_inactive_for_login(request.user):
        record_auth_event(request, request.user, AuthEvent.EventType.SESSION_REVOKED, "Sessão do admin revogada por usuário inativo.")
        if hasattr(request, "session"):
            logout(request)
        return False
    return can_access_admin(request.user)


admin.site.has_permission = admin_has_permission


class ManagedUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(label="Perfil", choices=[])
    stores = forms.ModelMultipleChoiceField(
        label="Lojas permitidas",
        queryset=Store.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "role", "stores")

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [choice for choice in UserProfile.Role.choices if choice[0] in SUBORDINATE_ROLES]
        if request:
            self.fields["stores"].queryset = get_allowed_stores(request.user)


class TenantScopedAdminMixin:
    tenant_field = "organization"
    tenant_list_filter = ["is_active"]

    def get_tenant_queryset(self, request, queryset):
        if request.user.is_superuser:
            return queryset
        organization = get_user_organization(request.user)
        if not organization:
            return queryset.none()
        return queryset.filter(**{self.tenant_field: organization})

    def get_queryset(self, request):
        return self.get_tenant_queryset(request, super().get_queryset(request))

    def get_list_filter(self, request):
        if request.user.is_superuser:
            return super().get_list_filter(request)
        return self.tenant_list_filter

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        organization = get_user_organization(request.user)
        if organization and db_field.name == "organization":
            kwargs["queryset"] = Organization.objects.filter(pk=organization.pk)
        if db_field.name == "store" and not request.user.is_superuser:
            kwargs["queryset"] = get_allowed_stores(request.user)
        if db_field.name == "profile" and organization:
            kwargs["queryset"] = get_manageable_profiles(request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    add_form = ManagedUserCreationForm
    list_per_page = 25

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(pk__in=get_manageable_users(request.user))

    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            return super().get_fieldsets(request, obj)
        if obj is None:
            return (
                (None, {"fields": ("username", "password1", "password2")}),
                ("Informações pessoais", {"fields": ("first_name", "last_name", "email")}),
                ("Acesso operacional", {"fields": ("role", "stores")}),
            )
        return (
            (None, {"fields": ("username", "password")}),
            ("Informações pessoais", {"fields": ("first_name", "last_name", "email")}),
            ("Status", {"fields": ("is_active",)}),
            ("Datas importantes", {"fields": ("last_login", "date_joined")}),
        )

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return super().get_readonly_fields(request, obj)
        if obj is None:
            return ()
        return ("last_login", "date_joined", "password")

    def get_form(self, request, obj=None, change=False, **kwargs):
        if not request.user.is_superuser and obj is None:
            kwargs["form"] = self.add_form
        form_class = super().get_form(request, obj, **kwargs)
        if request.user.is_superuser or obj is not None:
            return form_class

        class RequestManagedUserCreationForm(form_class):
            def __init__(self, *args, **form_kwargs):
                form_kwargs["request"] = request
                super().__init__(*args, **form_kwargs)

        return RequestManagedUserCreationForm

    def has_add_permission(self, request):
        return request.user.is_superuser or is_manager(request.user)

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        return is_manager(request.user) or get_manageable_users(request.user).exists()

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return is_manager(request.user) or get_manageable_users(request.user).exists()
        return get_manageable_users(request.user).filter(pk=obj.pk).exists()

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        return get_manageable_users(request.user).filter(pk=obj.pk).exists()

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
        organization = get_user_organization(request.user)
        if organization and not change:
            role = form.cleaned_data.get("role", UserProfile.Role.OPERATOR) if form else UserProfile.Role.OPERATOR
            profile, _created = UserProfile.objects.get_or_create(
                user=obj,
                defaults={"organization": organization, "role": role, "must_change_password": True},
            )
            if form:
                for store in form.cleaned_data.get("stores", []):
                    UserStoreAccess.objects.get_or_create(profile=profile, store=store)


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ["name", "document", "is_active", "created_at"]
    list_display_links = ["name"]
    list_filter = ["is_active"]
    list_per_page = 25
    search_fields = ["name", "legal_name", "document"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        if not can_manage_organization_settings(request.user):
            return queryset.none()
        organization = get_user_organization(request.user)
        if not organization:
            return queryset.none()
        return queryset.filter(pk=organization.pk)

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return super().get_readonly_fields(request, obj)
        return ("is_active", "created_at", "updated_at")

    def has_module_permission(self, request):
        return request.user.is_superuser or can_manage_organization_settings(request.user)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if not can_manage_organization_settings(request.user):
            return False
        if obj is None:
            return True
        organization = get_user_organization(request.user)
        return bool(organization and obj.pk == organization.pk)

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Store)
class StoreAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ["name", "code", "organization", "is_active"]
    list_display_links = ["name", "code"]
    list_filter = ["organization", "is_active"]
    list_per_page = 25
    search_fields = ["name", "code", "organization__name"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(pk__in=get_visible_stores(request.user))

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not request.user.is_superuser and not change and is_manager(request.user):
            UserStoreAccess.objects.get_or_create(profile=request.user.profile, store=obj)


@admin.register(UserProfile)
class UserProfileAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ["user", "organization", "role", "must_change_password", "is_active"]
    list_display_links = ["user"]
    list_filter = ["organization", "role", "is_active"]
    list_per_page = 25
    tenant_list_filter = ["role", "is_active"]
    search_fields = ["user__username", "user__email", "organization__name"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(pk__in=get_manageable_profiles(request.user))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        organization = get_user_organization(request.user)
        if organization and db_field.name == "user":
            kwargs["queryset"] = get_manageable_users(request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "role" and is_manager(request.user):
            kwargs["choices"] = [choice for choice in db_field.choices if choice[0] in SUBORDINATE_ROLES]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if is_manager(request.user):
            return False
        if obj is None:
            return True
        return get_manageable_profiles(request.user).filter(pk=obj.pk).exists()

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(UserStoreAccess)
class UserStoreAccessAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ["profile", "store", "is_active"]
    list_display_links = ["profile", "store"]
    list_filter = ["store__organization", "store", "is_active"]
    list_per_page = 25
    tenant_field = "profile__organization"
    search_fields = ["profile__user__username", "store__name"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(profile__in=get_manageable_profiles(request.user))

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return True
        return get_manageable_profiles(request.user).filter(pk=obj.profile_id).exists()

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
