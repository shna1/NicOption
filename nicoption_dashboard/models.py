from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
import uuid

from .article_content import sanitize_article_html


class UserAccessProfile(models.Model):
    class Role(models.TextChoices):
        TRADER = "trader", "معامله‌گر"
        VIEWER = "viewer", "فقط‌خواندنی"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_profile",
    )
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.VIEWER,
        db_index=True,
    )
    phone_number = models.CharField(max_length=16, blank=True, default="")
    email_verified_at = models.DateTimeField(null=True, blank=True, default=timezone.now)
    verification_email_sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سطح دسترسی کاربر"
        verbose_name_plural = "سطوح دسترسی کاربران"

    def __str__(self) -> str:
        return f"{self.user.username} · {self.get_role_display()}"


class LoginAttempt(models.Model):
    class Scope(models.TextChoices):
        IDENTITY = "identity", "شناسه کاربری"
        IP = "ip", "نشانی شبکه"

    key_hash = models.CharField(max_length=64, unique=True)
    scope = models.CharField(max_length=16, choices=Scope.choices)
    failures = models.PositiveSmallIntegerField(default=0)
    window_started = models.DateTimeField()
    blocked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تلاش ورود"
        verbose_name_plural = "تلاش‌های ورود"

    def __str__(self) -> str:
        return f"{self.scope} · {self.failures}"


class TradeRecord(models.Model):
    class QuantityKind(models.TextChoices):
        CONTRACT = "contract", "قرارداد"
        UNIT = "unit", "واحد دارایی پایه"

    class CurrencyUnit(models.TextChoices):
        RIAL = "rial", "ریال"
        TOMAN = "toman", "تومان"

    id = models.CharField(max_length=32, primary_key=True)
    status = models.CharField(max_length=16, default="open", db_index=True)
    payload = models.JSONField(default=dict)
    quantity_kind = models.CharField(
        max_length=16,
        choices=QuantityKind.choices,
        null=True,
        blank=True,
        db_index=True,
    )
    contract_size = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
    )
    currency_unit = models.CharField(
        max_length=8,
        choices=CurrencyUnit.choices,
        null=True,
        blank=True,
    )
    calculation_version = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )
    mutation_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="option_trades",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "معامله"
        verbose_name_plural = "معاملات"

    def __str__(self) -> str:
        return str(self.payload.get("option_symbol") or self.id)


class TradeMutationRequest(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trade_mutation_requests",
    )
    operation = models.CharField(max_length=32)
    key_hash = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)
    trade_id = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "operation", "key_hash"),
                name="uniq_trade_mutation_key_per_owner",
            )
        ]
        indexes = [
            models.Index(
                fields=("owner", "created_at"),
                name="nicoption_d_owner_i_6e370b_idx",
            )
        ]


class AccountPreference(models.Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="option_preferences",
        null=True,
        blank=True,
    )
    initial_capital = models.DecimalField(
        max_digits=30,
        decimal_places=6,
        null=True,
        blank=True,
    )
    cash_balance = models.DecimalField(
        max_digits=30,
        decimal_places=6,
        null=True,
        blank=True,
    )
    show_overview = models.BooleanField(default=True)
    show_articles = models.BooleanField(default=True)
    show_option_market = models.BooleanField(default=True)
    show_economic_data = models.BooleanField(default=True)
    show_market = models.BooleanField(default=True)
    show_tehran_options = models.BooleanField(default=True)
    show_order_flow = models.BooleanField(default=True)
    show_commodity_exchange = models.BooleanField(default=True)
    show_trades = models.BooleanField(default=True)
    show_closed_trades = models.BooleanField(default=True)
    show_profit_recognition = models.BooleanField(default=True)
    show_calculator = models.BooleanField(default=True)
    show_settings = models.BooleanField(default=True)
    show_forecast = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیم حساب"
        verbose_name_plural = "تنظیمات حساب"

    def __str__(self) -> str:
        return f"تنظیمات {self.owner or 'داده قدیمی'}"


