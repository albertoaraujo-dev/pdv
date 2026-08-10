from django.core.exceptions import ValidationError
from django.contrib import admin
from django import forms
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.admin import BooleanRadioFilter, CategoryAdmin, ProductAdmin, SimpleCatalogSaveActionsMixin, TenantCategoryFilter, TenantUnitFilter, UnitAdmin, is_product_relation_autocomplete
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

    def test_product_rejects_negative_price(self):
        organization = Organization.objects.create(name="Primeira")
        category = Category.objects.create(organization=organization, name="Bebidas")
        unit = Unit.objects.create(organization=organization, name="Unidade", symbol="UN")

        with self.assertRaisesMessage(ValidationError, "O preço não pode ser negativo."):
            Product.objects.create(
                organization=organization,
                category=category,
                unit=unit,
                name="Produto inválido",
                sku="NEG-001",
                price="-1.00",
            )

    def test_active_product_requires_active_category_and_unit(self):
        organization = Organization.objects.create(name="Primeira")
        category = Category.objects.create(organization=organization, name="Bebidas", is_active=False)
        unit = Unit.objects.create(organization=organization, name="Unidade", symbol="UN", is_active=False)

        with self.assertRaises(ValidationError) as context:
            Product.objects.create(
                organization=organization,
                category=category,
                unit=unit,
                name="Agua",
                sku="AGUA-001",
                price="3.50",
            )

        self.assertIn("Produto ativo precisa usar uma categoria ativa.", context.exception.message_dict["category"])
        self.assertIn("Produto ativo precisa usar uma unidade ativa.", context.exception.message_dict["unit"])

    def test_inactive_product_can_keep_inactive_category_and_unit(self):
        organization = Organization.objects.create(name="Primeira")
        category = Category.objects.create(organization=organization, name="Bebidas", is_active=False)
        unit = Unit.objects.create(organization=organization, name="Unidade", symbol="UN", is_active=False)

        product = Product.objects.create(
            organization=organization,
            category=category,
            unit=unit,
            name="Agua",
            sku="AGUA-001",
            price="3.50",
            is_active=False,
        )

        self.assertFalse(product.is_active)

    def test_catalog_queryset_filters_by_organization(self):
        first_org = Organization.objects.create(name="Primeira")
        second_org = Organization.objects.create(name="Segunda")
        Category.objects.create(organization=first_org, name="Bebidas")
        Category.objects.create(organization=second_org, name="Lanches")

        self.assertEqual(Category.objects.for_organization(first_org).count(), 1)

    def test_catalog_text_fields_are_trimmed_on_save(self):
        organization = Organization.objects.create(name="Primeira")
        category = Category.objects.create(organization=organization, name=" Bebidas ")
        unit = Unit.objects.create(organization=organization, name=" Unidade ", symbol=" UN ")
        product = Product.objects.create(
            organization=organization,
            category=category,
            unit=unit,
            name=" Agua ",
            sku=" AGUA-001 ",
            barcode=" 7891000000010 ",
            price="3.50",
        )

        self.assertEqual(category.name, "Bebidas")
        self.assertEqual(unit.name, "Unidade")
        self.assertEqual(unit.symbol, "UN")
        self.assertEqual(product.name, "Agua")
        self.assertEqual(product.sku, "AGUA-001")
        self.assertEqual(product.barcode, "7891000000010")

    def test_category_with_active_products_cannot_be_deactivated(self):
        organization = Organization.objects.create(name="Primeira")
        category = Category.objects.create(organization=organization, name="Bebidas")
        unit = Unit.objects.create(organization=organization, name="Unidade", symbol="UN")
        Product.objects.create(organization=organization, category=category, unit=unit, name="Agua", sku="AGUA-001", price="3.50")

        category.is_active = False

        with self.assertRaisesMessage(ValidationError, "Não é possível inativar categoria com produtos ativos."):
            category.save()

    def test_unit_with_active_products_cannot_be_deactivated(self):
        organization = Organization.objects.create(name="Primeira")
        category = Category.objects.create(organization=organization, name="Bebidas")
        unit = Unit.objects.create(organization=organization, name="Unidade", symbol="UN")
        Product.objects.create(organization=organization, category=category, unit=unit, name="Agua", sku="AGUA-001", price="3.50")

        unit.is_active = False

        with self.assertRaisesMessage(ValidationError, "Não é possível inativar unidade com produtos ativos."):
            unit.save()

    def test_category_and_unit_with_only_inactive_products_can_be_deactivated(self):
        organization = Organization.objects.create(name="Primeira")
        category = Category.objects.create(organization=organization, name="Bebidas")
        unit = Unit.objects.create(organization=organization, name="Unidade", symbol="UN")
        Product.objects.create(organization=organization, category=category, unit=unit, name="Agua", sku="AGUA-001", price="3.50", is_active=False)

        category.is_active = False
        unit.is_active = False
        category.save()
        unit.save()

        self.assertFalse(category.is_active)
        self.assertFalse(unit.is_active)


