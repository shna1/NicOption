import csv
import io
import secrets
import time
from pathlib import Path

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django import forms
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from .article_content import sanitize_article_html
from .economic_admin_forms import EconomicCSVUploadForm, ManualEconomicObservationForm
from .economic_data import (
    ConcurrentImportError,
    ImportConfigurationError,
    import_rows,
    ingestion_lock,
)

from .models import (
    AccountPreference,
    Article,
    ArticleImage,
    DataIssue,
    DataSource,
    EconomicIndicator,
    IndicatorObservation,
    IndicatorRelease,
    IndicatorSource,
    IngestionRun,
    TradeRecord,
    UnderlyingPositionRecord,
    UserAccessProfile,
    XPostTranslation,
)


ARTICLE_IMAGE_MAX_BYTES = 5 * 1024 * 1024
ARTICLE_IMAGE_TYPES = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
    "image/gif": (".gif",),
}


def _detect_article_image_type(header: bytes) -> str | None:
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


class ArticleEditorWidget(forms.Textarea):
    template_name = "admin/widgets/article_editor.html"

    class Media:
        css = {"all": ("/admin/article-editor.css",)}
        js = ("/admin/article-editor.js",)

    def format_value(self, value):
        return sanitize_article_html(value or "")


class ArticleAdminForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = "__all__"
        widgets = {"body": ArticleEditorWidget(attrs={"rows": 18})}

    def clean_body(self):
        body = sanitize_article_html(self.cleaned_data.get("body", ""))
        if not body:
            raise forms.ValidationError("متن مقاله را وارد کنید.")
        return body


class IndicatorSourceInline(admin.TabularInline):
    model = IndicatorSource
    extra = 0
    autocomplete_fields = ("source",)
    fields = ("source", "priority", "is_primary", "valid_from", "valid_to", "notes")


@admin.register(EconomicIndicator)
class EconomicIndicatorAdmin(admin.ModelAdmin):
    list_display = ("code", "name_fa", "kind", "category", "frequency", "unit", "is_active", "updated_at")
    list_filter = ("kind", "category", "frequency", "is_active")
    search_fields = ("code", "name_fa", "name_en")
    readonly_fields = ("created_at", "updated_at")
    inlines = (IndicatorSourceInline,)

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (("code",) if obj else ())


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "source_type", "is_primary", "is_active", "updated_at")
    list_filter = ("source_type", "is_primary", "is_active")
    search_fields = ("name", "organization")
    readonly_fields = ("created_at", "updated_at")


