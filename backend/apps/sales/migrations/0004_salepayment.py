from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("sales", "0003_sale_client_request_id_and_more")]

    operations = [
        migrations.CreateModel(
            name="SalePayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.CharField(max_length=128, unique=True)),
                ("provider_id", models.CharField(blank=True, max_length=128, null=True, unique=True)),
                ("amount_cents", models.PositiveBigIntegerField()),
                ("status", models.CharField(choices=[("pending", "Pendente"), ("paid", "Pago"), ("expired", "Expirado"), ("cancelled", "Cancelado"), ("failed", "Falhou")], default="pending", max_length=24)),
                ("br_code", models.TextField(blank=True)),
                ("br_code_base64", models.TextField(blank=True)),
                ("provider_response", models.JSONField(blank=True, default=dict)),
                ("failure_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sale", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="abacatepay_payment", to="sales.sale")),
            ],
            options={"verbose_name": "pagamento AbacatePay", "verbose_name_plural": "pagamentos AbacatePay"},
        ),
        migrations.AddIndex(
            model_name="salepayment",
            index=models.Index(fields=["status", "updated_at"], name="sales_salep_status_3f6d28_idx"),
        ),
    ]
