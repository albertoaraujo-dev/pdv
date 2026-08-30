from datetime import date, timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.tenants.models import Organization, UserProfile

from .admin import BillingNotificationAdmin, ModuleAdmin, PlanAdmin, PlanModuleAdmin, SubscriptionAdmin, SubscriptionModuleAdmin, SubscriptionInvoiceAdmin
from .models import BillingNotification, BillingPayment, BillingProviderEvent, Module, ModuleDependency, Plan, PlanModule, Subscription, SubscriptionChange, SubscriptionInvoice, SubscriptionModule
from .services import add_subscription_module, cancel_subscription, change_subscription_plan, generate_billing_notifications, generate_subscription_invoice, generate_subscription_invoices, get_module_limit, get_module_limits, get_active_modules, has_module, mark_subscription_past_due, provision_organization_subscription, record_manual_invoice_payment, record_provider_event, require_module, suspend_expired_subscriptions


class BillingTests(TestCase):
    def setUp(self):
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
        self.plan = Plan.objects.create(code="basic", name="Básico", monthly_price=Decimal("19.90"))
        self.first_subscription = Subscription.objects.create(organization=self.first_org, plan=self.plan)
        self.second_subscription = Subscription.objects.create(organization=self.second_org, plan=self.plan)
        self.invoice = SubscriptionInvoice.objects.create(
            organization=self.first_org, subscription=self.first_subscription, number="2026-001", amount=Decimal("19.90"), period_start=date(2026, 8, 1), period_end=date(2026, 8, 31), due_date=date(2026, 8, 31)
        )
        self.global_admin = get_user_model().objects.create_superuser(username="root", password="test-pass")
        self.operator = get_user_model().objects.create_user(username="operator", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.operator, organization=self.first_org, role=UserProfile.Role.ADMIN)
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.first_org, role=UserProfile.Role.MANAGER)
        self.core, _ = Module.objects.get_or_create(code="core", defaults={"name": "Core", "is_base": True})
        self.reports = Module.objects.create(code="reports", name="Relatórios")
        self.addon = Module.objects.create(code="addon", name="Addon")
        self.factory = RequestFactory()

    def test_provisioning_creates_trial_with_sales_and_base_modules(self):
        organization = Organization.objects.create(name="Nova")

        subscription = provision_organization_subscription(organization)

        self.assertEqual(subscription.status, Subscription.Status.TRIAL)
        self.assertEqual(subscription.plan.code, "mvp")
        self.assertEqual(subscription.gateway_provider, "")
        self.assertTrue(has_module(organization, "core"))
        self.assertTrue(has_module(organization, "catalog"))
        self.assertTrue(has_module(organization, "sales"))

    def test_provisioning_is_idempotent(self):
        organization = Organization.objects.create(name="Nova")

        first = provision_organization_subscription(organization)
        second = provision_organization_subscription(organization)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Subscription.objects.filter(organization=organization).count(), 1)

    def test_provisioning_ignores_inactive_default_plan(self):
        default_plan = Plan.objects.get(code="mvp")
        default_plan.is_active = False
        default_plan.save(update_fields=["is_active", "updated_at"])
        fallback = Plan.objects.create(code="mvp-fallback", name="MVP fallback", is_default=True, trial_days=0)
        PlanModule.objects.create(plan=fallback, module=Module.objects.get(code="sales"))
        organization = Organization.objects.create(name="Nova")

        subscription = provision_organization_subscription(organization)

        self.assertEqual(subscription.plan, fallback)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)

    def test_provisioning_does_not_share_subscription_between_organizations(self):
        first = Organization.objects.create(name="Primeira")
        second = Organization.objects.create(name="Segunda")

        provision_organization_subscription(first)

        self.assertFalse(Subscription.objects.filter(organization=second).exists())
        self.assertFalse(has_module(second, "sales"))

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

    def test_invoice_generation_is_idempotent_and_uses_period_and_plan_price(self):
        first = generate_subscription_invoice(self.first_subscription, "2026-09")
        second = generate_subscription_invoice(self.first_subscription, "2026-09")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.amount, Decimal("19.90"))
        self.assertEqual((first.period_start, first.period_end), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(SubscriptionInvoice.objects.filter(subscription=self.first_subscription).count(), 2)

    def test_invoice_generation_skips_cancelled_suspended_and_other_tenants(self):
        self.first_subscription.status = Subscription.Status.CANCELLED
        self.first_subscription.save(update_fields=["status", "updated_at"])
        self.second_subscription.status = Subscription.Status.SUSPENDED
        self.second_subscription.save(update_fields=["status", "updated_at"])
        self.assertEqual(generate_subscription_invoices(period="2026-09"), [])
        self.assertFalse(SubscriptionInvoice.objects.filter(period_start=date(2026, 9, 1)).exists())

    def test_batch_invoice_generation_is_idempotent(self):
        first = generate_subscription_invoices(period="2026-10")
        second = generate_subscription_invoices(period="2026-10")
        self.assertEqual(len(first), 2)
        self.assertEqual(second, [])
        self.assertEqual(SubscriptionInvoice.objects.filter(period_start=date(2026, 10, 1)).count(), 2)

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
        catalog = Module.objects.get(code="catalog")
        self.assertEqual(set(get_active_modules(self.first_org)), {self.core, catalog})

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

    def test_base_modules_are_effective_without_plan_rows(self):
        catalog, _ = Module.objects.get_or_create(code="catalog", defaults={"name": "Catálogo", "is_base": True})
        self.first_subscription.status = Subscription.Status.ACTIVE
        self.first_subscription.save(update_fields=["status", "updated_at"])

        self.assertEqual(set(get_active_modules(self.first_org)), {self.core, catalog})

    def test_dependency_is_required_and_cycles_are_rejected(self):
        catalog, _ = Module.objects.get_or_create(code="catalog", defaults={"name": "Catálogo", "is_base": True})
        sales, _ = Module.objects.get_or_create(code="sales", defaults={"name": "PDV"})
        ModuleDependency.objects.get_or_create(module=sales, depends_on=catalog)
        self.first_subscription.status = Subscription.Status.ACTIVE
        self.first_subscription.save(update_fields=["status", "updated_at"])

        self.assertFalse(has_module(self.first_org, "sales"))
        with self.assertRaises(PermissionDenied):
            require_module(self.first_org, "sales")
        with self.assertRaises(ValidationError):
            ModuleDependency.objects.create(module=catalog, depends_on=sales)

    def test_sales_requires_entitlement_and_inactive_organization(self):
        catalog, _ = Module.objects.get_or_create(code="catalog", defaults={"name": "Catálogo", "is_base": True})
        sales, _ = Module.objects.get_or_create(code="sales", defaults={"name": "PDV"})
        ModuleDependency.objects.get_or_create(module=sales, depends_on=catalog)
        self.first_subscription.status = Subscription.Status.ACTIVE
        self.first_subscription.save(update_fields=["status", "updated_at"])

        with self.assertRaises(PermissionDenied):
            require_module(self.first_org, "sales")
        PlanModule.objects.create(plan=self.plan, module=sales)
        self.assertTrue(has_module(self.first_org, "sales"))
        self.first_org.is_active = False
        self.first_org.save(update_fields=["is_active", "updated_at"])
        with self.assertRaises(PermissionDenied):
            require_module(self.first_org, "sales")

    def test_dependency_and_entitlements_are_tenant_scoped(self):
        catalog, _ = Module.objects.get_or_create(code="catalog", defaults={"name": "Catálogo", "is_base": True})
        sales, _ = Module.objects.get_or_create(code="sales", defaults={"name": "PDV"})
        ModuleDependency.objects.get_or_create(module=sales, depends_on=catalog)
        self.first_subscription.status = Subscription.Status.ACTIVE
        self.first_subscription.save(update_fields=["status", "updated_at"])
        PlanModule.objects.create(plan=self.plan, module=sales)
        other_plan = Plan.objects.create(code="other", name="Outro")
        self.second_subscription.plan = other_plan
        self.second_subscription.status = Subscription.Status.ACTIVE
        self.second_subscription.save(update_fields=["plan", "status", "updated_at"])

        self.assertTrue(has_module(self.first_org, "sales"))
        self.assertFalse(has_module(self.second_org, "sales"))

    @override_settings(BILLING_GRACE_PERIOD_DAYS=7)
    def test_overdue_transition_is_idempotent_and_suspends_after_grace(self):
        now = timezone.now()
        self.invoice.due_date = (now - timedelta(days=1)).date()
        self.invoice.save(update_fields=["due_date", "updated_at"])

        first = mark_subscription_past_due(self.first_subscription, now=now)
        second = mark_subscription_past_due(self.first_subscription, now=now + timedelta(days=1))
        self.assertEqual(first.status, Subscription.Status.PAST_DUE)
        self.assertEqual(second.grace_until, now + timedelta(days=7))
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.PAST_DUE)
        self.assertEqual(suspend_expired_subscriptions(now=now + timedelta(days=7)), 1)
        self.assertEqual(suspend_expired_subscriptions(now=now + timedelta(days=7)), 0)
        self.first_subscription.refresh_from_db()
        self.assertEqual(self.first_subscription.status, Subscription.Status.SUSPENDED)
        self.assertEqual(BillingNotification.objects.filter(invoice=self.invoice, notification_type=BillingNotification.NotificationType.PAST_DUE).count(), 1)
        self.assertEqual(BillingNotification.objects.filter(invoice=self.invoice, notification_type=BillingNotification.NotificationType.SUSPENDED).count(), 1)

    @override_settings(BILLING_DUE_SOON_DAYS=5, BILLING_SUSPENSION_WARNING_DAYS=2)
    def test_notifications_follow_windows_and_are_idempotent(self):
        now = timezone.make_aware(timezone.datetime(2026, 8, 20, 12))
        self.invoice.due_date = date(2026, 8, 25)
        self.invoice.save(update_fields=["due_date", "updated_at"])
        self.assertEqual(len(generate_billing_notifications(now=now)), 1)
        self.assertEqual(len(generate_billing_notifications(now=now)), 1)
        self.assertEqual(BillingNotification.objects.filter(notification_type=BillingNotification.NotificationType.DUE_SOON).count(), 1)
        self.first_subscription.status = Subscription.Status.PAST_DUE
        self.first_subscription.grace_until = now + timedelta(days=2)
        self.first_subscription.save(update_fields=["status", "grace_until", "updated_at"])
        self.invoice.status = SubscriptionInvoice.Status.PAST_DUE
        self.invoice.save(update_fields=["status", "updated_at"])
        self.assertEqual(len(generate_billing_notifications(now=now)), 1)
        self.assertEqual(BillingNotification.objects.filter(notification_type=BillingNotification.NotificationType.SUSPENSION_WARNING).count(), 1)

    def test_cancelled_subscription_does_not_create_notifications_and_history_remains(self):
        self.first_subscription.status = Subscription.Status.CANCELLED
        self.first_subscription.save(update_fields=["status", "updated_at"])
        self.assertEqual(generate_billing_notifications(now=timezone.now()), [])
        self.assertTrue(SubscriptionInvoice.objects.filter(pk=self.invoice.pk).exists())

    def test_notification_admin_is_read_only_and_global_only(self):
        model_admin = BillingNotificationAdmin(BillingNotification, admin.site)
        request = self.request_for(self.operator)
        self.assertFalse(model_admin.has_module_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))

    def test_cancellation_preserves_invoice_and_module_history(self):
        row = SubscriptionModule.objects.create(organization=self.first_org, subscription=self.first_subscription, module=self.core, is_active=False)
        cancel_subscription(self.first_subscription, actor=self.global_admin, reason="encerramento", metadata={"source": "test"})
        self.first_subscription.refresh_from_db()
        self.assertEqual(self.first_subscription.status, Subscription.Status.CANCELLED)
        self.assertEqual(self.first_subscription.cancellation_reason, "encerramento")
        self.assertTrue(SubscriptionInvoice.objects.filter(pk=self.invoice.pk).exists())
        self.assertTrue(SubscriptionModule.objects.filter(pk=row.pk).exists())

    def test_downgrade_preserves_records_and_removes_only_effective_module(self):
        premium = Plan.objects.create(code="premium", name="Premium")
        PlanModule.objects.create(plan=premium, module=self.reports)
        self.first_subscription.plan = premium
        self.first_subscription.status = Subscription.Status.ACTIVE
        self.first_subscription.save(update_fields=["plan", "status", "updated_at"])
        change_subscription_plan(self.first_subscription, self.plan, actor=self.global_admin, reason="downgrade")
        self.assertEqual(SubscriptionChange.objects.count(), 1)
        self.assertTrue(PlanModule.objects.filter(plan=premium, module=self.reports).exists())
        self.assertTrue(SubscriptionInvoice.objects.filter(pk=self.invoice.pk).exists())
        self.assertFalse(has_module(self.first_org, "reports"))

    def test_upgrade_records_change_and_exposes_new_module(self):
        PlanModule.objects.create(plan=self.plan, module=self.reports)
        premium = Plan.objects.create(code="premium", name="Premium")
        PlanModule.objects.create(plan=premium, module=self.reports)
        change_subscription_plan(self.first_subscription, premium, actor=self.global_admin, reason="upgrade")
        self.assertEqual(self.first_subscription.__class__.objects.get(pk=self.first_subscription.pk).plan_id, premium.pk)
        self.assertTrue(has_module(self.first_org, "reports"))
        self.assertEqual(SubscriptionChange.objects.get().reason, "upgrade")

    def test_payment_reactivates_suspended_but_not_cancelled_subscription(self):
        self.first_subscription.status = Subscription.Status.SUSPENDED
        self.first_subscription.past_due_since = timezone.now() - timedelta(days=8)
        self.first_subscription.grace_until = timezone.now() - timedelta(days=1)
        self.first_subscription.save(update_fields=["status", "past_due_since", "grace_until", "updated_at"])
        self.invoice.due_date = (timezone.now() - timedelta(days=1)).date()
        self.invoice.status = SubscriptionInvoice.Status.PAST_DUE
        self.invoice.save(update_fields=["due_date", "status", "updated_at"])
        record_manual_invoice_payment(self.invoice, actor=self.global_admin, idempotency_key="reactivate")
        self.first_subscription.refresh_from_db()
        self.assertEqual(self.first_subscription.status, Subscription.Status.ACTIVE)
        self.assertIsNone(self.first_subscription.grace_until)

        self.first_subscription.status = Subscription.Status.CANCELLED
        self.first_subscription.save(update_fields=["status", "updated_at"])
        other = SubscriptionInvoice.objects.create(organization=self.first_org, subscription=self.first_subscription, number="2026-002", amount=Decimal("1.00"), period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), due_date=date(2026, 8, 31))
        record_manual_invoice_payment(other, actor=self.global_admin, idempotency_key="cancelled-payment")
        self.first_subscription.refresh_from_db()
        self.assertEqual(self.first_subscription.status, Subscription.Status.CANCELLED)

    def test_lifecycle_mutations_are_global_only_and_tenant_safe(self):
        with self.assertRaises(PermissionDenied):
            cancel_subscription(self.first_subscription, actor=self.manager, reason="forbidden")
        with self.assertRaises(PermissionDenied):
            change_subscription_plan(self.first_subscription, self.plan, actor=self.operator)
        with self.assertRaises(ValidationError):
            SubscriptionInvoice.objects.create(organization=self.second_org, subscription=self.first_subscription, number="tenant-safe", amount=Decimal("1.00"), due_date=date(2026, 8, 31))
