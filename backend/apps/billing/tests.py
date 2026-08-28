from datetime import date, timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.tenants.models import Organization, UserProfile

from .admin import ModuleAdmin, PlanAdmin, PlanModuleAdmin, SubscriptionAdmin, SubscriptionModuleAdmin, SubscriptionInvoiceAdmin
from .models import BillingPayment, BillingProviderEvent, Module, Plan, PlanModule, Subscription, SubscriptionInvoice, SubscriptionModule
from .services import add_subscription_module, get_module_limit, get_module_limits, get_active_modules, has_module, record_manual_invoice_payment, record_provider_event, require_module


class BillingTests(TestCase):
    def setUp(self):
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
        self.plan = Plan.objects.create(code="basic", name="Básico", monthly_price=Decimal("19.90"))
        self.first_subscription = Subscription.objects.create(organization=self.first_org, plan=self.plan)
        self.second_subscription = Subscription.objects.create(organization=self.second_org, plan=self.plan)
        self.invoice = SubscriptionInvoice.objects.create(
            organization=self.first_org, subscription=self.first_subscription, number="2026-001", amount=Decimal("19.90"), due_date=date(2026, 8, 31)
        )
        self.global_admin = get_user_model().objects.create_superuser(username="root", password="test-pass")
        self.operator = get_user_model().objects.create_user(username="operator", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.operator, organization=self.first_org, role=UserProfile.Role.ADMIN)
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.first_org, role=UserProfile.Role.MANAGER)
        self.core = Module.objects.create(code="core", name="Core")
        self.reports = Module.objects.create(code="reports", name="Relatórios")
        self.addon = Module.objects.create(code="addon", name="Addon")
        self.factory = RequestFactory()

    def request_for(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def test_billing_admin_isolated_from_tenant_admin(self):
        model_admin = SubscriptionAdmin(Subscription, admin.site)
        self.assertEqual(model_admin.get_queryset(self.request_for(self.operator)).count(), 0)
        self.assertEqual(model_admin.get_queryset(self.request_for(self.global_admin)).count(), 2)
        self.assertFalse(model_admin.has_change_permission(self.request_for(self.operator), self.first_subscription))

    def test_manual_payment_activates_subscription(self):
        payment = record_manual_invoice_payment(self.invoice, actor=self.global_admin, idempotency_key="manual-001")
        self.invoice.refresh_from_db()
        self.first_subscription.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("19.90"))
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(self.first_subscription.status, Subscription.Status.ACTIVE)

    def test_duplicate_payment_and_event_are_idempotent(self):
        first = record_manual_invoice_payment(self.invoice, actor=self.global_admin, idempotency_key="manual-002")
        second = record_manual_invoice_payment(self.invoice, actor=self.global_admin, idempotency_key="manual-002")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BillingPayment.objects.count(), 1)
        event_one = record_provider_event(event_id="evt-001", provider="test", event_type="payment.paid", payload={"ok": True}, invoice=self.invoice, organization=self.first_org)
        event_two = record_provider_event(event_id="evt-001", provider="test", event_type="payment.paid", payload={"changed": True}, invoice=self.invoice, organization=self.first_org)
        self.assertEqual(event_one.pk, event_two.pk)
        self.assertEqual(BillingProviderEvent.objects.count(), 1)

    def test_suspension_preserves_historical_invoice(self):
        self.first_subscription.status = Subscription.Status.SUSPENDED
        self.first_subscription.save(update_fields=["status", "updated_at"])
        self.assertTrue(SubscriptionInvoice.objects.filter(pk=self.invoice.pk).exists())
        self.assertTrue(Organization.objects.filter(pk=self.first_org.pk).exists())

    def test_billing_mutations_require_superuser(self):
        with self.assertRaises(PermissionDenied):
            record_manual_invoice_payment(self.invoice, actor=self.operator, idempotency_key="forbidden")
        invoice_admin = SubscriptionInvoiceAdmin(SubscriptionInvoice, admin.site)
        request = self.request_for(self.operator)
        self.assertFalse(invoice_admin.has_module_permission(request))
        self.assertFalse(invoice_admin.has_add_permission(request))

    def test_billing_business_records_cannot_be_deleted(self):
        request = self.request_for(self.global_admin)

        for model_admin, obj in (
            (PlanAdmin(Plan, admin.site), self.plan),
            (ModuleAdmin(Module, admin.site), self.core),
            (PlanModuleAdmin(PlanModule, admin.site), PlanModule.objects.create(plan=self.plan, module=self.core)),
            (SubscriptionAdmin(Subscription, admin.site), self.first_subscription),
            (
                SubscriptionModuleAdmin(SubscriptionModule, admin.site),
                SubscriptionModule.objects.create(organization=self.first_org, subscription=self.first_subscription, module=self.core, is_active=False),
            ),
        ):
            self.assertFalse(model_admin.has_delete_permission(request, obj))

    def test_active_billing_children_require_active_parents(self):
        inactive_plan = Plan.objects.create(code="inactive", name="Inativo", is_active=False)
        inactive_module = Module.objects.create(code="inactive", name="Inativo", is_active=False)

        with self.assertRaises(ValidationError):
            PlanModule.objects.create(plan=inactive_plan, module=self.core)
        with self.assertRaises(ValidationError):
            SubscriptionModule.objects.create(organization=self.first_org, subscription=self.first_subscription, module=inactive_module)

    def test_inactive_billing_rows_preserve_history(self):
        row = SubscriptionModule.objects.create(
            organization=self.first_org, subscription=self.first_subscription, module=self.core, is_active=False
        )
        self.core.is_active = False
        self.core.save(update_fields=["is_active", "updated_at"])
        row.limits = {"historical": True}
        row.save()
        self.assertTrue(SubscriptionModule.objects.filter(pk=row.pk).exists())

    def test_cross_organization_invoice_is_rejected(self):
        with self.assertRaises(ValidationError):
            SubscriptionInvoice.objects.create(
                organization=self.second_org, subscription=self.first_subscription, number="wrong", amount=Decimal("1.00"), due_date=date(2026, 8, 31)
            )

    def test_plan_included_modules_and_limits(self):
        PlanModule.objects.create(plan=self.plan, module=self.core, included=True, limits={"users": 5})
        self.first_subscription.status = Subscription.Status.ACTIVE
        self.first_subscription.save(update_fields=["status", "updated_at"])
        self.assertTrue(has_module(self.first_org, "core"))
        self.assertEqual(get_module_limit(self.first_org, "core", "users"), 5)
        self.assertEqual(list(get_active_modules(self.first_org)), [self.core])

    def test_subscription_addon_and_override_limits(self):
        PlanModule.objects.create(plan=self.plan, module=self.core, included=True, limits={"users": 5, "stores": 1})
        self.first_subscription.status = Subscription.Status.ACTIVE
        self.first_subscription.save(update_fields=["status", "updated_at"])
        add_subscription_module(self.first_subscription, self.addon, actor=self.manager, limits={"users": 20})
        add_subscription_module(self.first_subscription, self.core, actor=self.manager, limits={"stores": 3})
        self.assertTrue(has_module(self.first_org, "addon"))
        self.assertEqual(get_module_limits(self.first_org, "core"), {"users": 5, "stores": 3})

    def test_suspended_subscription_denies_modules(self):
        PlanModule.objects.create(plan=self.plan, module=self.core)
        self.first_subscription.status = Subscription.Status.SUSPENDED
        self.first_subscription.save(update_fields=["status", "updated_at"])
        self.assertFalse(has_module(self.first_org, "core"))
        with self.assertRaises(PermissionDenied):
            require_module(self.first_org, "core")

    def test_past_due_and_cancelled_subscriptions_deny_modules(self):
        PlanModule.objects.create(plan=self.plan, module=self.core)
        for status in (Subscription.Status.PAST_DUE, Subscription.Status.CANCELLED):
            self.first_subscription.status = status
            self.first_subscription.save(update_fields=["status", "updated_at"])
            self.assertFalse(has_module(self.first_org, "core"))

    def test_trial_expiration_denies_modules(self):
        PlanModule.objects.create(plan=self.plan, module=self.core)
        self.first_subscription.trial_ends_at = timezone.now() - timedelta(minutes=1)
        self.first_subscription.save(update_fields=["trial_ends_at", "updated_at"])
        self.assertFalse(has_module(self.first_org, "core"))

    def test_cross_organization_subscription_module_is_rejected(self):
        with self.assertRaises(ValidationError):
            SubscriptionModule.objects.create(organization=self.second_org, subscription=self.first_subscription, module=self.core)

    def test_inactive_and_historical_module_records(self):
        PlanModule.objects.create(plan=self.plan, module=self.core)
        self.first_subscription.status = Subscription.Status.ACTIVE
        self.first_subscription.save(update_fields=["status", "updated_at"])
        row = add_subscription_module(self.first_subscription, self.addon, actor=self.manager, ends_at=timezone.now() - timedelta(days=1))
        self.addon.is_active = False
        self.addon.save(update_fields=["is_active", "updated_at"])
        self.assertFalse(has_module(self.first_org, "addon"))
        self.assertTrue(SubscriptionModule.objects.filter(pk=row.pk).exists())
        self.assertTrue(PlanModule.objects.filter(module=self.core).exists())

    def test_addon_mutation_requires_manager_or_global_admin(self):
        with self.assertRaises(PermissionDenied):
            add_subscription_module(self.first_subscription, self.addon, actor=self.operator)
