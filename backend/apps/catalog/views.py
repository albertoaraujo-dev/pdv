from django.db.models import Prefetch, Q
from rest_framework import permissions, viewsets

from apps.accounts.policies import can_access_admin, can_access_pos, get_allowed_stores, get_user_organization, is_inactive_for_login
from apps.inventory.models import Stock
from apps.tenants.models import Store

from .models import Category, Product, Unit
from .serializers import CategorySerializer, ProductSerializer, UnitSerializer


class CanReadCatalog(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and not is_inactive_for_login(user)
            and (can_access_admin(user) or can_access_pos(user))
        )


class TenantCatalogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [CanReadCatalog]

    def get_queryset(self):
        queryset = self.queryset.filter(is_active=True)
        user = self.request.user
        if user.is_superuser:
            return queryset
        organization = get_user_organization(user)
        if not organization:
            return queryset.none()
        return queryset.filter(organization=organization)


class CategoryViewSet(TenantCatalogViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class UnitViewSet(TenantCatalogViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class ProductViewSet(TenantCatalogViewSet):
    queryset = Product.objects.select_related("category", "unit")
    serializer_class = ProductSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        q = self.request.query_params.get("q", "").strip()
        sku = self.request.query_params.get("sku", "").strip()
        barcode = self.request.query_params.get("barcode", "").strip()
        category = self.request.query_params.get("category", "").strip()

        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q))
        if sku:
            queryset = queryset.filter(sku__iexact=sku)
        if barcode:
            queryset = queryset.filter(barcode__iexact=barcode)
        if category:
            queryset = queryset.filter(category_id=category)
        store_id = self.request.query_params.get("store", "").strip()
        if store_id:
            allowed_stores = Store.objects.filter(pk=store_id)
            user = self.request.user
            if not user.is_superuser:
                allowed_stores = allowed_stores.filter(pk__in=get_allowed_stores(user).values("pk"))
            if not allowed_stores.exists():
                return queryset.none()
            queryset = queryset.prefetch_related(
                Prefetch(
                    "stock_balances",
                    queryset=Stock.objects.filter(store_id=store_id),
                    to_attr="selected_store_stock",
                )
            )
        return queryset
