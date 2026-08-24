import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from django.conf import settings


class AbacatePayError(Exception):
    pass


def _request(method, path, payload=None):
    if not settings.ABACATEPAY_API_KEY:
        raise AbacatePayError("ABACATEPAY_API_KEY não configurada.")
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{settings.ABACATEPAY_API_BASE_URL}{path}", data=body, method=method,
        headers={
            "Authorization": f"Bearer {settings.ABACATEPAY_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "pdv-final-abacatepay/1.0 (+https://ligara.online)",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode() or "{}")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        if isinstance(exc, HTTPError):
            try:
                detail = exc.read().decode()[:500]
            except Exception:
                detail = str(exc)
        else:
            detail = str(exc)
        raise AbacatePayError(f"Falha na API AbacatePay: {detail}") from exc


def create_transparent(*, amount_cents, external_id, metadata):
    return _request("POST", "/transparents/create", {
        "method": "PIX",
        "data": {
            "amount": amount_cents,
            "externalId": external_id,
            "metadata": metadata,
        },
    })


def get_transparent(provider_id):
    return _request("GET", f"/transparents/check?{urlencode({'id': provider_id})}")


def simulate_transparent(provider_id):
    return _request("POST", f"/transparents/simulate-payment?{urlencode({'id': provider_id})}")
