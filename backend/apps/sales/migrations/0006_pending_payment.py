from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sales", "0005_salepaymentwebhookevent")]
    operations = [
        migrations.AlterField(
            model_name="sale", name="status",
            field=models.CharField(choices=[("completed", "Concluída"), ("pending_payment", "Pagamento pendente"), ("cancelled", "Cancelada")], default="completed", max_length=24, verbose_name="status"),
        ),
        migrations.AlterField(
            model_name="sale", name="payment_method",
            field=models.CharField(choices=[("cash", "Dinheiro"), ("card_external", "Cartão externo"), ("pix_manual", "Pix manual"), ("pix_abacatepay", "Pix AbacatePay"), ("other", "Outro")], default="cash", max_length=24, verbose_name="forma de pagamento"),
        ),
    ]
