from decimal import Decimal
import base64
import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.sales.admin import SaleAdmin, SaleItemAdmin
from apps.catalog.models import Category, Product, Unit
from apps.tenants.models import Organization, Store, UserProfile, UserStoreAccess
from apps.inventory.models import Stock, StockMovement
from apps.inventory.services import reserve_stock_for_sale

from .abacatepay import AbacatePayError
from .models import Sale, SaleItem, SalePayment
from .services import apply_payment_status


class SalesApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
        self.first_store = Store.objects.create(organization=self.first_org, name="Matriz", code="M01")
        self.second_store = Store.objects.create(organization=self.second_org, name="Filial", code="F01")
        self.category = Category.objects.create(organization=self.first_org, name="Bebidas")
        self.unit = Unit.objects.create(organization=self.first_org, name="Unidade", symbol="UN")
        self.product = Product.objects.create(organization=self.first_org, category=self.category, unit=self.unit, name="Água", sku="AGUA-001", price="3.50")
        self.other_product = Product.objects.create(organization=self.first_org, category=self.category, unit=self.unit, name="Suco", sku="SUCO-001", price="5.00")
        Stock.objects.create(organization=self.first_org, store=self.first_store, product=self.product, quantity="10.000")
        Stock.objects.create(organization=self.first_org, store=self.first_store, product=self.other_product, quantity="10.000")
        self.inactive_product = Product.objects.create(organization=self.first_org, category=self.category, unit=self.unit, name="Antigo", sku="OLD-001", price="2.00", is_active=False)
        self.second_category = Category.objects.create(organization=self.second_org, name="Lanches")
        self.second_unit = Unit.objects.create(organization=self.second_org, name="Unidade", symbol="UN2")
        self.second_product = Product.objects.create(organization=self.second_org, category=self.second_category, unit=self.second_unit, name="Sanduíche", sku="SAND-001", price="12.00")
        self.operator = get_user_model().objects.create_user(username="operator", password="test-pass")
        UserProfile.objects.create(user=self.operator, organization=self.first_org, role=UserProfile.Role.CASHIER)
        UserStoreAccess.objects.create(profile=self.operator.profile, store=self.first_store)
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.first_org, role=UserProfile.Role.MANAGER)
        UserStoreAccess.objects.create(profile=self.manager.profile, store=self.first_store)

    def test_sales_api_requires_authentication(self):
        response = self.client.get(reverse("sale-list"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "not_authenticated")

    def test_operator_can_create_sale_for_allowed_store(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(
            reverse("sale-list"),
            {
                "store": self.first_store.id,
                "payment_method": Sale.PaymentMethod.CASH,
                "amount_received": "20.00",
                "items": [
                    {"product": self.product.id, "quantity": "2.000"},
                    {"product": self.other_product.id, "quantity": "1.000"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.json())
        sale = Sale.objects.get()
        self.assertEqual(sale.organization, self.first_org)
        self.assertEqual(sale.store, self.first_store)
        self.assertEqual(sale.cashier, self.operator)
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(sale.total_amount, Decimal("12.00"))
        self.assertEqual(sale.payment_method, Sale.PaymentMethod.CASH)
        self.assertEqual(sale.amount_received, Decimal("20.00"))
        self.assertEqual(sale.change_amount, Decimal("8.00"))
        self.assertEqual(SaleItem.objects.count(), 2)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("8.000"))
        self.assertEqual(Stock.objects.get(product=self.other_product).quantity, Decimal("9.000"))
        self.assertEqual(StockMovement.objects.count(), 2)
        self.assertEqual(response.json()["total_amount"], "12.00")
        self.assertEqual(response.json()["payment_method_label"], "Dinheiro")
        self.assertEqual(response.json()["change_amount"], "8.00")

    def test_non_cash_sale_has_no_change(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(
            reverse("sale-list"),
            {
                "store": self.first_store.id,
                "payment_method": Sale.PaymentMethod.PIX_MANUAL,
                "amount_received": "3.50",
                "items": [{"product": self.product.id, "quantity": "1.000"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.json())
        sale = Sale.objects.get()
        self.assertEqual(sale.payment_method, Sale.PaymentMethod.PIX_MANUAL)
        self.assertEqual(sale.amount_received, Decimal("3.50"))
        self.assertEqual(sale.change_amount, Decimal("0.00"))

    def test_sale_create_is_idempotent_for_same_client_request_id(self):
        self.client.force_authenticate(self.operator)
        payload = {
            "store": self.first_store.id,
            "payment_method": Sale.PaymentMethod.CASH,
            "amount_received": "10.00",
            "client_request_id": "request-123",
            "items": [{"product": self.product.id, "quantity": "1.000"}],
        }

        first_response = self.client.post(reverse("sale-list"), payload, format="json")
        second_response = self.client.post(reverse("sale-list"), payload, format="json")

        self.assertEqual(first_response.status_code, 201, first_response.json())
        self.assertEqual(second_response.status_code, 201, second_response.json())
        self.assertEqual(first_response.json()["id"], second_response.json()["id"])
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(SaleItem.objects.count(), 1)

    def test_sale_cancel_reverses_stock_and_is_idempotent(self):
        self.client.force_authenticate(self.operator)
        create_response = self.client.post(
            reverse("sale-list"),
            {
                "store": self.first_store.id,
                "payment_method": Sale.PaymentMethod.CASH,
                "amount_received": "10.00",
                "items": [{"product": self.product.id, "quantity": "2.000"}],
            },
            format="json",
        )
        sale = Sale.objects.get(pk=create_response.json()["id"])
        stock_before_cancel = Stock.objects.get(product=self.product).quantity

        cancel_response = self.client.post(reverse("sale-cancel", kwargs={"pk": sale.pk}), format="json")
        repeat_response = self.client.post(reverse("sale-cancel", kwargs={"pk": sale.pk}), format="json")

        sale.refresh_from_db()
        self.assertEqual(cancel_response.status_code, 200, cancel_response.json())
        self.assertEqual(repeat_response.status_code, 200, repeat_response.json())
        self.assertEqual(sale.status, Sale.Status.CANCELLED)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, stock_before_cancel + Decimal("2.000"))
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.MovementType.SALE_REVERSAL).count(), 1)
        self.assertEqual(cancel_response.json()["status"], Sale.Status.CANCELLED)

    def test_sale_rejects_amount_received_lower_than_total(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(
            reverse("sale-list"),
            {
                "store": self.first_store.id,
                "payment_method": Sale.PaymentMethod.CASH,
                "amount_received": "3.00",
                "items": [{"product": self.product.id, "quantity": "1.000"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["amount_received"], ["O valor recebido não pode ser menor que o total da venda."])
        self.assertFalse(Sale.objects.exists())

    def test_sale_rejects_insufficient_stock_without_persisting_sale(self):
        self.client.force_authenticate(self.operator)
        Stock.objects.filter(product=self.product).update(quantity="0.000")

        response = self.client.post(
            reverse("sale-list"),
            {
                "store": self.first_store.id,
                "payment_method": Sale.PaymentMethod.CASH,
                "amount_received": "3.50",
                "items": [{"product": self.product.id, "quantity": "1.000"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["items"], "Estoque insuficiente para Água. Disponível: 0.000.")
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_sale_copies_product_price_and_identity(self):
        self.client.force_authenticate(self.operator)
        self.product.price = Decimal("4.00")
        self.product.save(update_fields=["price"])

        response = self.client.post(
            reverse("sale-list"),
            {"store": self.first_store.id, "payment_method": Sale.PaymentMethod.CASH, "amount_received": "12.00", "items": [{"product": self.product.id, "quantity": "3.000"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.json())
        item = SaleItem.objects.get()
        self.assertEqual(item.product_name, "Água")
        self.assertEqual(item.product_sku, "AGUA-001")
        self.assertEqual(item.unit_price, Decimal("4.00"))
        self.assertEqual(item.line_total, Decimal("12.00"))

    def test_sale_rejects_store_outside_allowed_scope(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(reverse("sale-list"), {"store": self.second_store.id, "payment_method": Sale.PaymentMethod.CASH, "amount_received": "3.50", "items": [{"product": self.product.id, "quantity": "1.000"}]}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["store"], ["Loja não permitida para este usuário."])
        self.assertFalse(Sale.objects.exists())

    def test_sale_rejects_product_from_other_organization(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(reverse("sale-list"), {"store": self.first_store.id, "payment_method": Sale.PaymentMethod.CASH, "amount_received": "12.00", "items": [{"product": self.second_product.id, "quantity": "1.000"}]}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["items"], ["Todos os produtos precisam pertencer à organização da loja."])
        self.assertFalse(Sale.objects.exists())

    def test_sale_rejects_inactive_product(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(reverse("sale-list"), {"store": self.first_store.id, "payment_method": Sale.PaymentMethod.CASH, "amount_received": "2.00", "items": [{"product": self.inactive_product.id, "quantity": "1.000"}]}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["items"], ["Produto inativo: Antigo."])
        self.assertFalse(Sale.objects.exists())

    def test_sale_rejects_empty_items(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(reverse("sale-list"), {"store": self.first_store.id, "payment_method": Sale.PaymentMethod.CASH, "amount_received": "0.00", "items": []}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["items"], ["Adicione pelo menos um item à venda."])

    def test_sale_rejects_non_positive_quantity(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(reverse("sale-list"), {"store": self.first_store.id, "payment_method": Sale.PaymentMethod.CASH, "amount_received": "0.00", "items": [{"product": self.product.id, "quantity": "0.000"}]}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["items"][0]["quantity"], ["A quantidade precisa ser maior que zero."])

    def test_sale_rejects_fractional_quantity(self):
        self.client.force_authenticate(self.operator)

        response = self.client.post(
            reverse("sale-list"),
            {
                "store": self.first_store.id,
                "payment_method": Sale.PaymentMethod.CASH,
                "amount_received": "7.00",
                "items": [{"product": self.product.id, "quantity": "1.500"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["items"][0]["quantity"], ["Venda somente em unidades inteiras."])
        self.assertFalse(Sale.objects.exists())

    def test_sales_list_is_scoped_to_allowed_stores(self):
        allowed_sale = Sale.objects.create(organization=self.first_org, store=self.first_store, cashier=self.operator, total_amount="3.50")
        other_user = get_user_model().objects.create_user(username="other", password="test-pass")
        Sale.objects.create(organization=self.second_org, store=self.second_store, cashier=other_user, total_amount="12.00")
        self.client.force_authenticate(self.operator)

        response = self.client.get(reverse("sale-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([sale["id"] for sale in response.json()["results"]], [allowed_sale.id])

    def test_abacatepay_requires_authentication_and_tenant_scope(self):
        sale = Sale.objects.create(organization=self.second_org, store=self.second_store, cashier=self.operator, total_amount="3.50")
        anonymous_response = self.client.post(reverse("sale-abacatepay", kwargs={"pk": sale.pk}), format="json")
        self.assertEqual(anonymous_response.status_code, 403)

        self.client.force_authenticate(self.operator)
        scoped_response = self.client.post(reverse("sale-abacatepay", kwargs={"pk": sale.pk}), format="json")
        self.assertEqual(scoped_response.status_code, 404)

    @patch("apps.sales.views.create_transparent")
    def test_abacatepay_creation_sends_cents_and_is_idempotent(self, create_transparent_mock):
        create_transparent_mock.return_value = {
            "data": {"id": "tr_123", "status": "pending", "brCode": "000201", "brCodeBase64": "base64"}
        }
        self.client.force_authenticate(self.operator)
        sale_response = self.client.post(
            reverse("sale-list"),
            {"store": self.first_store.id, "payment_method": Sale.PaymentMethod.PIX_MANUAL, "amount_received": "3.50", "items": [{"product": self.product.id, "quantity": "1.000"}]},
            format="json",
        )
        sale_id = sale_response.json()["id"]
        url = reverse("sale-abacatepay", kwargs={"pk": sale_id})
        first = self.client.post(url, format="json")
        second = self.client.post(url, format="json")

        self.assertEqual(first.status_code, 201, first.json())
        self.assertEqual(second.status_code, 200, second.json())
        self.assertEqual(first.json(), {"id": "tr_123", "status": "pending", "brCode": "000201", "brCodeBase64": "base64"})
        self.assertEqual(first.json(), second.json())
        create_transparent_mock.assert_called_once_with(
            amount_cents=350,
            external_id=f"pdv-sale-{self.first_org.id}-{sale_id}",
            metadata={"saleId": str(sale_id), "organizationId": str(self.first_org.id)},
        )
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("9.000"))
        self.assertEqual(Sale.objects.get(pk=sale_id).status, Sale.Status.COMPLETED)

    @patch("apps.sales.views.create_transparent")
    def test_abacatepay_provider_error_is_returned_without_exposing_secret(self, create_transparent_mock):
        create_transparent_mock.side_effect = AbacatePayError("provider down")
        self.client.force_authenticate(self.operator)
        sale = Sale.objects.create(organization=self.first_org, store=self.first_store, cashier=self.operator, total_amount="3.50")

        response = self.client.post(reverse("sale-abacatepay", kwargs={"pk": sale.pk}), format="json")

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("ABACATEPAY_API_KEY", response.content.decode())

    @patch("apps.sales.views.simulate_transparent")
    @patch("apps.sales.views.get_transparent")
    @patch("apps.sales.views.create_transparent")
    @override_settings(ABACATEPAY_ALLOW_SIMULATION=True)
    def test_abacatepay_status_and_simulation_do_not_change_sale_or_stock(self, create_mock, get_mock, simulate_mock):
        create_mock.return_value = {"data": {"id": "tr_status", "status": "pending", "brCode": "code", "brCodeBase64": "image"}}
        get_mock.return_value = {"data": {"id": "tr_status", "status": "PAID"}}
        simulate_mock.return_value = {"data": {"id": "tr_status", "status": "PAID", "brCode": "code", "brCodeBase64": "image"}}
        self.client.force_authenticate(self.operator)
        sale = Sale.objects.create(organization=self.first_org, store=self.first_store, cashier=self.operator, total_amount="3.50")
        self.client.post(reverse("sale-abacatepay", kwargs={"pk": sale.pk}), format="json")

        status_response = self.client.get(reverse("sale-abacatepay", kwargs={"pk": sale.pk}))
        simulate_response = self.client.post(reverse("sale-simulate-abacatepay", kwargs={"pk": sale.pk}), format="json")

        self.assertEqual(status_response.json()["status"], SalePayment.Status.PAID)
        self.assertEqual(simulate_response.json()["status"], SalePayment.Status.PAID)
        get_mock.assert_called_once_with("tr_status")
        simulate_mock.assert_called_once_with("tr_status")
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal("10.000"))

    @override_settings(ABACATEPAY_WEBHOOK_SECRET="webhook-secret")
    def test_abacatepay_webhook_verifies_signature_and_is_idempotent(self):
        sale = Sale.objects.create(organization=self.first_org, store=self.first_store, cashier=self.operator, total_amount="3.50")
        payment = SalePayment.objects.create(
            sale=sale,
            external_id="sale-webhook",
            provider_id="pix_char_webhook",
            amount_cents=350,
        )
        payload = {
            "id": "log_webhook_1",
            "event": "transparent.completed",
            "data": {"id": payment.provider_id, "status": "PAID"},
        }
        raw_body = json.dumps(payload).encode()
        signature = base64.b64encode(hmac.new(b"webhook-secret", raw_body, hashlib.sha256).digest()).decode()

        response = self.client.post(
            "/webhooks/abacatepay/?webhookSecret=webhook-secret",
            raw_body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=signature,
        )
        duplicate = self.client.post(
            "/webhooks/abacatepay/?webhookSecret=webhook-secret",
            raw_body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "processed"})
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json(), {"status": "duplicate"})
        payment.refresh_from_db()
        self.assertEqual(payment.status, SalePayment.Status.PAID)

        invalid = self.client.post(
            "/webhooks/abacatepay/?webhookSecret=webhook-secret",
            raw_body,
            content_type="application/json",
            HTTP_X_WEBHOOK_SIGNATURE="invalid",
        )
        self.assertEqual(invalid.status_code, 401)

    @patch("apps.sales.views.create_transparent")
    def test_pending_abacatepay_sale_reserves_and_cancellation_releases(self, create_mock):
        create_mock.return_value = {"data": {"id": "tr_pending", "status": "pending", "brCode": "code", "brCodeBase64": "image"}}
        self.client.force_authenticate(self.operator)
        response = self.client.post(reverse("sale-list"), {
            "store": self.first_store.id, "payment_method": Sale.PaymentMethod.PIX_ABACATEPAY,
            "amount_received": "7.00", "items": [{"product": self.product.id, "quantity": "2.000"}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        sale = Sale.objects.get(pk=response.json()["id"])
        stock = Stock.objects.get(product=self.product)
        self.assertEqual(sale.status, Sale.Status.PENDING_PAYMENT)
        self.assertEqual(stock.quantity, Decimal("10.000"))
        self.assertEqual(stock.reserved_quantity, Decimal("2.000"))
        self.client.post(reverse("sale-cancel", kwargs={"pk": sale.pk}), format="json")
        stock.refresh_from_db()
        self.assertEqual(stock.reserved_quantity, Decimal("0.000"))
        self.assertEqual(stock.quantity, Decimal("10.000"))

    def test_payment_confirmation_converts_reservation_only_once(self):
        sale = Sale.objects.create(
            organization=self.first_org, store=self.first_store, cashier=self.operator,
            status=Sale.Status.PENDING_PAYMENT, payment_method=Sale.PaymentMethod.PIX_ABACATEPAY,
            total_amount="3.50",
        )
        item = SaleItem.objects.create(sale=sale, product=self.product, product_name=self.product.name,
                                       product_sku=self.product.sku, quantity="1.000", unit_price="3.50", line_total="3.50")
        stock = Stock.objects.get(product=self.product)
        stock.reserved_quantity = 1
        stock.save(update_fields=["reserved_quantity", "updated_at"])
        payment = SalePayment.objects.create(sale=sale, external_id="confirm-once", provider_id="tr_confirm", amount_cents=350)
        apply_payment_status(payment, "PAID")
        apply_payment_status(payment, "PAID")
        sale.refresh_from_db()
        stock.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(stock.quantity, Decimal("9.000"))
        self.assertEqual(stock.reserved_quantity, Decimal("0.000"))
        self.assertEqual(StockMovement.objects.filter(sale=sale, movement_type=StockMovement.MovementType.SALE).count(), 1)

    def test_expired_payment_releases_reservation(self):
        sale = Sale.objects.create(
            organization=self.first_org, store=self.first_store, cashier=self.operator,
            status=Sale.Status.PENDING_PAYMENT, payment_method=Sale.PaymentMethod.PIX_ABACATEPAY,
            total_amount="3.50",
        )
        item = SaleItem.objects.create(sale=sale, product=self.product, product_name=self.product.name,
                                       product_sku=self.product.sku, quantity="1.000", unit_price="3.50", line_total="3.50")
        reserve_stock_for_sale(sale, [item], self.operator)
        payment = SalePayment.objects.create(sale=sale, external_id="expire-once", provider_id="tr_expire", amount_cents=350)

        apply_payment_status(payment, "EXPIRED")

        sale.refresh_from_db()
        stock = Stock.objects.get(product=self.product)
        self.assertEqual(sale.status, Sale.Status.CANCELLED)
        self.assertEqual(stock.quantity, Decimal("10.000"))
        self.assertEqual(stock.reserved_quantity, Decimal("0.000"))


class SalesAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
        self.first_store = Store.objects.create(organization=self.first_org, name="Matriz", code="M01")
        self.second_store = Store.objects.create(organization=self.second_org, name="Filial", code="F01")
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.first_org, role=UserProfile.Role.MANAGER)
        UserStoreAccess.objects.create(profile=self.manager.profile, store=self.first_store)
        self.cashier = get_user_model().objects.create_user(username="cashier", password="test-pass")
        UserProfile.objects.create(user=self.cashier, organization=self.first_org, role=UserProfile.Role.CASHIER)
        UserStoreAccess.objects.create(profile=self.cashier.profile, store=self.first_store)
        self.other_user = get_user_model().objects.create_user(username="other", password="test-pass")
        self.sale = Sale.objects.create(organization=self.first_org, store=self.first_store, cashier=self.cashier, total_amount="3.50")
        self.other_sale = Sale.objects.create(organization=self.second_org, store=self.second_store, cashier=self.other_user, total_amount="12.00")

    def request_for(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def test_manager_sales_admin_is_scoped_to_allowed_stores(self):
        model_admin = SaleAdmin(Sale, admin.site)
        request = self.request_for(self.manager)

        self.assertTrue(model_admin.has_module_permission(request))
        self.assertTrue(model_admin.has_view_permission(request, self.sale))
        self.assertFalse(model_admin.has_view_permission(request, self.other_sale))
        self.assertEqual(list(model_admin.get_queryset(request)), [self.sale])
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, self.sale))
        self.assertFalse(model_admin.has_delete_permission(request, self.sale))

    def test_sale_item_admin_is_hidden_from_manager_menu(self):
        model_admin = SaleItemAdmin(SaleItem, admin.site)
        request = self.request_for(self.manager)

        self.assertFalse(model_admin.has_module_permission(request))
