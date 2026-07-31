from django.contrib.auth import get_user_model

from apps.tenants.models import Store, UserProfile


ADMIN_ROLES = (UserProfile.Role.ADMIN, UserProfile.Role.MANAGER)
OPERATIONAL_ROLES = (UserProfile.Role.MANAGER, UserProfile.Role.OPERATOR, UserProfile.Role.CASHIER, UserProfile.Role.FISCAL)
SUBORDINATE_ROLES = (UserProfile.Role.OPERATOR, UserProfile.Role.CASHIER, UserProfile.Role.FISCAL)


def get_user_profile(user):
    if not user or user.is_anonymous or user.is_superuser:
        return None
    return getattr(user, "profile", None)


def get_user_organization(user):
    profile = get_user_profile(user)
    return profile.organization if profile else None


def has_active_profile(user):
    profile = get_user_profile(user)
    return bool(user and user.is_active and profile and profile.is_active and profile.organization.is_active)


def must_change_password(user):
    profile = get_user_profile(user)
    return bool(profile and profile.must_change_password)


def is_manager(user):
    profile = get_user_profile(user)
    return bool(profile and profile.role == UserProfile.Role.MANAGER)


def can_access_admin(user):
    if not user or not user.is_active:
        return False
    if user.is_superuser:
        return True
    profile = get_user_profile(user)
    return bool(user.is_staff and has_active_profile(user) and not must_change_password(user) and profile.role in ADMIN_ROLES)


def get_allowed_stores(user):
    profile = get_user_profile(user)
    if not profile or not has_active_profile(user):
        return Store.objects.none()
    if profile.role == UserProfile.Role.ADMIN:
        return Store.objects.filter(organization=profile.organization, is_active=True)
    return Store.objects.filter(user_accesses__profile=profile, user_accesses__is_active=True, is_active=True)


def get_visible_stores(user):
    profile = get_user_profile(user)
    if not profile or not has_active_profile(user):
        return Store.objects.none()
    if profile.role == UserProfile.Role.ADMIN:
        return Store.objects.filter(organization=profile.organization)
    return Store.objects.filter(user_accesses__profile=profile, user_accesses__is_active=True)


def can_access_pos(user):
    profile = get_user_profile(user)
    return bool(has_active_profile(user) and not must_change_password(user) and profile.role in OPERATIONAL_ROLES and get_allowed_stores(user).exists())


def get_manageable_profiles(user):
    profile = get_user_profile(user)
    if not profile or not has_active_profile(user):
        return UserProfile.objects.none()
    queryset = UserProfile.objects.filter(organization=profile.organization, user__is_superuser=False)
    if profile.role == UserProfile.Role.MANAGER:
        return queryset.filter(role__in=SUBORDINATE_ROLES)
    if profile.role == UserProfile.Role.ADMIN:
        return queryset
    return UserProfile.objects.none()


def get_manageable_users(user):
    organization = get_user_organization(user)
    if not organization or not has_active_profile(user):
        return get_user_model().objects.none()
    queryset = get_user_model().objects.filter(is_superuser=False, profile__organization=organization)
    if is_manager(user):
        return queryset.filter(profile__role__in=SUBORDINATE_ROLES)
    return queryset