@admin.register(IndicatorObservation)
class IndicatorObservationAdmin(admin.ModelAdmin):
    list_display = ("indicator", "source", "period_date", "value", "unit", "revision", "status", "is_current_revision", "collected_at")
    list_filter = ("indicator", "source", "status", "is_current_revision", "period_date")
    search_fields = ("indicator__code", "indicator__name_fa", "source__name", "external_id")
    readonly_fields = tuple(field.name for field in IndicatorObservation._meta.fields)
    list_select_related = ("indicator", "source")
    date_hierarchy = "period_date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD", "OPTIONS"}

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    change_list_template = "admin/nicoption_dashboard/ingestionrun/change_list.html"
    list_display = ("started_at", "channel", "status", "rows_seen", "rows_inserted", "rows_revised", "rows_rejected")
    list_filter = ("channel", "status", "started_at")
    readonly_fields = tuple(field.name for field in IngestionRun._meta.fields)
    date_hierarchy = "started_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        custom_urls = [
            path(
                "data-update/",
                self.admin_site.admin_view(self.data_update_view),
                name="nicoption_dashboard_ingestionrun_data_update",
            ),
        ]
        return custom_urls + super().get_urls()

    def data_update_view(self, request):
        if not request.user.is_active or not request.user.is_superuser:
            raise PermissionDenied

        manual_form = ManualEconomicObservationForm(prefix="manual")
        csv_form = EconomicCSVUploadForm(prefix="csv")
        preview = None
        committed_run = None

        if request.GET.get("run", "").isdigit():
            committed_run = IngestionRun.objects.filter(
                pk=int(request.GET["run"]), created_by=request.user
            ).first()

        if request.method == "POST":
            action = request.POST.get("action", "")
            if action == "preview_manual":
                manual_form = ManualEconomicObservationForm(request.POST, prefix="manual")
                if manual_form.is_valid():
                    preview = self._build_preview(
                        request,
                        [manual_form.as_import_row()],
                        channel=IngestionRun.Channel.MANUAL,
                        strict=True,
                        filename="",
                    )
            elif action == "preview_csv":
                csv_form = EconomicCSVUploadForm(request.POST, request.FILES, prefix="csv")
                if csv_form.is_valid():
                    try:
                        rows = self._read_csv_upload(csv_form.cleaned_data["file"])
                    except (UnicodeDecodeError, csv.Error, ImportConfigurationError) as exc:
                        csv_form.add_error("file", str(exc))
                    else:
                        preview = self._build_preview(
                            request,
                            rows,
                            channel=IngestionRun.Channel.CSV,
                            strict=csv_form.cleaned_data["strict"],
                            filename=csv_form.cleaned_data["file"].name,
                        )
            elif action == "commit_preview":
                return self._commit_preview(request)
            elif action == "cancel_preview":
                request.session.pop("economic_data_preview", None)
                messages.info(request, "پیش‌نمایش کنار گذاشته شد و داده‌ای ثبت نشد.")
                return HttpResponseRedirect(self._update_url())

        context = {
            **self.admin_site.each_context(request),
            "title": "بروزرسانی داده‌های اقتصادی",
            "opts": self.model._meta,
            "manual_form": manual_form,
            "csv_form": csv_form,
            "preview": preview,
            "committed_run": committed_run,
            "recent_runs": IngestionRun.objects.select_related("created_by")[:8],
            "media": self.media,
        }
        return render(
            request,
            "admin/nicoption_dashboard/ingestionrun/data_update.html",
            context,
        )

    @staticmethod
    def _read_csv_upload(uploaded_file) -> list[dict[str, str]]:
        text = uploaded_file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames is None:
            raise ImportConfigurationError("سطر عنوان ستون‌های CSV پیدا نشد.")
        rows = []
        for row in reader:
            if len(rows) >= 5000:
                raise ImportConfigurationError("فایل CSV نمی‌تواند بیشتر از ۵٬۰۰۰ ردیف داشته باشد.")
            rows.append({str(key or ""): str(value or "") for key, value in row.items()})
        if not rows:
            raise ImportConfigurationError("فایل CSV هیچ ردیف داده‌ای ندارد.")
        return rows

    def _build_preview(self, request, rows, *, channel, strict, filename):
        try:
            with ingestion_lock():
                summary = import_rows(rows, channel=channel, dry_run=True, strict=strict)
        except (ConcurrentImportError, ValueError) as exc:
            messages.error(request, f"پیش‌نمایش انجام نشد: {exc}")
            return None

        token = secrets.token_urlsafe(24)
        request.session["economic_data_preview"] = {
            "token": token,
            "created_at": time.time(),
            "rows": rows,
            "channel": channel,
            "strict": strict,
            "filename": filename,
            "rejected": summary.rejected,
        }
        request.session.modified = True
        return {
            "token": token,
            "summary": summary,
            "issues": [self._localized_issue(issue) for issue in summary.issues],
            "strict": strict,
            "channel": channel,
            "filename": filename,
            "can_commit": not (strict and summary.rejected),
        }

    def _commit_preview(self, request):
        staged = request.session.get("economic_data_preview") or {}
        token = request.POST.get("preview_token", "")
        if not token or not secrets.compare_digest(token, staged.get("token", "")):
            messages.error(request, "پیش‌نمایش معتبر نیست؛ دوباره داده‌ها را بررسی کنید.")
            return HttpResponseRedirect(self._update_url())
        if time.time() - float(staged.get("created_at", 0)) > 30 * 60:
            request.session.pop("economic_data_preview", None)
            messages.error(request, "مهلت پیش‌نمایش تمام شده است؛ دوباره بررسی را اجرا کنید.")
            return HttpResponseRedirect(self._update_url())
        if staged.get("strict") and staged.get("rejected"):
            messages.error(
                request,
                "این پیش‌نمایش خطای مسدودکننده دارد و قابل ثبت نیست.",
            )
            return HttpResponseRedirect(self._update_url())

        try:
            with ingestion_lock():
                summary = import_rows(
                    staged["rows"],
                    channel=staged["channel"],
                    strict=bool(staged["strict"]),
                    metadata={
                        "admin_entry": True,
                        "filename": "<redacted>" if staged.get("filename") else "",
                    },
                    created_by=request.user,
                )
        except (ConcurrentImportError, ValueError) as exc:
            messages.error(request, f"ثبت داده انجام نشد: {exc}")
            return HttpResponseRedirect(self._update_url())

        request.session.pop("economic_data_preview", None)
        messages.success(
            request,
            "ثبت انجام شد: "
            f"{summary.inserted} ردیف جدید، {summary.revised} اصلاح، "
            f"{summary.unchanged} بدون تغییر و {summary.rejected} ردشده.",
        )
        url = self._update_url()
        if summary.run:
            url = f"{url}?run={summary.run.pk}"
        return HttpResponseRedirect(url)

    @staticmethod
    def _localized_issue(issue):
        messages_fa = {
            "missing_columns": "ستون‌های اجباری فایل کامل نیستند.",
            "unknown_indicator": "کد شاخص در کاتالوگ فعال پیدا نشد.",
            "blank_source": "نام منبع اصلی الزامی است.",
            "unknown_source": "منبع در فهرست منابع فعال پیدا نشد.",
            "invalid_period_date": "تاریخ دوره باید میلادی و با قالب YYYY-MM-DD باشد.",
            "future_period": "تاریخ دوره بیش از حد در آینده است.",
            "missing_value": "مقدار الزامی است؛ مقدار خالی با صفر تفاوت دارد.",
            "invalid_decimal": "مقدار باید یک عدد معتبر باشد.",
            "missing_unit": "واحد اندازه‌گیری الزامی است.",
            "unit_mismatch": "واحد ردیف با واحد تعریف‌شده برای شاخص یکسان نیست.",
            "indicator_unit_unconfigured": "واحد شاخص در کاتالوگ تنظیم نشده است.",
            "invalid_status": "وضعیت داده معتبر نیست.",
            "invalid_published_at": "زمان انتشار باید تاریخ و زمان ISO معتبر باشد.",
            "invalid_url": "نشانی منبع باید با http یا https آغاز شود.",
            "invalid_revision": "شماره بازبینی باید عدد صحیح نامنفی باشد.",
            "source_not_linked": "این منبع برای شاخص انتخاب‌شده تعریف نشده است.",
            "source_kind_mismatch": "شاخص رسمی باید به منبع رسمی متصل باشد.",
            "duplicate_exact": "این ردیف در همین ورودی تکرار شده است.",
            "duplicate_conflict": "برای یک شاخص، منبع و دوره دو مقدار متفاوت وجود دارد.",
            "missing_published_at": "زمان انتشار وارد نشده است.",
            "chronology": "زمان انتشار پیش از تاریخ دوره قرار گرفته است.",
            "unusual_change": "تغییر مقدار از آستانه کنترل‌شده بیشتر است.",
        }
        return {
            "row_number": issue.row_number,
            "severity": issue.severity,
            "code": issue.code,
            "message": messages_fa.get(issue.code, issue.message),
            "indicator_code": issue.indicator_code,
        }

    @staticmethod
    def _update_url():
        return reverse("admin:nicoption_dashboard_ingestionrun_data_update")


