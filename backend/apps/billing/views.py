from django.db.models import Prefetch
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.policies import get_user_organization, is_inactive_for_login

from .models import BillingNotification, BillingPlanRequest, Module, ModuleDependency, Plan, PlanModule, Subscription, SubscriptionInvoice
from .serializers import BillingCatalogPlanSerializer, BillingInvoiceSerializer, BillingPlanRequestSerializer, BillingStatusSerializer
from .services import create_billing_plan_request, get_active_modules, get_module_limits


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


class BillingCatalogView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = BillingCatalogPlanSerializer
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        active_dependencies = ModuleDependency.objects.select_related("depends_on").filter(
            is_active=True, depends_on__is_active=True
        )
        active_plan_modules = PlanModule.objects.select_related("module").prefetch_related(
            Prefetch("module__dependencies", queryset=active_dependencies)
        ).filter(included=True, module__is_active=True)
        return Plan.objects.filter(is_active=True).prefetch_related(
            Prefetch("plan_modules", queryset=active_plan_modules),
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        base_modules = list(Module.objects.filter(is_active=True, is_base=True).prefetch_related(
            Prefetch("dependencies", queryset=ModuleDependency.objects.select_related("depends_on").filter(
                is_active=True, depends_on__is_active=True
            ))
        ))
        serializer = self.get_serializer(queryset, many=True, context={"base_modules": base_modules})
        return Response(serializer.data)


class BillingInvoiceListView(generics.ListAPIView):
    permission_classes = [CanReadBillingStatus]
    serializer_class = BillingInvoiceSerializer
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        if not organization:
            return SubscriptionInvoice.objects.none()
        return SubscriptionInvoice.objects.select_related("subscription__plan").prefetch_related("items").filter(
            organization_id=organization.pk
        )


class CanRequestBillingChange(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        profile = getattr(user, "profile", None)
        return bool(user and user.is_authenticated and not user.is_superuser and not is_inactive_for_login(user) and profile and profile.role in (profile.Role.ADMIN, profile.Role.MANAGER))


class BillingPlanRequestListCreateView(generics.ListCreateAPIView):
    permission_classes = [CanRequestBillingChange]
    serializer_class = BillingPlanRequestSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        return BillingPlanRequest.objects.none() if not organization else BillingPlanRequest.objects.select_related("requested_plan", "requested_module", "requester", "reviewed_by").filter(organization_id=organization.pk)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = get_user_organization(request.user)
        key = serializer.validated_data.pop("request_key", None) or request.headers.get("Idempotency-Key")
        obj = create_billing_plan_request(organization=organization, requester=request.user, request_key=key, **serializer.validated_data)
        return Response(self.get_serializer(obj).data, status=status.HTTP_201_CREATED if getattr(obj, "_was_created", False) else status.HTTP_200_OK)
