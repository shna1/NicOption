from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("nicoption_dashboard", "0019_statisticalcentersnapshot")]

    operations = [
        migrations.CreateModel(
            name="XPostTranslation",
            fields=[
                ("post_id", models.CharField(max_length=32, primary_key=True, serialize=False, verbose_name="شناسه پست X")),
                ("username", models.CharField(db_index=True, max_length=64, verbose_name="نام کاربری")),
                ("source_url", models.URLField(max_length=300, verbose_name="پیوند متن اصلی")),
                ("original_text", models.TextField(verbose_name="متن اصلی")),
                ("source_created_at", models.DateTimeField(db_index=True, verbose_name="زمان انتشار در X")),
                ("raw_payload", models.JSONField(blank=True, default=dict, verbose_name="داده خام")),
                ("translated_title", models.CharField(blank=True, max_length=180, verbose_name="عنوان ترجمه")),
                ("translated_summary", models.CharField(blank=True, max_length=500, verbose_name="خلاصه ترجمه")),
                ("translated_text", models.TextField(blank=True, verbose_name="ترجمه فارسی")),
                ("review_note", models.TextField(blank=True, verbose_name="یادداشت بازبینی")),
                ("needs_review", models.BooleanField(default=True, verbose_name="نیازمند بازبینی")),
                ("translation_status", models.CharField(choices=[("pending", "در انتظار ترجمه"), ("translated", "ترجمه‌شده"), ("failed", "خطای ترجمه")], db_index=True, default="pending", max_length=16, verbose_name="وضعیت ترجمه")),
                ("translation_model", models.CharField(blank=True, max_length=80, verbose_name="مدل ترجمه")),
                ("translation_attempts", models.PositiveSmallIntegerField(default=0, verbose_name="تعداد تلاش ترجمه")),
                ("translation_error", models.TextField(blank=True, verbose_name="خطای ترجمه")),
                ("translated_at", models.DateTimeField(blank=True, null=True, verbose_name="زمان ترجمه")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="زمان دریافت")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")),
                ("article", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="x_post_translation", to="nicoption_dashboard.article", verbose_name="مقاله")),
            ],
            options={
                "verbose_name": "ترجمه پست X",
                "verbose_name_plural": "ترجمه پست‌های X",
                "ordering": ("-source_created_at", "-post_id"),
            },
        ),
    ]
