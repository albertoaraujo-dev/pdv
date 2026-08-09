from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import BooleanRadioFilter, DropdownFilter

from apps.tenants.admin import TenantScopedAdminMixin, get_user_organization

from .models import Category, Product, Unit


class TenantCategoryFilter(DropdownFilter):
    title = "categoria"
    parameter_name = "categoria"

    def lookups(self, request, model_admin):
        queryset = Category.objects.all()
        organization = get_user_organization(request.user)
        if organization and not request.user.is_superuser:
            queryset = queryset.filter(organization=organization)
        return [(category.pk, category.name) for category in queryset.order_by("name")]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(category_id=self.value())
        return queryset


class TenantUnitFilter(DropdownFilter):
    title = "unidade"
    parameter_name = "unidade"

    def lookups(self, request, model_admin):
        queryset = Unit.objects.all()
        organization = get_user_organization(request.user)
        if organization and not request.user.is_superuser:
            queryset = queryset.filter(organization=organization)
        return [(unit.pk, unit.symbol) for unit in queryset.order_by("symbol")]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(unit_id=self.value())
        return queryset


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
    list_filter = ["organization", TenantCategoryFilter, TenantUnitFilter, ("is_active", BooleanRadioFilter)]
    list_filter_submit = True
    list_per_page = 25
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["name", "sku", "barcode", "organization__name"]
    tenant_list_filter = [TenantCategoryFilter, TenantUnitFilter, ("is_active", BooleanRadioFilter)]

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

    def get_form(self, request, obj=None, change=False, **kwargs):
        form_class = super().get_form(request, obj, change, **kwargs)
        organization = get_user_organization(request.user)
        if request.user.is_superuser or obj is not None or not organization:
            return form_class

        class TenantProductForm(form_class):
            def _post_clean(self):
                self.instance.organization = organization
                super()._post_clean()

        return TenantProductForm

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        organization = get_user_organization(request.user)
        if organization and db_field.name == "category":
            kwargs["queryset"] = Category.objects.filter(organization=organization)
        if organization and db_field.name == "unit":
            kwargs["queryset"] = Unit.objects.filter(organization=organization)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
