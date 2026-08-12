from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from unfold.admin import ModelAdmin
from unfold.forms import AuthenticationForm

from .models import AuthEvent, LoginAttempt, is_login_locked, record_login_attempt
from .policies import is_inactive_for_login, must_change_password


class AuditedAdminAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "locked": "Muitas tentativas inválidas. Tente novamente em alguns minutos.",
    }

    def clean(self):
        username = self.cleaned_data.get("username", "")

        if is_login_locked(self.request, username):
            record_login_attempt(self.request, username, LoginAttempt.Status.LOCKED, "Muitas tentativas inválidas no admin.")
            raise ValidationError(self.error_messages["locked"], code="locked")

        try:
            cleaned_data = super().clean()
        except ValidationError:
            record_login_attempt(self.request, username, LoginAttempt.Status.FAILED, "Credenciais inválidas no admin.")
            raise

        if is_inactive_for_login(self.user_cache):
            record_login_attempt(self.request, username, LoginAttempt.Status.FAILED, "Usuário inativo no admin.")
            raise ValidationError("Usuário inativo.", code="inactive")

        if must_change_password(self.user_cache):
            record_login_attempt(self.request, username, LoginAttempt.Status.FAILED, "Troca de senha obrigatória no admin.")
            raise ValidationError("Troque sua senha antes de acessar o painel administrativo.", code="password_change_required")

        record_login_attempt(self.request, username, LoginAttempt.Status.SUCCESS, "Login realizado no admin.")
        return cleaned_data


admin.site.login_form = AuditedAdminAuthenticationForm
admin.site.site_header = "PDV Final"
admin.site.site_title = "PDV Final"
admin.site.index_title = "Painel administrativo"


try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin, ModelAdmin):
    pass


@admin.register(LoginAttempt)
class LoginAttemptAdmin(ModelAdmin):
    list_display = ["created_at", "username", "ip_address", "status", "reason"]
    list_filter = ["status", "created_at"]
    search_fields = ["username", "normalized_username", "ip_address", "user_agent", "reason"]
    readonly_fields = ["username", "normalized_username", "ip_address", "user_agent", "status", "reason", "created_at"]

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AuthEvent)
class AuthEventAdmin(ModelAdmin):
    list_display = ["created_at", "username", "event_type", "ip_address", "reason"]
    list_filter = ["event_type", "created_at"]
    search_fields = ["username", "ip_address", "user_agent", "reason"]
    readonly_fields = ["user", "username", "event_type", "ip_address", "user_agent", "reason", "created_at"]

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
