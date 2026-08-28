from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from datetime import timedelta
from django.utils import timezone

from apps.accounts.policies import get_user_profile
from apps.tenants.models import Organization

from .models import BillingPayment, BillingProviderEvent, Module, ModuleDependency, Plan, PlanModule, Subscription, SubscriptionInvoice, SubscriptionModule


BASE_MODULE_CODES = ("core", "catalog")
REQUIRED_MODULE_CODES = {"sales": "catalog"}


@transaction.atomic
def provision_organization_subscription(organization):
    """Create the initial no-charge subscription, without changing existing billing."""
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    try:
        return organization.billing_subscription
    except Subscription.DoesNotExist:
        pass

    plan = Plan.objects.filter(is_active=True, is_default=True).first()
    if not plan:
        raise ValidationError("Nenhum plano padrão ativo está configurado.")
    if not PlanModule.objects.filter(plan=plan, module__code="sales", included=True, module__is_active=True).exists():
        raise ValidationError("O plano padrão ativo precisa incluir o módulo sales.")

    now = timezone.now()
    status = Subscription.Status.TRIAL if plan.trial_days else Subscription.Status.ACTIVE
    subscription = Subscription.objects.create(
        organization=organization,
        plan=plan,
        status=status,
        started_at=now,
        trial_ends_at=now + timedelta(days=plan.trial_days) if plan.trial_days else None,
        current_period_start=now.date(),
    )
    return subscription


def _require_global_admin(actor):
    if not actor or not actor.is_authenticated or not actor.is_active or not actor.is_superuser:
        raise PermissionDenied("Somente o administrador global pode alterar o billing.")


def _get_subscription(organization):
    if not organization:
        return None
    try:
        subscription = organization.billing_subscription
    except Subscription.DoesNotExist:
        return None
    now = timezone.now()
    if not organization.is_active or subscription.status not in (Subscription.Status.ACTIVE, Subscription.Status.TRIAL):
        return None
    if subscription.status == Subscription.Status.TRIAL and subscription.trial_ends_at and subscription.trial_ends_at <= now:
        return None
    return subscription


def _effective_module_rows(organization):
    subscription = _get_subscription(organization)
    if not subscription:
        return []
    now = timezone.now()
    plan_rows = {row.module_id: row for row in PlanModule.objects.select_related("module").filter(plan=subscription.plan, plan__is_active=True, included=True, module__is_active=True)}
    base_modules = Module.objects.filter(code__in=BASE_MODULE_CODES, is_active=True)
    for module in base_modules:
        plan_rows.setdefault(module.pk, module)
    overrides = SubscriptionModule.objects.select_related("module").filter(subscription=subscription, module__is_active=True)
    for row in overrides:
        if not row.included or not row.is_active or (row.starts_at and row.starts_at > now) or (row.ends_at and row.ends_at <= now):
            plan_rows.pop(row.module_id, None)
        else:
            plan_rows[row.module_id] = row
    # A module is usable only when every active dependency is usable too.
    changed = True
    while changed:
        changed = False
        for module_id in list(plan_rows):
            required_ids = ModuleDependency.objects.filter(module_id=module_id, is_active=True).values_list("depends_on_id", flat=True)
            module_code = plan_rows[module_id].module.code if hasattr(plan_rows[module_id], "module") else plan_rows[module_id].code
            required_code = REQUIRED_MODULE_CODES.get(module_code)
            if required_code:
                required_ids = list(required_ids) + list(Module.objects.filter(code=required_code).values_list("pk", flat=True))
                if not Module.objects.filter(code=required_code, is_active=True).exists():
                    del plan_rows[module_id]
                    changed = True
                    continue
            if any(required_id not in plan_rows for required_id in required_ids):
                del plan_rows[module_id]
                changed = True
    return list(plan_rows.values())


def get_active_modules(organization):
    module_ids = [getattr(row, "module_id", row.pk) for row in _effective_module_rows(organization)]
    return Module.objects.filter(pk__in=module_ids, is_active=True)


def has_module(organization, code):
    return get_active_modules(organization).filter(code=code).exists()


def require_module(organization, code):
    module = get_active_modules(organization).filter(code=code).first()
    if not module:
        raise PermissionDenied(f"O módulo '{code}' não está disponível para esta organização.")
    return module


def get_module_limits(organization, code):
    module = require_module(organization, code)
    rows = _effective_module_rows(organization)
    row = next(row for row in rows if row.module_id == module.pk)
    if isinstance(row, SubscriptionModule):
        plan_limits = PlanModule.objects.filter(plan=_get_subscription(organization).plan, module=module).values_list("limits", flat=True).first() or {}
        return {**plan_limits, **(row.limits or {})}
    return getattr(row, "limits", None) or {}


def get_module_limit(organization, code, key, default=None):
    return get_module_limits(organization, code).get(key, default)


def _require_module_manager(actor, organization):
    if actor and actor.is_authenticated and actor.is_active and actor.is_superuser:
        return
    profile = get_user_profile(actor)
    if not profile or profile.organization_id != organization.pk or not profile.is_active or profile.role != profile.Role.MANAGER:
        raise PermissionDenied("Somente um gerente da organização ou o administrador global pode alterar módulos.")


@transaction.atomic
def add_subscription_module(subscription, module, *, actor, starts_at=None, ends_at=None, limits=None):
    subscription = Subscription.objects.select_for_update().select_related("organization").get(pk=subscription.pk)
    _require_module_manager(actor, subscription.organization)
    module = Module.objects.get(pk=module.pk)
    if not module.is_active:
        raise ValidationError("Não é possível adicionar um módulo inativo.")
    available_ids = {getattr(row, "module_id", row.pk) for row in _effective_module_rows(subscription.organization)}
    missing = ModuleDependency.objects.filter(module=module, is_active=True).exclude(depends_on_id__in=available_ids)
    required_code = REQUIRED_MODULE_CODES.get(module.code)
    if required_code and not has_module(subscription.organization, required_code):
        raise ValidationError("Não é possível adicionar um módulo sem suas dependências ativas.")
    if missing.exists():
        raise ValidationError("Não é possível adicionar um módulo sem suas dependências ativas.")
    row, _created = SubscriptionModule.objects.get_or_create(
        subscription=subscription,
        module=module,
        defaults={"organization": subscription.organization, "included": True, "starts_at": starts_at, "ends_at": ends_at, "limits": limits},
    )
    if not _created:
        row.organization = subscription.organization
        row.included, row.is_active, row.starts_at, row.ends_at, row.limits = True, True, starts_at, ends_at, limits
        row.save()
    return row


@transaction.atomic
def remove_subscription_module(subscription, module, *, actor):
    subscription = Subscription.objects.select_for_update().select_related("organization").get(pk=subscription.pk)
    _require_module_manager(actor, subscription.organization)
    row = SubscriptionModule.objects.get(subscription=subscription, module=module)
    row.is_active = False
    row.ends_at = row.ends_at or timezone.now()
    row.save(update_fields=["is_active", "ends_at", "updated_at"])
    return row


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
