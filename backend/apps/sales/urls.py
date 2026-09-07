from rest_framework.routers import DefaultRouter

from .views import CashRegisterViewSet, SaleViewSet


router = DefaultRouter()
router.register("sales", SaleViewSet, basename="sale")
router.register("cash-register", CashRegisterViewSet, basename="cash-register")

urlpatterns = router.urls
