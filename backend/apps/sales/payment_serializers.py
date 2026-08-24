from rest_framework import serializers

from .models import SalePayment


class SalePaymentSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="provider_id", read_only=True)
    brCode = serializers.CharField(source="br_code", read_only=True)
    brCodeBase64 = serializers.CharField(source="br_code_base64", read_only=True)

    class Meta:
        model = SalePayment
        fields = ["id", "status", "brCode", "brCodeBase64"]
