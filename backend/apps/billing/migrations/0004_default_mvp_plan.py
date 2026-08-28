from decimal import Decimal

from django.db import migrations, models


def seed_default_plan(apps, schema_editor):
    Module = apps.get_model("billing", "Module")
    Plan = apps.get_model("billing", "Plan")
    PlanModule = apps.get_model("billing", "PlanModule")
    plan, _ = Plan.objects.get_or_create(
        code="mvp",
        defaults={
            "name": "MVP",
            "description": "Plano inicial com acesso ao PDV.",
            "monthly_price": Decimal("0.00"),
            "trial_days": 14,
            "is_active": True,
            "is_default": True,
        },
    )
    if not plan.is_default or not plan.is_active:
        plan.is_default = True
        plan.is_active = True
        plan.save(update_fields=["is_default", "is_active"])
    sales = Module.objects.get(code="sales")
    PlanModule.objects.get_or_create(plan=plan, module=sales, defaults={"included": True})


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_module_base_and_dependencies")]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="is_default",
            field=models.BooleanField(default=False, verbose_name="plano padrão"),
        ),
        migrations.RunPython(seed_default_plan, migrations.RunPython.noop),
    ]
