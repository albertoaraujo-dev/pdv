import json

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth import password_validation, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models import Q
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import AuthEvent, LoginAttempt, is_login_locked, record_auth_event, record_login_attempt
from .policies import can_access_admin, can_access_pos, get_allowed_stores, get_user_profile, is_inactive_for_login, must_change_password


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
            {"id": store.id, "name": store.name, "code": store.code, "pix_key": store.pix_key}
            for store in get_allowed_stores(user)
        ],
    }


def reject_inactive_session(request):
    if request.user.is_authenticated and is_inactive_for_login(request.user):
        record_auth_event(request, request.user, AuthEvent.EventType.SESSION_REVOKED, "Sessão revogada por usuário inativo.")
        logout(request)
        return JsonResponse({"detail": "Usuário inativo."}, status=403)
    return None


def parse_json_request(request):
    if request.content_type != "application/json":
        return None, JsonResponse({"detail": "Content-Type inválido."}, status=415)
    try:
        return json.loads(request.body or "{}"), None
    except json.JSONDecodeError:
        return None, JsonResponse({"detail": "JSON inválido."}, status=400)


@ensure_csrf_cookie
@require_GET
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_GET
def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Usuário não autenticado."}, status=401)
    inactive_response = reject_inactive_session(request)
    if inactive_response:
        return inactive_response
    return JsonResponse(user_payload(request.user))


@csrf_protect
@require_POST
def login_view(request):
    payload, error_response = parse_json_request(request)
    if error_response:
        return error_response

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
    if is_inactive_for_login(user):
        record_login_attempt(request, username, LoginAttempt.Status.FAILED, "Usuário inativo.")
        return JsonResponse({"detail": "Usuário inativo."}, status=403)

    login(request, user)
    record_login_attempt(request, username, LoginAttempt.Status.SUCCESS, "Login realizado.")
    return JsonResponse(user_payload(user))


@csrf_protect
@require_POST
def logout_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Usuário não autenticado."}, status=401)
    record_auth_event(request, request.user, AuthEvent.EventType.LOGOUT, "Logout realizado.")
    logout(request)
    return JsonResponse({"status": "ok"})


@csrf_protect
@require_POST
def change_password(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Usuário não autenticado."}, status=401)
    inactive_response = reject_inactive_session(request)
    if inactive_response:
        return inactive_response

    payload, error_response = parse_json_request(request)
    if error_response:
        return error_response

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
    record_auth_event(request, request.user, AuthEvent.EventType.PASSWORD_CHANGE, "Senha alterada.")
    return JsonResponse({"status": "ok"})


@csrf_protect
@require_POST
def password_reset_request(request):
    payload, error_response = parse_json_request(request)
    if error_response:
        return error_response

    identifier = str(payload.get("identifier", "")).strip()
    user = get_user_model().objects.filter(is_active=True).filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier)
    ).first()
    if user and user.email:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = f"{settings.FRONTEND_URL}/redefinir-senha?uid={uid}&token={token}"
        send_mail(
            "Redefinição de senha - PDV Final",
            f"Use este link para redefinir sua senha: {reset_url}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )
    return JsonResponse({"status": "ok"})


@csrf_protect
@require_POST
def password_reset_confirm(request):
    payload, error_response = parse_json_request(request)
    if error_response:
        return error_response

    try:
        user_id = force_str(urlsafe_base64_decode(payload.get("uid", "")))
        user = get_user_model().objects.get(pk=user_id, is_active=True)
    except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
        return JsonResponse({"detail": "Link de redefinição inválido ou expirado."}, status=400)

    if not default_token_generator.check_token(user, payload.get("token", "")):
        return JsonResponse({"detail": "Link de redefinição inválido ou expirado."}, status=400)

    new_password = payload.get("new_password", "")
    if new_password != payload.get("new_password_confirm", ""):
        return JsonResponse({"detail": "A confirmação da nova senha não confere."}, status=400)
    try:
        password_validation.validate_password(new_password, user)
    except ValidationError as error:
        return JsonResponse({"detail": " ".join(error.messages)}, status=400)

    user.set_password(new_password)
    user.save(update_fields=["password"])
    profile = getattr(user, "profile", None)
    if profile and profile.must_change_password:
        profile.must_change_password = False
        profile.save(update_fields=["must_change_password"])
    return JsonResponse({"status": "ok"})
