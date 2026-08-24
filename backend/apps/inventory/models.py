from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.catalog.models import Product
from apps.tenants.models import Organization, Store


class Stock(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="stock_balances", verbose_name="organização")
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="stock_balances", verbose_name="loja")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_balances", verbose_name="produto")
    quantity = models.DecimalField("saldo", max_digits=12, decimal_places=3, default=Decimal("0.000"))
    reserved_quantity = models.DecimalField("reservado", max_digits=12, decimal_places=3, default=Decimal("0.000"))
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "saldo de estoque"
        verbose_name_plural = "saldos de estoque"
        ordering = ["store__name", "product__name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "product"], name="unique_stock_per_store_product"),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="stock_quantity_non_negative"),
            models.CheckConstraint(condition=models.Q(reserved_quantity__gte=0), name="stock_reserved_non_negative"),
            models.CheckConstraint(condition=models.Q(reserved_quantity__lte=models.F("quantity")), name="stock_reserved_not_above_quantity"),
        ]
        indexes = [
            models.Index(fields=["organization", "store"]),
            models.Index(fields=["organization", "product"]),
        ]

    def clean(self):
        errors = {}
        if self.quantity is not None and self.quantity < 0:
            errors["quantity"] = "O saldo de estoque não pode ser negativo."
        if self.reserved_quantity is not None and self.reserved_quantity < 0:
            errors["reserved_quantity"] = "O estoque reservado não pode ser negativo."
        if self.quantity is not None and self.reserved_quantity is not None and self.reserved_quantity > self.quantity:
            errors["reserved_quantity"] = "O estoque reservado não pode superar o saldo."
        if self.store_id and self.organization_id and self.store.organization_id != self.organization_id:
            errors["store"] = "A loja precisa pertencer à mesma organização do estoque."
        if self.product_id and self.organization_id and self.product.organization_id != self.organization_id:
            errors["product"] = "O produto precisa pertencer à mesma organização do estoque."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.store} - {self.product}: {self.quantity - self.reserved_quantity} disponível"


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        INBOUND = "inbound", "Entrada"
        SALE = "sale", "Venda"
        SALE_REVERSAL = "sale_reversal", "Estorno de venda"
        RESERVATION = "reservation", "Reserva"
        RELEASE = "release", "Liberação de reserva"
        ADJUSTMENT = "adjustment", "Ajuste"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="stock_movements", verbose_name="organização")
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="stock_movements", verbose_name="loja")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_movements", verbose_name="produto")
    movement_type = models.CharField("tipo", max_length=24, choices=MovementType.choices)
    quantity = models.DecimalField("quantidade", max_digits=12, decimal_places=3)
    balance_after = models.DecimalField("saldo após movimento", max_digits=12, decimal_places=3)
    sale = models.ForeignKey("sales.Sale", on_delete=models.PROTECT, related_name="stock_movements", null=True, blank=True, verbose_name="venda")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_movements", null=True, blank=True, verbose_name="responsável")
    reason = models.CharField("motivo", max_length=255, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "movimentação de estoque"
        verbose_name_plural = "movimentações de estoque"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "store", "product", "created_at"]),
            models.Index(fields=["sale", "movement_type"]),
        ]

    def clean(self):
        errors = {}
        if self.quantity is not None and self.quantity <= 0:
            errors["quantity"] = "A quantidade movimentada precisa ser maior que zero."
        if self.balance_after is not None and self.balance_after < 0:
            errors["balance_after"] = "O saldo após o movimento não pode ser negativo."
        if self.store_id and self.organization_id and self.store.organization_id != self.organization_id:
            errors["store"] = "A loja precisa pertencer à mesma organização da movimentação."
        if self.product_id and self.organization_id and self.product.organization_id != self.organization_id:
            errors["product"] = "O produto precisa pertencer à mesma organização da movimentação."
        if self.sale_id and (self.sale.store_id != self.store_id or self.sale.organization_id != self.organization_id):
            errors["sale"] = "A venda precisa pertencer à mesma organização e loja da movimentação."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.product} x {self.quantity}"