class CatalogAdminScopeTests(TestCase):
    def setUp(self):
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
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
        Product.objects.create(
            organization=self.second_org,
            category=self.second_category,
            unit=self.second_unit,
            name="Sanduiche",
            sku="SAND-001",
            price="12.00",
        )
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.first_org, role=UserProfile.Role.MANAGER)

    def request_for(self, user):
        request = RequestFactory().get("/admin/")
        request.user = user
        return request

    def autocomplete_request_for(self, user, field_name):
        request = RequestFactory().get(
            "/admin/autocomplete/",
            {"app_label": "catalog", "model_name": "product", "field_name": field_name},
        )
        request.user = user
        return request

    def test_manager_only_sees_products_from_own_organization(self):
        model_admin = ProductAdmin(Product, admin.site)

        queryset = model_admin.get_queryset(self.request_for(self.manager))

        self.assertEqual(list(queryset), [self.first_product])

    def test_manager_product_form_limits_tenant_relations(self):
        model_admin = ProductAdmin(Product, admin.site)
        request = self.request_for(self.manager)
        Category.objects.create(organization=self.first_org, name="Inativa", is_active=False)
        Unit.objects.create(organization=self.first_org, name="Inativa", symbol="IN", is_active=False)

        category_field = model_admin.formfield_for_foreignkey(Product._meta.get_field("category"), request)
        unit_field = model_admin.formfield_for_foreignkey(Product._meta.get_field("unit"), request)

        self.assertEqual(list(category_field.queryset), [self.first_category])
        self.assertEqual(list(unit_field.queryset), [self.first_unit])

    def test_product_admin_uses_autocomplete_for_catalog_relations(self):
        model_admin = ProductAdmin(Product, admin.site)
        category_admin = CategoryAdmin(Category, admin.site)
        unit_admin = UnitAdmin(Unit, admin.site)

        self.assertEqual(model_admin.autocomplete_fields, ["category", "unit"])
        self.assertIn("name", category_admin.search_fields)
        self.assertIn("symbol", unit_admin.search_fields)

    def test_product_relation_autocomplete_only_returns_active_options(self):
        inactive_category = Category.objects.create(organization=self.first_org, name="Inativa", is_active=False)
        inactive_unit = Unit.objects.create(organization=self.first_org, name="Inativa", symbol="IN", is_active=False)
        category_request = self.autocomplete_request_for(self.manager, "category")
        unit_request = self.autocomplete_request_for(self.manager, "unit")

        categories = CategoryAdmin(Category, admin.site).get_queryset(category_request)
        units = UnitAdmin(Unit, admin.site).get_queryset(unit_request)

        self.assertTrue(is_product_relation_autocomplete(category_request, "category"))
        self.assertNotIn(inactive_category, categories)
        self.assertNotIn(inactive_unit, units)
        self.assertEqual(list(categories), [self.first_category])
        self.assertEqual(list(units), [self.first_unit])

    def test_manager_product_edit_form_keeps_current_inactive_relations(self):
        inactive_category = Category.objects.create(organization=self.first_org, name="Inativa", is_active=False)
        inactive_unit = Unit.objects.create(organization=self.first_org, name="Inativa", symbol="IN", is_active=False)
        inactive_product = Product.objects.create(
            organization=self.first_org,
            category=inactive_category,
            unit=inactive_unit,
            name="Produto inativo",
            sku="PROD-INATIVO",
            price="1.00",
            is_active=False,
        )
        model_admin = ProductAdmin(Product, admin.site)
        form_class = model_admin.get_form(self.request_for(self.manager), obj=inactive_product)
        form = form_class(instance=inactive_product)

        self.assertEqual(list(form.fields["category"].queryset), [self.first_category, inactive_category])
        self.assertEqual(list(form.fields["unit"].queryset), [inactive_unit, self.first_unit])

    def test_manager_create_forms_hide_organization_field(self):
        category_admin = CategoryAdmin(Category, admin.site)
        product_admin = ProductAdmin(Product, admin.site)
        request = self.request_for(self.manager)

        category_form = category_admin.get_form(request, obj=None)
        product_form = product_admin.get_form(request, obj=None)

        self.assertNotIn("organization", category_form.base_fields)
        self.assertNotIn("organization", product_form.base_fields)

    def test_manager_catalog_fieldsets_omit_organization_on_create(self):
        category_admin = CategoryAdmin(Category, admin.site)
        product_admin = ProductAdmin(Product, admin.site)
        request = self.request_for(self.manager)

        category_fields = category_admin.get_fieldsets(request, obj=None)[0][1]["fields"]
        product_identity_fields = product_admin.get_fieldsets(request, obj=None)[0][1]["fields"]

        self.assertNotIn("organization", category_fields)
        self.assertNotIn("organization", product_identity_fields)

    def test_catalog_admin_exposes_quick_status_toggle(self):
        category_admin = CategoryAdmin(Category, admin.site)
        product_admin = ProductAdmin(Product, admin.site)

        self.assertEqual(category_admin.list_editable, ["is_active"])
        self.assertEqual(product_admin.list_editable, ["is_active"])

    def test_catalog_admin_forms_show_exit_button(self):
        category_admin = CategoryAdmin(Category, admin.site)
        product_admin = ProductAdmin(Product, admin.site)

        self.assertTrue(category_admin.change_form_show_cancel_button)
        self.assertTrue(product_admin.change_form_show_cancel_button)

    def test_manager_catalog_forms_hide_secondary_save_buttons(self):
        class DummyBase:
            def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
                return context

        class DummyAdmin(SimpleCatalogSaveActionsMixin, DummyBase):
            pass

        context = {"show_save_and_continue": True, "show_save_and_add_another": True}

        result = DummyAdmin().render_change_form(self.request_for(self.manager), context)

        self.assertFalse(result["show_save_and_continue"])
        self.assertFalse(result["show_save_and_add_another"])

    def test_superuser_catalog_forms_keep_secondary_save_buttons(self):
        class DummyBase:
            def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
                return context

        class DummyAdmin(SimpleCatalogSaveActionsMixin, DummyBase):
            pass

        superuser = get_user_model().objects.create_superuser(username="root", password="test-pass")
        context = {"show_save_and_continue": True, "show_save_and_add_another": True}

        result = DummyAdmin().render_change_form(self.request_for(superuser), context)

        self.assertTrue(result["show_save_and_continue"])
        self.assertTrue(result["show_save_and_add_another"])

    def test_manager_product_list_filters_are_scoped_to_tenant(self):
        model_admin = ProductAdmin(Product, admin.site)
        request = self.request_for(self.manager)

        category_filter = TenantCategoryFilter(request, {}, Product, model_admin)
        unit_filter = TenantUnitFilter(request, {}, Product, model_admin)

        self.assertEqual(model_admin.get_list_filter(request), [TenantCategoryFilter, TenantUnitFilter, ("is_active", BooleanRadioFilter)])
        self.assertTrue(model_admin.list_filter_submit)
        self.assertEqual(list(category_filter.lookups(request, model_admin)), [(self.first_category.pk, self.first_category.name)])
        self.assertEqual(list(unit_filter.lookups(request, model_admin)), [(self.first_unit.pk, self.first_unit.symbol)])

    def test_manager_product_create_form_validates_with_user_organization(self):
        model_admin = ProductAdmin(Product, admin.site)
        request = self.request_for(self.manager)
        form_class = model_admin.get_form(request, obj=None)

        form = form_class(
            data={
                "name": "Suco",
                "sku": "SUCO-001",
                "barcode": "",
                "category": self.first_category.pk,
                "unit": self.first_unit.pk,
                "price": "5.00",
                "is_active": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors.as_data())
        self.assertEqual(form.instance.organization, self.first_org)

    def test_product_admin_price_field_preserves_money_format(self):
        model_admin = ProductAdmin(Product, admin.site)
        form_class = model_admin.get_form(self.request_for(self.manager), obj=None)
        form = form_class()

        self.assertIsInstance(form.fields["price"].widget, forms.TextInput)
        self.assertEqual(form.fields["price"].widget.attrs["inputmode"], "decimal")
        self.assertEqual(form.fields["price"].widget.attrs["placeholder"], "0,00")

    def test_product_admin_list_formats_price_as_money(self):
        model_admin = ProductAdmin(Product, admin.site)

        self.assertIn("formatted_price", model_admin.list_display)
        self.assertEqual(model_admin.formatted_price(self.first_product), "R$ 3,50")
        self.assertEqual(model_admin.formatted_price.admin_order_field, "price")

    def test_category_and_unit_admin_show_active_product_count(self):
        Product.objects.create(
            organization=self.first_org,
            category=self.first_category,
            unit=self.first_unit,
            name="Produto inativo",
            sku="INATIVO-001",
            price="1.00",
            is_active=False,
        )
        category_admin = CategoryAdmin(Category, admin.site)
        unit_admin = UnitAdmin(Unit, admin.site)

        category = category_admin.get_queryset(self.request_for(self.manager)).get(pk=self.first_category.pk)
        unit = unit_admin.get_queryset(self.request_for(self.manager)).get(pk=self.first_unit.pk)

        self.assertIn("active_products_count", category_admin.list_display)
        self.assertEqual(category_admin.active_products_count(category), 1)
        self.assertEqual(category_admin.active_products_count.admin_order_field, "active_products_count")
        self.assertIn("active_products_count", unit_admin.list_display)
        self.assertEqual(unit_admin.active_products_count(unit), 1)
        self.assertEqual(unit_admin.active_products_count.admin_order_field, "active_products_count")

    def test_manager_cannot_change_product_organization_on_existing_record(self):
        model_admin = ProductAdmin(Product, admin.site)

        readonly_fields = model_admin.get_readonly_fields(self.request_for(self.manager), self.first_product)

        self.assertIn("organization", readonly_fields)
        self.assertIn("created_at", readonly_fields)
        self.assertIn("updated_at", readonly_fields)

    def test_manager_save_forces_category_organization(self):
        model_admin = CategoryAdmin(Category, admin.site)
        category = Category(organization=self.second_org, name="Pizzas")

        model_admin.save_model(self.request_for(self.manager), category, form=None, change=False)

        self.assertEqual(category.organization, self.first_org)


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

    def results(self, response):
        return response.json()["results"]

    def test_catalog_api_requires_authentication(self):
        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "not_authenticated")

    def test_product_list_is_scoped_to_user_organization_and_active_records(self):
        self.client.force_authenticate(self.operator)

        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)
        self.assertEqual([product["id"] for product in self.results(response)], [self.first_product.id, self.other_first_product.id])

    def test_product_detail_outside_user_organization_returns_not_found(self):
        self.client.force_authenticate(self.operator)

        response = self.client.get(reverse("product-detail", args=[self.second_product.id]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    def test_category_and_unit_lists_are_scoped_to_user_organization(self):
        self.client.force_authenticate(self.operator)

        categories_response = self.client.get(reverse("category-list"))
        units_response = self.client.get(reverse("unit-list"))

        self.assertEqual(categories_response.status_code, 200)
        self.assertEqual(units_response.status_code, 200)
        self.assertEqual([category["id"] for category in self.results(categories_response)], [self.first_category.id])
        self.assertEqual([unit["id"] for unit in self.results(units_response)], [self.first_unit.id])

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
        self.assertEqual([product["id"] for product in self.results(response)], [self.first_product.id, self.other_first_product.id, self.second_product.id])

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

        self.assertEqual([product["id"] for product in self.results(name_response)], [self.first_product.id])
        self.assertEqual([product["id"] for product in self.results(sku_response)], [self.other_first_product.id])
        self.assertEqual([product["id"] for product in self.results(barcode_response)], [self.other_first_product.id])

    def test_product_list_filters_by_sku_barcode_and_category(self):
        self.client.force_authenticate(self.operator)

        sku_response = self.client.get(reverse("product-list"), {"sku": " coca-001 "})
        barcode_response = self.client.get(reverse("product-list"), {"barcode": "7891000000010"})
        category_response = self.client.get(reverse("product-list"), {"category": self.first_category.id})

        self.assertEqual([product["id"] for product in self.results(sku_response)], [self.other_first_product.id])
        self.assertEqual([product["id"] for product in self.results(barcode_response)], [self.other_first_product.id])
        self.assertEqual([product["id"] for product in self.results(category_response)], [self.first_product.id, self.other_first_product.id])
