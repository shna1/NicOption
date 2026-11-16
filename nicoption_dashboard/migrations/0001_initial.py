from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="AccountPreference",
            fields=[
                ("singleton", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("initial_capital", models.FloatField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "تنظیم حساب", "verbose_name_plural": "تنظیمات حساب"},
        ),
        migrations.CreateModel(
            name="TradeRecord",
            fields=[
                ("id", models.CharField(max_length=32, primary_key=True, serialize=False)),
                ("status", models.CharField(db_index=True, default="open", max_length=16)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "معامله", "verbose_name_plural": "معاملات", "ordering": ("created_at", "id")},
        ),
    ]
