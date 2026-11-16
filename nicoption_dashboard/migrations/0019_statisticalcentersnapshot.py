from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("nicoption_dashboard", "0018_centralbanksnapshot")]

    operations = [
        migrations.CreateModel(
            name="StatisticalCenterSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("collected_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("server_name", models.CharField(default="amar-mcp", max_length=80)),
                ("server_version", models.CharField(blank=True, max_length=32)),
                ("payload", models.JSONField(default=dict)),
                ("errors", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "تصویر گسترده مرکز آمار",
                "verbose_name_plural": "تصاویر گسترده مرکز آمار",
                "ordering": ("-collected_at", "-pk"),
            },
        ),
    ]
