from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("nicoption_dashboard", "0009_copy_explicit_financial_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="traderecord",
            name="mutation_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.CreateModel(
            name="TradeMutationRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation", models.CharField(max_length=32)),
                ("key_hash", models.CharField(max_length=64)),
                ("request_hash", models.CharField(max_length=64)),
                ("trade_id", models.CharField(blank=True, max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trade_mutation_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["owner", "created_at"], name="nicoption_d_owner_i_6e370b_idx")],
                "constraints": [models.UniqueConstraint(fields=("owner", "operation", "key_hash"), name="uniq_trade_mutation_key_per_owner")],
            },
        ),
    ]