@admin.register(DataIssue)
class DataIssueAdmin(admin.ModelAdmin):
    list_display = ("created_at", "severity", "issue_code", "indicator", "source", "row_number", "resolved_at")
    list_filter = ("severity", "issue_code", "resolved_at", "indicator", "source")
    search_fields = ("indicator__code", "indicator__name_fa", "source__name", "message", "external_row_id")
    readonly_fields = ("ingestion_run", "indicator", "source", "row_number", "external_row_id", "severity", "issue_code", "message", "safe_payload", "created_at")
    list_select_related = ("indicator", "source", "ingestion_run")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IndicatorRelease)
class IndicatorReleaseAdmin(admin.ModelAdmin):
    list_display = ("indicator", "period_date", "expected_at", "status", "source", "published_at")
    list_filter = ("status", "indicator", "source", "expected_at")
    search_fields = ("indicator__code", "indicator__name_fa", "source__name")
    autocomplete_fields = ("indicator", "source")
    list_select_related = ("indicator", "source")


class UserAccessProfileInline(admin.StackedInline):
    model = UserAccessProfile
    can_delete = False
    extra = 0
    max_num = 1
    fields = (
        "role",
        "phone_number",
        "email_verified_at",
        "verification_email_sent_at",
        "updated_at",
    )
    readonly_fields = ("verification_email_sent_at", "updated_at")


class AccountPreferenceAdminForm(forms.ModelForm):
    class Meta:
        model = AccountPreference
        fields = "__all__"
        labels = {
            "show_overview": "نمایش برترین‌ها",
            "show_articles": "مقالات",
            "show_option_market": "بازار آپشن",
            "show_economic_data": "داده‌های اقتصادی",
            "show_market": "نمایش فرصت‌های بازار آپشن",
            "show_tehran_options": "نمایش جدول جامع",
            "show_order_flow": "نمایش جریان سفارشات",
            "show_commodity_exchange": "نمایش بورس کالا",
            "show_trades": "نمایش معاملات باز",
            "show_closed_trades": "نمایش معاملات بسته",
            "show_profit_recognition": "نمایش شناسایی سود",
            "show_calculator": "نمایش ماشین‌حساب",
            "show_settings": "نمایش تنظیمات",
            "show_forecast": "نمایش پیش‌بینی",
        }


