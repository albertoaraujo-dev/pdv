from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing.models import Subscription, SubscriptionInvoice
from apps.billing.services import mark_subscription_past_due, suspend_expired_subscriptions


class Command(BaseCommand):
    help = "Marca faturas vencidas e suspende assinaturas após o período de carência."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria alterado sem gravar.")
        parser.add_argument("--grace-period-days", type=int, help="Sobrescreve a carência configurada.")

    def handle(self, *args, **options):
        now = timezone.now()
        grace_days = options["grace_period_days"]
        candidates = Subscription.objects.exclude(status=Subscription.Status.CANCELLED)
        overdue_count = 0
        past_due_count = 0
        if options["dry_run"]:
            for subscription in candidates.iterator():
                overdue_count += SubscriptionInvoice.objects.filter(
                    subscription=subscription, due_date__lt=now.date(), status=SubscriptionInvoice.Status.OPEN
                ).count()
                if subscription.status != Subscription.Status.PAST_DUE and SubscriptionInvoice.objects.filter(
                    subscription=subscription, due_date__lt=now.date(), status__in=(SubscriptionInvoice.Status.OPEN, SubscriptionInvoice.Status.PAST_DUE)
                ).exists():
                    past_due_count += 1
            suspensions = candidates.filter(status=Subscription.Status.PAST_DUE, grace_until__lte=now).count()
        else:
            for subscription in candidates.iterator():
                before = subscription.status
                updated = mark_subscription_past_due(subscription, now=now, grace_period_days=grace_days)
                overdue_count += updated.invoices.filter(status=SubscriptionInvoice.Status.PAST_DUE, due_date__lt=now.date()).count()
                if before != Subscription.Status.PAST_DUE and updated.status == Subscription.Status.PAST_DUE:
                    past_due_count += 1
            suspensions = suspend_expired_subscriptions(now=now)
        prefix = "Simulação: " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}faturas inadimplentes: {overdue_count}; assinaturas em carência: {past_due_count}; suspensões: {suspensions}."
        ))
