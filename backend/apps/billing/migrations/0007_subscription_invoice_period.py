from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0006_subscription_lifecycle")]

    operations = [
        migrations.AddField(
            model_name="subscriptioninvoice",
            name="period_start",
            field=models.DateField(blank=True, null=True, verbose_name="início do período"),
        ),
        migrations.AddField(
            model_name="subscriptioninvoice",
            name="period_end",
            field=models.DateField(blank=True, null=True, verbose_name="fim do período"),
        ),
        migrations.AddConstraint(
            model_name="subscriptioninvoice",
            constraint=models.UniqueConstraint(
                fields=("subscription", "period_start", "period_end"),
                name="unique_subscription_invoice_period",
            ),
        ),
    ]
