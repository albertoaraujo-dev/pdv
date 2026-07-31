from django.contrib.auth import get_user_model
from django.test import TestCase

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
