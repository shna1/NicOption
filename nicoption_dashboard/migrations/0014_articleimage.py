from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import nicoption_dashboard.models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("nicoption_dashboard", "0013_article_accountpreference_show_articles"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArticleImage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("file", models.FileField(upload_to=nicoption_dashboard.models.article_image_upload_path, verbose_name="فایل")),
                ("content_type", models.CharField(max_length=32, verbose_name="نوع فایل")),
                ("size", models.PositiveIntegerField(verbose_name="حجم فایل")),
                ("alt_text", models.CharField(max_length=180, verbose_name="متن جایگزین")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="زمان بارگذاری")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="nicoption_article_images", to=settings.AUTH_USER_MODEL, verbose_name="بارگذار")),
            ],
            options={
                "verbose_name": "تصویر مقاله",
                "verbose_name_plural": "تصاویر مقاله",
                "ordering": ("-created_at",),
            },
        ),
    ]
