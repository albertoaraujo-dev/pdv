from rest_framework import serializers

from .models import SubscriptionInvoice


class BillingModuleStatusSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    limits = serializers.JSONField()


class BillingNotificationStatusSerializer(serializers.Serializer):
    type = serializers.CharField(source="notification_type")
    period_start = serializers.DateField(allow_null=True)
    period_end = serializers.DateField(allow_null=True)
    delivered_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class BillingPlanStatusSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class BillingSubscriptionStatusSerializer(serializers.Serializer):
    public_id = serializers.UUIDField()
    status = serializers.CharField()
    plan = BillingPlanStatusSerializer()
    started_at = serializers.DateTimeField(allow_null=True)
    trial_ends_at = serializers.DateTimeField(allow_null=True)
    past_due_since = serializers.DateTimeField(allow_null=True)
    grace_until = serializers.DateTimeField(allow_null=True)
    current_period_start = serializers.DateField(allow_null=True)
    current_period_end = serializers.DateField(allow_null=True)
    cancelled_at = serializers.DateTimeField(allow_null=True)


class BillingStatusSerializer(serializers.Serializer):
    organization = serializers.SerializerMethodField()
    subscription = BillingSubscriptionStatusSerializer(allow_null=True)
    effective_modules = BillingModuleStatusSerializer(many=True)
    recent_notifications = BillingNotificationStatusSerializer(many=True)

    def get_organization(self, obj):
        organization = obj["organization"]
        return {"id": organization.pk, "name": organization.name}


class BillingInvoicePlanSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class BillingInvoiceSerializer(serializers.ModelSerializer):
    plan = BillingInvoicePlanSerializer(source="subscription.plan", read_only=True)
    items = serializers.SerializerMethodField()

    def get_items(self, invoice):
        return [{"type": item.item_type, "code": item.code, "description": item.description,
                 "amount": str(item.total_amount)} for item in invoice.items.all()]

    class Meta:
        model = SubscriptionInvoice
        fields = (
            "public_id",
            "number",
            "amount",
            "status",
            "due_date",
            "period_start",
            "period_end",
            "paid_at",
            "plan",
            "items",
        )
        read_only_fields = fields
