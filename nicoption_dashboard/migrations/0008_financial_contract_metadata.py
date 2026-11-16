from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nicoption_dashboard", "0007_loginattempt")]

    operations = [
        migrations.AddField(
            model_name="traderecord",
            name="quantity_kind",
            field=models.CharField(
                blank=True,
                choices=[("contract", "قرارداد"), ("unit", "واحد دارایی پایه")],
                db_index=True,
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="traderecord",
            name="contract_size",
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=20, null=True
            ),
        ),
        migrations.AddField(
            model_name="traderecord",
            name="currency_unit",
            field=models.CharField(
                blank=True,
                choices=[("rial", "ریال"), ("toman", "تومان")],
                max_length=8,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="traderecord",
            name="calculation_version",
            field=models.PositiveSmallIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="underlyingpositionrecord",
            name="quantity_kind",
            field=models.CharField(
                blank=True,
                choices=[("unit", "واحد دارایی پایه")],
                db_index=True,
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="underlyingpositionrecord",
            name="currency_unit",
            field=models.CharField(
                blank=True,
                choices=[("rial", "ریال"), ("toman", "تومان")],
                max_length=8,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="underlyingpositionrecord",
            name="calculation_version",
            field=models.PositiveSmallIntegerField(blank=True, db_index=True, null=True),
        ),
    ]
