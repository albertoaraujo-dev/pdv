from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from unfold.widgets import UnfoldAdminPasswordWidget

from .admin import OrganizationAdmin, StoreAdmin, UserAdmin, UserProfileAdmin, UserStoreAccessAdmin
from .models import Organization, Store, UserProfile, UserStoreAccess


class TenantModelTests(TestCase):
    def test_user_store_access_requires_same_organization(self):
        first_org = Organization.objects.create(name="Primeira")
        second_org = Organization.objects.create(name="Segunda")
        user = get_user_model().objects.create_user(username="operator", password="test-pass")
        profile = UserProfile.objects.create(user=user, organization=first_org)
        store = Store.objects.create(organization=second_org, name="Filial", code="F01")

        with self.assertRaises(ValidationError):
            UserStoreAccess.objects.create(profile=profile, store=store)

    def test_active_queryset_filters_active_records(self):
        Organization.objects.create(name="Ativa")
        Organization.objects.create(name="Inativa", is_active=False)

        self.assertEqual(Organization.objects.active().count(), 1)

    def test_duplicate_user_store_access_has_domain_message(self):
        organization = Organization.objects.create(name="Empresa")
        user = get_user_model().objects.create_user(username="operator", password="test-pass")
        profile = UserProfile.objects.create(user=user, organization=organization)
        store = Store.objects.create(organization=organization, name="Matriz", code="M01")
        UserStoreAccess.objects.create(profile=profile, store=store)

        with self.assertRaisesMessage(ValidationError, "Este usuário já possui acesso a esta loja."):
            UserStoreAccess.objects.create(profile=profile, store=store)


class TenantAdminScopeTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
        self.first_store = Store.objects.create(organization=self.first_org, name="Matriz", code="M01")
        self.second_store = Store.objects.create(organization=self.second_org, name="Filial", code="F01")
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        self.profile = UserProfile.objects.create(user=self.manager, organization=self.first_org, role=UserProfile.Role.MANAGER)
        UserStoreAccess.objects.create(profile=self.profile, store=self.first_store)
        self.admin_user = get_user_model().objects.create_user(username="admin-org", password="test-pass", is_staff=True)
        self.admin_profile = UserProfile.objects.create(user=self.admin_user, organization=self.first_org, role=UserProfile.Role.ADMIN)
        self.operator_user = get_user_model().objects.create_user(username="operator", password="test-pass")
        self.operator_profile = UserProfile.objects.create(user=self.operator_user, organization=self.first_org, role=UserProfile.Role.OPERATOR)
        self.operator_access = UserStoreAccess.objects.create(profile=self.operator_profile, store=self.first_store)

    def request_for(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def test_manager_only_sees_own_organization_in_admin(self):
        model_admin = OrganizationAdmin(Organization, admin.site)

        queryset = model_admin.get_queryset(self.request_for(self.manager))

        self.assertEqual(list(queryset), [self.first_org])

    def test_management_lists_show_usage_counts(self):
        organization_admin = OrganizationAdmin(Organization, admin.site)
        store_admin = StoreAdmin(Store, admin.site)

        organization = organization_admin.get_queryset(self.request_for(self.manager)).get(pk=self.first_org.pk)
        store = store_admin.get_queryset(self.request_for(self.manager)).get(pk=self.first_store.pk)

        self.assertIn("active_stores_count", organization_admin.list_display)
        self.assertIn("active_users_count", store_admin.list_display)
        self.assertEqual(organization_admin.active_stores_count(organization), 1)
        self.assertEqual(store_admin.active_users_count(store), 2)
        self.assertEqual(organization_admin.active_stores_count.short_description, "lojas ativas")
        self.assertEqual(store_admin.active_users_count.short_description, "usuários ativos")

    def test_manager_can_view_and_change_own_organization_in_admin(self):
        model_admin = OrganizationAdmin(Organization, admin.site)
        request = self.request_for(self.manager)

        self.assertTrue(model_admin.has_module_permission(request))
        self.assertTrue(model_admin.has_view_permission(request, self.first_org))
        self.assertTrue(model_admin.has_change_permission(request, self.first_org))

    def test_manager_cannot_view_other_organization_in_admin(self):
        model_admin = OrganizationAdmin(Organization, admin.site)
        request = self.request_for(self.manager)

        self.assertFalse(model_admin.has_view_permission(request, self.second_org))
        self.assertFalse(model_admin.has_change_permission(request, self.second_org))

    def test_manager_cannot_add_delete_or_change_status_on_organization(self):
        model_admin = OrganizationAdmin(Organization, admin.site)
        request = self.request_for(self.manager)

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, self.first_org))
        self.assertEqual(model_admin.get_readonly_fields(request, self.first_org), ["created_at", "updated_at", "is_active"])

    def test_management_forms_use_localized_fieldsets(self):
        organization_admin = OrganizationAdmin(Organization, admin.site)
        store_admin = StoreAdmin(Store, admin.site)
        request = self.request_for(self.manager)

        self.assertEqual(
            organization_admin.get_fieldsets(request, self.first_org),
            [
                ("Dados da organização", {"fields": ("name", "legal_name", "document")}),
                ("Status", {"fields": ("is_active",)}),
                ("Controle", {"fields": ("created_at", "updated_at")}),
            ],
        )
        self.assertEqual(
            store_admin.get_fieldsets(request, self.first_store),
            [
                ("Dados da loja", {"fields": ["organization", "name", "code", "is_active"]}),
                ("Controle", {"fields": ["created_at", "updated_at"]}),
            ],
        )
        self.assertIn("created_at", store_admin.get_readonly_fields(request, self.first_store))
        self.assertIn("updated_at", store_admin.get_readonly_fields(request, self.first_store))

    def test_superuser_organization_control_fields_are_readonly(self):
        model_admin = OrganizationAdmin(Organization, admin.site)
        superuser = get_user_model().objects.create_superuser(username="root", password="test-pass")

        readonly_fields = model_admin.get_readonly_fields(self.request_for(superuser), self.first_org)

        self.assertIn("created_at", readonly_fields)
        self.assertIn("updated_at", readonly_fields)

    def test_manager_management_actions_hide_bulk_delete(self):
        request = self.request_for(self.manager)

        self.assertNotIn("delete_selected", OrganizationAdmin(Organization, admin.site).get_actions(request))
        self.assertNotIn("delete_selected", StoreAdmin(Store, admin.site).get_actions(request))
        self.assertNotIn("delete_selected", UserAdmin(get_user_model(), admin.site).get_actions(request))

    def test_superuser_management_actions_keep_bulk_delete(self):
        superuser = get_user_model().objects.create_superuser(username="root", password="test-pass")
        request = self.request_for(superuser)

        self.assertIn("delete_selected", StoreAdmin(Store, admin.site).get_actions(request))

    def test_manager_only_sees_allowed_stores_in_admin(self):
        model_admin = StoreAdmin(Store, admin.site)

        queryset = model_admin.get_queryset(self.request_for(self.manager))

        self.assertEqual(list(queryset), [self.first_store])

    def test_manager_still_sees_inactive_allowed_store_in_admin(self):
        self.first_store.is_active = False
        self.first_store.save(update_fields=["is_active"])
        model_admin = StoreAdmin(Store, admin.site)

        queryset = model_admin.get_queryset(self.request_for(self.manager))

        self.assertEqual(list(queryset), [self.first_store])

    def test_store_admin_searches_by_organization_details(self):
        model_admin = StoreAdmin(Store, admin.site)

        self.assertIn("organization__name", model_admin.search_fields)
        self.assertIn("organization__legal_name", model_admin.search_fields)
        self.assertIn("organization__document", model_admin.search_fields)

    def test_manager_gets_access_to_store_created_in_admin(self):
        model_admin = StoreAdmin(Store, admin.site)
        request = self.request_for(self.manager)
        store = Store(organization=self.first_org, name="Nova loja", code="N01")

        model_admin.save_model(request, store, form=None, change=False)

        self.assertTrue(UserStoreAccess.objects.filter(profile=self.profile, store=store).exists())
        self.assertIn(store, model_admin.get_queryset(request))

    def test_manager_does_not_see_admin_profiles(self):
        model_admin = UserProfileAdmin(UserProfile, admin.site)

        queryset = model_admin.get_queryset(self.request_for(self.manager))

        self.assertEqual(list(queryset), [self.operator_profile])

    def test_manager_cannot_change_admin_profile(self):
        model_admin = UserProfileAdmin(UserProfile, admin.site)

        allowed = model_admin.has_change_permission(self.request_for(self.manager), self.admin_profile)

        self.assertFalse(allowed)

    def test_manager_cannot_change_profiles_directly(self):
        model_admin = UserProfileAdmin(UserProfile, admin.site)

        allowed = model_admin.has_change_permission(self.request_for(self.manager), self.operator_profile)

        self.assertFalse(allowed)

    def test_manager_does_not_see_admin_user_in_auth_admin(self):
        model_admin = UserAdmin(get_user_model(), admin.site)

        queryset = model_admin.get_queryset(self.request_for(self.manager))

        self.assertEqual(list(queryset), [self.operator_user])

    def test_user_admin_searches_by_identity_fields(self):
        model_admin = UserAdmin(get_user_model(), admin.site)

        self.assertEqual(model_admin.search_fields, ["username", "first_name", "last_name", "email"])

    def test_user_admin_list_uses_operational_columns(self):
        model_admin = UserAdmin(get_user_model(), admin.site)

        self.assertEqual(model_admin.list_display, ["username", "first_name", "last_name", "email", "is_active"])
        self.assertEqual(model_admin.list_editable, ["is_active"])
        self.assertEqual(model_admin.list_filter, ["is_active"])
        self.assertNotIn("is_staff", model_admin.list_display)
        self.assertNotIn("is_superuser", model_admin.list_display)

    def test_manager_sees_user_menu_when_has_subordinates(self):
        model_admin = UserAdmin(get_user_model(), admin.site)
        request = self.request_for(self.manager)

        self.assertTrue(model_admin.has_module_permission(request))
        self.assertTrue(model_admin.has_view_permission(request))

    def test_manager_sees_user_menu_without_subordinates(self):
        manager = get_user_model().objects.create_user(username="empty-manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=manager, organization=self.first_org, role=UserProfile.Role.MANAGER)
        model_admin = UserAdmin(get_user_model(), admin.site)
        request = self.request_for(manager)

        self.assertTrue(model_admin.has_module_permission(request))
        self.assertTrue(model_admin.has_view_permission(request))
        self.assertTrue(model_admin.has_add_permission(request))

    def test_manager_cannot_view_admin_user_detail(self):
        model_admin = UserAdmin(get_user_model(), admin.site)
        allowed = model_admin.has_view_permission(self.request_for(self.manager), self.admin_user)

        self.assertFalse(allowed)

    def test_manager_created_user_gets_operator_profile_in_own_organization(self):
        model_admin = UserAdmin(get_user_model(), admin.site)
        request = self.request_for(self.manager)
        user = get_user_model()(username="new-employee", is_staff=True, is_superuser=True)
        user.set_password("test-pass")

        model_admin.save_model(request, user, form=None, change=False)

        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.profile.organization, self.first_org)
        self.assertEqual(user.profile.role, UserProfile.Role.OPERATOR)
        self.assertTrue(user.profile.must_change_password)

    def test_manager_creation_form_includes_subordinate_role_choice(self):
        model_admin = UserAdmin(get_user_model(), admin.site)
        request = self.request_for(self.manager)

        fieldsets = model_admin.get_fieldsets(request, obj=None)
        form_class = model_admin.get_form(request, obj=None, change=False)
        form = form_class()
        role_choices = dict(form.fields["role"].choices)

        self.assertIn(("Credenciais", {"fields": ("username", "password1", "password2")}), fieldsets)
        self.assertIn(("Acesso operacional", {"fields": ("role", "stores")}), fieldsets)
        self.assertIsInstance(form.fields["password1"].widget, UnfoldAdminPasswordWidget)
        self.assertIsInstance(form.fields["password2"].widget, UnfoldAdminPasswordWidget)
        self.assertEqual(form.fields["password1"].widget.attrs["autocomplete"], "new-password")
        self.assertEqual(form.fields["password2"].widget.attrs["autocomplete"], "new-password")
        self.assertEqual(form.fields["stores"].error_messages["required"], "Selecione pelo menos uma loja permitida.")
        self.assertEqual(set(role_choices), {UserProfile.Role.OPERATOR, UserProfile.Role.CASHIER, UserProfile.Role.FISCAL})
        self.assertEqual(list(form.fields["stores"].queryset), [self.first_store])

    def test_manager_user_edit_form_uses_credentials_section(self):
        model_admin = UserAdmin(get_user_model(), admin.site)
        fieldsets = model_admin.get_fieldsets(self.request_for(self.manager), obj=self.operator_user)

        self.assertIn(("Credenciais", {"fields": ("username", "password")}), fieldsets)

    def test_manager_created_user_uses_selected_subordinate_role(self):
        class FormStub:
            cleaned_data = {"role": UserProfile.Role.CASHIER, "stores": [self.first_store]}

        model_admin = UserAdmin(get_user_model(), admin.site)
        request = self.request_for(self.manager)
        user = get_user_model()(username="new-cashier")
        user.set_password("test-pass")

        model_admin.save_model(request, user, FormStub(), change=False)

        self.assertEqual(user.profile.role, UserProfile.Role.CASHIER)
        self.assertTrue(user.profile.must_change_password)
        self.assertTrue(UserStoreAccess.objects.filter(profile=user.profile, store=self.first_store).exists())

    def test_manager_cannot_access_store_access_admin_directly(self):
        UserStoreAccess.objects.create(profile=self.admin_profile, store=self.first_store)
        model_admin = UserStoreAccessAdmin(UserStoreAccess, admin.site)
        request = self.request_for(self.manager)

        queryset = model_admin.get_queryset(request)

        self.assertFalse(model_admin.has_module_permission(request))
        self.assertFalse(model_admin.has_view_permission(request, self.operator_access))
        self.assertFalse(model_admin.has_change_permission(request, self.operator_access))
        self.assertEqual(list(queryset), [])

    def test_manager_profile_field_lists_subordinates_for_store_access(self):
        model_admin = UserStoreAccessAdmin(UserStoreAccess, admin.site)
        db_field = UserStoreAccess._meta.get_field("profile")

        formfield = model_admin.formfield_for_foreignkey(db_field, self.request_for(self.manager))

        self.assertEqual(list(formfield.queryset), [self.operator_profile])


class TenantUserApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
        self.first_store = Store.objects.create(organization=self.first_org, name="Matriz", code="M01")
        self.second_store = Store.objects.create(organization=self.second_org, name="Filial", code="F01")
        self.admin_user = get_user_model().objects.create_user(username="admin-org", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.admin_user, organization=self.first_org, role=UserProfile.Role.ADMIN)
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.first_org, role=UserProfile.Role.MANAGER)
        UserStoreAccess.objects.create(profile=self.manager.profile, store=self.first_store)
        self.operator = get_user_model().objects.create_user(username="operator", password="test-pass")
        UserProfile.objects.create(user=self.operator, organization=self.first_org, role=UserProfile.Role.OPERATOR)
        UserStoreAccess.objects.create(profile=self.operator.profile, store=self.first_store)
        self.cashier = get_user_model().objects.create_user(username="cashier", password="test-pass")
        UserProfile.objects.create(user=self.cashier, organization=self.first_org, role=UserProfile.Role.CASHIER)
        UserStoreAccess.objects.create(profile=self.cashier.profile, store=self.first_store)
        self.other_operator = get_user_model().objects.create_user(username="other-operator", password="test-pass")
        UserProfile.objects.create(user=self.other_operator, organization=self.second_org, role=UserProfile.Role.OPERATOR)
        UserStoreAccess.objects.create(profile=self.other_operator.profile, store=self.second_store)

    def results(self, response):
        return response.json()["results"]

    def test_tenant_user_api_requires_authentication(self):
        response = self.client.get(reverse("tenant-user-list"))

        self.assertEqual(response.status_code, 403)

    def test_operator_cannot_read_tenant_users(self):
        self.client.force_authenticate(self.operator)

        response = self.client.get(reverse("tenant-user-list"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "permission_denied")

    def test_admin_lists_users_from_own_organization(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(reverse("tenant-user-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [user["username"] for user in self.results(response)],
            ["admin-org", "cashier", "manager", "operator"],
        )
        self.assertNotIn("password", self.results(response)[0])
        self.assertEqual(self.results(response)[0]["profile"]["organization_name"], "Primeira")

    def test_manager_lists_only_subordinate_users(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get(reverse("tenant-user-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([user["username"] for user in self.results(response)], ["cashier", "operator"])

    def test_detail_outside_manager_scope_returns_not_found(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get(reverse("tenant-user-detail", args=[self.admin_user.id]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    def test_superuser_lists_all_users(self):
        superuser = get_user_model().objects.create_superuser(username="root", password="test-pass")
        self.client.force_authenticate(superuser)

        response = self.client.get(reverse("tenant-user-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [user["username"] for user in self.results(response)],
            ["admin-org", "cashier", "manager", "operator", "other-operator", "root"],
        )


class TenantOrganizationStoreApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.first_org = Organization.objects.create(name="Primeira")
        self.second_org = Organization.objects.create(name="Segunda")
        self.first_store = Store.objects.create(organization=self.first_org, name="Matriz", code="M01")
        self.second_store = Store.objects.create(organization=self.second_org, name="Filial", code="F01")
        self.inactive_store = Store.objects.create(organization=self.first_org, name="Inativa", code="I01", is_active=False)
        self.admin_user = get_user_model().objects.create_user(username="admin-org", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.admin_user, organization=self.first_org, role=UserProfile.Role.ADMIN)
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.first_org, role=UserProfile.Role.MANAGER)
        UserStoreAccess.objects.create(profile=self.manager.profile, store=self.first_store)
        UserStoreAccess.objects.create(profile=self.manager.profile, store=self.inactive_store)
        self.operator = get_user_model().objects.create_user(username="operator", password="test-pass")
        UserProfile.objects.create(user=self.operator, organization=self.first_org, role=UserProfile.Role.OPERATOR)
        UserStoreAccess.objects.create(profile=self.operator.profile, store=self.first_store)

    def results(self, response):
        return response.json()["results"]

    def test_admin_lists_only_own_organization(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(reverse("tenant-organization-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual([organization["id"] for organization in self.results(response)], [self.first_org.id])

    def test_organization_detail_outside_scope_returns_not_found(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(reverse("tenant-organization-detail", args=[self.second_org.id]))

        self.assertEqual(response.status_code, 404)

    def test_manager_lists_only_visible_stores(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get(reverse("tenant-store-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([store["id"] for store in self.results(response)], [self.inactive_store.id, self.first_store.id])

    def test_store_detail_outside_scope_returns_not_found(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get(reverse("tenant-store-detail", args=[self.second_store.id]))

        self.assertEqual(response.status_code, 404)

    def test_operator_cannot_read_organization_or_store_admin_api(self):
        self.client.force_authenticate(self.operator)

        organizations_response = self.client.get(reverse("tenant-organization-list"))
        stores_response = self.client.get(reverse("tenant-store-list"))

        self.assertEqual(organizations_response.status_code, 403)
        self.assertEqual(stores_response.status_code, 403)

    def test_superuser_lists_all_organizations_and_stores(self):
        superuser = get_user_model().objects.create_superuser(username="root", password="test-pass")
        self.client.force_authenticate(superuser)

        organizations_response = self.client.get(reverse("tenant-organization-list"))
        stores_response = self.client.get(reverse("tenant-store-list"))

        self.assertEqual(organizations_response.status_code, 200)
        self.assertEqual(stores_response.status_code, 200)
        self.assertEqual([organization["id"] for organization in self.results(organizations_response)], [self.first_org.id, self.second_org.id])
        self.assertEqual([store["id"] for store in self.results(stores_response)], [self.inactive_store.id, self.first_store.id, self.second_store.id])
