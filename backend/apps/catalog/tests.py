from django.core.exceptions import ValidationError
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.admin import ProductAdmin
from apps.catalog.models import Category, Product, Unit
from apps.tenants.models import Organization, Store, UserProfile, UserStoreAccess


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


class CatalogApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
        self.first_store = Store.objects.create(organization=self.first_org, name="Matriz", code="M01")
        self.first_category = Category.objects.create(organization=self.first_org, name="Bebidas")
        self.second_category = Category.objects.create(organization=self.second_org, name="Lanches")
        self.first_unit = Unit.objects.create(organization=self.first_org, name="Unidade", symbol="UN")
        self.second_unit = Unit.objects.create(organization=self.second_org, name="Caixa", symbol="CX")
        self.first_product = Product.objects.create(
            organization=self.first_org,
            category=self.first_category,
            unit=self.first_unit,
            name="Agua",
            sku="AGUA-001",
            price="3.50",
        )
        self.second_product = Product.objects.create(
            organization=self.second_org,
            category=self.second_category,
            unit=self.second_unit,
            name="Sanduiche",
            sku="SAND-001",
            price="12.00",
        )
        self.other_first_product = Product.objects.create(
            organization=self.first_org,
            category=self.first_category,
            unit=self.first_unit,
            name="Coca Cola",
            sku="COCA-001",
            barcode="7891000000010",
            price="7.50",
        )
        self.inactive_product = Product.objects.create(
            organization=self.first_org,
            category=self.first_category,
            unit=self.first_unit,
            name="Refrigerante antigo",
            sku="REF-OLD",
            price="6.00",
            is_active=False,
        )
        self.operator = get_user_model().objects.create_user(username="operator", password="test-pass")
        UserProfile.objects.create(user=self.operator, organization=self.first_org, role=UserProfile.Role.OPERATOR)
        UserStoreAccess.objects.create(profile=self.operator.profile, store=self.first_store)

    def test_catalog_api_requires_authentication(self):
        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 403)

    def test_product_list_is_scoped_to_user_organization_and_active_records(self):
        self.client.force_authenticate(self.operator)

        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([product["id"] for product in response.json()], [self.first_product.id, self.other_first_product.id])

    def test_product_detail_outside_user_organization_returns_not_found(self):
        self.client.force_authenticate(self.operator)

        response = self.client.get(reverse("product-detail", args=[self.second_product.id]))

        self.assertEqual(response.status_code, 404)

    def test_category_and_unit_lists_are_scoped_to_user_organization(self):
        self.client.force_authenticate(self.operator)

        categories_response = self.client.get(reverse("category-list"))
        units_response = self.client.get(reverse("unit-list"))

        self.assertEqual(categories_response.status_code, 200)
        self.assertEqual(units_response.status_code, 200)
        self.assertEqual([category["id"] for category in categories_response.json()], [self.first_category.id])
        self.assertEqual([unit["id"] for unit in units_response.json()], [self.first_unit.id])

    def test_inactive_profile_cannot_read_catalog_api(self):
        self.operator.profile.is_active = False
        self.operator.profile.save(update_fields=["is_active"])
        self.client.force_authenticate(self.operator)

        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 403)

    def test_superuser_can_read_active_catalog_from_all_organizations(self):
        superuser = get_user_model().objects.create_superuser(username="root", password="test-pass")
        self.client.force_authenticate(superuser)

        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([product["id"] for product in response.json()], [self.first_product.id, self.other_first_product.id, self.second_product.id])

    def test_product_search_filters_by_name_sku_or_barcode_inside_user_organization(self):
        Product.objects.create(
            organization=self.second_org,
            category=self.second_category,
            unit=self.second_unit,
            name="Agua importada",
            sku="AGUA-IMPORT",
            barcode="7891000000010",
            price="20.00",
        )
        self.client.force_authenticate(self.operator)

        name_response = self.client.get(reverse("product-list"), {"q": "agua"})
        sku_response = self.client.get(reverse("product-list"), {"q": "coca"})
        barcode_response = self.client.get(reverse("product-list"), {"q": "7891000000010"})

        self.assertEqual([product["id"] for product in name_response.json()], [self.first_product.id])
        self.assertEqual([product["id"] for product in sku_response.json()], [self.other_first_product.id])
        self.assertEqual([product["id"] for product in barcode_response.json()], [self.other_first_product.id])

    def test_product_list_filters_by_sku_barcode_and_category(self):
        self.client.force_authenticate(self.operator)

        sku_response = self.client.get(reverse("product-list"), {"sku": " coca-001 "})
        barcode_response = self.client.get(reverse("product-list"), {"barcode": "7891000000010"})
        category_response = self.client.get(reverse("product-list"), {"category": self.first_category.id})

        self.assertEqual([product["id"] for product in sku_response.json()], [self.other_first_product.id])
        self.assertEqual([product["id"] for product in barcode_response.json()], [self.other_first_product.id])
        self.assertEqual([product["id"] for product in category_response.json()], [self.first_product.id, self.other_first_product.id])
