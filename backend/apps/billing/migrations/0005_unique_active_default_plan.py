from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0004_default_mvp_plan")]

    operations = [
        migrations.AddConstraint(
            model_name="plan",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True, is_default=True),
                fields=("is_default",),
                name="unique_active_default_plan",
            ),
        ),
    ]
