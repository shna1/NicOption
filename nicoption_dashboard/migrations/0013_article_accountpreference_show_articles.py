from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("nicoption_dashboard", "0012_datasource_economicindicator_ingestionrun_dataissue_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountpreference",
            name="show_articles",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="Article",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180, verbose_name="عنوان")),
                ("slug", models.SlugField(allow_unicode=True, max_length=200, unique=True, verbose_name="نشانی")),
                ("summary", models.TextField(max_length=500, verbose_name="خلاصه")),
                ("body", models.TextField(verbose_name="متن مقاله")),
                ("is_published", models.BooleanField(db_index=True, default=False, verbose_name="منتشر شده")),
                ("published_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="زمان انتشار")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")),
                ("author", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="nicoption_articles", to=settings.AUTH_USER_MODEL, verbose_name="نویسنده")),
            ],
            options={
                "verbose_name": "مقاله",
                "verbose_name_plural": "مقالات",
                "ordering": ("-published_at", "-created_at"),
            },
        ),
    ]
