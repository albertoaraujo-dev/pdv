from rest_framework import permissions, viewsets

from apps.accounts.policies import can_access_admin, can_access_pos, get_user_organization, is_inactive_for_login

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
