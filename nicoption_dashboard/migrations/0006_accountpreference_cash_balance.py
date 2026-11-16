from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nicoption_dashboard", "0005_accountpreference_show_calculator_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountpreference",
            name="cash_balance",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
