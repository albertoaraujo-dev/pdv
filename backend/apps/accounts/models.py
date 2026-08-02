from datetime import timedelta

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


def normalize_username(username):
    return (username or "").strip().lower()


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if settings.TRUST_X_FORWARDED_FOR and forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_login_attempt(request, username, status, reason=""):
    return LoginAttempt.objects.create(
        username=(username or "").strip(),
        normalized_username=normalize_username(username),
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
        status=status,
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
