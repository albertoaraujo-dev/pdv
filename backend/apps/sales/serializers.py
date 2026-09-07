from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.accounts.policies import get_allowed_stores
from apps.catalog.models import Product
from apps.inventory.services import InsufficientStockError, deduct_stock_for_sale, reserve_stock_for_sale

from .models import CardPaymentTransaction, CashRegisterMovement, CashRegisterSession, Sale, SaleItem


MONEY_QUANT = Decimal("0.01")


class SaleItemInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.select_related("organization"))
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("A quantidade precisa ser maior que zero.")
        if value != value.to_integral_value():
            raise serializers.ValidationError("Venda somente em unidades inteiras.")
        return value


class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_name", "product_sku", "quantity", "unit_price", "line_total"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    payment_method_label = serializers.CharField(source="get_payment_method_display", read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "organization",
            "store",
            "cashier",
            "status",
            "total_amount",
            "payment_method",
            "payment_method_label",
            "amount_received",
            "change_amount",
            "client_request_id",
            "items",
            "created_at",
        ]
        read_only_fields = ["organization", "cashier", "status", "total_amount", "payment_method_label", "amount_received", "change_amount", "client_request_id", "created_at"]


class CardPaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CardPaymentTransaction
        fields = ["id", "sale", "external_id", "client_reference", "provider", "terminal_id", "amount_cents", "status", "reconciled_at", "reconciled_by", "created_at", "updated_at"]
        read_only_fields = fields


class SaleCreateSerializer(serializers.ModelSerializer):
    items = SaleItemInputSerializer(many=True, write_only=True)
    amount_received = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = Sale
        fields = ["id", "store", "payment_method", "amount_received", "client_request_id", "items"]

    def calculate_total(self, items):
        total = Decimal("0.00")
        for item in items:
            total += (item["quantity"] * item["product"].price).quantize(MONEY_QUANT)
        return total.quantize(MONEY_QUANT)

    def validate(self, attrs):
        request = self.context["request"]
        store = attrs["store"]
        items = attrs.get("items") or []
        allowed_stores = get_allowed_stores(request.user)

        if not allowed_stores.filter(pk=store.pk).exists():
            raise serializers.ValidationError({"store": "Loja não permitida para este usuário."})
        if not items:
            raise serializers.ValidationError({"items": "Adicione pelo menos um item à venda."})

        for item in items:
            product = item["product"]
            if product.organization_id != store.organization_id:
                raise serializers.ValidationError({"items": "Todos os produtos precisam pertencer à organização da loja."})
            if not product.is_active:
                raise serializers.ValidationError({"items": f"Produto inativo: {product.name}."})
        total = self.calculate_total(items)
        amount_received = attrs["amount_received"].quantize(MONEY_QUANT)
        if amount_received < total:
            raise serializers.ValidationError({"amount_received": "O valor recebido não pode ser menor que o total da venda."})
        attrs["amount_received"] = amount_received
        attrs["_calculated_total"] = total
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        store = validated_data["store"]
        items_data = validated_data.pop("items")
        total = validated_data.pop("_calculated_total")
        amount_received = validated_data["amount_received"]
        payment_method = validated_data.get("payment_method", Sale.PaymentMethod.CASH)
        client_request_id = validated_data.get("client_request_id")
        if client_request_id:
            existing_sale = Sale.objects.filter(cashier=request.user, store=store, client_request_id=client_request_id).first()
            if existing_sale:
                if existing_sale.payment_method == Sale.PaymentMethod.CARD_EXTERNAL:
                    _ensure_card_transaction(existing_sale)
                return existing_sale
        sale = Sale.objects.create(
            organization=store.organization,
            store=store,
            cashier=request.user,
            status=Sale.Status.PENDING_PAYMENT if payment_method == Sale.PaymentMethod.PIX_ABACATEPAY else Sale.Status.COMPLETED,
            payment_method=payment_method,
            amount_received=amount_received,
            change_amount=(amount_received - total).quantize(MONEY_QUANT) if payment_method == Sale.PaymentMethod.CASH else Decimal("0.00"),
            client_request_id=client_request_id,
        )
        for item_data in items_data:
            product = item_data["product"]
            quantity = item_data["quantity"]
            line_total = (quantity * product.price).quantize(MONEY_QUANT)
            SaleItem.objects.create(
                sale=sale,
                product=product,
                product_name=product.name,
                product_sku=product.sku,
                quantity=quantity,
                unit_price=product.price,
                line_total=line_total,
            )
        try:
            if payment_method == Sale.PaymentMethod.PIX_ABACATEPAY:
                reserve_stock_for_sale(sale, sale.items.select_related("product"), request.user)
            else:
                deduct_stock_for_sale(sale, sale.items.select_related("product"), request.user)
        except InsufficientStockError as exc:
            raise serializers.ValidationError({"items": str(exc)}) from exc
        sale.total_amount = total
        sale.save(update_fields=["total_amount", "updated_at"])
        if payment_method == Sale.PaymentMethod.CARD_EXTERNAL:
            _ensure_card_transaction(sale)
        return sale

    def to_representation(self, instance):
        return SaleSerializer(instance, context=self.context).data


