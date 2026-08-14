from rest_framework import permissions, viewsets

from apps.accounts.policies import can_access_pos, get_allowed_stores, get_user_organization, is_inactive_for_login

from .models import Sale
from .serializers import SaleCreateSerializer, SaleSerializer


class CanUseSalesApi(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not is_inactive_for_login(user) and can_access_pos(user))


class SaleViewSet(viewsets.ModelViewSet):
    permission_classes = [CanUseSalesApi]
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return SaleCreateSerializer
        return SaleSerializer

    def get_queryset(self):
        queryset = Sale.objects.select_related("organization", "store", "cashier").prefetch_related("items")
        user = self.request.user
        if user.is_superuser:
            return queryset
        organization = get_user_organization(user)
        if not organization:
            return queryset.none()
        return queryset.filter(organization=organization, store__in=get_allowed_stores(user))
