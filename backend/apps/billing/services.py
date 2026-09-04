from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
import calendar
from datetime import date, datetime, timedelta
from django.utils import timezone
from decimal import Decimal

from apps.accounts.policies import get_user_profile
from apps.tenants.models import Organization

from .models import BillingNotification, BillingPayment, BillingPlanRequest, BillingProviderEvent, Module, ModuleDependency, Plan, PlanModule, Subscription, SubscriptionChange, SubscriptionInvoice, SubscriptionInvoiceItem, SubscriptionModule


BASE_MODULE_CODES = ("core", "catalog")
REQUIRED_MODULE_CODES = {"sales": "catalog"}


def _create_billing_notification(notification_type, subscription, *, invoice=None, now=None):
    period_start = invoice.period_start if invoice else subscription.current_period_start
    period_end = invoice.period_end if invoice else subscription.current_period_end
    subject = f"invoice:{invoice.pk}" if invoice else f"subscription:{subscription.pk}:{period_start or 'current'}"
    key = f"{notification_type}:{subject}"
    payload = {
        "type": notification_type,
        "organization_id": subscription.organization_id,
        "subscription_id": subscription.pk,
        "invoice_id": invoice.pk if invoice else None,
        "invoice_number": invoice.number if invoice else None,
        "amount": str(invoice.amount) if invoice else None,
        "due_date": invoice.due_date.isoformat() if invoice else None,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "grace_until": subscription.grace_until.isoformat() if subscription.grace_until else None,
    }
    try:
        notification, _created = BillingNotification.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "organization_id": subscription.organization_id,
                "subscription": subscription,
                "invoice": invoice,
                "notification_type": notification_type,
                "period_start": period_start,
                "period_end": period_end,
                "payload": payload,
            },
        )
    except IntegrityError:
        notification = BillingNotification.objects.get(idempotency_key=key)
    return notification


def generate_billing_notifications(*, now=None, period=None, dry_run=False):
    """Record proactive billing notices; delivery is intentionally out of scope."""
    now = now or timezone.now()
    start, end = _monthly_period(period) if period else (None, None)
    due_days = settings.BILLING_DUE_SOON_DAYS
    warning_days = settings.BILLING_SUSPENSION_WARNING_DAYS
    due_invoices = SubscriptionInvoice.objects.select_related("subscription").filter(
        organization__is_active=True,
        subscription__status__in=(Subscription.Status.ACTIVE, Subscription.Status.TRIAL),
        status=SubscriptionInvoice.Status.OPEN,
        due_date__gte=now.date(), due_date__lte=now.date() + timedelta(days=due_days),
    )
    warning_subscriptions = Subscription.objects.filter(
        organization__is_active=True, status=Subscription.Status.PAST_DUE,
        grace_until__gt=now, grace_until__lte=now + timedelta(days=warning_days),
    )
    candidates = [(BillingNotification.NotificationType.DUE_SOON, invoice.subscription, invoice) for invoice in due_invoices]
    for subscription in warning_subscriptions:
        invoices = SubscriptionInvoice.objects.filter(
            subscription=subscription, status=SubscriptionInvoice.Status.PAST_DUE,
        )
        candidates.extend((BillingNotification.NotificationType.SUSPENSION_WARNING, subscription, invoice) for invoice in invoices)
    if start:
        candidates = [candidate for candidate in candidates if candidate[2] is None or (candidate[2].period_start == start and candidate[2].period_end == end)]
    if dry_run:
        return candidates
    return [_create_billing_notification(notification_type, subscription, invoice=invoice, now=now) for notification_type, subscription, invoice in candidates]


def _monthly_period(period=None):
    if period is None:
        period = timezone.localdate()
    if isinstance(period, str):
        try:
            period = datetime.strptime(period, "%Y-%m").date()
        except ValueError as exc:
            raise ValidationError("O período precisa estar no formato AAAA-MM.") from exc
    if not isinstance(period, date):
        raise ValidationError("O período precisa ser uma data ou estar no formato AAAA-MM.")
    start = period.replace(day=1)
    end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    return start, end


