import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .policies import can_access_admin, can_access_pos, get_allowed_stores, get_user_profile


def user_payload(user):
    profile = get_user_profile(user)
    return {
        "id": user.id,
        "username": user.get_username(),
        "name": user.get_full_name(),
        "email": user.email,
        "profile": {
            "role": profile.role if profile else None,
            "role_label": profile.get_role_display() if profile else None,
            "organization_id": profile.organization_id if profile else None,
            "organization_name": profile.organization.name if profile else None,
        },
        "permissions": {
            "can_access_admin": can_access_admin(user),
            "can_access_pos": can_access_pos(user),
        },
        "stores": [
            {"id": store.id, "name": store.name, "code": store.code}
            for store in get_allowed_stores(user)
        ],
    }


@ensure_csrf_cookie
@require_GET
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_GET
def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Usuário não autenticado."}, status=401)
    return JsonResponse(user_payload(request.user))


@csrf_protect
@require_POST
def login_view(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "JSON inválido."}, status=400)

    username = payload.get("username", "")
    password = payload.get("password", "")
    user = authenticate(request, username=username, password=password)

    if user is None:
        return JsonResponse({"detail": "Usuário ou senha inválidos."}, status=400)
    if not user.is_active:
        return JsonResponse({"detail": "Usuário inativo."}, status=403)

    login(request, user)
    return JsonResponse(user_payload(user))


@csrf_protect
@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({"status": "ok"})
