import base64
import hashlib
import hmac
import json

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import SalePayment, SalePaymentWebhookEvent
from .services import apply_payment_status


def _status(value, fallback):
    normalized = str(value or "").lower()
    return normalized if normalized in SalePayment.Status.values else fallback


@csrf_exempt
@require_POST
def abacatepay_webhook(request):
    if not settings.ABACATEPAY_WEBHOOK_SECRET or not hmac.compare_digest(
        request.GET.get("webhookSecret", ""), settings.ABACATEPAY_WEBHOOK_SECRET
    ):
        return JsonResponse({"detail": "Não autorizado."}, status=401)

    signature = request.headers.get("X-Webhook-Signature", "")
    expected = base64.b64encode(hmac.new(
        settings.ABACATEPAY_WEBHOOK_SECRET.encode(), request.body, hashlib.sha256
    ).digest()).decode()
    if not hmac.compare_digest(signature, expected):
        return JsonResponse({"detail": "Assinatura inválida."}, status=401)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "JSON inválido."}, status=400)

    event_id = payload.get("id")
    event_name = payload.get("event", "")
    if not event_id or not event_name:
        return JsonResponse({"detail": "Evento inválido."}, status=400)

    with transaction.atomic():
        event, created = SalePaymentWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={"event": event_name, "payload": payload},
        )
        if not created:
            return JsonResponse({"status": "duplicate"})

        data = payload.get("data") or {}
        provider_id = data.get("id")
        payment = SalePayment.objects.select_for_update().filter(provider_id=provider_id).first()
        if payment:
            event.payment = payment
            event.save(update_fields=["payment"])
            payment = apply_payment_status(
                payment,
                SalePayment.Status.PAID if event_name == "transparent.completed" else _status(data.get("status"), payment.status),
                payload,
            )
            payment.br_code = data.get("brCode", payment.br_code)
            payment.br_code_base64 = data.get("brCodeBase64", payment.br_code_base64)
            payment.save(update_fields=["br_code", "br_code_base64", "updated_at"])

    return JsonResponse({"status": "processed"})
