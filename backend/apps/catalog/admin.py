from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.tenants.admin import TenantScopedAdminMixin, get_user_organization

from .models import Category, Product, Unit


@admin.register(Category)
class CategoryAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ["name", "organization", "is_active"]
    list_display_links = ["name"]
    list_editable = ["is_active"]
    list_filter = ["organization", "is_active"]
    list_per_page = 25
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["name", "organization__name"]

    def get_fieldsets(self, request, obj=None):
        main_fields = ["name", "is_active"]
        if request.user.is_superuser or obj is not None:
            main_fields.insert(1, "organization")
        fieldsets = [("Dados da categoria", {"fields": main_fields})]
        if obj is not None:
            fieldsets.append(("Controle", {"fields": ["created_at", "updated_at"]}))
        return fieldsets


@admin.register(Unit)
class UnitAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ["symbol", "name", "organization", "is_active"]
    list_display_links = ["symbol", "name"]
    list_editable = ["is_active"]
    list_filter = ["organization", "is_active"]
    list_per_page = 25
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["symbol", "name", "organization__name"]

    def get_fieldsets(self, request, obj=None):
        main_fields = ["symbol", "name", "is_active"]
        if request.user.is_superuser or obj is not None:
            main_fields.insert(2, "organization")
        fieldsets = [("Dados da unidade", {"fields": main_fields})]
        if obj is not None:
            fieldsets.append(("Controle", {"fields": ["created_at", "updated_at"]}))
        return fieldsets


@admin.register(Product)
class ProductAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ["name", "sku", "organization", "category", "unit", "price", "is_active"]
    list_display_links = ["name", "sku"]
    list_editable = ["is_active"]
    list_filter = ["organization", "category", "unit", "is_active"]
    list_per_page = 25
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["name", "sku", "barcode", "organization__name"]

    def get_fieldsets(self, request, obj=None):
        identity_fields = ["name", "sku", "barcode"]
        if request.user.is_superuser or obj is not None:
            identity_fields.insert(0, "organization")
        fieldsets = [
            ("Identificação", {"fields": identity_fields}),
            ("Classificação", {"fields": ["category", "unit"]}),
            ("Venda", {"fields": ["price", "is_active"]}),
        ]
        if obj is not None:
            fieldsets.append(("Controle", {"fields": ["created_at", "updated_at"]}))
        return fieldsets

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        organization = get_user_organization(request.user)
        if organization and db_field.name == "category":
            kwargs["queryset"] = Category.objects.filter(organization=organization)
        if organization and db_field.name == "unit":
            kwargs["queryset"] = Unit.objects.filter(organization=organization)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
