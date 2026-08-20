from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.catalog.models import Category, Product, Unit
from apps.tenants.models import Organization, Store, UserProfile, UserStoreAccess

from .admin import StockAdmin, StockMovementAdmin
from .models import Stock, StockMovement


class InventoryAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
        self.first_store = Store.objects.create(organization=self.first_org, name="Matriz", code="M01")
        self.second_store = Store.objects.create(organization=self.second_org, name="Filial", code="F01")
        first_category = Category.objects.create(organization=self.first_org, name="Bebidas")
        first_unit = Unit.objects.create(organization=self.first_org, name="Unidade", symbol="UN")
        second_category = Category.objects.create(organization=self.second_org, name="Lanches")
        second_unit = Unit.objects.create(organization=self.second_org, name="Unidade", symbol="UN2")
        first_product = Product.objects.create(organization=self.first_org, category=first_category, unit=first_unit, name="Água", sku="AGUA-001", price="3.50")
        second_product = Product.objects.create(organization=self.second_org, category=second_category, unit=second_unit, name="Suco", sku="SUCO-001", price="5.00")
        self.first_stock = Stock.objects.create(organization=self.first_org, store=self.first_store, product=first_product, quantity="5.000")
        self.second_stock = Stock.objects.create(organization=self.second_org, store=self.second_store, product=second_product, quantity="5.000")
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.first_org, role=UserProfile.Role.MANAGER)
        UserStoreAccess.objects.create(profile=self.manager.profile, store=self.first_store)
        self.movement = StockMovement.objects.create(
            organization=self.first_org,
            store=self.first_store,
            product=first_product,
            movement_type=StockMovement.MovementType.INBOUND,
            quantity="5.000",
            balance_after="5.000",
            created_by=self.manager,
        )

    def request_for(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def test_manager_stock_admin_is_scoped_to_allowed_stores(self):
        model_admin = StockAdmin(Stock, admin.site)
        request = self.request_for(self.manager)

        self.assertTrue(model_admin.has_module_permission(request))
        self.assertEqual(list(model_admin.get_queryset(request)), [self.first_stock])
        self.assertTrue(model_admin.has_view_permission(request, self.first_stock))
        self.assertFalse(model_admin.has_view_permission(request, self.second_stock))
        self.assertFalse(model_admin.has_add_permission(request))

    def test_manager_movement_admin_is_scoped_to_organization(self):
        model_admin = StockMovementAdmin(StockMovement, admin.site)
        request = self.request_for(self.manager)

        self.assertTrue(model_admin.has_module_permission(request))
        self.assertEqual(list(model_admin.get_queryset(request)), [self.movement])
