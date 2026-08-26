from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.policies import can_access_admin, can_access_pos, get_allowed_stores, get_user_organization, is_inactive_for_login

from .abacatepay import AbacatePayError, create_transparent, get_transparent, simulate_transparent
from .models import CardPaymentTransaction, Sale, SalePayment
from .services import apply_payment_status
from .payment_serializers import SalePaymentSerializer
from .serializers import CardPaymentTransactionSerializer, SaleCreateSerializer, SaleSerializer
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

    @action(detail=True, methods=["get"], url_path="transaction")
    def transaction(self, request, pk=None):
        sale = self.get_object()
        if sale.payment_method != Sale.PaymentMethod.CARD_EXTERNAL:
            return Response({"detail": "A venda não usa cartão externo."}, status=status.HTTP_404_NOT_FOUND)
        try:
            transaction_record = sale.card_transaction
        except CardPaymentTransaction.DoesNotExist:
            return Response({"detail": "Transação de cartão não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CardPaymentTransactionSerializer(transaction_record).data)

    @action(detail=True, methods=["post"], url_path="transaction/reconcile")
    def reconcile_transaction(self, request, pk=None):
        if not can_access_admin(request.user):
            return Response({"detail": "Somente gerente ou administrador pode conciliar transações."}, status=status.HTTP_403_FORBIDDEN)
        sale = self.get_object()
        if sale.payment_method != Sale.PaymentMethod.CARD_EXTERNAL:
            return Response({"detail": "A venda não usa cartão externo."}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            try:
                transaction_record = CardPaymentTransaction.objects.select_for_update().get(sale=sale)
            except CardPaymentTransaction.DoesNotExist:
                return Response({"detail": "Transação de cartão não encontrada."}, status=status.HTTP_404_NOT_FOUND)
            if transaction_record.amount_cents != int(sale.total_amount * 100):
                return Response({"detail": "O valor da transação não corresponde ao total da venda."}, status=status.HTTP_409_CONFLICT)
            try:
                transaction_record.reconcile(request.user)
            except ValidationError as exc:
                return Response({"detail": exc.message}, status=status.HTTP_409_CONFLICT)
        return Response(CardPaymentTransactionSerializer(transaction_record).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        sale = reverse_stock_for_sale(self.get_object(), request.user)
        return Response(SaleSerializer(sale, context={"request": request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post", "get"], url_path="abacatepay")
    def abacatepay(self, request, pk=None):
        sale = self.get_object()
        # Keep the already-shipped administrative endpoint usable for legacy
        # completed sales; new gateway sales always use the pending lifecycle.
        if sale.payment_method != Sale.PaymentMethod.PIX_ABACATEPAY and sale.status != Sale.Status.COMPLETED:
            return Response({"detail": "A venda não usa Pix AbacatePay."}, status=status.HTTP_409_CONFLICT)
        if sale.status not in {Sale.Status.PENDING_PAYMENT, Sale.Status.COMPLETED}:
            return Response({"detail": "A venda não está aguardando pagamento."}, status=status.HTTP_409_CONFLICT)
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
            if not created and payment.status not in {SalePayment.Status.FAILED, SalePayment.Status.EXPIRED}:
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
                payment.br_code = data.get("brCode", "")
                payment.br_code_base64 = data.get("brCodeBase64", "")
                payment.provider_response = response
                if not payment.provider_id:
                    raise AbacatePayError("A API AbacatePay não retornou o ID do pagamento.")
                payment.save()
                payment = apply_payment_status(payment, provider_status, response, request.user)
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
        payment = apply_payment_status(
            payment,
            self._payment_status(data.get("status"), payment.status),
            response,
        )
        payment.br_code = data.get("brCode", payment.br_code)
        payment.br_code_base64 = data.get("brCodeBase64", payment.br_code_base64)
        payment.provider_response = response
        payment.save(update_fields=["br_code", "br_code_base64", "provider_response", "updated_at"])
        return Response(SalePaymentSerializer(payment).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="abacatepay/simulate")
    def simulate_abacatepay(self, request, pk=None):
        if not settings.ABACATEPAY_ALLOW_SIMULATION:
            return Response({"detail": "Simulação AbacatePay desabilitada neste ambiente."}, status=status.HTTP_403_FORBIDDEN)
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
        payment = apply_payment_status(
            payment,
            self._payment_status(data.get("status"), payment.status),
            response,
        )
        payment.br_code = data.get("brCode", payment.br_code)
        payment.br_code_base64 = data.get("brCodeBase64", payment.br_code_base64)
        payment.provider_response = response
        payment.save(update_fields=["br_code", "br_code_base64", "provider_response", "updated_at"])
        return Response(SalePaymentSerializer(payment).data, status=status.HTTP_200_OK)