@transaction.atomic
def generate_subscription_invoice(subscription, period=None, *, period_end=None, due_date=None):
    """Create one open invoice for a subscription period, without charging it."""
    start, calculated_end = _monthly_period(period)
    end = calculated_end if period_end is None else period_end
    if end < start:
        raise ValidationError("O fim do período precisa ser igual ou posterior ao início.")
    subscription = Subscription.objects.select_for_update().select_related("organization", "plan").get(pk=subscription.pk)
    if not subscription.organization.is_active or subscription.status not in (Subscription.Status.ACTIVE, Subscription.Status.TRIAL):
        return None
    if subscription.status == Subscription.Status.TRIAL and subscription.trial_ends_at and subscription.trial_ends_at.date() < start:
        return None
    existing = SubscriptionInvoice.objects.filter(
        subscription=subscription, period_start=start, period_end=end
    ).first()
    if existing:
        return existing
    plan_rows = {row.module_id: row for row in PlanModule.objects.select_related("module").filter(
        plan=subscription.plan, included=True, module__is_active=True
    ) if row.module.code not in BASE_MODULE_CODES}
    subscription_rows = SubscriptionModule.objects.select_related("module").filter(
        subscription=subscription, module__is_active=True
    )
    for row in subscription_rows:
        active_for_period = not row.starts_at or row.starts_at.date() <= end
        active_for_period = active_for_period and (not row.ends_at or row.ends_at.date() >= start)
        if not row.included or not row.is_active or not active_for_period:
            plan_rows.pop(row.module_id, None)
        elif row.module.code not in BASE_MODULE_CODES:
            plan_rows[row.module_id] = row

    invoice_data = {
        "organization": subscription.organization,
        "subscription": subscription,
        "amount": Decimal("0.00"),
        "status": SubscriptionInvoice.Status.OPEN,
        "period_start": start,
        "period_end": end,
        "due_date": due_date or end,
    }
    def create_invoice(number):
        invoice = SubscriptionInvoice.objects.create(number=number, **invoice_data)
        SubscriptionInvoiceItem.objects.create(invoice=invoice, item_type=SubscriptionInvoiceItem.ItemType.PLAN,
            code=subscription.plan.code, description=subscription.plan.name, amount=subscription.plan.monthly_price)
        for row in plan_rows.values():
            price = row.monthly_price
            if price is None and isinstance(row, SubscriptionModule):
                price = PlanModule.objects.filter(plan=subscription.plan, module=row.module).values_list("monthly_price", flat=True).first()
            SubscriptionInvoiceItem.objects.create(invoice=invoice, item_type=SubscriptionInvoiceItem.ItemType.MODULE,
                module=row.module, code=row.module.code, description=row.module.name, amount=price or Decimal("0.00"))
        invoice.recalculate_total()
        return invoice

    try:
        with transaction.atomic():
            return create_invoice(f"{start:%Y-%m}")
    except IntegrityError:
        existing = SubscriptionInvoice.objects.filter(
            subscription=subscription, period_start=start, period_end=end
        ).first()
        if existing:
            return existing
        # Do not overwrite a manually numbered historical invoice.
        return create_invoice(f"{start:%Y-%m}-{subscription.pk}")


def generate_subscription_invoices(*, period=None, organization=None, dry_run=False):
    """Generate monthly invoices for eligible subscriptions; never performs payment."""
    start, end = _monthly_period(period)
    subscriptions = Subscription.objects.select_related("organization", "plan").filter(
        status__in=(Subscription.Status.ACTIVE, Subscription.Status.TRIAL),
        organization__is_active=True,
    )
    if organization is not None:
        subscriptions = subscriptions.filter(organization_id=getattr(organization, "pk", organization))
    generated = []
    for subscription in subscriptions.iterator():
        if subscription.status == Subscription.Status.TRIAL and subscription.trial_ends_at and subscription.trial_ends_at.date() < start:
            continue
        if dry_run:
            if not SubscriptionInvoice.objects.filter(subscription=subscription, period_start=start, period_end=end).exists():
                generated.append(subscription)
            continue
        if SubscriptionInvoice.objects.filter(subscription=subscription, period_start=start, period_end=end).exists():
            continue
        invoice = generate_subscription_invoice(subscription, start, period_end=end)
        if invoice:
            generated.append(invoice)
    return generated


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


