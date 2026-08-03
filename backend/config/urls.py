from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from .api_schema import openapi_schema


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", openapi_schema),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/tenants/", include("apps.tenants.urls")),
    path("health/", health),
]
