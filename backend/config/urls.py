from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from .api_schema import api_docs, openapi_schema
from apps.sales.webhooks import abacatepay_webhook


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/docs/", api_docs),
    path("api/schema/", openapi_schema),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/billing/", include("apps.billing.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/tenants/", include("apps.tenants.urls")),
    path("health/", health),
    path("webhooks/abacatepay/", abacatepay_webhook),
]
