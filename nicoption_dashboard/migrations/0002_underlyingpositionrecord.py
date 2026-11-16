from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("nicoption_dashboard", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="UnderlyingPositionRecord",
            fields=[
                ("id", models.CharField(max_length=32, primary_key=True, serialize=False)),
                ("status", models.CharField(db_index=True, default="open", max_length=16)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name":"دارایی پایه","verbose_name_plural":"دارایی‌های پایه","ordering":("created_at","id")},
        )
    ]
