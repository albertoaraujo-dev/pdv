from django.core.management.base import BaseCommand

from apps.billing.services import generate_billing_notifications


class Command(BaseCommand):
    help = "Gera registros de aviso de billing sem enviar mensagens externas."

    def add_arguments(self, parser):
        parser.add_argument("--period", help="Período no formato AAAA-MM; limita os avisos a esse período.")
        parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria registrado sem gravar.")

    def handle(self, *args, **options):
        notifications = generate_billing_notifications(period=options["period"], dry_run=options["dry_run"])
        prefix = "Simulação: " if options["dry_run"] else "Notificações registradas: "
        self.stdout.write(self.style.SUCCESS(f"{prefix}{len(notifications)}."))