def _ensure_card_transaction(sale):
    client_reference = (
        f"card-{sale.organization_id}-{sale.client_request_id}"
        if sale.client_request_id
        else f"card-sale-{sale.organization_id}-{sale.pk}"
    )
    transaction, _created = CardPaymentTransaction.objects.get_or_create(
        sale=sale,
        defaults={
            "external_id": f"pdv-card-sale-{sale.organization_id}-{sale.pk}",
            "client_reference": client_reference,
            "amount_cents": int(sale.total_amount * 100),
            "status": CardPaymentTransaction.Status.APPROVED,
        },
    )
    if transaction.amount_cents != int(sale.total_amount * 100):
        raise serializers.ValidationError({"amount_received": "O valor da transação não corresponde ao total da venda."})
    return transaction


class CashRegisterMovementSerializer(serializers.ModelSerializer):
    movement_type_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = CashRegisterMovement
        fields = ["id", "movement_type", "movement_type_label", "amount", "reason", "created_by_username", "created_at"]
        read_only_fields = ["id", "movement_type_label", "created_by_username", "created_at"]


class CashRegisterSessionSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    opened_by_username = serializers.CharField(source="opened_by.username", read_only=True)
    movements = CashRegisterMovementSerializer(many=True, read_only=True)
    total_supplies = serializers.SerializerMethodField()
    total_withdrawals = serializers.SerializerMethodField()
    expected_cash = serializers.SerializerMethodField()

    class Meta:
        model = CashRegisterSession
        fields = ["id", "store", "store_name", "status", "status_label", "opening_amount", "closing_amount", "closing_note", "opened_by_username", "opened_at", "closed_at", "movements", "total_supplies", "total_withdrawals", "expected_cash"]
        read_only_fields = ["id", "status", "status_label", "store_name", "closing_amount", "opened_by_username", "opened_at", "closed_at", "movements", "total_supplies", "total_withdrawals", "expected_cash"]

    def _total(self, obj, movement_type):
        return sum((movement.amount for movement in obj.movements.all() if movement.movement_type == movement_type), Decimal("0.00"))

    def get_total_supplies(self, obj):
        return str(self._total(obj, CashRegisterMovement.MovementType.SUPPLY))

    def get_total_withdrawals(self, obj):
        return str(self._total(obj, CashRegisterMovement.MovementType.WITHDRAWAL))

    def get_expected_cash(self, obj):
        return str(obj.opening_amount + self._total(obj, CashRegisterMovement.MovementType.SUPPLY) - self._total(obj, CashRegisterMovement.MovementType.WITHDRAWAL))


class CashRegisterOpenSerializer(serializers.Serializer):
    store = serializers.IntegerField()
    opening_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.00"))


class CashRegisterMovementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashRegisterMovement
        fields = ["movement_type", "amount", "reason"]

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("Informe o motivo da movimentação.")
        return value.strip()
