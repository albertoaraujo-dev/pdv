from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.accounts.policies import can_access_admin, get_allowed_stores, get_user_organization

from .models import Stock, StockMovement


@admin.register(Stock)
class StockAdmin(ModelAdmin):
    list_display = ["store", "product", "quantity", "updated_at"]
    list_filter = ["store", "updated_at"]
    search_fields = ["store__name", "product__name", "product__sku"]
    readonly_fields = ["organization", "store", "product", "quantity", "updated_at"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("organization", "store", "product")
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
        return False


@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display = ["created_at", "store", "product", "movement_type", "quantity", "balance_after", "sale"]
    list_filter = ["movement_type", "store", "created_at"]
    search_fields = ["product__name", "product__sku", "sale__id", "reason"]
    readonly_fields = [
        "organization", "store", "product", "movement_type", "quantity", "balance_after", "sale", "created_by", "reason", "created_at"
    ]

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("organization", "store", "product", "sale")
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
        return False
