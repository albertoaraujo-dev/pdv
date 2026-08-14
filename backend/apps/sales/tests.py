from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.sales.admin import SaleAdmin, SaleItemAdmin
from apps.catalog.models import Category, Product, Unit
from apps.tenants.models import Organization, Store, UserProfile, UserStoreAccess

from .models import Sale, SaleItem


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
        self.assertEqual(response.json()["total_amount"], "12.00")
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

    def test_sales_list_is_scoped_to_allowed_stores(self):
        allowed_sale = Sale.objects.create(organization=self.first_org, store=self.first_store, cashier=self.operator, total_amount="3.50")
        other_user = get_user_model().objects.create_user(username="other", password="test-pass")
        Sale.objects.create(organization=self.second_org, store=self.second_store, cashier=other_user, total_amount="12.00")
        self.client.force_authenticate(self.operator)

        response = self.client.get(reverse("sale-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([sale["id"] for sale in response.json()["results"]], [allowed_sale.id])


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
