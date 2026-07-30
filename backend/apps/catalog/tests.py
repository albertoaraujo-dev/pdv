from django.core.exceptions import ValidationError
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.catalog.admin import ProductAdmin
from apps.catalog.models import Category, Product, Unit
from apps.tenants.models import Organization, UserProfile


class CatalogModelTests(TestCase):
    def test_product_requires_category_and_unit_from_same_organization(self):
        first_org = Organization.objects.create(name="Primeira")
        second_org = Organization.objects.create(name="Segunda")
        category = Category.objects.create(organization=second_org, name="Bebidas")
        unit = Unit.objects.create(organization=first_org, name="Unidade", symbol="UN")

        with self.assertRaises(ValidationError):
            Product.objects.create(
                organization=first_org,
                category=category,
                unit=unit,
                name="Agua",
                sku="AGUA-001",
                price="3.50",
            )

    def test_catalog_queryset_filters_by_organization(self):
        first_org = Organization.objects.create(name="Primeira")
        second_org = Organization.objects.create(name="Segunda")
        Category.objects.create(organization=first_org, name="Bebidas")
        Category.objects.create(organization=second_org, name="Lanches")

        self.assertEqual(Category.objects.for_organization(first_org).count(), 1)


class CatalogAdminScopeTests(TestCase):
    def test_manager_only_sees_products_from_own_organization(self):
        first_org = Organization.objects.create(name="Primeira")
        second_org = Organization.objects.create(name="Segunda")
        first_category = Category.objects.create(organization=first_org, name="Bebidas")
        second_category = Category.objects.create(organization=second_org, name="Lanches")
        first_unit = Unit.objects.create(organization=first_org, name="Unidade", symbol="UN")
        second_unit = Unit.objects.create(organization=second_org, name="Caixa", symbol="CX")
        first_product = Product.objects.create(
            organization=first_org,
            category=first_category,
            unit=first_unit,
            name="Agua",
            sku="AGUA-001",
            price="3.50",
        )
        Product.objects.create(
            organization=second_org,
            category=second_category,
            unit=second_unit,
            name="Sanduiche",
            sku="SAND-001",
            price="12.00",
        )
        manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=manager, organization=first_org, role=UserProfile.Role.MANAGER)
        request = RequestFactory().get("/admin/")
        request.user = manager
        model_admin = ProductAdmin(Product, admin.site)

        queryset = model_admin.get_queryset(request)

        self.assertEqual(list(queryset), [first_product])
