import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenants", "0005_store_pix_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="Plan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64, unique=True, verbose_name="código")),
                ("name", models.CharField(max_length=120, verbose_name="nome")),
                ("description", models.TextField(blank=True, verbose_name="descrição")),
                ("monthly_price", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="preço mensal")),
                ("trial_days", models.PositiveIntegerField(default=0, verbose_name="dias de trial")),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
            ],
            options={"ordering": ["name"], "verbose_name": "plano", "verbose_name_plural": "planos"},
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[("trial", "Trial"), ("active", "Ativa"), ("past_due", "Inadimplente"), ("suspended", "Suspensa"), ("cancelled", "Cancelada")], default="trial", max_length=16, verbose_name="status")),
                ("gateway_provider", models.CharField(blank=True, max_length=64, verbose_name="provedor de gateway")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="iniciada em")),
                ("trial_ends_at", models.DateTimeField(blank=True, null=True, verbose_name="trial termina em")),
                ("current_period_start", models.DateField(blank=True, null=True, verbose_name="início do período")),
                ("current_period_end", models.DateField(blank=True, null=True, verbose_name="fim do período")),
                ("cancelled_at", models.DateTimeField(blank=True, null=True, verbose_name="cancelada em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criada em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizada em")),
                ("organization", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="billing_subscription", to="tenants.organization", verbose_name="organização")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="billing.plan", verbose_name="plano")),
            ],
            options={"ordering": ["organization__name"], "verbose_name": "assinatura", "verbose_name_plural": "assinaturas"},
        ),
        migrations.CreateModel(
            name="SubscriptionInvoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("number", models.CharField(max_length=64, verbose_name="número")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="valor")),
                ("status", models.CharField(choices=[("open", "Aberta"), ("paid", "Paga"), ("void", "Cancelada")], default="open", max_length=16, verbose_name="status")),
                ("due_date", models.DateField(verbose_name="vencimento")),
                ("paid_at", models.DateTimeField(blank=True, null=True, verbose_name="paga em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criada em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizada em")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_invoices", to="tenants.organization", verbose_name="organização")),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoices", to="billing.subscription", verbose_name="assinatura")),
            ],
            options={"ordering": ["-due_date", "-created_at"], "verbose_name": "fatura de assinatura", "verbose_name_plural": "faturas de assinatura"},
        ),
        migrations.CreateModel(
            name="BillingPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("idempotency_key", models.CharField(max_length=128, unique=True, verbose_name="chave de idempotência")),
                ("provider_payment_id", models.CharField(blank=True, max_length=128, null=True, unique=True, verbose_name="ID do pagamento no provedor")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="valor")),
                ("method", models.CharField(choices=[("manual", "Manual"), ("gateway", "Gateway")], default="manual", max_length=16, verbose_name="método")),
                ("paid_at", models.DateTimeField(verbose_name="paga em")),
                ("notes", models.TextField(blank=True, verbose_name="observações")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="billing.subscriptioninvoice", verbose_name="fatura")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_payments", to="tenants.organization", verbose_name="organização")),
                ("recorded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recorded_billing_payments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-paid_at"], "verbose_name": "pagamento de billing", "verbose_name_plural": "pagamentos de billing"},
        ),
        migrations.CreateModel(
            name="BillingProviderEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.CharField(max_length=160, unique=True, verbose_name="ID do evento")),
                ("provider", models.CharField(max_length=64, verbose_name="provedor")),
                ("event_type", models.CharField(max_length=100, verbose_name="tipo")),
                ("payload", models.JSONField(default=dict, verbose_name="payload")),
                ("processed_at", models.DateTimeField(blank=True, null=True, verbose_name="processado em")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="recebido em")),
                ("invoice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="provider_events", to="billing.subscriptioninvoice", verbose_name="fatura")),
                ("organization", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="billing_provider_events", to="tenants.organization", verbose_name="organização")),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "evento de provedor de billing", "verbose_name_plural": "eventos de provedor de billing"},
        ),
        migrations.AddConstraint(
            model_name="subscriptioninvoice",
            constraint=models.UniqueConstraint(fields=("organization", "number"), name="unique_billing_invoice_number_per_org"),
        ),
        migrations.AddIndex(model_name="subscription", index=models.Index(fields=["organization", "status"], name="billing_sub_organiz_e1331c_idx")),
        migrations.AddIndex(model_name="subscription", index=models.Index(fields=["status", "current_period_end"], name="billing_sub_status_684a21_idx")),
        migrations.AddIndex(model_name="subscriptioninvoice", index=models.Index(fields=["organization", "status", "due_date"], name="billing_sub_organiz_5af397_idx")),
        migrations.AddIndex(model_name="billingpayment", index=models.Index(fields=["organization", "paid_at"], name="billing_bil_organiz_94f199_idx")),
        migrations.AddIndex(model_name="billingproviderevent", index=models.Index(fields=["organization", "created_at"], name="billing_bil_organiz_e05571_idx")),
    ]
