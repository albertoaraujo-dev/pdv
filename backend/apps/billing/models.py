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
    is_base = models.BooleanField("módulo base", default=False)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "módulo"
        verbose_name_plural = "módulos"

    def __str__(self):
        return f"{self.name} ({self.code})"


class ModuleDependency(models.Model):
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="dependencies", verbose_name="módulo")
    depends_on = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="required_by", verbose_name="depende de")
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["module__code", "depends_on__code"]
        constraints = [models.UniqueConstraint(fields=["module", "depends_on"], name="unique_module_dependency")]
        verbose_name = "dependência de módulo"
        verbose_name_plural = "dependências de módulos"

    def clean(self):
        if self.module_id and self.module_id == self.depends_on_id:
            raise ValidationError("Um módulo não pode depender de si mesmo.")
        if self.module_id and self.depends_on_id:
            dependencies = {self.depends_on_id}
            pending = [self.depends_on_id]
            while pending:
                current = pending.pop()
                for dependency_id in ModuleDependency.objects.filter(
                    module_id=current, is_active=True
                ).values_list("depends_on_id", flat=True):
                    if dependency_id == self.module_id:
                        raise ValidationError("Dependências de módulos não podem formar ciclos.")
                    if dependency_id not in dependencies:
                        dependencies.add(dependency_id)
                        pending.append(dependency_id)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Plan(models.Model):
    code = models.SlugField("código", max_length=64, unique=True)
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True)
    monthly_price = models.DecimalField("preço mensal", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    trial_days = models.PositiveIntegerField("dias de trial", default=0)
    is_active = models.BooleanField("ativo", default=True)
    is_default = models.BooleanField("plano padrão", default=False)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True, is_active=True),
                name="unique_active_default_plan",
            )
        ]
        verbose_name = "plano"
        verbose_name_plural = "planos"

    def __str__(self):
        return self.name


