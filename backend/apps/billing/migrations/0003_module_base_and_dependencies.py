import django.db.models.deletion
from django.db import migrations, models


def seed_modules(apps, schema_editor):
    Module = apps.get_model("billing", "Module")
    ModuleDependency = apps.get_model("billing", "ModuleDependency")
    core, _ = Module.objects.get_or_create(
        code="core", defaults={"name": "Base", "description": "Conta, organização e acesso", "is_base": True}
    )
    if not core.is_base:
        core.is_base = True
        core.save(update_fields=["is_base"])
    catalog, _ = Module.objects.get_or_create(
        code="catalog", defaults={"name": "Catálogo", "description": "Produtos, categorias e preços", "is_base": True}
    )
    if not catalog.is_base:
        catalog.is_base = True
        catalog.save(update_fields=["is_base"])
    sales, _ = Module.objects.get_or_create(
        code="sales", defaults={"name": "PDV / Vendas", "description": "Operação de vendas", "is_base": False}
    )
    ModuleDependency.objects.get_or_create(module=sales, depends_on=catalog)


def unseed_modules(apps, schema_editor):
    Module = apps.get_model("billing", "Module")
    Module.objects.filter(code__in=["core", "catalog", "sales"]).delete()


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_module_entitlements")]

    operations = [
        migrations.AddField(
            model_name="module",
            name="is_base",
            field=models.BooleanField(default=False, verbose_name="módulo base"),
        ),
        migrations.CreateModel(
            name="ModuleDependency",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("depends_on", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="required_by", to="billing.module", verbose_name="depende de")),
                ("module", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="dependencies", to="billing.module", verbose_name="módulo")),
            ],
            options={
                "ordering": ["module__code", "depends_on__code"],
                "verbose_name": "dependência de módulo",
                "verbose_name_plural": "dependências de módulos",
            },
        ),
        migrations.AddConstraint(
            model_name="moduledependency",
            constraint=models.UniqueConstraint(fields=("module", "depends_on"), name="unique_module_dependency"),
        ),
        migrations.RunPython(seed_modules, unseed_modules),
    ]
