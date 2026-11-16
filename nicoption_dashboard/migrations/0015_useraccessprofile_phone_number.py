from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nicoption_dashboard", "0014_articleimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccessprofile",
            name="phone_number",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
