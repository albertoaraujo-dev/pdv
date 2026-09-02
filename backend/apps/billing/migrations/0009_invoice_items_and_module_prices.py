from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("billing", "0008_billingnotification")]

    operations = [
        migrations.AddField(
            model_name="planmodule", name="monthly_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="preço mensal do módulo"),
        ),
        migrations.AddField(
            model_name="subscriptionmodule", name="monthly_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="preço mensal do módulo"),
        ),
        migrations.CreateModel(
            name="SubscriptionInvoiceItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("item_type", models.CharField(choices=[("plan", "Plano"), ("module", "Módulo")], max_length=16, verbose_name="tipo")),
                ("code", models.CharField(max_length=64, verbose_name="código")),
                ("description", models.CharField(max_length=200, verbose_name="descrição")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="valor")),
                ("amount_override", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="valor sobrescrito")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="items", to="billing.subscriptioninvoice", verbose_name="fatura")),
                ("module", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="invoice_items", to="billing.module", verbose_name="módulo")),
            ],
            options={"ordering": ["item_type", "code"], "verbose_name": "item de fatura", "verbose_name_plural": "itens de faturas"},
        ),
    ]
