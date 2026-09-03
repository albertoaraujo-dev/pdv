from django.http import HttpResponse, JsonResponse
from django.utils.html import escape
from django.views.decorators.http import require_GET


API_PATHS = {
    "/api/auth/csrf/": ["get"],
    "/api/auth/me/": ["get"],
    "/api/auth/login/": ["post"],
    "/api/auth/logout/": ["post"],
    "/api/auth/change-password/": ["post"],
    "/api/billing/status/": ["get"],
    "/api/billing/invoices/": ["get"],
    "/api/billing/plans/": ["get"],
    "/api/catalog/categories/": ["get"],
    "/api/catalog/categories/{id}/": ["get"],
    "/api/catalog/units/": ["get"],
    "/api/catalog/units/{id}/": ["get"],
    "/api/catalog/products/": ["get"],
    "/api/catalog/products/{id}/": ["get"],
    "/api/sales/sales/": ["get", "post"],
    "/api/sales/sales/{id}/": ["get"],
    "/api/sales/sales/{id}/abacatepay/": ["get", "post"],
    "/api/sales/sales/{id}/abacatepay/simulate/": ["post"],
    "/webhooks/abacatepay/": ["post"],
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


@require_GET
def api_docs(request):
    rows = "".join(
        f"<tr><td><code>{escape(method.upper())}</code></td><td><code>{escape(path)}</code></td></tr>"
        for path, methods in API_PATHS.items()
        for method in methods
    )
    return HttpResponse(
        f"""
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PDV Final API</title>
  <style>
    body {{ margin: 0; padding: 32px; background: #0f172a; color: #e2e8f0; font-family: Inter, system-ui, sans-serif; }}
    main {{ max-width: 980px; margin: 0 auto; }}
    a {{ color: #38bdf8; }}
    h1 {{ margin-bottom: 8px; color: #fff; }}
    p {{ color: #cbd5e1; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 24px; background: #111827; border-radius: 16px; overflow: hidden; }}
    th, td {{ padding: 14px 16px; border-bottom: 1px solid #1f2937; text-align: left; }}
    th {{ color: #93c5fd; font-size: 0.82rem; letter-spacing: 0.08em; text-transform: uppercase; }}
    code {{ color: #bfdbfe; }}
  </style>
</head>
<body>
  <main>
    <h1>PDV Final API</h1>
    <p>Documentação inicial dos endpoints disponíveis. Schema JSON: <a href="/api/schema/">/api/schema/</a>.</p>
    <table>
      <thead><tr><th>Método</th><th>Caminho</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </main>
</body>
</html>
""",
        content_type="text/html; charset=utf-8",
    )