class AccountPreferenceInline(admin.StackedInline):
    model = AccountPreference
    form = AccountPreferenceAdminForm
    can_delete = False
    extra = 1
    max_num = 1
    fieldsets = (
        (
            "دسترسی‌های اصلی",
            {
                "fields": (
                    "show_option_market",
                    "show_economic_data",
                    "show_articles",
                ),
                "description": (
                    "با برداشتن هر انتخاب، لینک‌های همان بخش پنهان و دسترسی مستقیم "
                    "کاربر به صفحه‌های آن مسدود می‌شود."
                ),
            },
        ),
        (
            "جزئیات بازار آپشن",
            {
                "classes": ("collapse",),
                "fields": (
                    "show_market",
                    "show_tehran_options",
                    "show_order_flow",
                    "show_commodity_exchange",
                    "show_trades",
                    "show_closed_trades",
                    "show_profit_recognition",
                    "show_forecast",
                ),
                "description": "این گزینه‌ها فقط وقتی «بازار آپشن» فعال باشد اثر دارند.",
            },
        ),
        (
            "سایر بخش‌ها",
            {
                "classes": ("collapse",),
                "fields": (
                    "show_overview",
                    "show_calculator",
                    "show_settings",
                    "initial_capital",
                    "updated_at",
                ),
            },
        ),
    )
    readonly_fields = ("initial_capital", "updated_at")
    verbose_name = "دسترسی به بخش‌های سایت"
    verbose_name_plural = "دسترسی به بخش‌های سایت"


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    form = ArticleAdminForm
    list_display = ("title", "is_published", "published_at", "author", "updated_at")
    list_filter = ("is_published", "published_at")
    search_fields = ("title", "summary", "body")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "published_at"

    def get_urls(self):
        custom_urls = [
            path(
                "image-upload/",
                self.admin_site.admin_view(self.image_upload_view),
                name="nicoption_dashboard_article_image_upload",
            ),
        ]
        return custom_urls + super().get_urls()

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "body" and formfield:
            formfield.widget.attrs["data-upload-url"] = reverse(
                "admin:nicoption_dashboard_article_image_upload"
            )
        return formfield

    def image_upload_view(self, request):
        if request.method != "POST":
            return JsonResponse({"error": "روش درخواست معتبر نیست."}, status=405)
        if not self.has_change_permission(request):
            raise PermissionDenied
        uploaded = request.FILES.get("image")
        alt_text = request.POST.get("alt_text", "").strip()
        if uploaded is None:
            return JsonResponse({"error": "ابتدا یک تصویر انتخاب کنید."}, status=400)
        if not alt_text:
            return JsonResponse({"error": "متن جایگزین تصویر الزامی است."}, status=400)
        if len(alt_text) > 180:
            return JsonResponse({"error": "متن جایگزین حداکثر ۱۸۰ نویسه است."}, status=400)
        if uploaded.size <= 0 or uploaded.size > ARTICLE_IMAGE_MAX_BYTES:
            return JsonResponse({"error": "حجم تصویر باید بین ۱ بایت و ۵ مگابایت باشد."}, status=400)

        header = uploaded.read(16)
        uploaded.seek(0)
        content_type = _detect_article_image_type(header)
        suffix = Path(uploaded.name).suffix.lower()
        if not content_type or suffix not in ARTICLE_IMAGE_TYPES[content_type]:
            return JsonResponse(
                {"error": "فرمت تصویر باید JPG، PNG، WebP یا GIF باشد."},
                status=400,
            )

        image = ArticleImage.objects.create(
            file=uploaded,
            content_type=content_type,
            size=uploaded.size,
            alt_text=alt_text,
            uploaded_by=request.user,
        )
        return JsonResponse(
            {
                "url": reverse("article-media", kwargs={"image_id": image.pk}),
                "alt": image.alt_text,
            },
            status=201,
        )

    def save_model(self, request, obj, form, change):
        if obj.author_id is None:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(XPostTranslation)
