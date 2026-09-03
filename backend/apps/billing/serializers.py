from rest_framework import serializers

from .models import Plan, SubscriptionInvoice


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


class BillingCatalogModuleSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    included = serializers.BooleanField()
    is_base = serializers.BooleanField()
    is_free = serializers.BooleanField()
    limits = serializers.JSONField()
    monthly_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    dependencies = serializers.ListField(child=serializers.CharField())


class BillingCatalogPlanSerializer(serializers.ModelSerializer):
    modules = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = ("code", "name", "description", "monthly_price", "trial_days", "is_default", "modules")
        read_only_fields = fields

    def get_modules(self, plan):
        base_modules = {
            module.pk: {
                "code": module.code,
                "name": module.name,
                "description": module.description,
                "included": True,
                "is_base": True,
                "is_free": True,
                "limits": {},
                "monthly_price": 0,
                "dependencies": [dependency.depends_on.code for dependency in module.dependencies.all()],
            }
            for module in self.context["base_modules"]
        }
        for row in plan.plan_modules.all():
            if row.module_id in base_modules:
                continue
            base_modules[row.module_id] = {
                "code": row.module.code,
                "name": row.module.name,
                "description": row.module.description,
                "included": row.included,
                "is_base": row.module.is_base,
                "is_free": row.module.is_base or row.monthly_price in (None, 0),
                "limits": row.limits or {},
                "monthly_price": 0 if row.module.is_base else (row.monthly_price or 0),
                "dependencies": [dependency.depends_on.code for dependency in row.module.dependencies.all()],
            }
        return BillingCatalogModuleSerializer(base_modules.values(), many=True).data


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