class PlanModule(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="plan_modules", verbose_name="plano")
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="plan_modules", verbose_name="módulo")
    included = models.BooleanField("incluído", default=True)
    limits = models.JSONField("limites", null=True, blank=True)
    monthly_price = models.DecimalField("preço mensal do módulo", max_digits=12, decimal_places=2, null=True, blank=True)

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
        if self.included and self.module_id:
            missing = ModuleDependency.objects.filter(module=self.module, is_active=True).exclude(
                depends_on__is_base=True
            ).exclude(depends_on__code__in=("core", "catalog")).exclude(
                depends_on_id__in=PlanModule.objects.filter(
                    plan_id=self.plan_id, included=True
                ).values("module_id")
            )
            if self.module.code == "sales" and not (
                self.module.__class__.objects.filter(code="catalog", is_active=True).exists()
                and (
                    self.module.__class__.objects.filter(code="catalog", is_base=True).exists()
                    or PlanModule.objects.filter(plan_id=self.plan_id, module__code="catalog", included=True).exists()
                )
            ):
                raise ValidationError("O módulo sales precisa de um catálogo ativo.")
            if missing.exists():
                raise ValidationError("Um módulo incluído no plano precisa incluir suas dependências.")
        if self.limits is not None and not isinstance(self.limits, dict):
            raise ValidationError({"limits": "Os limites precisam ser um objeto JSON."})
        if self.monthly_price is not None and self.monthly_price < 0:
            raise ValidationError({"monthly_price": "O preço do módulo não pode ser negativo."})

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
    past_due_since = models.DateTimeField("inadimplência desde", null=True, blank=True)
    grace_until = models.DateTimeField("fim da carência", null=True, blank=True)
    current_period_start = models.DateField("início do período", null=True, blank=True)
    current_period_end = models.DateField("fim do período", null=True, blank=True)
    cancelled_at = models.DateTimeField("cancelada em", null=True, blank=True)
    cancellation_reason = models.CharField("motivo do cancelamento", max_length=255, blank=True)
    cancellation_metadata = models.JSONField("metadados do cancelamento", default=dict, blank=True)
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
    monthly_price = models.DecimalField("preço mensal do módulo", max_digits=12, decimal_places=2, null=True, blank=True)
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
        if self.monthly_price is not None and self.monthly_price < 0:
            errors["monthly_price"] = "O preço do módulo não pode ser negativo."
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
        PAST_DUE = "past_due", "Inadimplente"
        PAID = "paid", "Paga"
        VOID = "void", "Cancelada"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="billing_invoices", verbose_name="organização")
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="invoices", verbose_name="assinatura")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    number = models.CharField("número", max_length=64)
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2)
    status = models.CharField("status", max_length=16, choices=Status.choices, default=Status.OPEN)
    period_start = models.DateField("início do período", null=True, blank=True)
    period_end = models.DateField("fim do período", null=True, blank=True)
    due_date = models.DateField("vencimento")
    paid_at = models.DateTimeField("paga em", null=True, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        ordering = ["-due_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="unique_billing_invoice_number_per_org"),
            models.UniqueConstraint(
                fields=["subscription", "period_start", "period_end"],
                name="unique_subscription_invoice_period",
            ),
        ]
        indexes = [models.Index(fields=["organization", "status", "due_date"])]
        verbose_name = "fatura de assinatura"
        verbose_name_plural = "faturas de assinatura"

    def clean(self):
        errors = {}
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("status", "amount").first()
            if previous and previous["status"] == self.Status.PAID and previous["amount"] != self.amount:
                errors["amount"] = "O valor de uma fatura paga não pode ser alterado."
        if self.subscription_id and self.organization_id and self.subscription.organization_id != self.organization_id:
            errors["subscription"] = "A assinatura precisa pertencer à mesma organização da fatura."
        if bool(self.period_start) != bool(self.period_end):
            errors["period_end"] = "O início e o fim do período devem ser informados juntos."
        elif self.period_start and self.period_end and self.period_end < self.period_start:
            errors["period_end"] = "O fim do período precisa ser igual ou posterior ao início."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.number

    def calculate_total(self):
        return sum((item.total_amount for item in self.items.all()), Decimal("0.00"))

    def recalculate_total(self):
        if self.status == self.Status.PAID:
            raise ValidationError("O total de uma fatura paga não pode ser alterado.")
        self.amount = self.calculate_total()
        self.save(update_fields=["amount", "updated_at"])
        return self.amount


class SubscriptionInvoiceItem(models.Model):
    class ItemType(models.TextChoices):
        PLAN = "plan", "Plano"
        MODULE = "module", "Módulo"

    invoice = models.ForeignKey(SubscriptionInvoice, on_delete=models.PROTECT, related_name="items", verbose_name="fatura")
    item_type = models.CharField("tipo", max_length=16, choices=ItemType.choices)
    module = models.ForeignKey(Module, on_delete=models.PROTECT, null=True, blank=True, related_name="invoice_items", verbose_name="módulo")
    code = models.CharField("código", max_length=64)
    description = models.CharField("descrição", max_length=200)
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2)
    amount_override = models.DecimalField("valor sobrescrito", max_digits=12, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["item_type", "code"]
        verbose_name = "item de fatura"
        verbose_name_plural = "itens de faturas"

    @property
    def total_amount(self):
        return self.amount if self.amount_override is None else self.amount_override

    def clean(self):
        errors = {}
        invoice_status = SubscriptionInvoice.objects.filter(pk=self.invoice_id).values_list("status", flat=True).first() if self.invoice_id else None
        if self.invoice_id and invoice_status == SubscriptionInvoice.Status.PAID:
            if self.pk:
                old = type(self).objects.filter(pk=self.pk).values("amount", "amount_override", "code", "description").first()
                if old and any(old[key] != getattr(self, key) for key in ("amount", "amount_override", "code", "description")):
                    errors["invoice"] = "Os itens de uma fatura paga são somente leitura."
            else:
                errors["invoice"] = "Não é possível adicionar itens a uma fatura paga."
        if self.item_type == self.ItemType.PLAN and self.module_id:
            errors["module"] = "O item de plano não pode ter módulo."
        if self.item_type == self.ItemType.MODULE and not self.module_id:
            errors["module"] = "O item de módulo precisa ter módulo."
        if self.module_id and self.module.is_base:
            errors["module"] = "Módulos base não são faturáveis."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        result = super().save(*args, **kwargs)
        if self.invoice.status != SubscriptionInvoice.Status.PAID:
            self.invoice.recalculate_total()
        return result

    def __str__(self):
        return self.description


class BillingNotification(models.Model):
    class NotificationType(models.TextChoices):
        DUE_SOON = "due_soon", "Vencimento próximo"
        PAST_DUE = "past_due", "Fatura vencida"
        SUSPENSION_WARNING = "suspension_warning", "Aviso de suspensão"
        SUSPENDED = "suspended", "Assinatura suspensa"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="billing_notifications", verbose_name="organização")
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="billing_notifications", verbose_name="assinatura")
    invoice = models.ForeignKey(SubscriptionInvoice, on_delete=models.PROTECT, null=True, blank=True, related_name="billing_notifications", verbose_name="fatura")
    notification_type = models.CharField("tipo", max_length=32, choices=NotificationType.choices)
    idempotency_key = models.CharField("chave de idempotência", max_length=200, unique=True)
    period_start = models.DateField("início do período", null=True, blank=True)
    period_end = models.DateField("fim do período", null=True, blank=True)
    delivered_at = models.DateTimeField("entregue em", null=True, blank=True)
    payload = models.JSONField("payload", default=dict)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "notification_type", "created_at"])]
        verbose_name = "notificação de billing"
        verbose_name_plural = "notificações de billing"

    def clean(self):
        errors = {}
        if self.subscription_id and self.organization_id and self.subscription.organization_id != self.organization_id:
            errors["subscription"] = "A assinatura precisa pertencer à mesma organização da notificação."
        if self.invoice_id and self.subscription_id and self.invoice.subscription_id != self.subscription_id:
            errors["invoice"] = "A fatura precisa pertencer à mesma assinatura da notificação."
        if self.invoice_id and self.organization_id and self.invoice.organization_id != self.organization_id:
            errors["invoice"] = "A fatura precisa pertencer à mesma organização da notificação."
        if bool(self.period_start) != bool(self.period_end):
            errors["period_end"] = "O início e o fim do período devem ser informados juntos."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.organization}"


class SubscriptionChange(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="plan_changes", verbose_name="assinatura")
    old_plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscription_changes_from", verbose_name="plano anterior")
    new_plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscription_changes_to", verbose_name="novo plano")
    effective_at = models.DateTimeField("vigente em")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="billing_subscription_changes")
    reason = models.TextField("motivo", blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        ordering = ["-effective_at", "-created_at"]
        verbose_name = "alteração de assinatura"
        verbose_name_plural = "alterações de assinaturas"

    def clean(self):
        if self.old_plan_id == self.new_plan_id:
            raise ValidationError("O novo plano precisa ser diferente do plano anterior.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


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
