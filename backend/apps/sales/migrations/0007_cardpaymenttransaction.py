from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0006_pending_payment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CardPaymentTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.CharField(max_length=128, unique=True, verbose_name="ID externo")),
                ("client_reference", models.CharField(max_length=128, unique=True, verbose_name="referência do cliente")),
                ("provider", models.CharField(default="external_card", max_length=80, verbose_name="provedor")),
                ("terminal_id", models.CharField(blank=True, max_length=80, verbose_name="terminal")),
                ("amount_cents", models.PositiveBigIntegerField(verbose_name="valor em centavos")),
                ("status", models.CharField(choices=[("approved", "Aprovada"), ("pending", "Pendente"), ("declined", "Recusada"), ("cancelled", "Cancelada"), ("reconciled", "Conciliada")], default="approved", max_length=24, verbose_name="status")),
                ("reconciled_at", models.DateTimeField(blank=True, null=True, verbose_name="conciliado em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("reconciled_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reconciled_card_transactions", to=settings.AUTH_USER_MODEL)),
                ("sale", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="card_transaction", to="sales.sale", verbose_name="venda")),
            ],
            options={"verbose_name": "transação de cartão externo", "verbose_name_plural": "transações de cartão externo", "indexes": [models.Index(fields=["status", "updated_at"], name="sales_cardp_status_c7aeb6_idx")]},
        ),
    ]
