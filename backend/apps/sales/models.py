from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.catalog.models import Product
from apps.tenants.models import Organization, Store


class Sale(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Concluída"
        PENDING_PAYMENT = "pending_payment", "Pagamento pendente"
        CANCELLED = "cancelled", "Cancelada"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Dinheiro"
        CARD_EXTERNAL = "card_external", "Cartão externo"
        PIX_MANUAL = "pix_manual", "Pix manual"
        PIX_ABACATEPAY = "pix_abacatepay", "Pix AbacatePay"
        OTHER = "other", "Outro"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="sales", verbose_name="organização")
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="sales", verbose_name="loja")
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales", verbose_name="operador")
    status = models.CharField("status", max_length=24, choices=Status.choices, default=Status.COMPLETED)
    total_amount = models.DecimalField("total", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_method = models.CharField("forma de pagamento", max_length=24, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    amount_received = models.DecimalField("valor recebido", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    change_amount = models.DecimalField("troco", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    client_request_id = models.CharField("ID da requisição do PDV", max_length=64, blank=True, null=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "venda"
        verbose_name_plural = "vendas"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "store", "created_at"]),
            models.Index(fields=["organization", "status", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["cashier", "store", "client_request_id"],
                condition=Q(client_request_id__isnull=False),
                name="unique_sale_client_request_per_cashier_store",
            ),
        ]

    def clean(self):
        if self.store_id and self.organization_id and self.store.organization_id != self.organization_id:
            raise ValidationError({"store": "A loja precisa pertencer à mesma organização da venda."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Venda #{self.pk or 'nova'} - {self.store}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items", verbose_name="venda")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_items", verbose_name="produto")
    product_name = models.CharField("nome do produto", max_length=180)
    product_sku = models.CharField("SKU do produto", max_length=64)
    quantity = models.DecimalField("quantidade", max_digits=10, decimal_places=3)
    unit_price = models.DecimalField("preço unitário", max_digits=12, decimal_places=2)
    line_total = models.DecimalField("total do item", max_digits=12, decimal_places=2)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "item de venda"
        verbose_name_plural = "itens de venda"
        ordering = ["id"]
        indexes = [models.Index(fields=["product", "created_at"])]

    def clean(self):
        errors = {}
        if self.quantity is not None and self.quantity <= 0:
            errors["quantity"] = "A quantidade precisa ser maior que zero."
        elif self.quantity is not None and self.quantity != self.quantity.to_integral_value():
            errors["quantity"] = "Venda somente em unidades inteiras."
        if self.product_id and self.sale_id and self.product.organization_id != self.sale.organization_id:
            errors["product"] = "O produto precisa pertencer à mesma organização da venda."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"


class SalePayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PAID = "paid", "Pago"
        EXPIRED = "expired", "Expirado"
        CANCELLED = "cancelled", "Cancelado"
        FAILED = "failed", "Falhou"

    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name="abacatepay_payment")
    external_id = models.CharField(max_length=128, unique=True)
    provider_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    amount_cents = models.PositiveBigIntegerField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    br_code = models.TextField(blank=True)
    br_code_base64 = models.TextField(blank=True)
    provider_response = models.JSONField(default=dict, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "pagamento AbacatePay"
        verbose_name_plural = "pagamentos AbacatePay"
        indexes = [models.Index(fields=["status", "updated_at"])]

    def __str__(self):
        return f"AbacatePay #{self.provider_id or self.external_id}"


class SalePaymentWebhookEvent(models.Model):
    event_id = models.CharField(max_length=128, unique=True)
    event = models.CharField(max_length=80)
    payment = models.ForeignKey(SalePayment, on_delete=models.SET_NULL, null=True, blank=True, related_name="webhook_events")
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "evento de webhook de pagamento"
        verbose_name_plural = "eventos de webhook de pagamento"

    def __str__(self):
        return f"Webhook {self.event} #{self.event_id}"


class CardPaymentTransaction(models.Model):
    class Status(models.TextChoices):
        APPROVED = "approved", "Aprovada"
        PENDING = "pending", "Pendente"
        DECLINED = "declined", "Recusada"
        CANCELLED = "cancelled", "Cancelada"
        RECONCILED = "reconciled", "Conciliada"

    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name="card_transaction", verbose_name="venda")
    external_id = models.CharField("ID externo", max_length=128, unique=True)
    client_reference = models.CharField("referência do cliente", max_length=128, unique=True)
    provider = models.CharField("provedor", max_length=80, default="external_card")
    terminal_id = models.CharField("terminal", max_length=80, blank=True)
    amount_cents = models.PositiveBigIntegerField("valor em centavos")
    status = models.CharField("status", max_length=24, choices=Status.choices, default=Status.APPROVED)
    reconciled_at = models.DateTimeField("conciliado em", null=True, blank=True)
    reconciled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reconciled_card_transactions")
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "transação de cartão externo"
        verbose_name_plural = "transações de cartão externo"
        indexes = [models.Index(fields=["status", "updated_at"])]

    def clean(self):
        if self.sale_id and self.sale.payment_method != Sale.PaymentMethod.CARD_EXTERNAL:
            raise ValidationError({"sale": "A transação precisa estar vinculada a uma venda de cartão externo."})
        if self.sale_id and self.amount_cents != int(self.sale.total_amount * 100):
            raise ValidationError({"amount_cents": "O valor da transação precisa ser igual ao total da venda."})

    def reconcile(self, user):
        if self.status == self.Status.RECONCILED:
            return False
        if self.status != self.Status.APPROVED:
            raise ValidationError("Somente transações aprovadas podem ser conciliadas.")
        self.status = self.Status.RECONCILED
        self.reconciled_by = user
        from django.utils import timezone
        self.reconciled_at = timezone.now()
        self.save(update_fields=["status", "reconciled_by", "reconciled_at", "updated_at"])
        return True

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Cartão externo #{self.external_id}"
