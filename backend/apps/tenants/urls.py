from rest_framework.routers import DefaultRouter

from .views import OrganizationViewSet, StoreViewSet, TenantUserViewSet


router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="tenant-organization")
router.register("stores", StoreViewSet, basename="tenant-store")
router.register("users", TenantUserViewSet, basename="tenant-user")

urlpatterns = router.urls
