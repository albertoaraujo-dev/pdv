import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Module",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64, unique=True, verbose_name="código")),
                ("name", models.CharField(max_length=120, verbose_name="nome")),
                ("description", models.TextField(blank=True, verbose_name="descrição")),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
            ],
            options={"ordering": ["name"], "verbose_name": "módulo", "verbose_name_plural": "módulos"},
        ),
        migrations.CreateModel(
            name="PlanModule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("included", models.BooleanField(default=True, verbose_name="incluído")),
                ("limits", models.JSONField(blank=True, null=True, verbose_name="limites")),
                ("module", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="plan_modules", to="billing.module", verbose_name="módulo")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plan_modules", to="billing.plan", verbose_name="plano")),
            ],
            options={"ordering": ["plan__name", "module__name"], "verbose_name": "módulo do plano", "verbose_name_plural": "módulos dos planos"},
        ),
        migrations.CreateModel(
            name="SubscriptionModule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("included", models.BooleanField(default=True, verbose_name="incluído")),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
                ("starts_at", models.DateTimeField(blank=True, null=True, verbose_name="inicia em")),
                ("ends_at", models.DateTimeField(blank=True, null=True, verbose_name="termina em")),
                ("limits", models.JSONField(blank=True, null=True, verbose_name="limites")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("module", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscription_modules", to="billing.module", verbose_name="módulo")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="billing_subscription_modules", to="tenants.organization", verbose_name="organização")),
                ("subscription", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscription_modules", to="billing.subscription", verbose_name="assinatura")),
            ],
            options={"ordering": ["organization__name", "module__name"], "verbose_name": "módulo da assinatura", "verbose_name_plural": "módulos das assinaturas"},
        ),
        migrations.AddConstraint(model_name="planmodule", constraint=models.UniqueConstraint(fields=("plan", "module"), name="unique_module_per_plan")),
        migrations.AddConstraint(model_name="subscriptionmodule", constraint=models.UniqueConstraint(fields=("subscription", "module"), name="unique_module_per_subscription")),
        migrations.AddIndex(model_name="subscriptionmodule", index=models.Index(fields=["organization", "is_active", "starts_at", "ends_at"], name="billing_sub_organiz_b6db18_idx")),
    ]