class Article(models.Model):
    title = models.CharField(max_length=180, verbose_name="عنوان")
    slug = models.SlugField(max_length=200, unique=True, allow_unicode=True, verbose_name="نشانی")
    summary = models.TextField(max_length=500, verbose_name="خلاصه")
    body = models.TextField(verbose_name="متن مقاله")
    is_published = models.BooleanField(default=False, db_index=True, verbose_name="منتشر شده")
    published_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="زمان انتشار")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nicoption_articles",
        verbose_name="نویسنده",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")

    class Meta:
        ordering = ("-published_at", "-created_at")
        verbose_name = "مقاله"
        verbose_name_plural = "مقالات"

    def clean(self):
        super().clean()
        self.body = sanitize_article_html(self.body)
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()

    def save(self, *args, **kwargs):
        self.body = sanitize_article_html(self.body)
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class XPostTranslation(models.Model):
    class TranslationStatus(models.TextChoices):
        PENDING = "pending", "در انتظار ترجمه"
        TRANSLATED = "translated", "ترجمه‌شده"
        FAILED = "failed", "خطای ترجمه"

    post_id = models.CharField(max_length=32, primary_key=True, verbose_name="شناسه پست X")
    username = models.CharField(max_length=64, db_index=True, verbose_name="نام کاربری")
    source_url = models.URLField(max_length=300, verbose_name="پیوند متن اصلی")
    original_text = models.TextField(verbose_name="متن اصلی")
    source_created_at = models.DateTimeField(db_index=True, verbose_name="زمان انتشار در X")
    raw_payload = models.JSONField(default=dict, blank=True, verbose_name="داده خام")
    translated_title = models.CharField(max_length=180, blank=True, verbose_name="عنوان ترجمه")
    translated_summary = models.CharField(max_length=500, blank=True, verbose_name="خلاصه ترجمه")
    translated_text = models.TextField(blank=True, verbose_name="ترجمه فارسی")
    review_note = models.TextField(blank=True, verbose_name="یادداشت بازبینی")
    needs_review = models.BooleanField(default=True, verbose_name="نیازمند بازبینی")
    translation_status = models.CharField(
        max_length=16,
        choices=TranslationStatus.choices,
        default=TranslationStatus.PENDING,
        db_index=True,
        verbose_name="وضعیت ترجمه",
    )
    translation_model = models.CharField(max_length=80, blank=True, verbose_name="مدل ترجمه")
    translation_attempts = models.PositiveSmallIntegerField(default=0, verbose_name="تعداد تلاش ترجمه")
    translation_error = models.TextField(blank=True, verbose_name="خطای ترجمه")
    translated_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان ترجمه")
    article = models.OneToOneField(
        Article,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="x_post_translation",
        verbose_name="مقاله",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان دریافت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")

    class Meta:
        ordering = ("-source_created_at", "-post_id")
        verbose_name = "ترجمه پست X"
        verbose_name_plural = "ترجمه پست‌های X"

    def __str__(self) -> str:
        return f"@{self.username} · {self.post_id}"


def article_image_upload_path(instance, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"articles/{instance.id}.{suffix}"


class ArticleImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to=article_image_upload_path, verbose_name="فایل")
    content_type = models.CharField(max_length=32, verbose_name="نوع فایل")
    size = models.PositiveIntegerField(verbose_name="حجم فایل")
    alt_text = models.CharField(max_length=180, verbose_name="متن جایگزین")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nicoption_article_images",
        verbose_name="بارگذار",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان بارگذاری")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "تصویر مقاله"
        verbose_name_plural = "تصاویر مقاله"

    def __str__(self) -> str:
        return self.alt_text


class UnderlyingPositionRecord(models.Model):
    class QuantityKind(models.TextChoices):
        UNIT = "unit", "واحد دارایی پایه"

    class CurrencyUnit(models.TextChoices):
        RIAL = "rial", "ریال"
        TOMAN = "toman", "تومان"

    id = models.CharField(max_length=32, primary_key=True)
    status = models.CharField(max_length=16, default="open", db_index=True)
    payload = models.JSONField(default=dict)
    quantity_kind = models.CharField(
        max_length=16,
        choices=QuantityKind.choices,
        null=True,
        blank=True,
        db_index=True,
    )
    currency_unit = models.CharField(
        max_length=8,
        choices=CurrencyUnit.choices,
        null=True,
        blank=True,
    )
    calculation_version = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="underlying_positions",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "دارایی پایه"
        verbose_name_plural = "دارایی‌های پایه"

    def __str__(self) -> str:
        return str(self.payload.get("asset") or self.id)


class EconomicIndicator(models.Model):
    class Kind(models.TextChoices):
        OFFICIAL = "official", "رسمی"
        ANALYTICAL = "analytical", "تحلیلی"

    class Category(models.TextChoices):
        MACRO = "macro", "اقتصاد کلان"
        FX = "fx", "ارز"
        CAPITAL_MARKET = "capital_market", "بازار سرمایه"
        COMMODITY = "commodity", "کالا"

    class Frequency(models.TextChoices):
        DAILY = "daily", "روزانه"
        MONTHLY = "monthly", "ماهانه"
        QUARTERLY = "quarterly", "فصلی"
        ANNUAL = "annual", "سالانه"

    code = models.CharField(max_length=64, unique=True)
    name_fa = models.CharField(max_length=160)
    name_en = models.CharField(max_length=160)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    category = models.CharField(max_length=32, choices=Category.choices)
    frequency = models.CharField(max_length=16, choices=Frequency.choices)
    unit = models.CharField(max_length=64, blank=True)
    definition = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    expected_release_lag_days = models.PositiveSmallIntegerField(default=0)
    stale_after_days = models.PositiveSmallIntegerField(default=45)
    free_history_years = models.PositiveSmallIntegerField(default=5)
    full_history_requires_subscription = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code",)
        verbose_name = "شاخص اقتصادی"
        verbose_name_plural = "شاخص‌های اقتصادی"

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values_list("code", flat=True).first()
            if original is not None and original != self.code:
                raise ValidationError({"code": "کد شاخص پس از ایجاد قابل تغییر نیست."})
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} · {self.name_fa}"


