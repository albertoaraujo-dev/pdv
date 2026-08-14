from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.accounts.policies import get_allowed_stores
from apps.catalog.models import Product

from .models import Sale, SaleItem


MONEY_QUANT = Decimal("0.01")


class SaleItemInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.select_related("organization"))
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("A quantidade precisa ser maior que zero.")
        return value


class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = ["id", "product", "product_name", "product_sku", "quantity", "unit_price", "line_total"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = ["id", "organization", "store", "cashier", "status", "total_amount", "items", "created_at"]
        read_only_fields = ["organization", "cashier", "status", "total_amount", "created_at"]


class SaleCreateSerializer(serializers.ModelSerializer):
    items = SaleItemInputSerializer(many=True, write_only=True)

    class Meta:
        model = Sale
        fields = ["id", "store", "items"]

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
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        store = validated_data["store"]
        items_data = validated_data.pop("items")
        sale = Sale.objects.create(
            organization=store.organization,
            store=store,
            cashier=request.user,
            status=Sale.Status.COMPLETED,
        )
        total = Decimal("0.00")
        for item_data in items_data:
            product = item_data["product"]
            quantity = item_data["quantity"]
            line_total = (quantity * product.price).quantize(MONEY_QUANT)
            total += line_total
            SaleItem.objects.create(
                sale=sale,
                product=product,
                product_name=product.name,
                product_sku=product.sku,
                quantity=quantity,
                unit_price=product.price,
                line_total=line_total,
            )
        sale.total_amount = total.quantize(MONEY_QUANT)
        sale.save(update_fields=["total_amount", "updated_at"])
        return sale

    def to_representation(self, instance):
        return SaleSerializer(instance, context=self.context).data
