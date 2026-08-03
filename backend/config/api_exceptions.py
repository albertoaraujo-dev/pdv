from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    detail = data.get("detail") if isinstance(data, dict) else None
    if detail is not None:
        response.data = {
            "detail": str(detail),
            "code": getattr(detail, "code", "error"),
            "errors": {},
        }
        return response

    response.data = {
        "detail": "Erro de validação.",
        "code": "validation_error",
        "errors": data,
    }
    return response
