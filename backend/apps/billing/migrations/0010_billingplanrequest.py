from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0009_invoice_items_and_module_prices"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BillingPlanRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("open", "Aberta"), ("approved", "Aprovada"), ("rejected", "Rejeitada"), ("cancelled", "Cancelada")], default="open", max_length=16, verbose_name="status")),
                ("request_key", models.CharField(max_length=200, verbose_name="chave da solicitação")),
                ("notes", models.TextField(blank=True, verbose_name="observações")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, verbose_name="revisado em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criada em")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_plan_requests", to="tenants.organization", verbose_name="organização")),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_plan_requests", to=settings.AUTH_USER_MODEL, verbose_name="solicitante")),
                ("requested_module", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="billing_requests", to="billing.module", verbose_name="módulo solicitado")),
                ("requested_plan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="billing_requests", to="billing.plan", verbose_name="plano solicitado")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reviewed_billing_requests", to=settings.AUTH_USER_MODEL, verbose_name="revisado por")),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "solicitação de billing", "verbose_name_plural": "solicitações de billing"},
        ),
        migrations.AddConstraint(model_name="billingplanrequest", constraint=models.CheckConstraint(condition=models.Q(("requested_plan__isnull", False), ("requested_module__isnull", True), _connector="AND") | models.Q(("requested_plan__isnull", True), ("requested_module__isnull", False), _connector="AND"), name="billing_request_exactly_one_target")),
        migrations.AddConstraint(model_name="billingplanrequest", constraint=models.UniqueConstraint(fields=("organization", "request_key"), name="unique_billing_request_key_per_org")),
        migrations.AddIndex(model_name="billingplanrequest", index=models.Index(fields=["organization", "status", "created_at"], name="billing_bil_organiz_b29bbd_idx")),
    ]
