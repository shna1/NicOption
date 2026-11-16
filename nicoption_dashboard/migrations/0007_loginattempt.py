from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nicoption_dashboard", "0006_accountpreference_cash_balance")]

    operations = [
        migrations.CreateModel(
            name="LoginAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key_hash", models.CharField(max_length=64, unique=True)),
                ("scope", models.CharField(choices=[("identity", "شناسه کاربری"), ("ip", "نشانی شبکه")], max_length=16)),
                ("failures", models.PositiveSmallIntegerField(default=0)),
                ("window_started", models.DateTimeField()),
                ("blocked_until", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "تلاش ورود", "verbose_name_plural": "تلاش‌های ورود"},
        )
    ]
