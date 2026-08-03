from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ProductViewSet, UnitViewSet


router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("units", UnitViewSet, basename="unit")
router.register("products", ProductViewSet, basename="product")

urlpatterns = router.urls
