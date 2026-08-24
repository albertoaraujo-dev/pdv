from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="stock", name="reserved_quantity",
            field=models.DecimalField(decimal_places=3, default=Decimal("0.000"), max_digits=12, verbose_name="reservado"),
        ),
        migrations.AddConstraint(
            model_name="stock",
            constraint=models.CheckConstraint(condition=models.Q(reserved_quantity__gte=0), name="stock_reserved_non_negative"),
        ),
        migrations.AddConstraint(
            model_name="stock",
            constraint=models.CheckConstraint(condition=models.Q(quantity__gte=0), name="stock_quantity_non_negative"),
        ),
        migrations.AddConstraint(
            model_name="stock",
            constraint=models.CheckConstraint(condition=models.Q(reserved_quantity__lte=models.F("quantity")), name="stock_reserved_not_above_quantity"),
        ),
        migrations.AlterField(
            model_name="stockmovement", name="movement_type",
            field=models.CharField(choices=[
                ("inbound", "Entrada"), ("sale", "Venda"), ("sale_reversal", "Estorno de venda"),
                ("reservation", "Reserva"), ("release", "Liberação de reserva"), ("adjustment", "Ajuste"),
            ], max_length=24, verbose_name="tipo"),
        ),
    ]
