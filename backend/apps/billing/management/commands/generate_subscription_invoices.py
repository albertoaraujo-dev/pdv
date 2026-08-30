from django.core.management.base import BaseCommand

from apps.billing.services import generate_subscription_invoices


class Command(BaseCommand):
    help = "Gera faturas mensais de assinaturas sem cobrar ou chamar um gateway."

    def add_arguments(self, parser):
        parser.add_argument("--period", help="Período no formato AAAA-MM; por padrão, o mês atual.")
        parser.add_argument("--organization", type=int, help="ID de uma organização específica.")
        parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria gerado sem gravar.")

    def handle(self, *args, **options):
        invoices = generate_subscription_invoices(
            period=options["period"],
            organization=options["organization"],
            dry_run=options["dry_run"],
        )
        prefix = "Simulação: " if options["dry_run"] else "Faturas geradas: "
        self.stdout.write(self.style.SUCCESS(f"{prefix}{len(invoices)}."))
