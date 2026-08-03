from django.http import JsonResponse
from django.views.decorators.http import require_GET


API_PATHS = {
    "/api/auth/csrf/": ["get"],
    "/api/auth/me/": ["get"],
    "/api/auth/login/": ["post"],
    "/api/auth/logout/": ["post"],
    "/api/auth/change-password/": ["post"],
    "/api/catalog/categories/": ["get"],
    "/api/catalog/categories/{id}/": ["get"],
    "/api/catalog/units/": ["get"],
    "/api/catalog/units/{id}/": ["get"],
    "/api/catalog/products/": ["get"],
    "/api/catalog/products/{id}/": ["get"],
    "/api/tenants/organizations/": ["get"],
    "/api/tenants/organizations/{id}/": ["get"],
    "/api/tenants/stores/": ["get"],
    "/api/tenants/stores/{id}/": ["get"],
    "/api/tenants/users/": ["get"],
    "/api/tenants/users/{id}/": ["get"],
}


def operation_for(method, path):
    summary = f"{method.upper()} {path}"
    operation = {
        "summary": summary,
        "responses": {
            "200": {"description": "Sucesso"},
            "401": {"description": "Não autenticado"},
            "403": {"description": "Não autorizado"},
            "404": {"description": "Não encontrado"},
        },
    }
    if "{id}" in path:
        operation["parameters"] = [
            {
                "name": "id",
                "in": "path",
                "required": True,
                "schema": {"type": "integer"},
            }
        ]
    return operation


@require_GET
def openapi_schema(request):
    paths = {
        path: {method: operation_for(method, path) for method in methods}
        for path, methods in API_PATHS.items()
    }
    return JsonResponse(
        {
            "openapi": "3.0.3",
            "info": {
                "title": "PDV Final API",
                "version": "0.1.0",
                "description": "Contrato inicial da API para ERP + PDV.",
            },
            "paths": paths,
        }
    )
