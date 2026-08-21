from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.policies import can_access_pos, get_allowed_stores, get_user_organization, is_inactive_for_login

from .models import Sale
from .serializers import SaleCreateSerializer, SaleSerializer
from apps.inventory.services import reverse_stock_for_sale


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

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        sale = reverse_stock_for_sale(self.get_object(), request.user)
        return Response(SaleSerializer(sale, context={"request": request}).data, status=status.HTTP_200_OK)