class XPostTranslationAdmin(admin.ModelAdmin):
    list_select_related = ("article",)
    list_display = (
        "post_id",
        "username",
        "translation_status",
        "needs_review",
        "publication_status",
        "source_created_at",
    )
    list_filter = ("translation_status", "needs_review", "username", "source_created_at")
    search_fields = ("post_id", "username", "original_text", "translated_title", "translated_text")
    readonly_fields = (
        "post_id",
        "username",
        "source_link",
        "source_created_at",
        "original_text",
        "translated_title",
        "translated_summary",
        "translated_text",
        "review_note",
        "needs_review",
        "translation_status",
        "translation_model",
        "translation_attempts",
        "translation_error",
        "translated_at",
        "article_link",
        "raw_payload",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "source_created_at"
    actions = ("retry_translation",)

    @admin.display(description="متن اصلی")
    def source_link(self, obj):
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">مشاهده در X</a>',
            obj.source_url,
        )

    @admin.display(description="مقاله")
    def article_link(self, obj):
        if not obj.article_id:
            return "—"
        url = reverse("admin:nicoption_dashboard_article_change", args=(obj.article_id,))
        return format_html('<a href="{}">ویرایش و انتشار مقاله</a>', url)

    @admin.display(boolean=True, description="منتشرشده")
    def publication_status(self, obj):
        return bool(obj.article_id and obj.article.is_published)

    @admin.action(description="تلاش دوباره برای ترجمه انتخاب‌شده‌ها")
    def retry_translation(self, request, queryset):
        updated = queryset.exclude(
            translation_status=XPostTranslation.TranslationStatus.TRANSLATED
        ).update(
            translation_status=XPostTranslation.TranslationStatus.PENDING,
            translation_attempts=0,
            translation_error="",
        )
        self.message_user(request, f"{updated} مورد برای تلاش دوباره آماده شد.", messages.SUCCESS)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ArticleImage)
class ArticleImageAdmin(admin.ModelAdmin):
    list_display = ("alt_text", "content_type", "size", "uploaded_by", "created_at")
    search_fields = ("alt_text",)
    readonly_fields = ("file", "content_type", "size", "alt_text", "uploaded_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD", "OPTIONS"}

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.unregister(get_user_model())


@admin.register(get_user_model())
class SiteUserAdmin(UserAdmin):
    inlines = (UserAccessProfileInline, AccountPreferenceInline)
    list_display = (
        "username",
        "access_role",
        "option_market_access",
        "economic_data_access",
        "articles_access",
        "is_active",
        "is_staff",
        "is_superuser",
    )
    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "access_profile__role",
        "option_preferences__show_option_market",
        "option_preferences__show_economic_data",
        "option_preferences__show_articles",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "access_profile",
            "option_preferences",
        )

    @admin.display(description="نقش")
    def access_role(self, obj):
        if obj.is_superuser:
            return "مدیر کل"
        profile = getattr(obj, "access_profile", None)
        return profile.get_role_display() if profile else "تعیین‌نشده"

    def _preference_access(self, obj, field):
        if obj.is_superuser:
            return True
        preference = getattr(obj, "option_preferences", None)
        return True if preference is None else bool(getattr(preference, field))

    @admin.display(boolean=True, description="بازار آپشن")
    def option_market_access(self, obj):
        return self._preference_access(obj, "show_option_market")

    @admin.display(boolean=True, description="داده‌های اقتصادی")
    def economic_data_access(self, obj):
        return self._preference_access(obj, "show_economic_data")

    @admin.display(boolean=True, description="مقالات")
    def articles_access(self, obj):
        return self._preference_access(obj, "show_articles")

    def _is_global_admin(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_module_permission(self, request):
        return self._is_global_admin(request)

    def has_view_permission(self, request, obj=None):
        return self._is_global_admin(request)

    def has_add_permission(self, request):
        return self._is_global_admin(request)

    def has_change_permission(self, request, obj=None):
        return self._is_global_admin(request)

    def has_delete_permission(self, request, obj=None):
        return self._is_global_admin(request)


@admin.register(TradeRecord)
class TradeRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "option_symbol", "strategy_type", "status", "updated_at")
    list_filter = ("status", "owner")
    search_fields = ("id", "payload")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="نماد اختیار")
    def option_symbol(self, obj):
        return obj.payload.get("option_symbol")

    @admin.display(description="استراتژی")
    def strategy_type(self, obj):
        return obj.payload.get("strategy_type")


@admin.register(UnderlyingPositionRecord)
class UnderlyingPositionRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "asset", "status", "updated_at")
    list_filter = ("status", "owner")
    search_fields = ("id", "payload")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="دارایی")
    def asset(self,obj):
        return obj.payload.get("asset")


admin.site.site_header = "مدیریت کل nicoption"
admin.site.site_title = "مدیریت nicoption"
admin.site.index_title = "کاربران و داده‌های سامانه"
