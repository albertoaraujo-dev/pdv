from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils import timezone
from unfold.admin import ModelAdmin

from apps.tenants.admin import NoDeleteAdminMixin

from .models import BillingNotification, BillingPayment, BillingPlanRequest, BillingProviderEvent, Module, ModuleDependency, Plan, PlanModule, Subscription, SubscriptionChange, SubscriptionInvoice, SubscriptionInvoiceItem, SubscriptionModule
from .services import approve_billing_plan_request, record_manual_invoice_payment, reject_billing_plan_request


class GlobalBillingAdminMixin:
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if request.user.is_superuser else queryset.none()

    def has_module_permission(self, request):
        return bool(request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_add_permission(self, request):
        return bool(request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)


@admin.register(BillingPlanRequest)
class BillingPlanRequestAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["organization", "organization_pending_count", "requester", "target", "status", "request_key", "reviewed_by", "created_at", "reviewed_at"]
    list_filter = ["status", "requested_plan", "requested_module", "created_at", "reviewed_at"]
    search_fields = [
        "organization__name", "organization__document", "requester__username", "requester__email",
        "request_key", "requested_plan__code", "requested_plan__name", "requested_module__code", "requested_module__name",
    ]
    date_hierarchy = "created_at"
    list_per_page = 25
    readonly_fields = ["organization", "requester", "requested_plan", "requested_module", "status", "request_key", "notes", "reviewed_by", "reviewed_at", "created_at"]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("approve_requests", None)
            actions.pop("reject_requests", None)
        return actions
    list_select_related = ["organization", "requester", "requested_plan", "requested_module", "reviewed_by"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            organization_pending_count=Count(
                "organization__billing_plan_requests",
                filter=Q(organization__billing_plan_requests__status=BillingPlanRequest.Status.OPEN),
                distinct=True,
            )
        )

    @admin.display(ordering="organization_pending_count", description="pendentes na organização")
    def organization_pending_count(self, obj):
        return obj.organization_pending_count

    def target(self, obj):
        return obj.requested_plan or obj.requested_module

    target.short_description = "alvo"

    def _run_request_action(self, request, queryset, service, success_message, skipped_message):
        selected = queryset.count()
        pending = queryset.filter(status=BillingPlanRequest.Status.OPEN)
        skipped = selected - pending.count()
        succeeded = 0
        failed = 0
        for billing_request in pending:
            try:
                service(billing_request, reviewer=request.user)
            except Exception as exc:
                failed += 1
                self.message_user(
                    request,
                    f"Solicitação {billing_request.request_key}: {exc}",
                    messages.ERROR,
                )
            else:
                succeeded += 1
        if succeeded:
            self.message_user(request, success_message.format(count=succeeded), messages.SUCCESS)
        if skipped:
            self.message_user(request, skipped_message.format(count=skipped), messages.WARNING)
        if failed:
            self.message_user(request, f"{failed} solicitação(ões) não puderam ser processadas.", messages.ERROR)

    @admin.action(description="Aprovar solicitações selecionadas")
    def approve_requests(self, request, queryset):
        self._run_request_action(
            request, queryset, approve_billing_plan_request,
            "{count} solicitação(ões) aprovada(s).",
            "{count} solicitação(ões) já revisada(s) foram ignorada(s).",
        )

    @admin.action(description="Rejeitar solicitações selecionadas")
    def reject_requests(self, request, queryset):
        self._run_request_action(
            request, queryset, reject_billing_plan_request,
            "{count} solicitação(ões) rejeitada(s).",
            "{count} solicitação(ões) já revisada(s) foram ignorada(s).",
        )

    actions = ["approve_requests", "reject_requests"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # The form is read-only; Django still requires change permission to expose actions.
        return super().has_change_permission(request, obj)


@admin.register(Plan)
class PlanAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["code", "name", "monthly_price", "trial_days", "is_default", "is_active"]
    list_filter = ["is_default", "is_active"]
    search_fields = ["code", "name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Module)
class ModuleAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["code", "name", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ModuleDependency)
class ModuleDependencyAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["module", "depends_on", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["module__code", "depends_on__code"]


@admin.register(PlanModule)
class PlanModuleAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["plan", "module", "included", "monthly_price", "limits"]
    list_filter = ["included", "plan"]
    search_fields = ["plan__name", "module__code", "module__name"]


@admin.register(SubscriptionModule)
class SubscriptionModuleAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["organization", "subscription", "module", "included", "monthly_price", "is_active", "starts_at", "ends_at", "limits"]
    list_filter = ["is_active", "module"]
    search_fields = ["organization__name", "module__code", "module__name"]
    readonly_fields = ["created_at", "updated_at"]
    list_select_related = ["organization", "subscription", "module"]


@admin.register(Subscription)
class SubscriptionAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["organization", "plan", "status", "gateway_provider", "current_period_end", "updated_at"]
    list_filter = ["status", "plan", "gateway_provider"]
    search_fields = ["organization__name", "organization__document", "public_id"]
    readonly_fields = ["public_id", "created_at", "updated_at", "past_due_since", "grace_until", "cancelled_at"]
    list_select_related = ["organization", "plan"]

    @admin.action(description="Suspender assinaturas selecionadas")
    def suspend_subscriptions(self, request, queryset):
        updated = queryset.exclude(status=Subscription.Status.CANCELLED).update(status=Subscription.Status.SUSPENDED, updated_at=timezone.now())
        self.message_user(request, f"{updated} assinatura(s) suspensa(s).", messages.SUCCESS)

    actions = ["suspend_subscriptions"]


@admin.register(SubscriptionChange)
class SubscriptionChangeAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["subscription", "old_plan", "new_plan", "effective_at", "actor", "reason"]
    list_filter = ["old_plan", "new_plan", "effective_at"]
    search_fields = ["subscription__organization__name", "reason"]
    readonly_fields = ["subscription", "old_plan", "new_plan", "effective_at", "actor", "reason", "created_at"]


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["number", "organization", "amount", "status", "period_start", "period_end", "due_date", "paid_at"]
    list_filter = ["status", "due_date"]
    search_fields = ["number", "organization__name", "organization__document", "public_id"]
    readonly_fields = ["public_id", "created_at", "updated_at", "paid_at"]
    list_select_related = ["organization", "subscription", "subscription__plan"]

    @admin.action(description="Registrar pagamento manual e ativar assinatura")
    def record_manual_payment(self, request, queryset):
        count = 0
        for invoice in queryset.select_related("organization"):
            if invoice.status == SubscriptionInvoice.Status.PAID:
                continue
            record_manual_invoice_payment(invoice, actor=request.user, idempotency_key=f"admin:{invoice.public_id}")
            count += 1
        self.message_user(request, f"{count} pagamento(s) manual(is) registrado(s).", messages.SUCCESS)

    actions = ["record_manual_payment"]

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.status == SubscriptionInvoice.Status.PAID:
            fields.extend(["organization", "subscription", "number", "amount", "status", "period_start", "period_end", "due_date"])
        return fields


@admin.register(SubscriptionInvoiceItem)
class SubscriptionInvoiceItemAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["invoice", "item_type", "code", "amount", "amount_override"]
    list_filter = ["item_type"]
    search_fields = ["invoice__number", "code", "description"]
    list_select_related = ["invoice", "module"]

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and not (obj and obj.invoice.status == SubscriptionInvoice.Status.PAID)


@admin.register(BillingPayment)
class BillingPaymentAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["invoice", "organization", "amount", "method", "paid_at", "recorded_by"]
    list_filter = ["method", "paid_at"]
    search_fields = ["invoice__number", "organization__name", "idempotency_key", "provider_payment_id"]
    readonly_fields = ["public_id", "created_at"]
    list_select_related = ["invoice", "organization", "recorded_by"]


@admin.register(BillingProviderEvent)
class BillingProviderEventAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["event_id", "provider", "event_type", "organization", "invoice", "processed_at", "created_at"]
    list_filter = ["provider", "event_type", "processed_at"]
    search_fields = ["event_id", "provider", "event_type", "organization__name"]
    readonly_fields = ["event_id", "provider", "event_type", "organization", "invoice", "payload", "processed_at", "created_at"]
    list_select_related = ["organization", "invoice"]


@admin.register(BillingNotification)
class BillingNotificationAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["notification_type", "organization", "subscription", "invoice", "delivered_at", "created_at"]
    list_filter = ["notification_type", "delivered_at", "created_at"]
    search_fields = ["organization__name", "invoice__number", "idempotency_key"]
    readonly_fields = ["organization", "subscription", "invoice", "notification_type", "idempotency_key", "period_start", "period_end", "delivered_at", "payload", "created_at"]
    list_select_related = ["organization", "subscription", "invoice"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