class DataSource(models.Model):
    class SourceType(models.TextChoices):
        OFFICIAL = "official", "رسمی"
        AGGREGATOR = "aggregator", "تجمیع‌کننده"
        INTERNAL = "internal", "داخلی"

    name = models.CharField(max_length=180, unique=True)
    organization = models.CharField(max_length=180, blank=True)
    homepage_url = models.URLField(blank=True)
    data_url = models.URLField(blank=True)
    source_type = models.CharField(max_length=16, choices=SourceType.choices)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    terms_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "منبع داده اقتصادی"
        verbose_name_plural = "منابع داده اقتصادی"

    def __str__(self) -> str:
        return self.name


class IndicatorSource(models.Model):
    indicator = models.ForeignKey(EconomicIndicator, on_delete=models.PROTECT, related_name="source_links")
    source = models.ForeignKey(DataSource, on_delete=models.PROTECT, related_name="indicator_links")
    priority = models.PositiveSmallIntegerField(default=100)
    is_primary = models.BooleanField(default=False)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("indicator", "priority", "source")
        constraints = [
            models.UniqueConstraint(fields=("indicator", "source", "valid_from"), name="uniq_indicator_source_period"),
            models.UniqueConstraint(
                fields=("indicator",),
                condition=Q(is_primary=True, valid_to__isnull=True),
                name="uniq_active_primary_source",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_from__isnull=True) | Q(valid_to__gte=models.F("valid_from")),
                name="indicator_source_valid_dates",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.indicator.code} · {self.source.name}"


class IngestionRun(models.Model):
    class Channel(models.TextChoices):
        GOOGLE_SHEETS = "google_sheets", "Google Sheets"
        CSV = "csv", "CSV"
        MANUAL = "manual", "دستی"
        API = "api", "API"

    class Status(models.TextChoices):
        RUNNING = "running", "در حال اجرا"
        SUCCESS = "success", "موفق"
        PARTIAL = "partial", "بخشی"
        FAILED = "failed", "ناموفق"
        DRY_RUN = "dry_run", "آزمایشی"

    channel = models.CharField(max_length=20, choices=Channel.choices)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING, db_index=True)
    rows_seen = models.PositiveIntegerField(default=0)
    rows_inserted = models.PositiveIntegerField(default=0)
    rows_revised = models.PositiveIntegerField(default=0)
    rows_unchanged = models.PositiveIntegerField(default=0)
    rows_rejected = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("channel", "status", "started_at"), name="econ_run_channel_status_idx")]

    def __str__(self) -> str:
        return f"{self.channel} · {self.status} · {self.started_at:%Y-%m-%d %H:%M}"


