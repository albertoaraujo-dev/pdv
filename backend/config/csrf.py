from django.http import JsonResponse
from django.shortcuts import render


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/"):
        return JsonResponse(
            {
                "detail": "Token CSRF inválido ou expirado. Recarregue a página e tente novamente.",
                "code": "csrf_failed",
            },
            status=403,
        )

    is_admin_logout = request.path == "/admin/logout/"
    if is_admin_logout and hasattr(request, "session"):
        request.session.flush()

    return render(
        request,
        "403_csrf.html",
        {
            "reason": reason,
            "is_admin_logout": is_admin_logout,
        },
        status=403,
    )
