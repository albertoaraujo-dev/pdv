from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.test import TestCase

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

    def test_non_superuser_only_sees_own_organization_in_admin(self):
        model_admin = OrganizationAdmin(Organization, admin.site)

        queryset = model_admin.get_queryset(self.request_for(self.manager))

        self.assertEqual(list(queryset), [self.first_org])

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

    def test_manager_does_not_see_admin_user_in_auth_admin(self):
        model_admin = UserAdmin(get_user_model(), admin.site)

        queryset = model_admin.get_queryset(self.request_for(self.manager))

        self.assertEqual(list(queryset), [self.operator_user])

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
        role_choices = dict(form_class().fields["role"].choices)

        self.assertIn(("Acesso operacional", {"fields": ("role",)}), fieldsets)
        self.assertEqual(set(role_choices), {UserProfile.Role.OPERATOR, UserProfile.Role.CASHIER, UserProfile.Role.FISCAL})

    def test_manager_created_user_uses_selected_subordinate_role(self):
        class FormStub:
            cleaned_data = {"role": UserProfile.Role.CASHIER}

        model_admin = UserAdmin(get_user_model(), admin.site)
        request = self.request_for(self.manager)
        user = get_user_model()(username="new-cashier")
        user.set_password("test-pass")

        model_admin.save_model(request, user, FormStub(), change=False)

        self.assertEqual(user.profile.role, UserProfile.Role.CASHIER)
        self.assertTrue(user.profile.must_change_password)

    def test_manager_only_sees_store_accesses_from_subordinates(self):
        UserStoreAccess.objects.create(profile=self.admin_profile, store=self.first_store)
        model_admin = UserStoreAccessAdmin(UserStoreAccess, admin.site)

        queryset = model_admin.get_queryset(self.request_for(self.manager))

        self.assertEqual(list(queryset), [self.operator_access])

    def test_manager_profile_field_lists_subordinates_for_store_access(self):
        model_admin = UserStoreAccessAdmin(UserStoreAccess, admin.site)
        db_field = UserStoreAccess._meta.get_field("profile")

        formfield = model_admin.formfield_for_foreignkey(db_field, self.request_for(self.manager))

        self.assertEqual(list(formfield.queryset), [self.operator_profile])
