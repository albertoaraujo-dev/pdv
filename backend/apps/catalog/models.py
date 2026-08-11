from django.core.exceptions import ValidationError
from django.db import models

from apps.tenants.models import ActiveQuerySet, Organization


def strip_text_fields(instance, field_names):
    for field_name in field_names:
        value = getattr(instance, field_name)
        if isinstance(value, str):
            setattr(instance, field_name, value.strip())


def uppercase_text_fields(instance, field_names):
    for field_name in field_names:
        value = getattr(instance, field_name)
        if isinstance(value, str):
            setattr(instance, field_name, value.upper())


class Category(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="categories", verbose_name="organização")
    name = models.CharField("nome", max_length=120)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["organization__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_category_name_per_organization",
                violation_error_message="Já existe uma categoria com este nome nesta organização.",
            )
        ]
        indexes = [models.Index(fields=["organization", "is_active"])]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        strip_text_fields(self, ["name"])
        if self.pk and not self.is_active and self.products.filter(is_active=True).exists():
            errors["is_active"] = "Não é possível inativar categoria com produtos ativos."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Unit(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="units", verbose_name="organização")
    name = models.CharField("nome", max_length=80)
    symbol = models.CharField("símbolo", max_length=12)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        verbose_name = "unidade"
        verbose_name_plural = "unidades"
        ordering = ["organization__name", "symbol"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "symbol"],
                name="unique_unit_symbol_per_organization",
                violation_error_message="Já existe uma unidade com este símbolo nesta organização.",
            )
        ]
        indexes = [models.Index(fields=["organization", "is_active"])]

    def __str__(self):
        return self.symbol

    def clean(self):
        errors = {}
        strip_text_fields(self, ["name", "symbol"])
        uppercase_text_fields(self, ["symbol"])
        if self.pk and not self.is_active and self.products.filter(is_active=True).exists():
            errors["is_active"] = "Não é possível inativar unidade com produtos ativos."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Product(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="products", verbose_name="organização")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="categoria")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="products", verbose_name="unidade")
    name = models.CharField("nome", max_length=180)
    sku = models.CharField("SKU", max_length=64)
    barcode = models.CharField("código de barras", max_length=64, blank=True)
    price = models.DecimalField("preço", max_digits=12, decimal_places=2)
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["organization__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "sku"],
                name="unique_product_sku_per_organization",
                violation_error_message="Já existe um produto com este SKU nesta organização.",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "is_active"]),
            models.Index(fields=["organization", "barcode"]),
        ]

    def clean(self):
        errors = {}
        strip_text_fields(self, ["name", "sku", "barcode"])
        uppercase_text_fields(self, ["sku", "barcode"])
        if self.price is not None and self.price < 0:
            errors["price"] = "O preço não pode ser negativo."
        if self.category_id and self.category.organization_id != self.organization_id:
            errors["category"] = "A categoria precisa pertencer à mesma organização do produto."
        if self.unit_id and self.unit.organization_id != self.organization_id:
            errors["unit"] = "A unidade precisa pertencer à mesma organização do produto."
        if self.is_active and self.category_id and not self.category.is_active:
            errors["category"] = "Produto ativo precisa usar uma categoria ativa."
        if self.is_active and self.unit_id and not self.unit.is_active:
            errors["unit"] = "Produto ativo precisa usar uma unidade ativa."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name
