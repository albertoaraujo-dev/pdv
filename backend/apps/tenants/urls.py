from rest_framework.routers import DefaultRouter

from .views import TenantUserViewSet


router = DefaultRouter()
router.register("users", TenantUserViewSet, basename="tenant-user")

urlpatterns = router.urls
