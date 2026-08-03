from django.contrib.auth import get_user_model
from rest_framework import permissions, viewsets

from apps.accounts.policies import can_access_admin, get_allowed_stores, get_manageable_users, get_user_organization, get_visible_stores, is_inactive_for_login

from .models import Organization, Store
from .serializers import OrganizationSerializer, StoreSerializer, TenantUserSerializer


class CanReadTenantUsers(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not is_inactive_for_login(user) and can_access_admin(user))


class TenantUserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TenantUserSerializer
    permission_classes = [CanReadTenantUsers]

    def get_queryset(self):
        queryset = get_user_model().objects.select_related("profile", "profile__organization").order_by("username")
        user = self.request.user
        if user.is_superuser:
            return queryset
        return queryset.filter(pk__in=get_manageable_users(user))


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [CanReadTenantUsers]

    def get_queryset(self):
        queryset = Organization.objects.order_by("name")
        user = self.request.user
        if user.is_superuser:
            return queryset
        organization = get_user_organization(user)
        if not organization:
            return queryset.none()
        return queryset.filter(pk=organization.pk)


class StoreViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StoreSerializer
    permission_classes = [CanReadTenantUsers]

    def get_queryset(self):
        queryset = Store.objects.select_related("organization").order_by("organization__name", "name")
        user = self.request.user
        if user.is_superuser:
            return queryset
        if can_access_admin(user):
            return queryset.filter(pk__in=get_visible_stores(user))
        return queryset.filter(pk__in=get_allowed_stores(user))
