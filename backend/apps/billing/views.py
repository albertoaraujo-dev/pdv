from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policies import get_user_organization, is_inactive_for_login

from .models import BillingNotification, Subscription, SubscriptionInvoice
from .serializers import BillingInvoiceSerializer, BillingStatusSerializer
from .services import get_active_modules, get_module_limits


class CanReadBillingStatus(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        # Never infer a tenant for a global administrator.
        return bool(
            user
            and user.is_authenticated
            and not user.is_superuser
            and not is_inactive_for_login(user)
            and get_user_organization(user)
        )


class BillingStatusView(APIView):
    permission_classes = [CanReadBillingStatus]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        organization = get_user_organization(request.user)
        subscription = Subscription.objects.select_related("plan").filter(
            organization_id=organization.pk
        ).first()
        modules = []
        if subscription:
            modules = [
                {
                    "code": module.code,
                    "name": module.name,
                    "limits": get_module_limits(organization, module.code),
                }
                for module in get_active_modules(organization)
            ]
        notifications = BillingNotification.objects.filter(
            organization_id=organization.pk,
        ).order_by("-created_at")[:10]
        data = {
            "organization": organization,
            "subscription": subscription,
            "effective_modules": modules,
            "recent_notifications": notifications,
        }
        return Response(BillingStatusSerializer(data).data)


class BillingInvoiceListView(generics.ListAPIView):
    permission_classes = [CanReadBillingStatus]
    serializer_class = BillingInvoiceSerializer
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        if not organization:
            return SubscriptionInvoice.objects.none()
        return SubscriptionInvoice.objects.select_related("subscription__plan").filter(
            organization_id=organization.pk
        )
