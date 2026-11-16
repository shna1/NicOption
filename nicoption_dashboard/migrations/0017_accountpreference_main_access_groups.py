from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nicoption_dashboard", "0016_useraccessprofile_email_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountpreference",
            name="show_economic_data",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="accountpreference",
            name="show_option_market",
            field=models.BooleanField(default=True),
        ),
    ]
