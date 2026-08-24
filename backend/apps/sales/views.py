from django.conf import settings
from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.policies import can_access_pos, get_allowed_stores, get_user_organization, is_inactive_for_login

from .abacatepay import AbacatePayError, create_transparent, get_transparent, simulate_transparent
from .models import Sale, SalePayment
from .payment_serializers import SalePaymentSerializer
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

    @staticmethod
    def _payment_status(value, fallback):
        normalized = str(value or "").lower()
        return normalized if normalized in SalePayment.Status.values else fallback

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

    @action(detail=True, methods=["post", "get"], url_path="abacatepay")
    def abacatepay(self, request, pk=None):
        sale = self.get_object()
        if request.method == "GET":
            return self._refresh_abacatepay(sale)

        with transaction.atomic():
            sale = Sale.objects.select_for_update().get(pk=sale.pk)
            payment, created = SalePayment.objects.select_for_update().get_or_create(
                sale=sale,
                defaults={
                    "external_id": f"pdv-sale-{sale.organization_id}-{sale.pk}",
                    "amount_cents": int(sale.total_amount * 100),
                },
            )
            if not created and payment.status != SalePayment.Status.FAILED:
                return Response(SalePaymentSerializer(payment).data, status=status.HTTP_200_OK)
            try:
                response = create_transparent(
                    amount_cents=payment.amount_cents,
                    external_id=payment.external_id,
                    metadata={"saleId": str(sale.pk), "organizationId": str(sale.organization_id)},
                )
                data = response.get("data", response)
                provider_status = self._payment_status(data.get("status"), SalePayment.Status.PENDING)
                payment.provider_id = data.get("id")
                payment.status = provider_status
                payment.br_code = data.get("brCode", "")
                payment.br_code_base64 = data.get("brCodeBase64", "")
                payment.provider_response = response
                if not payment.provider_id:
                    raise AbacatePayError("A API AbacatePay não retornou o ID do pagamento.")
                payment.save()
            except AbacatePayError as exc:
                payment.status = SalePayment.Status.FAILED
                payment.failure_reason = str(exc)
                payment.save(update_fields=["status", "failure_reason", "updated_at"])
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(SalePaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    def _refresh_abacatepay(self, sale):
        try:
            payment = sale.abacatepay_payment
        except SalePayment.DoesNotExist:
            return Response({"detail": "Pagamento AbacatePay não criado."}, status=status.HTTP_404_NOT_FOUND)
        if not payment.provider_id:
            return Response(SalePaymentSerializer(payment).data, status=status.HTTP_200_OK)
        try:
            response = get_transparent(payment.provider_id)
        except AbacatePayError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        data = response.get("data", response)
        payment.status = self._payment_status(data.get("status"), payment.status)
        payment.br_code = data.get("brCode", payment.br_code)
        payment.br_code_base64 = data.get("brCodeBase64", payment.br_code_base64)
        payment.provider_response = response
        payment.save(update_fields=["status", "br_code", "br_code_base64", "provider_response", "updated_at"])
        return Response(SalePaymentSerializer(payment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="abacatepay/simulate")
    def simulate_abacatepay(self, request, pk=None):
        if not settings.DEBUG:
            return Response({"detail": "Simulação disponível somente em DEBUG."}, status=status.HTTP_403_FORBIDDEN)
        sale = self.get_object()
        try:
            payment = sale.abacatepay_payment
        except SalePayment.DoesNotExist:
            return Response({"detail": "Pagamento AbacatePay não criado."}, status=status.HTTP_404_NOT_FOUND)
        if not payment.provider_id:
            return Response({"detail": "Pagamento ainda não possui ID no provedor."}, status=status.HTTP_409_CONFLICT)
        try:
            response = simulate_transparent(payment.provider_id)
        except AbacatePayError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        data = response.get("data", response)
        payment.status = self._payment_status(data.get("status"), payment.status)
        payment.br_code = data.get("brCode", payment.br_code)
        payment.br_code_base64 = data.get("brCodeBase64", payment.br_code_base64)
        payment.provider_response = response
        payment.save(update_fields=["status", "br_code", "br_code_base64", "provider_response", "updated_at"])
        return Response(SalePaymentSerializer(payment).data, status=status.HTTP_200_OK)