@transaction.atomic
def mark_subscription_past_due(subscription, *, now=None, grace_period_days=None):
    """Mark overdue invoices and start one stable grace window for a subscription."""
    now = now or timezone.now()
    subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
    if subscription.status == Subscription.Status.CANCELLED:
        return subscription
    overdue = SubscriptionInvoice.objects.select_for_update().filter(
        subscription=subscription, due_date__lt=now.date(), status=SubscriptionInvoice.Status.OPEN
    )
    has_overdue = SubscriptionInvoice.objects.filter(
        subscription=subscription, due_date__lt=now.date(), status__in=(SubscriptionInvoice.Status.OPEN, SubscriptionInvoice.Status.PAST_DUE)
    ).exists()
    changed = overdue.update(status=SubscriptionInvoice.Status.PAST_DUE, updated_at=now)
    if not has_overdue and subscription.status != Subscription.Status.PAST_DUE:
        return subscription
    if subscription.status == Subscription.Status.SUSPENDED:
        return subscription
    days = settings.BILLING_GRACE_PERIOD_DAYS if grace_period_days is None else grace_period_days
    if days < 0:
        raise ValidationError("O período de carência não pode ser negativo.")
    fields = []
    if subscription.status != Subscription.Status.PAST_DUE:
        subscription.status = Subscription.Status.PAST_DUE
        fields.append("status")
    if not subscription.past_due_since:
        subscription.past_due_since = now
        fields.append("past_due_since")
    if not subscription.grace_until:
        subscription.grace_until = now + timedelta(days=days)
        fields.append("grace_until")
    if fields:
        fields.append("updated_at")
        subscription.save(update_fields=fields)
    if subscription.status == Subscription.Status.PAST_DUE:
        for invoice in SubscriptionInvoice.objects.filter(subscription=subscription, status=SubscriptionInvoice.Status.PAST_DUE):
            _create_billing_notification(BillingNotification.NotificationType.PAST_DUE, subscription, invoice=invoice, now=now)
        generate_billing_notifications(now=now)
    return subscription


@transaction.atomic
def suspend_expired_subscriptions(*, now=None, grace_period_days=None):
    now = now or timezone.now()
    count = 0
    for subscription in Subscription.objects.select_for_update().filter(
        status=Subscription.Status.PAST_DUE, grace_until__isnull=False, grace_until__lte=now
    ):
        subscription.status = Subscription.Status.SUSPENDED
        subscription.save(update_fields=["status", "updated_at"])
        for invoice in SubscriptionInvoice.objects.filter(subscription=subscription, status=SubscriptionInvoice.Status.PAST_DUE):
            _create_billing_notification(BillingNotification.NotificationType.SUSPENDED, subscription, invoice=invoice, now=now)
        count += 1
    return count


@transaction.atomic
def cancel_subscription(subscription, *, actor, reason="", metadata=None, cancelled_at=None):
    _require_global_admin(actor)
    subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
    if subscription.status == Subscription.Status.CANCELLED:
        return subscription
    subscription.status = Subscription.Status.CANCELLED
    subscription.cancelled_at = cancelled_at or timezone.now()
    subscription.cancellation_reason = reason or ""
    subscription.cancellation_metadata = metadata or {}
    subscription.save(update_fields=["status", "cancelled_at", "cancellation_reason", "cancellation_metadata", "updated_at"])
    return subscription


@transaction.atomic
def change_subscription_plan(subscription, new_plan, *, actor, reason="", effective_at=None):
    _require_global_admin(actor)
    subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
    new_plan = Plan.objects.get(pk=new_plan.pk)
    if not new_plan.is_active:
        raise ValidationError("Não é possível alterar para um plano inativo.")
    if subscription.status == Subscription.Status.CANCELLED:
        raise ValidationError("Uma assinatura cancelada não pode mudar de plano.")
    if subscription.plan_id == new_plan.pk:
        return subscription
    old_plan = subscription.plan
    SubscriptionChange.objects.create(
        subscription=subscription, old_plan=old_plan, new_plan=new_plan,
        effective_at=effective_at or timezone.now(), actor=actor, reason=reason or "",
    )
    subscription.plan = new_plan
    subscription.save(update_fields=["plan", "updated_at"])
    return subscription


def downgrade_subscription(subscription, new_plan, *, actor, reason="", effective_at=None):
    return change_subscription_plan(subscription, new_plan, actor=actor, reason=reason, effective_at=effective_at)


def _get_subscription(organization):
    if not organization:
        return None
    subscription = Subscription.objects.select_related("plan").filter(organization_id=organization.pk).first()
    if not subscription:
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
    row = next(row for row in rows if getattr(row, "module_id", row.pk) == module.pk)
    if isinstance(row, SubscriptionModule):
        plan_limits = PlanModule.objects.filter(plan=_get_subscription(organization).plan, module=module).values_list("limits", flat=True).first() or {}
        return {**plan_limits, **(row.limits or {})}
    return getattr(row, "limits", None) or {}


def get_module_limit(organization, code, key, default=None):
    return get_module_limits(organization, code).get(key, default)


