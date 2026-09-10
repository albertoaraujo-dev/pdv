from django.conf import settings
from datetime import date
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.policies import can_access_admin, can_access_pos, get_allowed_stores, get_user_organization, is_inactive_for_login
from apps.billing.services import require_module

from .abacatepay import AbacatePayError, create_transparent, get_transparent, simulate_transparent
from .models import CardPaymentTransaction, CashRegisterMovement, CashRegisterSession, Customer, Sale, SalePayment
from .services import apply_payment_status
from .payment_serializers import SalePaymentSerializer
from .serializers import CardPaymentTransactionSerializer, CashRegisterMovementCreateSerializer, CashRegisterOpenSerializer, CashRegisterSessionSerializer, CustomerSerializer, SaleCreateSerializer, SaleSerializer
from apps.inventory.services import reverse_stock_for_sale


class CanUseSalesApi(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and not is_inactive_for_login(user) and can_access_pos(user)):
            return False
        if user.is_superuser:
            return True
        try:
            require_module(get_user_organization(user), "sales")
        except PermissionDenied:
            return False
        return True


class CashRegisterViewSet(viewsets.ViewSet):
    permission_classes = [CanUseSalesApi]

    def _stores(self, request):
        return get_allowed_stores(request.user)

    def _session(self, request, pk):
        queryset = CashRegisterSession.objects.prefetch_related("movements").select_related("store", "opened_by")
        if request.user.is_superuser:
            return queryset.get(pk=pk)
        return queryset.get(pk=pk, organization=get_user_organization(request.user), store__in=self._stores(request))

    def list(self, request):
        queryset = CashRegisterSession.objects.prefetch_related("movements").select_related("store", "opened_by")
        if request.user.is_superuser:
            queryset = queryset.all()
        else:
            queryset = queryset.filter(organization=get_user_organization(request.user), store__in=self._stores(request))
        store_id = request.query_params.get("store")
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        return Response(CashRegisterSessionSerializer(queryset[:20], many=True).data)

    def create(self, request):
        serializer = CashRegisterOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        store = self._stores(request).filter(pk=serializer.validated_data["store"]).first()
        if not store:
            return Response({"detail": "Loja não permitida para este usuário."}, status=status.HTTP_404_NOT_FOUND)
        try:
            session = CashRegisterSession.objects.create(
                organization=store.organization, store=store, opened_by=request.user,
                opening_amount=serializer.validated_data["opening_amount"],
            )
        except ValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=status.HTTP_409_CONFLICT)
        return Response(CashRegisterSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        try:
            session = self._session(request, pk)
        except CashRegisterSession.DoesNotExist:
            return Response({"detail": "Sessão de caixa não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CashRegisterSessionSerializer(session).data)

    @action(detail=False, methods=["get"], url_path="report")
    def report(self, request):
        report_date = request.query_params.get("date")
        try:
            selected_date = date.fromisoformat(report_date) if report_date else timezone.localdate()
        except ValueError:
            return Response({"date": ["Use a data no formato AAAA-MM-DD."]}, status=status.HTTP_400_BAD_REQUEST)
        queryset = CashRegisterSession.objects.select_related("store").prefetch_related("movements", "sales__items").filter(
            store__in=self._stores(request), opened_at__date=selected_date,
        )
        store_id = request.query_params.get("store")
        if store_id:
            queryset = queryset.filter(store_id=store_id)
        by_payment = {}
        completed_total = Decimal("0.00")
        cancelled_count = 0
        sales_count = 0
        completed_count = 0
        opening_total = Decimal("0.00")
        supplies_total = Decimal("0.00")
        withdrawals_total = Decimal("0.00")
        counted_total = Decimal("0.00")
        item_count = Decimal("0.000")
        product_totals = {}
        store_totals = {}
        for session in queryset:
            store = store_totals.setdefault(session.store_id, {"store": session.store_id, "store_name": session.store.name, "sales_count": 0, "completed_total": Decimal("0.00"), "expected_cash": Decimal("0.00"), "counted_cash": Decimal("0.00")})
            opening_total += session.opening_amount
            session_supplies = sum((movement.amount for movement in session.movements.all() if movement.movement_type == CashRegisterMovement.MovementType.SUPPLY), Decimal("0.00"))
            session_withdrawals = sum((movement.amount for movement in session.movements.all() if movement.movement_type == CashRegisterMovement.MovementType.WITHDRAWAL), Decimal("0.00"))
            supplies_total += session_supplies
            withdrawals_total += session_withdrawals
            store["expected_cash"] += session.opening_amount + session_supplies - session_withdrawals
            if session.closing_amount is not None:
                counted_total += session.closing_amount
                store["counted_cash"] += session.closing_amount
            for sale in session.sales.all():
                sales_count += 1
                store["sales_count"] += 1
                if sale.status == Sale.Status.CANCELLED:
                    cancelled_count += 1
                elif sale.status == Sale.Status.COMPLETED:
                    completed_count += 1
                    completed_total += sale.total_amount
                    store["completed_total"] += sale.total_amount
                    by_payment[sale.payment_method] = str(Decimal(by_payment.get(sale.payment_method, "0.00")) + sale.total_amount)
                    for item in sale.items.all():
                        item_count += item.quantity
                        product = product_totals.setdefault(item.product_id, {"product": item.product_id, "name": item.product_name, "quantity": Decimal("0.000"), "total": Decimal("0.00")})
                        product["quantity"] += item.quantity
                        product["total"] += item.line_total
        expected_total = opening_total + supplies_total - withdrawals_total
        return Response({
            "date": selected_date.isoformat(), "store": int(store_id) if store_id else None,
            "sessions_count": queryset.count(), "sales_count": sales_count,
            "cancelled_count": cancelled_count, "completed_total": str(completed_total),
            "sales_by_payment": by_payment, "opening_total": str(opening_total),
            "supplies_total": str(supplies_total), "withdrawals_total": str(withdrawals_total),
            "expected_cash_total": str(expected_total), "counted_cash_total": str(counted_total),
            "variance_total": str(counted_total - expected_total), "item_count": str(item_count),
            "average_ticket": str((completed_total / completed_count).quantize(Decimal("0.01")) if completed_count else Decimal("0.00")),
            "top_products": [
                {"product": value["product"], "name": value["name"], "quantity": str(value["quantity"]), "total": str(value["total"])}
                for value in sorted(product_totals.values(), key=lambda item: item["total"], reverse=True)[:10]
            ],
            "by_store": [
                {**value, "completed_total": str(value["completed_total"]), "expected_cash": str(value["expected_cash"]), "counted_cash": str(value["counted_cash"]), "variance": str(value["counted_cash"] - value["expected_cash"])}
                for value in sorted(store_totals.values(), key=lambda item: item["store_name"])
            ],
        })

    @action(detail=True, methods=["post"], url_path="movements")
    def movements(self, request, pk=None):
        try:
            session = self._session(request, pk)
        except CashRegisterSession.DoesNotExist:
            return Response({"detail": "Sessão de caixa não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        if session.status != CashRegisterSession.Status.OPEN:
            return Response({"detail": "O caixa já está fechado."}, status=status.HTTP_409_CONFLICT)
        serializer = CashRegisterMovementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            movement = CashRegisterMovement.objects.create(session=session, created_by=request.user, **serializer.validated_data)
        except ValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        session = self._session(request, session.pk)
        return Response(CashRegisterSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        try:
            session = self._session(request, pk)
        except CashRegisterSession.DoesNotExist:
            return Response({"detail": "Sessão de caixa não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        if session.status != CashRegisterSession.Status.OPEN:
            return Response(CashRegisterSessionSerializer(session).data)
        closing_amount = request.data.get("closing_amount")
        if closing_amount in (None, ""):
            return Response({"closing_amount": ["Informe o valor contado no fechamento."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            session.closing_amount = closing_amount
            session.closing_note = str(request.data.get("closing_note", "")).strip()
            session.status = CashRegisterSession.Status.CLOSED
            session.closed_by = request.user
            from django.utils import timezone
            session.closed_at = timezone.now()
            session.save()
        except ValidationError as exc:
            return Response({"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CashRegisterSessionSerializer(session).data)


class CustomerViewSet(viewsets.ModelViewSet):
    permission_classes = [CanUseSalesApi]
    serializer_class = CustomerSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Customer.objects.filter(is_active=True).annotate(sales_count=models.Count("sales")).order_by("name", "id")
        if self.request.query_params.get("include_inactive") == "1" and can_access_admin(self.request.user):
            queryset = Customer.objects.all().annotate(sales_count=models.Count("sales")).order_by("name", "id")
        user = self.request.user
        if user.is_superuser:
            return queryset
        organization = get_user_organization(user)
        queryset = queryset.filter(organization=organization) if organization else queryset.none()
        query = self.request.query_params.get("q", "").strip()
        if query:
            queryset = queryset.filter(models.Q(name__icontains=query) | models.Q(phone__icontains=query) | models.Q(document__icontains=query))
        return queryset

    def perform_create(self, serializer):
        serializer.save(organization=get_user_organization(self.request.user))

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        try:
            customer = self.get_object()
        except Customer.DoesNotExist:
            return Response({"detail": "Cliente não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        sales = Sale.objects.select_related("store", "cashier").prefetch_related("items").filter(customer=customer)
        if not request.user.is_superuser:
            sales = sales.filter(store__in=get_allowed_stores(request.user))
        completed = sales.filter(status=Sale.Status.COMPLETED)
        total = sum((sale.total_amount for sale in completed), Decimal("0.00"))
        return Response({
            "customer": CustomerSerializer(customer).data,
            "sales_count": sales.count(),
            "completed_sales_count": completed.count(),
            "completed_total": str(total),
            "last_sale_at": completed.values_list("created_at", flat=True).first(),
            "sales": SaleSerializer(sales[:50], many=True).data,
        })

    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        if not can_access_admin(request.user):
            return Response({"detail": "Somente gerente ou administrador pode alterar o status do cliente."}, status=status.HTTP_403_FORBIDDEN)
        customer_queryset = Customer.objects.all()
        if not request.user.is_superuser:
            customer_queryset = customer_queryset.filter(organization=get_user_organization(request.user))
        try:
            customer = customer_queryset.get(pk=pk)
        except Customer.DoesNotExist:
            return Response({"detail": "Cliente não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        active = request.data.get("is_active")
        if not isinstance(active, bool):
            return Response({"is_active": ["Informe true ou false."]}, status=status.HTTP_400_BAD_REQUEST)
        customer.is_active = active
        customer.save(update_fields=["is_active", "updated_at"])
        return Response(CustomerSerializer(customer).data)


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
