import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.tenants.models import Organization


class Module(models.Model):
    code = models.SlugField("código", max_length=64, unique=True)
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "módulo"
        verbose_name_plural = "módulos"

    def __str__(self):
        return f"{self.name} ({self.code})"


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


class PlanModule(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="plan_modules", verbose_name="plano")
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="plan_modules", verbose_name="módulo")
    included = models.BooleanField("incluído", default=True)
    limits = models.JSONField("limites", null=True, blank=True)

    class Meta:
        ordering = ["plan__name", "module__name"]
        constraints = [models.UniqueConstraint(fields=["plan", "module"], name="unique_module_per_plan")]
        verbose_name = "módulo do plano"
        verbose_name_plural = "módulos dos planos"

    def __str__(self):
        return f"{self.plan} - {self.module}"

    def clean(self):
        if self._state.adding and self.plan_id and self.module_id and (not self.plan.is_active or not self.module.is_active):
            raise ValidationError("Um módulo de plano precisa usar plano e módulo ativos.")
        if self.limits is not None and not isinstance(self.limits, dict):
            raise ValidationError({"limits": "Os limites precisam ser um objeto JSON."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


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

    def clean(self):
        if self.status in (self.Status.TRIAL, self.Status.ACTIVE) and self.organization_id and self.plan_id:
            errors = {}
            if not self.organization.is_active:
                errors["organization"] = "Uma assinatura ativa precisa pertencer a uma organização ativa."
            if not self.plan.is_active:
                errors["plan"] = "Uma assinatura ativa precisa usar um plano ativo."
            if errors:
                raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class SubscriptionModule(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="billing_subscription_modules", verbose_name="organização")
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="subscription_modules", verbose_name="assinatura")
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="subscription_modules", verbose_name="módulo")
    included = models.BooleanField("incluído", default=True)
    is_active = models.BooleanField("ativo", default=True)
    starts_at = models.DateTimeField("inicia em", null=True, blank=True)
    ends_at = models.DateTimeField("termina em", null=True, blank=True)
    limits = models.JSONField("limites", null=True, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["organization__name", "module__name"]
        constraints = [models.UniqueConstraint(fields=["subscription", "module"], name="unique_module_per_subscription")]
        indexes = [models.Index(fields=["organization", "is_active", "starts_at", "ends_at"])]
        verbose_name = "módulo da assinatura"
        verbose_name_plural = "módulos das assinaturas"

    def clean(self):
        errors = {}
        if self.subscription_id and self.organization_id and self.subscription.organization_id != self.organization_id:
            errors["organization"] = "A organização precisa ser a mesma da assinatura."
        if self.is_active and self.subscription_id and self.module_id and self.organization_id:
            if (
                not self.organization.is_active
                or self.subscription.status not in (Subscription.Status.TRIAL, Subscription.Status.ACTIVE)
                or not self.module.is_active
            ):
                errors["is_active"] = "Um módulo de assinatura ativo precisa usar organização, assinatura e módulo ativos."
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "O fim precisa ser posterior ao início."
        if self.limits is not None and not isinstance(self.limits, dict):
            errors["limits"] = "Os limites precisam ser um objeto JSON."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.organization} - {self.module}"


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
