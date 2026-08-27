import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.tenants.models import Organization


class Plan(models.Model):
    code = models.SlugField("código", max_length=64, unique=True)
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    monthly_price = models.DecimalField("preço mensal", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    trial_days = models.PositiveIntegerField("dias de trial", default=0)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "plano"
        verbose_name_plural = "planos"

    def __str__(self):
        return self.name


class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Ativa"
        PAST_DUE = "past_due", "Inadimplente"
        SUSPENDED = "suspended", "Suspensa"
        CANCELLED = "cancelled", "Cancelada"

    organization = models.OneToOneField(Organization, on_delete=models.PROTECT, related_name="billing_subscription", verbose_name="organização")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions", verbose_name="plano")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField("status", max_length=16, choices=Status.choices, default=Status.TRIAL)
    gateway_provider = models.CharField("provedor de gateway", max_length=64, blank=True)
    started_at = models.DateTimeField("iniciada em", null=True, blank=True)
    trial_ends_at = models.DateTimeField("trial termina em", null=True, blank=True)
    current_period_start = models.DateField("início do período", null=True, blank=True)
    current_period_end = models.DateField("fim do período", null=True, blank=True)
    cancelled_at = models.DateTimeField("cancelada em", null=True, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        ordering = ["organization__name"]
        indexes = [models.Index(fields=["organization", "status"]), models.Index(fields=["status", "current_period_end"])]
        verbose_name = "assinatura"
        verbose_name_plural = "assinaturas"

    def __str__(self):
        return f"{self.organization} - {self.plan}"


class SubscriptionInvoice(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Aberta"
        PAID = "paid", "Paga"
        VOID = "void", "Cancelada"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="billing_invoices", verbose_name="organização")
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="invoices", verbose_name="assinatura")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    number = models.CharField("número", max_length=64)
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2)
    status = models.CharField("status", max_length=16, choices=Status.choices, default=Status.OPEN)
    due_date = models.DateField("vencimento")
    paid_at = models.DateTimeField("paga em", null=True, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        ordering = ["-due_date", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "number"], name="unique_billing_invoice_number_per_org")]
        indexes = [models.Index(fields=["organization", "status", "due_date"])]
        verbose_name = "fatura de assinatura"
        verbose_name_plural = "faturas de assinatura"

    def clean(self):
        if self.subscription_id and self.organization_id and self.subscription.organization_id != self.organization_id:
            raise ValidationError({"subscription": "A assinatura precisa pertencer à mesma organização da fatura."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.number


class BillingPayment(models.Model):
    class Method(models.TextChoices):
        MANUAL = "manual", "Manual"
        GATEWAY = "gateway", "Gateway"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="billing_payments", verbose_name="organização")
    invoice = models.ForeignKey(SubscriptionInvoice, on_delete=models.PROTECT, related_name="payments", verbose_name="fatura")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    idempotency_key = models.CharField("chave de idempotência", max_length=128, unique=True)
    provider_payment_id = models.CharField("ID do pagamento no provedor", max_length=128, unique=True, null=True, blank=True)
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2)
    method = models.CharField("método", max_length=16, choices=Method.choices, default=Method.MANUAL)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_billing_payments")
    paid_at = models.DateTimeField("paga em")
    notes = models.TextField("observações", blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]
        indexes = [models.Index(fields=["organization", "paid_at"])]
        verbose_name = "pagamento de billing"
        verbose_name_plural = "pagamentos de billing"

    def clean(self):
        if self.invoice_id and self.organization_id and self.invoice.organization_id != self.organization_id:
            raise ValidationError({"invoice": "A fatura precisa pertencer à mesma organização do pagamento."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Pagamento {self.public_id}"


class BillingProviderEvent(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="billing_provider_events", verbose_name="organização")
    invoice = models.ForeignKey(SubscriptionInvoice, on_delete=models.PROTECT, null=True, blank=True, related_name="provider_events", verbose_name="fatura")
    event_id = models.CharField("ID do evento", max_length=160, unique=True)
    provider = models.CharField("provedor", max_length=64)
    event_type = models.CharField("tipo", max_length=100)
    payload = models.JSONField("payload", default=dict)
    processed_at = models.DateTimeField("processado em", null=True, blank=True)
    created_at = models.DateTimeField("recebido em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "created_at"])]
        verbose_name = "evento de provedor de billing"
        verbose_name_plural = "eventos de provedor de billing"

    def clean(self):
        if self.invoice_id and not self.organization_id:
            raise ValidationError({"organization": "Um evento associado a uma fatura precisa de organização."})
        if self.invoice_id and self.organization_id and self.invoice.organization_id != self.organization_id:
            raise ValidationError({"invoice": "A fatura precisa pertencer à mesma organização do evento."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.provider}: {self.event_id}"
