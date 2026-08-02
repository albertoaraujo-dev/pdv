from django.contrib.auth import get_user_model
from django.contrib import admin
from django.conf import settings
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.admin import LoginAttemptAdmin
from apps.accounts.models import LoginAttempt
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

    def test_pending_password_change_blocks_admin_and_pos_permissions(self):
        user = self.create_user_with_profile("manager", UserProfile.Role.MANAGER, is_staff=True)
        user.profile.must_change_password = True
        user.profile.save(update_fields=["must_change_password"])
        UserStoreAccess.objects.create(profile=user.profile, store=self.store)

        self.assertFalse(can_access_admin(user))
        self.assertFalse(can_access_pos(user))

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

    def test_csrf_endpoint_returns_token_with_httponly_cookie(self):
        response = self.client.get(reverse("accounts:csrf"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["csrfToken"])
        self.assertTrue(response.cookies["csrftoken"]["httponly"])
        self.assertEqual(response.cookies["csrftoken"]["samesite"], "Lax")

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
        self.assertEqual(LoginAttempt.objects.get().status, LoginAttempt.Status.FAILED)

    def test_login_reports_inactive_user(self):
        get_user_model().objects.create_user(username="inactive", password="test-pass", is_active=False)
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "inactive", "password": "test-pass"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Usuário inativo.")
        self.assertEqual(LoginAttempt.objects.get().status, LoginAttempt.Status.FAILED)

    def test_login_rejects_inactive_profile(self):
        self.manager.profile.is_active = False
        self.manager.profile.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "manager", "password": "test-pass"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Usuário inativo.")
        self.assertNotIn("sessionid", self.client.cookies)
        self.assertEqual(LoginAttempt.objects.get().status, LoginAttempt.Status.FAILED)

    def test_login_rejects_inactive_organization(self):
        self.organization.is_active = False
        self.organization.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "manager", "password": "test-pass"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Usuário inativo.")
        self.assertNotIn("sessionid", self.client.cookies)
        self.assertEqual(LoginAttempt.objects.get().status, LoginAttempt.Status.FAILED)

    def test_login_returns_user_permissions_and_session(self):
        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "manager", "password": "test-pass"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["permissions"]["can_access_admin"])
        self.assertFalse(response.json()["permissions"]["must_change_password"])
        self.assertEqual(response.json()["profile"]["role"], UserProfile.Role.MANAGER)
        self.assertIn("sessionid", self.client.cookies)
        self.assertTrue(self.client.cookies["sessionid"]["httponly"])
        self.assertEqual(self.client.cookies["sessionid"]["samesite"], "Lax")
        self.assertEqual(int(self.client.cookies["sessionid"]["max-age"]), settings.SESSION_COOKIE_AGE)
        self.assertEqual(LoginAttempt.objects.get().status, LoginAttempt.Status.SUCCESS)

        me_response = self.client.get(reverse("accounts:me"))
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["username"], "manager")

    def test_login_locks_after_repeated_failures_by_username_and_ip(self):
        token = self.csrf_token()
        for _ in range(5):
            response = self.client.post(
                reverse("accounts:login"),
                data={"username": "manager", "password": "wrong"},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(response.status_code, 400)

        response = self.client.post(
            reverse("accounts:login"),
            data={"username": "manager", "password": "test-pass"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(LoginAttempt.objects.filter(status=LoginAttempt.Status.FAILED).count(), 5)
        self.assertEqual(LoginAttempt.objects.filter(status=LoginAttempt.Status.LOCKED).count(), 1)

    def test_login_lockout_is_scoped_by_ip(self):
        first_client = self.client
        second_client = Client(enforce_csrf_checks=True, REMOTE_ADDR="10.0.0.2")
        token = self.csrf_token()
        for _ in range(5):
            first_client.post(
                reverse("accounts:login"),
                data={"username": "manager", "password": "wrong"},
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            )

        csrf_response = second_client.get(reverse("accounts:csrf"))
        response = second_client.post(
            reverse("accounts:login"),
            data={"username": "manager", "password": "test-pass"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_response.json()["csrfToken"],
        )

        self.assertEqual(response.status_code, 200)

    def test_logout_invalidates_session(self):
        self.client.login(username="manager", password="test-pass")
        response = self.client.post(reverse("accounts:logout"), HTTP_X_CSRFTOKEN=self.csrf_token())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:me")).status_code, 401)

    def test_change_password_requires_authentication(self):
        response = self.client.post(
            reverse("accounts:change_password"),
            data={"current_password": "test-pass", "new_password": "new-strong-pass-123", "new_password_confirm": "new-strong-pass-123"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 401)

    def test_change_password_requires_csrf(self):
        self.client.login(username="manager", password="test-pass")
        response = self.client.post(
            reverse("accounts:change_password"),
            data={"current_password": "test-pass", "new_password": "new-strong-pass-123", "new_password_confirm": "new-strong-pass-123"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_change_password_rejects_wrong_current_password(self):
        self.client.login(username="manager", password="test-pass")
        response = self.client.post(
            reverse("accounts:change_password"),
            data={"current_password": "wrong", "new_password": "new-strong-pass-123", "new_password_confirm": "new-strong-pass-123"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Senha atual incorreta.")

    def test_change_password_rejects_mismatched_confirmation(self):
        self.client.login(username="manager", password="test-pass")
        response = self.client.post(
            reverse("accounts:change_password"),
            data={"current_password": "test-pass", "new_password": "new-strong-pass-123", "new_password_confirm": "different-pass-123"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "A confirmação da nova senha não confere.")

    def test_change_password_rejects_weak_password(self):
        self.client.login(username="manager", password="test-pass")
        response = self.client.post(
            reverse("accounts:change_password"),
            data={"current_password": "test-pass", "new_password": "123", "new_password_confirm": "123"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 400)

    def test_change_password_updates_password_and_keeps_session(self):
        self.manager.profile.must_change_password = True
        self.manager.profile.save(update_fields=["must_change_password"])
        self.client.login(username="manager", password="test-pass")
        response = self.client.post(
            reverse("accounts:change_password"),
            data={
                "current_password": "test-pass",
                "new_password": "new-strong-pass-123",
                "new_password_confirm": "new-strong-pass-123",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token(),
        )

        self.assertEqual(response.status_code, 200)
        self.manager.refresh_from_db()
        self.manager.profile.refresh_from_db()
        self.assertTrue(self.manager.check_password("new-strong-pass-123"))
        self.assertFalse(self.manager.profile.must_change_password)
        self.assertEqual(self.client.get(reverse("accounts:me")).status_code, 200)


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

    def test_only_superuser_sees_login_attempts_admin(self):
        model_admin = LoginAttemptAdmin(LoginAttempt, admin.site)
        superuser = get_user_model().objects.create_superuser(username="root", password="test-pass")
        manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=manager, organization=self.organization, role=UserProfile.Role.MANAGER)

        self.assertTrue(model_admin.has_module_permission(self.request_for(superuser)))
        self.assertFalse(model_admin.has_module_permission(self.request_for(manager)))


class AdminLoginAuditTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.organization = Organization.objects.create(name="Empresa")
        self.manager = get_user_model().objects.create_user(username="manager", password="test-pass", is_staff=True)
        UserProfile.objects.create(user=self.manager, organization=self.organization, role=UserProfile.Role.MANAGER)

    def test_admin_login_records_success(self):
        response = self.client.post(
            reverse("admin:login"),
            data={"username": "manager", "password": "test-pass", "next": "/admin/"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LoginAttempt.objects.get().status, LoginAttempt.Status.SUCCESS)

    def test_admin_login_locks_after_repeated_failures(self):
        for _ in range(5):
            response = self.client.post(
                reverse("admin:login"),
                data={"username": "manager", "password": "wrong", "next": "/admin/"},
            )
            self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("admin:login"),
            data={"username": "manager", "password": "test-pass", "next": "/admin/"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Muitas tentativas inválidas", status_code=200)
        self.assertEqual(LoginAttempt.objects.filter(status=LoginAttempt.Status.FAILED).count(), 5)
        self.assertEqual(LoginAttempt.objects.filter(status=LoginAttempt.Status.LOCKED).count(), 1)