def enforce_module_limit(organization, module_code, resource_key, increment=1):
    """Allow a resource addition only when the tenant's effective entitlement permits it."""
    if increment <= 0:
        return

    from apps.catalog.models import Product
    from apps.tenants.models import Store, UserProfile

    resource_querysets = {
        "users": UserProfile.objects.filter(organization=organization, is_active=True),
        "products": Product.objects.filter(organization=organization, is_active=True),
        "stores": Store.objects.filter(organization=organization, is_active=True),
    }
    queryset = resource_querysets.get(resource_key)
    if queryset is None:
        raise ValidationError(f"Recurso de limite desconhecido: {resource_key}.")

    limit = get_module_limit(organization, module_code, resource_key)
    if limit is None:
        return
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ValidationError(f"O limite de {resource_key} não é válido.")
    current = queryset.count()
    if current + increment > limit:
        raise ValidationError(
            f"O limite de {resource_key} para o módulo '{module_code}' foi atingido ({limit})."
        )


def _require_module_manager(actor, organization):
    if actor and actor.is_authenticated and actor.is_active and actor.is_superuser:
        return
    profile = get_user_profile(actor)
    if not profile or profile.organization_id != organization.pk or not profile.is_active or profile.role != profile.Role.MANAGER:
        raise PermissionDenied("Somente um gerente da organização ou o administrador global pode alterar módulos.")


@transaction.atomic
def add_subscription_module(subscription, module, *, actor, starts_at=None, ends_at=None, limits=None, monthly_price=None):
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
        defaults={"organization": subscription.organization, "included": True, "starts_at": starts_at, "ends_at": ends_at, "limits": limits, "monthly_price": monthly_price},
    )
    if not _created:
        row.organization = subscription.organization
        row.included, row.is_active, row.starts_at, row.ends_at, row.limits, row.monthly_price = True, True, starts_at, ends_at, limits, monthly_price
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
        subscription.past_due_since = None
        subscription.grace_until = None
        subscription.save(update_fields=["status", "started_at", "past_due_since", "grace_until", "updated_at"])
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


@transaction.atomic
def create_billing_plan_request(*, organization, requester, request_key, requested_plan=None, requested_module=None, notes=""):
    if not request_key:
        raise ValidationError("Uma chave da solicitação é obrigatória.")
    profile = get_user_profile(requester)
    if not profile or profile.organization_id != organization.pk or not profile.is_active or profile.role not in (profile.Role.ADMIN, profile.Role.MANAGER):
        raise PermissionDenied("Somente administradores e gerentes podem solicitar alterações de billing.")
    existing = BillingPlanRequest.objects.select_for_update().filter(organization=organization, request_key=request_key).first()
    if existing:
        if existing.status == BillingPlanRequest.Status.OPEN:
            if existing.requested_plan_id != getattr(requested_plan, "pk", None) or existing.requested_module_id != getattr(requested_module, "pk", None):
                raise ValidationError("A chave da solicitação já foi usada para outro alvo.")
            existing._was_created = False
            return existing
        raise ValidationError("A chave da solicitação já foi utilizada.")
    request = BillingPlanRequest.objects.create(
        organization=organization, requester=requester, request_key=request_key,
        requested_plan=requested_plan, requested_module=requested_module, notes=notes or "",
    )
    request._was_created = True
    return request


@transaction.atomic
def approve_billing_plan_request(request, *, reviewer):
    _require_global_admin(reviewer)
    # Lock only the request row; nullable target relations make PostgreSQL reject
    # SELECT ... FOR UPDATE across the outer joins created by select_related.
    request = BillingPlanRequest.objects.select_for_update().get(pk=request.pk)
    request = BillingPlanRequest.objects.select_related("organization", "requested_plan", "requested_module").get(pk=request.pk)
    if request.status != BillingPlanRequest.Status.OPEN:
        return request
    subscription = Subscription.objects.get(organization=request.organization)
    reason = request.notes or "Solicitação de billing aprovada"
    if request.requested_plan_id:
        change_subscription_plan(subscription, request.requested_plan, actor=reviewer, reason=reason)
    else:
        add_subscription_module(subscription, request.requested_module, actor=reviewer)
    request.status = BillingPlanRequest.Status.APPROVED
    request.reviewed_by = reviewer
    request.reviewed_at = timezone.now()
    request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return request


@transaction.atomic
def reject_billing_plan_request(request, *, reviewer, notes=""):
    _require_global_admin(reviewer)
    request = BillingPlanRequest.objects.select_for_update().get(pk=request.pk)
    if request.status == BillingPlanRequest.Status.OPEN:
        request.status = BillingPlanRequest.Status.REJECTED
        request.reviewed_by = reviewer
        request.reviewed_at = timezone.now()
        if notes:
            request.notes = notes
        request.save(update_fields=["status", "reviewed_by", "reviewed_at", "notes"])
    return request