class IndicatorObservation(models.Model):
    class Status(models.TextChoices):
        PRELIMINARY = "preliminary", "مقدماتی"
        PUBLISHED = "published", "منتشرشده"
        REVISED = "revised", "تجدیدنظرشده"

    indicator = models.ForeignKey(EconomicIndicator, on_delete=models.PROTECT, related_name="observations")
    source = models.ForeignKey(DataSource, on_delete=models.PROTECT, related_name="observations")
    period_date = models.DateField()
    value = models.DecimalField(max_digits=38, decimal_places=12)
    unit = models.CharField(max_length=64)
    published_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField()
    revision = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PUBLISHED)
    source_url = models.URLField(blank=True)
    external_id = models.CharField(max_length=180, blank=True)
    content_hash = models.CharField(max_length=64)
    supersedes = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="superseded_by")
    is_current_revision = models.BooleanField(default=True, db_index=True)
    raw_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("indicator", "source", "period_date", "revision")
        constraints = [
            models.UniqueConstraint(fields=("indicator", "source", "period_date", "revision"), name="uniq_econ_observation_revision"),
            models.UniqueConstraint(
                fields=("indicator", "source", "period_date"),
                condition=Q(is_current_revision=True),
                name="uniq_current_econ_observation",
            ),
            models.CheckConstraint(condition=Q(revision__gte=0), name="econ_revision_nonnegative"),
        ]
        indexes = [
            models.Index(fields=("indicator", "source", "period_date"), name="econ_obs_series_idx"),
            models.Index(fields=("indicator", "is_current_revision", "period_date"), name="econ_obs_current_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.indicator.code} · {self.period_date} · r{self.revision}"


class DataIssue(models.Model):
    class Severity(models.TextChoices):
        WARNING = "warning", "هشدار"
        ERROR = "error", "خطا"
        CRITICAL = "critical", "بحرانی"

    ingestion_run = models.ForeignKey(IngestionRun, on_delete=models.PROTECT, related_name="issues", null=True, blank=True)
    indicator = models.ForeignKey(EconomicIndicator, on_delete=models.PROTECT, null=True, blank=True)
    source = models.ForeignKey(DataSource, on_delete=models.PROTECT, null=True, blank=True)
    row_number = models.PositiveIntegerField(null=True, blank=True)
    external_row_id = models.CharField(max_length=180, blank=True)
    severity = models.CharField(max_length=12, choices=Severity.choices)
    issue_code = models.CharField(max_length=64, db_index=True)
    message = models.CharField(max_length=500)
    safe_payload = models.JSONField(default=dict, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("resolved_at", "severity", "created_at"), name="econ_issue_open_idx")]


class IndicatorRelease(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "برنامه‌ریزی‌شده"
        PUBLISHED = "published", "منتشرشده"
        DELAYED = "delayed", "به‌تعویق‌افتاده"
        CANCELLED = "cancelled", "لغوشده"

    indicator = models.ForeignKey(EconomicIndicator, on_delete=models.PROTECT, related_name="releases")
    expected_at = models.DateTimeField()
    period_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
    published_at = models.DateTimeField(null=True, blank=True)
    source = models.ForeignKey(DataSource, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("expected_at",)
        constraints = [models.UniqueConstraint(fields=("indicator", "source", "period_date"), name="uniq_econ_release_period")]
        indexes = [models.Index(fields=("status", "expected_at"), name="econ_release_status_idx")]


class CentralBankSnapshot(models.Model):
    """A durable, point-in-time result of the read-only cbi-mcp tools."""

    collected_at = models.DateTimeField(default=timezone.now, db_index=True)
    server_name = models.CharField(max_length=80, default="cbi-mcp")
    server_version = models.CharField(max_length=32, blank=True)
    payload = models.JSONField(default=dict)
    errors = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-collected_at", "-pk")
        verbose_name = "تصویر داده بانک مرکزی"
        verbose_name_plural = "تصاویر داده بانک مرکزی"

    def __str__(self) -> str:
        return f"{self.server_name} · {self.collected_at:%Y-%m-%d %H:%M}"


class StatisticalCenterSnapshot(models.Model):
    """A durable, point-in-time result of the read-only amar-mcp tools."""

    collected_at = models.DateTimeField(default=timezone.now, db_index=True)
    server_name = models.CharField(max_length=80, default="amar-mcp")
    server_version = models.CharField(max_length=32, blank=True)
    payload = models.JSONField(default=dict)
    errors = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-collected_at", "-pk")
        verbose_name = "تصویر گسترده مرکز آمار"
        verbose_name_plural = "تصاویر گسترده مرکز آمار"

    def __str__(self) -> str:
        return f"{self.server_name} · {self.collected_at:%Y-%m-%d %H:%M}"
