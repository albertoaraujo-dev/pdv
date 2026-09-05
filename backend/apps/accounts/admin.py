from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.contrib.auth import logout
from django.conf import settings
from django.http import HttpResponseRedirect
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
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
            record_login_attempt(self.request, username, LoginAttempt.Status.LOCKED, "Muitas tentativas inválidas no painel administrativo.")
            raise ValidationError(self.error_messages["locked"], code="locked")

        try:
            cleaned_data = super().clean()
        except ValidationError:
            record_login_attempt(self.request, username, LoginAttempt.Status.FAILED, "Credenciais inválidas no painel administrativo.")
            raise

        if is_inactive_for_login(self.user_cache):
            record_login_attempt(self.request, username, LoginAttempt.Status.FAILED, "Usuário inativo no painel administrativo.")
            raise ValidationError("Usuário inativo.", code="inactive")

        if must_change_password(self.user_cache):
            record_login_attempt(self.request, username, LoginAttempt.Status.FAILED, "Troca de senha obrigatória no painel administrativo.")
            raise ValidationError("Troque sua senha antes de acessar o painel administrativo.", code="password_change_required")

        record_login_attempt(self.request, username, LoginAttempt.Status.SUCCESS, "Login realizado no painel administrativo.")
        return cleaned_data


admin.site.login_form = AuditedAdminAuthenticationForm
admin.site.empty_value_display = "Não informado"
admin.site.site_header = "PDV Final"
admin.site.site_title = "PDV Final"
admin.site.index_title = "Painel administrativo"


@never_cache
@csrf_protect
def admin_logout(request, extra_context=None):
    logout(request)
    return HttpResponseRedirect(settings.FRONTEND_URL)


admin.site.logout = admin_logout


def localized_admin_reason(reason):
    return (reason or "").replace(" no admin.", " no painel administrativo.").replace(" do admin ", " do painel administrativo ")


try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin, ModelAdmin):
    pass


@admin.register(LoginAttempt)
class LoginAttemptAdmin(ModelAdmin):
    list_display = ["created_at", "username", "ip_address", "status", "display_reason"]
    list_filter = ["status", "created_at"]
    search_fields = ["username", "normalized_username", "ip_address", "user_agent", "reason"]
    fields = ["username", "normalized_username", "ip_address", "browser_device", "status", "display_reason", "created_at"]
    readonly_fields = ["username", "normalized_username", "ip_address", "browser_device", "status", "display_reason", "created_at"]

    @admin.display(description="navegador/dispositivo")
    def browser_device(self, obj):
        return obj.user_agent

    @admin.display(description="motivo", ordering="reason")
    def display_reason(self, obj):
        return localized_admin_reason(obj.reason)

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
    list_display = ["created_at", "username", "event_type", "ip_address", "display_reason"]
    list_filter = ["event_type", "created_at"]
    search_fields = ["username", "ip_address", "user_agent", "reason"]
    fields = ["user", "username", "event_type", "ip_address", "browser_device", "display_reason", "created_at"]
    readonly_fields = ["user", "username", "event_type", "ip_address", "browser_device", "display_reason", "created_at"]

    @admin.display(description="navegador/dispositivo")
    def browser_device(self, obj):
        return obj.user_agent

    @admin.display(description="motivo", ordering="reason")
    def display_reason(self, obj):
        return localized_admin_reason(obj.reason)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
