from rest_framework.routers import DefaultRouter

from .views import CashRegisterViewSet, CustomerViewSet, SaleViewSet


router = DefaultRouter()
router.register("sales", SaleViewSet, basename="sale")
router.register("cash-register", CashRegisterViewSet, basename="cash-register")
router.register("customers", CustomerViewSet, basename="customer")

urlpatterns = router.urls
