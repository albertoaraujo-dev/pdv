from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.accounts.policies import can_access_admin, get_allowed_stores, get_user_organization

from .models import Sale, SaleItem


class SaleItemInline(TabularInline):
    model = SaleItem
    extra = 0
    can_delete = False
    readonly_fields = ["product", "product_name", "product_sku", "quantity", "unit_price", "line_total", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(ModelAdmin):
    list_display = ["id", "store", "cashier", "status", "payment_method", "total_amount", "amount_received", "change_amount", "created_at"]
    list_filter = ["status", "payment_method", "store", "created_at"]
    readonly_fields = ["organization", "store", "cashier", "status", "payment_method", "total_amount", "amount_received", "change_amount", "created_at", "updated_at"]
    search_fields = ["id", "store__name", "cashier__username"]
    inlines = [SaleItemInline]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("organization", "store", "cashier")
        if request.user.is_superuser:
            return queryset
        organization = get_user_organization(request.user)
        if not organization:
            return queryset.none()
        return queryset.filter(organization=organization, store__in=get_allowed_stores(request.user))

    def has_module_permission(self, request):
        return can_access_admin(request.user)

    def has_view_permission(self, request, obj=None):
        if not can_access_admin(request.user):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(SaleItem)
class SaleItemAdmin(ModelAdmin):
    list_display = ["sale", "product_name", "quantity", "unit_price", "line_total"]
    readonly_fields = ["sale", "product", "product_name", "product_sku", "quantity", "unit_price", "line_total", "created_at"]
    search_fields = ["product_name", "product_sku", "sale__id"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("sale", "sale__organization", "sale__store", "product")
        if request.user.is_superuser:
            return queryset
        organization = get_user_organization(request.user)
        if not organization:
            return queryset.none()
        return queryset.filter(sale__organization=organization, sale__store__in=get_allowed_stores(request.user))

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj is None:
            return False
        return self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
