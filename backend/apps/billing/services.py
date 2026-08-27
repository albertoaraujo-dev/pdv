from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import BillingPayment, BillingProviderEvent, Subscription, SubscriptionInvoice


def _require_global_admin(actor):
    if not actor or not actor.is_authenticated or not actor.is_active or not actor.is_superuser:
        raise PermissionDenied("Somente o administrador global pode alterar o billing.")


@transaction.atomic
def record_manual_invoice_payment(invoice, *, actor, idempotency_key, amount=None, notes=""):
    _require_global_admin(actor)
    if not idempotency_key:
        raise ValidationError("Uma chave de idempotência é obrigatória.")
    existing = BillingPayment.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.invoice_id != invoice.pk:
            raise ValidationError("A chave de idempotência já foi usada para outra fatura.")
        return existing
    invoice = SubscriptionInvoice.objects.select_for_update().select_related("subscription").get(pk=invoice.pk)
    payment = BillingPayment.objects.create(
        organization=invoice.organization,
        invoice=invoice,
        idempotency_key=idempotency_key,
        amount=invoice.amount if amount is None else amount,
        method=BillingPayment.Method.MANUAL,
        recorded_by=actor,
        paid_at=timezone.now(),
        notes=notes,
    )
    invoice.status = SubscriptionInvoice.Status.PAID
    invoice.paid_at = payment.paid_at
    invoice.save(update_fields=["status", "paid_at", "updated_at"])
    subscription = Subscription.objects.select_for_update().get(pk=invoice.subscription_id)
    if subscription.status != Subscription.Status.CANCELLED:
        subscription.status = Subscription.Status.ACTIVE
        subscription.started_at = subscription.started_at or payment.paid_at
        subscription.save(update_fields=["status", "started_at", "updated_at"])
    return payment


@transaction.atomic
def record_provider_event(*, event_id, provider, event_type, payload, organization=None, invoice=None):
    organization = organization or (invoice.organization if invoice else None)
    try:
        event, _created = BillingProviderEvent.objects.get_or_create(
            event_id=event_id,
            defaults={"provider": provider, "event_type": event_type, "payload": payload, "organization": organization, "invoice": invoice},
        )
    except IntegrityError:
        event = BillingProviderEvent.objects.get(event_id=event_id)
    return event
