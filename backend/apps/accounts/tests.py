from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.policies import can_access_admin, can_access_pos, get_allowed_stores, get_manageable_profiles, get_visible_stores
from apps.tenants.models import Organization, Store, UserProfile, UserStoreAccess


class AccessPolicyTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Empresa")
        self.store = Store.objects.create(organization=self.organization, name="Matriz", code="M01")

    def create_user_with_profile(self, username, role, is_staff=False, is_superuser=False):
        user = get_user_model().objects.create_user(
            username=username,
            password="test-pass",
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        if not is_superuser:
            UserProfile.objects.create(user=user, organization=self.organization, role=role)
        return user

    def test_superuser_can_access_admin(self):
        user = self.create_user_with_profile("root", UserProfile.Role.ADMIN, is_staff=True, is_superuser=True)

        self.assertTrue(can_access_admin(user))

    def test_manager_with_staff_can_access_admin(self):
        user = self.create_user_with_profile("manager", UserProfile.Role.MANAGER, is_staff=True)

        self.assertTrue(can_access_admin(user))

    def test_manager_with_active_store_access_can_access_pos(self):
        user = self.create_user_with_profile("manager", UserProfile.Role.MANAGER, is_staff=True)
        UserStoreAccess.objects.create(profile=user.profile, store=self.store)

        self.assertTrue(can_access_pos(user))

    def test_operator_cannot_access_admin_even_if_active(self):
        user = self.create_user_with_profile("operator", UserProfile.Role.OPERATOR)

        self.assertFalse(can_access_admin(user))

    def test_operational_user_needs_active_store_access_for_pos(self):
        user = self.create_user_with_profile("cashier", UserProfile.Role.CASHIER)

        self.assertFalse(can_access_pos(user))

        UserStoreAccess.objects.create(profile=user.profile, store=self.store)

        self.assertTrue(can_access_pos(user))

    def test_inactive_store_blocks_pos_access(self):
        user = self.create_user_with_profile("cashier", UserProfile.Role.CASHIER)
        UserStoreAccess.objects.create(profile=user.profile, store=self.store)
        self.store.is_active = False
        self.store.save(update_fields=["is_active"])

        self.assertFalse(can_access_pos(user))

    def test_manager_can_only_manage_subordinate_profiles(self):
        manager = self.create_user_with_profile("manager", UserProfile.Role.MANAGER, is_staff=True)
        operator = self.create_user_with_profile("operator", UserProfile.Role.OPERATOR)
        admin = self.create_user_with_profile("admin", UserProfile.Role.ADMIN, is_staff=True)

        profiles = list(get_manageable_profiles(manager))

        self.assertIn(operator.profile, profiles)
        self.assertNotIn(admin.profile, profiles)
        self.assertNotIn(manager.profile, profiles)

    def test_allowed_stores_only_returns_active_stores(self):
        user = self.create_user_with_profile("operator", UserProfile.Role.OPERATOR)
        UserStoreAccess.objects.create(profile=user.profile, store=self.store)

        self.assertEqual(list(get_allowed_stores(user)), [self.store])

    def test_visible_stores_include_inactive_store_for_management(self):
        user = self.create_user_with_profile("manager", UserProfile.Role.MANAGER, is_staff=True)
        UserStoreAccess.objects.create(profile=user.profile, store=self.store)
        self.store.is_active = False
        self.store.save(update_fields=["is_active"])

        self.assertEqual(list(get_visible_stores(user)), [self.store])
        self.assertEqual(list(get_allowed_stores(user)), [])


class SessionAuthTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.organization = Organization.objects.create(name="Empresa")
        self.store = Store.objects.create(organization=self.organization, name="Matriz", code="M01")
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.organization, role=UserProfile.Role.MANAGER)
        UserStoreAccess.objects.create(profile=self.manager.profile, store=self.store)

    def csrf_token(self):
        response = self.client.get(reverse("accounts:csrf"))
        self.assertEqual(response.status_code, 200)
        return response.json()["csrfToken"]

    def test_me_requires_authentication(self):
        response = self.client.get(reverse("accounts:me"))

        self.assertEqual(response.status_code, 401)

    def test_login_requires_valid_csrf_token(self):
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "manager", "password": "test-pass"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_login_rejects_invalid_credentials(self):
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "manager", "password": "wrong"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Usuário ou senha inválidos.")

    def test_login_returns_user_permissions_and_session(self):
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "manager", "password": "test-pass"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["permissions"]["can_access_admin"])
        self.assertEqual(response.json()["profile"]["role"], UserProfile.Role.MANAGER)
        self.assertIn("sessionid", self.client.cookies)

        me_response = self.client.get(reverse("accounts:me"))
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["username"], "manager")

    def test_logout_invalidates_session(self):
        self.client.login(username="manager", password="test-pass")
        response = self.client.post(reverse("accounts:logout"), HTTP_X_CSRFTOKEN=self.csrf_token())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:me")).status_code, 401)


class AdminSitePolicyTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.organization = Organization.objects.create(name="Empresa")

    def request_for(self, user):
        request = self.factory.get("/admin/")
        request.user = user
        return request

    def test_admin_site_uses_role_policy(self):
        from django.contrib import admin

        manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=manager, organization=self.organization, role=UserProfile.Role.MANAGER)
        operator = get_user_model().objects.create_user(username="operator", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=operator, organization=self.organization, role=UserProfile.Role.OPERATOR)

        self.assertTrue(admin.site.has_permission(self.request_for(manager)))
        self.assertFalse(admin.site.has_permission(self.request_for(operator)))
