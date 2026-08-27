from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, TestCase

from apps.tenants.models import Organization, UserProfile

from .admin import SubscriptionAdmin, SubscriptionInvoiceAdmin
from .models import BillingPayment, BillingProviderEvent, Plan, Subscription, SubscriptionInvoice
from .services import record_manual_invoice_payment, record_provider_event


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

    def test_cross_organization_invoice_is_rejected(self):
        with self.assertRaises(ValidationError):
            SubscriptionInvoice.objects.create(
                organization=self.second_org, subscription=self.first_subscription, number="wrong", amount=Decimal("1.00"), due_date=date(2026, 8, 31)
            )
