from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nicoption_dashboard", "0010_trade_mutation_safety")]

    operations = [
        migrations.AlterField(
            model_name="accountpreference",
            name="initial_capital",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=30,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="accountpreference",
            name="cash_balance",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=30,
                null=True,
            ),
        ),
    ]
