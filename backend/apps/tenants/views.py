from django.contrib.auth import get_user_model
from rest_framework import permissions, viewsets

from apps.accounts.policies import can_access_admin, get_manageable_users, is_inactive_for_login

from .serializers import TenantUserSerializer


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
