from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("nicoption_dashboard", "0015_useraccessprofile_phone_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccessprofile",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True),
        ),
        migrations.AddField(
            model_name="useraccessprofile",
            name="verification_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
