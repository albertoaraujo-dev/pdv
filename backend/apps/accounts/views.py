import json

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth import password_validation, update_session_auth_hash
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import LoginAttempt, is_login_locked, record_login_attempt
from .policies import can_access_admin, can_access_pos, get_allowed_stores, get_user_profile, must_change_password


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
            "must_change_password": must_change_password(user),
        },
        "stores": [
            {"id": store.id, "name": store.name, "code": store.code}
            for store in get_allowed_stores(user)
        ],
    }


def user_is_inactive_for_login(user):
    profile = get_user_profile(user)
    if not user.is_active:
        return True
    if profile and (not profile.is_active or not profile.organization.is_active):
        return True
    return False


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

    if is_login_locked(request, username):
        record_login_attempt(request, username, LoginAttempt.Status.LOCKED, "Muitas tentativas inválidas.")
        return JsonResponse({"detail": "Muitas tentativas inválidas. Tente novamente em alguns minutos."}, status=429)

    user = authenticate(request, username=username, password=password)

    if user is None:
        inactive_user = get_user_model().objects.filter(username__iexact=username, is_active=False).first()
        if inactive_user and inactive_user.check_password(password):
            record_login_attempt(request, username, LoginAttempt.Status.FAILED, "Usuário inativo.")
            return JsonResponse({"detail": "Usuário inativo."}, status=403)
        record_login_attempt(request, username, LoginAttempt.Status.FAILED, "Credenciais inválidas.")
        return JsonResponse({"detail": "Usuário ou senha inválidos."}, status=400)
    if user_is_inactive_for_login(user):
        record_login_attempt(request, username, LoginAttempt.Status.FAILED, "Usuário inativo.")
        return JsonResponse({"detail": "Usuário inativo."}, status=403)

    login(request, user)
    record_login_attempt(request, username, LoginAttempt.Status.SUCCESS, "Login realizado.")
    return JsonResponse(user_payload(user))


@csrf_protect
@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({"status": "ok"})


@csrf_protect
@require_POST
def change_password(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Usuário não autenticado."}, status=401)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "JSON inválido."}, status=400)

    current_password = payload.get("current_password", "")
    new_password = payload.get("new_password", "")
    new_password_confirm = payload.get("new_password_confirm", "")

    if not request.user.check_password(current_password):
        return JsonResponse({"detail": "Senha atual incorreta."}, status=400)
    if new_password != new_password_confirm:
        return JsonResponse({"detail": "A confirmação da nova senha não confere."}, status=400)

    try:
        password_validation.validate_password(new_password, request.user)
    except ValidationError as error:
        return JsonResponse({"detail": " ".join(error.messages)}, status=400)

    request.user.set_password(new_password)
    request.user.save(update_fields=["password"])
    profile = get_user_profile(request.user)
    if profile and profile.must_change_password:
        profile.must_change_password = False
        profile.save(update_fields=["must_change_password"])
    update_session_auth_hash(request, request.user)
    return JsonResponse({"status": "ok"})
