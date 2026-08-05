from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.tenants.admin import TenantScopedAdminMixin, get_user_organization

from .models import Category, Product, Unit


@admin.register(Category)
class CategoryAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ["name", "organization", "is_active"]
    list_filter = ["organization", "is_active"]
    search_fields = ["name", "organization__name"]


@admin.register(Unit)
class UnitAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ["symbol", "name", "organization", "is_active"]
    list_filter = ["organization", "is_active"]
    search_fields = ["symbol", "name", "organization__name"]


@admin.register(Product)
class ProductAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ["name", "sku", "organization", "category", "unit", "price", "is_active"]
    list_filter = ["organization", "category", "unit", "is_active"]
    search_fields = ["name", "sku", "barcode", "organization__name"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        organization = get_user_organization(request.user)
        if organization and db_field.name == "category":
            kwargs["queryset"] = Category.objects.filter(organization=organization)
        if organization and db_field.name == "unit":
            kwargs["queryset"] = Unit.objects.filter(organization=organization)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
