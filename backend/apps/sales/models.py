from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.catalog.models import Product
from apps.tenants.models import Organization, Store


class Sale(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Concluída"
        CANCELLED = "cancelled", "Cancelada"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Dinheiro"
        CARD_EXTERNAL = "card_external", "Cartão externo"
        PIX_MANUAL = "pix_manual", "Pix manual"
        OTHER = "other", "Outro"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="sales", verbose_name="organização")
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="sales", verbose_name="loja")
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales", verbose_name="operador")
    status = models.CharField("status", max_length=24, choices=Status.choices, default=Status.COMPLETED)
    total_amount = models.DecimalField("total", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_method = models.CharField("forma de pagamento", max_length=24, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    amount_received = models.DecimalField("valor recebido", max_digits=12, decimal_places=2, default=Decimal("0.00"))
    change_amount = models.DecimalField("troco", max_digits=12, decimal_places=2, default=Decimal("0.00"))
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
        if self.product_id and self.sale_id and self.product.organization_id != self.sale.organization_id:
            errors["product"] = "O produto precisa pertencer à mesma organização da venda."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"
