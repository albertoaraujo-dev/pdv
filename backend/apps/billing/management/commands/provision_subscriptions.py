from django.core.management.base import BaseCommand

from apps.billing.services import provision_organization_subscription
from apps.tenants.models import Organization


class Command(BaseCommand):
    help = "Provisiona assinaturas ausentes sem cobrar ou alterar assinaturas existentes."

    def add_arguments(self, parser):
        parser.add_argument("--organization", type=int, help="ID de uma organização específica.")

    def handle(self, *args, **options):
        organizations = Organization.objects.all()
        if options["organization"]:
            organizations = organizations.filter(pk=options["organization"])
        created = 0
        existing = 0
        skipped = 0
        for organization in organizations.iterator():
            if hasattr(organization, "billing_subscription"):
                existing += 1
                continue
            if not organization.is_active:
                skipped += 1
                continue
            provision_organization_subscription(organization)
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Assinaturas criadas: {created}; já existentes: {existing}; organizações inativas ignoradas: {skipped}."))
