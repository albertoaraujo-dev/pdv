from datetime import timedelta
from ipaddress import ip_address

from django.conf import settings
from django.db import models
from django.utils import timezone


class LoginAttempt(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Sucesso"
        FAILED = "failed", "Falha"
        LOCKED = "locked", "Bloqueado"

    username = models.CharField("usuário informado", max_length=150)
    normalized_username = models.CharField("usuário normalizado", max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField("IP", null=True, blank=True)
    user_agent = models.TextField("user agent", blank=True)
    status = models.CharField("status", max_length=16, choices=Status.choices)
    reason = models.CharField("motivo", max_length=120, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "tentativa de login"
        verbose_name_plural = "tentativas de login"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["normalized_username", "ip_address", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.username} - {self.get_status_display()}"


class AuthEvent(models.Model):
    class EventType(models.TextChoices):
        LOGOUT = "logout", "Logout"
        PASSWORD_CHANGE = "password_change", "Troca de senha"
        PASSWORD_RESET = "password_reset", "Redefinição de senha"
        SESSION_REVOKED = "session_revoked", "Sessão revogada"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="auth_events", verbose_name="usuário")
    username = models.CharField("usuário", max_length=150)
    event_type = models.CharField("tipo", max_length=32, choices=EventType.choices)
    ip_address = models.GenericIPAddressField("IP", null=True, blank=True)
    user_agent = models.TextField("user agent", blank=True)
    reason = models.CharField("motivo", max_length=120, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "evento de autenticação"
        verbose_name_plural = "eventos de autenticação"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "event_type", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.username} - {self.get_event_type_display()}"


def normalize_username(username):
    return (username or "").strip().lower()


def normalize_ip(value):
    if not value:
        return None
    try:
        return str(ip_address(value.strip()))
    except ValueError:
        return None


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if settings.TRUST_X_FORWARDED_FOR and forwarded_for:
        forwarded_ip = normalize_ip(forwarded_for.split(",")[0])
        if forwarded_ip:
            return forwarded_ip
    return normalize_ip(request.META.get("REMOTE_ADDR"))


def record_login_attempt(request, username, status, reason=""):
    return LoginAttempt.objects.create(
        username=(username or "").strip(),
        normalized_username=normalize_username(username),
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
        status=status,
        reason=reason,
    )


def record_auth_event(request, user, event_type, reason=""):
    return AuthEvent.objects.create(
        user=user if user and user.is_authenticated else None,
        username=(user.get_username() if user and user.is_authenticated else ""),
        event_type=event_type,
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
        reason=reason,
    )


def is_login_locked(request, username, *, max_failures=5, window_minutes=15):
    since = timezone.now() - timedelta(minutes=window_minutes)
    return LoginAttempt.objects.filter(
        normalized_username=normalize_username(username),
        ip_address=get_client_ip(request),
        status=LoginAttempt.Status.FAILED,
        created_at__gte=since,
    ).count() >= max_failures
