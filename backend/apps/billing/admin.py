from django.contrib import admin, messages
from django.utils import timezone
from unfold.admin import ModelAdmin

from apps.tenants.admin import NoDeleteAdminMixin

from .models import BillingPayment, BillingProviderEvent, Module, ModuleDependency, Plan, PlanModule, Subscription, SubscriptionChange, SubscriptionInvoice, SubscriptionModule
from .services import record_manual_invoice_payment


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
    list_display = ["plan", "module", "included", "limits"]
    list_filter = ["included", "plan"]
    search_fields = ["plan__name", "module__code", "module__name"]


@admin.register(SubscriptionModule)
class SubscriptionModuleAdmin(NoDeleteAdminMixin, GlobalBillingAdminMixin, ModelAdmin):
    list_display = ["organization", "subscription", "module", "included", "is_active", "starts_at", "ends_at", "limits"]
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
    list_display = ["number", "organization", "amount", "status", "due_date", "paid_at"]
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
