from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0004_userprofile_must_change_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="pix_key",
            field=models.CharField(blank=True, max_length=120, verbose_name="chave Pix"),
        ),
    ]
