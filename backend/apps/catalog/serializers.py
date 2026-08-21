from decimal import Decimal

from rest_framework import serializers

from .models import Category, Product, Unit


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "name", "symbol"]


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    unit = UnitSerializer(read_only=True)
    stock_quantity = serializers.SerializerMethodField()

    def get_stock_quantity(self, obj):
        stock = getattr(obj, "selected_store_stock", None)
        if stock is None:
            return None
        quantity = stock[0].quantity if stock else Decimal("0.000")
        return format(quantity.quantize(Decimal("0.001")), "f")

    class Meta:
        model = Product
        fields = ["id", "name", "sku", "barcode", "price", "category", "unit", "stock_quantity"]
