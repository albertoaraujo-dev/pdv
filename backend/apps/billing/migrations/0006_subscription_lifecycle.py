from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0005_unique_active_default_plan"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="subscription", name="past_due_since", field=models.DateTimeField(blank=True, null=True, verbose_name="inadimplência desde")),
        migrations.AddField(model_name="subscription", name="grace_until", field=models.DateTimeField(blank=True, null=True, verbose_name="fim da carência")),
        migrations.AddField(model_name="subscription", name="cancellation_reason", field=models.CharField(blank=True, max_length=255, verbose_name="motivo do cancelamento")),
        migrations.AddField(model_name="subscription", name="cancellation_metadata", field=models.JSONField(blank=True, default=dict, verbose_name="metadados do cancelamento")),
        migrations.AlterField(model_name="subscriptioninvoice", name="status", field=models.CharField(choices=[("open", "Aberta"), ("past_due", "Inadimplente"), ("paid", "Paga"), ("void", "Cancelada")], default="open", max_length=16, verbose_name="status")),
        migrations.CreateModel(
            name="SubscriptionChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_at", models.DateTimeField(verbose_name="vigente em")),
                ("reason", models.TextField(blank=True, verbose_name="motivo")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criada em")),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="billing_subscription_changes", to=settings.AUTH_USER_MODEL)),
                ("new_plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscription_changes_to", to="billing.plan", verbose_name="novo plano")),
                ("old_plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscription_changes_from", to="billing.plan", verbose_name="plano anterior")),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="plan_changes", to="billing.subscription", verbose_name="assinatura")),
            ],
            options={"ordering": ["-effective_at", "-created_at"], "verbose_name": "alteração de assinatura", "verbose_name_plural": "alterações de assinaturas"},
        ),
    ]
