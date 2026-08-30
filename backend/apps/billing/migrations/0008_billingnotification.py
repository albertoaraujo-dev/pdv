from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("billing", "0007_subscription_invoice_period")]

    operations = [
        migrations.CreateModel(
            name="BillingNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("notification_type", models.CharField(choices=[("due_soon", "Vencimento próximo"), ("past_due", "Fatura vencida"), ("suspension_warning", "Aviso de suspensão"), ("suspended", "Assinatura suspensa")], max_length=32, verbose_name="tipo")),
                ("idempotency_key", models.CharField(max_length=200, unique=True, verbose_name="chave de idempotência")),
                ("period_start", models.DateField(blank=True, null=True, verbose_name="início do período")),
                ("period_end", models.DateField(blank=True, null=True, verbose_name="fim do período")),
                ("delivered_at", models.DateTimeField(blank=True, null=True, verbose_name="entregue em")),
                ("payload", models.JSONField(default=dict, verbose_name="payload")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criada em")),
                ("invoice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="billing_notifications", to="billing.subscriptioninvoice", verbose_name="fatura")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_notifications", to="tenants.organization", verbose_name="organização")),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_notifications", to="billing.subscription", verbose_name="assinatura")),
            ],
            options={
                "verbose_name": "notificação de billing",
                "verbose_name_plural": "notificações de billing",
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["organization", "notification_type", "created_at"], name="billing_bil_organiz_4e0580_idx")],
            },
        ),
    ]
