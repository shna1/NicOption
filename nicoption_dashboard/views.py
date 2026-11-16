from __future__ import annotations

import json
import logging
import hashlib
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from bambo_bot.dates import format_jalali_date, parse_user_date
from bambo_bot.trades import (
    quote_key, validate_underlying_link, validate_underlying_position_change,
    prepare_underlying_payload, resolve_trade_quote, trade_underlying_units,
)
from bambo_bot.web import calculate_custom_covered_call

from .services import get_runtime
from .economic_api import economic_indicators_payload
from .monetary_data import MonetaryDataError, monetary_payload
from .central_bank_data import central_bank_snapshot_payload
from .amar_data import AmarSnapshotError, amar_comparison_catalog, amar_snapshot_payload
from .statistical_center_data import (
    StatisticalCenterDataError,
    statistical_center_catalog,
    statistical_center_comparison_catalog,
    statistical_center_series,
)
from .feature_access import page_feature, user_has_feature
from .article_content import sanitize_article_html
from .models import Article, ArticleImage, TradeMutationRequest, TradeRecord, UnderlyingPositionRecord
from .email_verification import email_verification_token, is_email_verified


LOGGER = logging.getLogger(__name__)


def truthy(value) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "on", "yes"}


def require_price_confirmation(payload: dict) -> None:
    if not truthy(payload.get("price_confirmed")):
        raise ValueError("پیش از ثبت، قیمت پیشنهادی بازار را بررسی و تأیید کنید")


def confirmed_trade_prices(payload: dict, quote: dict, generated_at: str) -> dict:
    require_price_confirmation(payload)
    enriched = dict(payload)
    enriched.update({
        "suggested_base_price": quote.get("base_last"),
        "suggested_option_price": quote.get("option_last"),
        "suggested_price_fetched_at": generated_at,
        "confirmed_base_price": payload.get("entry_base_price"),
        "confirmed_option_price": payload.get("entry_premium"),
        "price_confirmed_at": datetime.now().astimezone().isoformat(),
    })
    return enriched


def confirmed_underlying_price(payload: dict, runtime) -> dict:
    require_price_confirmation(payload)
    enriched = dict(payload)
    dashboard = runtime.cache.get()
    quotes = runtime.cache.trade_quotes()
    from bambo_bot.trades import build_underlying_quote_map, underlying_quote_key
    base_quotes = build_underlying_quote_map(quotes)
    quote = base_quotes.get(
        underlying_quote_key(enriched.get("market"), enriched.get("asset"))
    ) or {}
    enriched.update({
        "suggested_price": quote.get("last"),
        "suggested_price_fetched_at": dashboard.get("generated_at"),
        "confirmed_price": enriched.get("entry_price"),
        "price_confirmed_at": datetime.now().astimezone().isoformat(),
    })
    return enriched


def json_response(payload: dict, status: int = 200) -> JsonResponse:
    response = JsonResponse(
        payload,
        status=status,
        json_dumps_params={"ensure_ascii": False, "separators": (",", ":")},
    )
    response["Cache-Control"] = "no-store"
    return response


def read_json(request: HttpRequest) -> dict:
    if not request.body or len(request.body) > 65536:
        raise ValueError("حجم درخواست معتبر نیست")
    # Preserve monetary decimal lexemes until domain validation captures them.
    # Integers remain Python ints; decimal/exponent JSON numbers remain exact
    # text and are validated explicitly by the financial boundary.
    payload = json.loads(request.body.decode("utf-8"), parse_float=str)
    if not isinstance(payload, dict):
        raise ValueError("ساختار درخواست معتبر نیست")
    return payload


def _mutation_fingerprint(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _idempotency_hash(request: HttpRequest) -> str | None:
    key = str(request.headers.get("Idempotency-Key") or "").strip()
    if not key:
        return None
    if len(key) > 200:
        raise ValueError("کلید تکرارپذیری درخواست معتبر نیست")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def error_response(exc: Exception, *, operation: str) -> JsonResponse:
    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return json_response({"error": str(exc)}, 400)
    if isinstance(exc, KeyError):
        return json_response({"error": str(exc).strip("'")}, 404)
    LOGGER.exception("%s failed", operation)
    return json_response({"error": f"{operation} ناموفق بود"}, 502)


def personal_api_login_required(view_func):
    @wraps(view_func)
    def wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_response(
                {"error": "برای دسترسی به اطلاعات حساب وارد شوید"},
                403,
            )
        return view_func(request, *args, **kwargs)

    return wrapped


@never_cache
@require_GET
def landing_page(request: HttpRequest) -> HttpResponse:
    path = Path(django_settings.WEB_STATIC_DIR) / "landing.html"
    try:
        response = HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")
    except FileNotFoundError:
        return json_response({"error": "صفحه معرفی موجود نیست"}, 404)
    response["Cache-Control"] = "no-store"
    return response


@never_cache
@require_GET
def about_page(request: HttpRequest) -> HttpResponse:
    path = Path(django_settings.WEB_STATIC_DIR) / "about.html"
    try:
        response = HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")
    except FileNotFoundError:
        return json_response({"error": "صفحه درباره ما موجود نیست"}, 404)
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def robots_txt(request: HttpRequest) -> HttpResponse:
    private_paths = (
        "/admin/",
        "/api/",
        "/dashboard",
        "/index.html",
        "/articles",
        "/login",
        "/signup",
        "/health",
        "/ready",
        "/opportunities",
        "/market",
        "/tehran-options",
        "/commodity-exchange",
        "/order-flow",
        "/trades",
        "/profit-recognition",
        "/performance",
        "/closed-trades",
        "/calculator",
        "/methodology",
        "/settings",
        "/forecast",
        "/economic-indicators",
        "/economic-comparison",
        "/statistical-center",
        "/central-bank",
        "/monetary-details",
    )
    lines = ["User-agent: *", *(f"Disallow: {path}" for path in private_paths)]
    lines.extend(("", f"Sitemap: {django_settings.PUBLIC_SITE_ORIGIN}/sitemap.xml", ""))
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
def sitemap_xml(request: HttpRequest) -> HttpResponse:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        f"    <loc>{django_settings.PUBLIC_SITE_ORIGIN}/</loc>\n"
        "  </url>\n"
        "  <url>\n"
        f"    <loc>{django_settings.PUBLIC_SITE_ORIGIN}/about</loc>\n"
        "  </url>\n"
        "</urlset>\n"
    )
    return HttpResponse(xml, content_type="application/xml; charset=utf-8")


@never_cache
@require_GET
def login_page(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("overview")
    path = Path(django_settings.WEB_STATIC_DIR) / "login.html"
    try:
        response = HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response
    except FileNotFoundError:
        return json_response({"error": "صفحه ورود موجود نیست"}, 404)


@never_cache
@require_GET
def signup_page(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("overview")
    path = Path(django_settings.WEB_STATIC_DIR) / "signup.html"
    try:
        response = HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response
    except FileNotFoundError:
        return json_response({"error": "صفحه ثبت‌نام موجود نیست"}, 404)


@never_cache
@require_GET
def verify_email_page(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"{reverse('login-page')}?{query}")
    if is_email_verified(request.user):
        return redirect("overview")
    path = Path(django_settings.WEB_STATIC_DIR) / "verify-email.html"
    try:
        response = HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response
    except FileNotFoundError:
        return json_response({"error": "صفحه تأیید ایمیل موجود نیست"}, 404)


@never_cache
@require_GET
def verify_email_confirm(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = get_user_model().objects.select_related("access_profile").get(pk=user_id)
    except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
        user = None

    if user is None or not email_verification_token.check_token(user, token):
        return redirect(f"{reverse('login-page')}?verification=invalid")

    profile = user.access_profile
    profile.email_verified_at = timezone.now()
    profile.save(update_fields=("email_verified_at", "updated_at"))
    if request.user.is_authenticated and request.user.pk == user.pk:
        return redirect("overview")
    return redirect(f"{reverse('login-page')}?verification=success")


@never_cache
def not_found_page(request: HttpRequest, exception=None) -> HttpResponse:
    if request.path.startswith("/api/"):
        return json_response({"error": "مسیر درخواستی پیدا نشد"}, 404)

    path = Path(django_settings.WEB_STATIC_DIR) / "404.html"
    try:
        response = HttpResponse(
            path.read_bytes(),
            content_type="text/html; charset=utf-8",
            status=404,
        )
    except FileNotFoundError:
        response = HttpResponse(
            "صفحه موردنظر پیدا نشد.",
            content_type="text/plain; charset=utf-8",
            status=404,
        )
    response["Cache-Control"] = "no-store"
    return response


@ensure_csrf_cookie
@never_cache
@require_GET
def dashboard_page(
    request: HttpRequest,
    trade_id: str | None = None,
    article_slug: str | None = None,
) -> HttpResponse:
    if not request.user.is_authenticated:
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"{reverse('login-page')}?{query}")
    required_feature = page_feature(request.path)
    if required_feature and not user_has_feature(request.user, required_feature):
        return json_response(
            {"error": "این بخش در تنظیمات حساب شما غیرفعال است"},
            403,
        )
    path = Path(django_settings.WEB_STATIC_DIR) / "index.html"
    try:
        response = HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")
    except FileNotFoundError:
        return json_response({"error": "فایل رابط کاربری موجود نیست"}, 404)
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@never_cache
@require_GET
@personal_api_login_required
def api_articles(request: HttpRequest) -> JsonResponse:
    if not user_has_feature(request.user, "articles"):
        return json_response({"error": "این بخش در تنظیمات حساب شما غیرفعال است"}, 403)
    try:
        limit = min(50, max(1, int(request.GET.get("limit", "20"))))
    except ValueError:
        return json_response({"error": "تعداد مقاله معتبر نیست"}, 400)
    articles = Article.objects.filter(
        is_published=True,
        published_at__isnull=False,
        published_at__lte=timezone.now(),
    ).select_related("author", "x_post_translation")[:limit]
    return json_response({
        "articles": [
            {
                "title": article.title,
                "slug": article.slug,
                "summary": article.summary,
                "body": sanitize_article_html(article.body),
                "published_at": article.published_at.isoformat(),
                "published_at_display": format_jalali_date(timezone.localtime(article.published_at).date()),
                "author": article.author.get_full_name() or article.author.username if article.author else "تحریریه nicoption",
                "source": (
                    {
                        "kind": "x",
                        "label": f"@{article.x_post_translation.username}",
                        "url": article.x_post_translation.source_url,
                        "original_text": article.x_post_translation.original_text,
                        "created_at": article.x_post_translation.source_created_at.isoformat(),
                        "translation_notice": "ترجمه فارسی با هوش مصنوعی و نظارت تحریریه",
                    }
                    if hasattr(article, "x_post_translation")
                    else None
                ),
            }
            for article in articles
        ]
    })


@never_cache
@require_GET
@personal_api_login_required
def article_media(request: HttpRequest, image_id) -> FileResponse:
    if not user_has_feature(request.user, "articles"):
        raise Http404
    try:
        image = ArticleImage.objects.get(pk=image_id)
        file_handle = image.file.open("rb")
    except (ArticleImage.DoesNotExist, FileNotFoundError, OSError, ValueError):
        raise Http404 from None
    response = FileResponse(file_handle, content_type=image.content_type)
    response["Content-Length"] = str(image.size)
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    return json_response({"ok": True, "framework": "django"})


@require_GET
def readiness(request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        LOGGER.exception("Database readiness check failed")
        return json_response(
            {"ok": False, "database": "unavailable"},
            503,
        )
    return json_response({"ok": True, "database": "available"})


@require_GET
@personal_api_login_required
def api_data(request: HttpRequest) -> JsonResponse:
    try:
        return json_response(get_runtime().cache.get(force=request.GET.get("refresh") == "1"))
    except Exception as exc:
        return error_response(exc, operation="دریافت اطلاعات بازار")


@require_GET
@personal_api_login_required
def api_history(request: HttpRequest) -> JsonResponse:
    asset = request.GET.get("asset", "").strip()
    source_asset = request.GET.get("source_asset", "").strip()
    if not asset:
        return json_response({"error": "نام دارایی مشخص نشده است"}, 400)
    try:
        return json_response(get_runtime().history.fetch(asset, source_asset))
    except Exception as exc:
        return error_response(exc, operation="دریافت تاریخچه قیمت")


@require_GET
@personal_api_login_required
def api_forecast(request: HttpRequest) -> JsonResponse:
    try:
        return json_response(
            get_runtime().forecast.get(force=request.GET.get("refresh") == "1")
        )
    except Exception as exc:
        return error_response(exc, operation="دریافت پیش‌بینی")


@require_GET
@personal_api_login_required
def api_economic_indicators(request: HttpRequest) -> JsonResponse:
    """Return persisted, provenance-aware observations without reading upstreams."""
    if not user_has_feature(request.user, "economic_data"):
        return json_response({"error": "این بخش در تنظیمات حساب شما غیرفعال است"}, 403)
    if request.GET.get("range") == "all":
        return json_response({
            "error": "دسترسی به کل تاریخچه نیازمند اشتراک است",
            "code": "full_history_subscription_required",
            "access": {"full_history_granted": False, "free_history_years": 5},
        }, 403)
    return json_response(economic_indicators_payload())


@require_GET
@personal_api_login_required
def api_monetary_indicators(request: HttpRequest) -> JsonResponse:
    if not user_has_feature(request.user, "economic_data"):
        return json_response({"error": "دسترسی به داده‌های اقتصادی برای این حساب فعال نیست"}, 403)
    try:
        return json_response(monetary_payload(request.GET.get("scope", "main")))
    except MonetaryDataError as exc:
        return json_response({"error": str(exc)}, 422)


@require_GET
@personal_api_login_required
def api_central_bank_snapshot(request: HttpRequest) -> JsonResponse:
    if not user_has_feature(request.user, "economic_data"):
        return json_response({"error": "دسترسی به داده‌های اقتصادی برای این حساب فعال نیست"}, 403)
    return json_response(central_bank_snapshot_payload())


@require_GET
@personal_api_login_required
def api_amar_statistics(request: HttpRequest) -> JsonResponse:
    if not user_has_feature(request.user, "economic_data"):
        return json_response({"error": "دسترسی به داده‌های اقتصادی برای این حساب فعال نیست"}, 403)
    topic = str(request.GET.get("topic") or "").strip()
    if len(topic) > 40:
        return json_response({"error": "شناسه موضوع آماری معتبر نیست"}, 400)
    try:
        return json_response(amar_snapshot_payload(topic=topic))
    except AmarSnapshotError as exc:
        return json_response({"error": str(exc)}, 404)


@require_GET
@personal_api_login_required
def api_economic_comparison_indicators(request: HttpRequest) -> JsonResponse:
    """Unify every comparison-capable catalog while keeping SCI series lazy."""
    if not user_has_feature(request.user, "economic_data"):
        return json_response({"error": "دسترسی به داده‌های اقتصادی برای این حساب فعال نیست"}, 403)
    try:
        economic = economic_indicators_payload()
        monetary = monetary_payload("all")
        statistical = statistical_center_comparison_catalog()
    except (MonetaryDataError, StatisticalCenterDataError) as exc:
        return json_response({"error": str(exc)}, 422)

    primary_economic_codes = {
        "IR-INF", "IR-INF_MOM", "IR_CPI", "IR_M2", "IR_M2_MOM_GROWTH",
        "IR_MONETARY_BASE", "IR_USD_FREE_MARKET", "IR_GOLD_18K", "IR_TEDPIX",
    }
    indicators = [
        {
            **item,
            "comparison_source": "economic",
            "comparison_source_label": item.get("source", {}).get("organization") or "بازار و شاخص‌های منتخب",
            "is_primary": item.get("code") in primary_economic_codes,
        }
        for item in economic["indicators"]
    ]
    indicators.extend({
        "code": f"CBI:{item['technical_id']}",
        "name_fa": item["title_fa"],
        "name_en": "",
        "kind": "official",
        "category": "macro",
        "frequency": "monthly",
        "unit": item.get("unit") or "—",
        "classification": item.get("classification") or "",
        "economic_group": item.get("economic_group") or "",
        "comparison_source": "central_bank",
        "comparison_source_label": "بانک مرکزی",
        "is_primary": item.get("classification") == "اصلی",
        "current": item.get("current") or {},
        "source": {"name": "بانک مرکزی", "organization": "بانک مرکزی"},
        "series": [
            {
                "period_date": point.get("date"),
                "period_date_jalali": point.get("jalali_date"),
                "value": point.get("value"),
            }
            for point in item.get("series", [])
            if point.get("date") and point.get("value") is not None
        ],
    } for item in monetary["indicators"])
    indicators.extend({
        "code": f"SCI:{item['series_key']}",
        "name_fa": item.get("display_title_fa") or item.get("title_fa") or item["technical_id"],
        "name_en": "",
        "kind": "official",
        "category": "macro",
        "frequency": item.get("frequency") or "",
        "unit": item.get("unit") or "—",
        "classification": item.get("classification") or "",
        "lifecycle": item.get("lifecycle") or "",
        "economic_group": item.get("economic_group") or "",
        "comparison_source": "statistical_center",
        "comparison_source_label": "مرکز آمار ایران",
        "comparison_series_key": item["series_key"],
        "is_primary": item.get("classification") == "اصلی",
        "current": {"value": item.get("latest")},
        "source": {"name": "مرکز آمار ایران", "organization": "مرکز آمار ایران"},
        "series": [],
    } for item in statistical)
    indicators.extend(amar_comparison_catalog())
    indicators.sort(key=lambda item: (
        not item.get("is_primary", False),
        {"economic": 0, "central_bank": 1, "amar_mcp": 2, "statistical_center": 3}.get(item.get("comparison_source"), 9),
        item.get("name_fa") or "",
        item.get("code") or "",
    ))
    return json_response({
        "generated_at": max(economic["generated_at"], monetary["generated_at"]),
        "indicators": indicators,
        "summary": {
            "total": len(indicators),
            "primary": sum(bool(item.get("is_primary")) for item in indicators),
            "economic": len(economic["indicators"]),
            "central_bank": len(monetary["indicators"]),
            "statistical_center": len(statistical),
            "amar_mcp": len([item for item in indicators if item.get("comparison_source") == "amar_mcp"]),
        },
    })


@require_GET
@personal_api_login_required
def api_statistical_center_indicators(request: HttpRequest) -> JsonResponse:
    if not user_has_feature(request.user, "economic_data"):
        return json_response({"error": "دسترسی به داده‌های اقتصادی برای این حساب فعال نیست"}, 403)
    try:
        payload = statistical_center_catalog(request.GET)
        payload["amar_mcp_series"] = amar_comparison_catalog()
        return json_response(payload)
    except StatisticalCenterDataError as exc:
        return json_response({"error": str(exc)}, 422)


@require_GET
@personal_api_login_required
def api_statistical_center_series(request: HttpRequest) -> JsonResponse:
    if not user_has_feature(request.user, "economic_data"):
        return json_response({"error": "دسترسی به داده‌های اقتصادی برای این حساب فعال نیست"}, 403)
    series_key = str(request.GET.get("series_key") or "").strip()
    if not series_key or len(series_key) > 220:
        return json_response({"error": "شناسه سری مرکز آمار معتبر نیست"}, 400)
    try:
        return json_response(statistical_center_series(series_key))
    except KeyError as exc:
        return json_response({"error": str(exc).strip("'")}, 404)
    except StatisticalCenterDataError as exc:
        return json_response({"error": str(exc)}, 422)


@require_GET
@personal_api_login_required
def api_commodity_fx(request: HttpRequest) -> JsonResponse:
    if not user_has_feature(request.user, "commodity_exchange"):
        return json_response({"error": "این بخش در تنظیمات حساب شما غیرفعال است"}, 403)
    try:
        return json_response(
            get_runtime().commodity_fx.get(force=request.GET.get("refresh") == "1")
        )
    except Exception as exc:
        return error_response(exc, operation="دریافت دلار ضمنی بورس کالا")


@require_GET
@personal_api_login_required
def api_order_book_catalog(request: HttpRequest) -> JsonResponse:
    if not user_has_feature(request.user, "order_flow"):
        return json_response({"error": "این بخش در تنظیمات حساب شما غیرفعال است"}, 403)
    try:
        return json_response(get_runtime().cache.order_flow_catalog())
    except Exception as exc:
        return error_response(exc, operation="دریافت فهرست جریان سفارش‌ها")


@require_GET
@personal_api_login_required
def api_order_book(request: HttpRequest) -> JsonResponse:
    if not user_has_feature(request.user, "order_flow"):
        return json_response({"error": "این بخش در تنظیمات حساب شما غیرفعال است"}, 403)
    market = request.GET.get("market", "tehran")
    instrument_type = request.GET.get("instrument_type", "option")
    symbol = request.GET.get("symbol", "").strip()
    if market not in {"tehran", "goods"} or instrument_type not in {"option", "base"} or not symbol:
        return json_response({"error": "بازار، نوع نماد یا نام نماد معتبر نیست"}, 400)
    try:
        return json_response(get_runtime().cache.order_flow(
            market=market, instrument_type=instrument_type, symbol=symbol,
            force=request.GET.get("refresh") == "1",
        ))
    except KeyError as exc:
        return json_response({"error": str(exc).strip("'")}, 404)
    except Exception as exc:
        return error_response(exc, operation="دریافت عمق سفارش‌ها")


@require_POST
@personal_api_login_required
def api_covered_score(request: HttpRequest) -> JsonResponse:
    try:
        payload = read_json(request)
        market = str(payload.get("market") or "tehran")
        if market not in {"tehran", "goods"}:
            raise ValueError("بازار معتبر نیست")
        runtime = get_runtime()
        dashboard = runtime.cache.get()
        values = [
            item["transaction_value"]
            for group in dashboard["covered_call"]
            if group["market"] == market
            for item in group["items"]
        ]
        return json_response(calculate_custom_covered_call(
            payload, values, runtime.settings.long_underlying_interest_rate
        ))
    except Exception as exc:
        return error_response(exc, operation="محاسبه امتیاز کاوردکال")


@require_POST
@personal_api_login_required
def api_account(request: HttpRequest) -> JsonResponse:
    try:
        payload = read_json(request)
        runtime = get_runtime(request.user.pk)
        runtime.account.save(
            payload.get("initial_capital"), payload.get("cash_balance")
        )
        return json_response(runtime.trade_payload())
    except Exception as exc:
        return error_response(exc, operation="ثبت سرمایه اولیه")


@require_http_methods(["GET", "POST"])
@personal_api_login_required
def api_trades(request: HttpRequest) -> JsonResponse:
    runtime = get_runtime(request.user.pk)
    try:
        if request.method == "POST":
            payload = read_json(request)
            payload.update({
                "quantity_kind": "contract",
                "currency_unit": "rial",
                "calculation_version": 8,
            })
            key_hash = _idempotency_hash(request)
            request_hash = _mutation_fingerprint(payload)
            dashboard = runtime.cache.get()
            live_quote = runtime.cache.trade_quotes().get(
                quote_key(payload.get("market"), payload.get("option_symbol"))
            )
            quote = resolve_trade_quote(payload, live_quote)
            payload["option_symbol"] = quote.get("symbol") or payload.get("option_symbol")
            payload = confirmed_trade_prices(payload, quote, dashboard["generated_at"])
            with transaction.atomic():
                get_user_model().objects.select_for_update().only("pk").get(
                    pk=request.user.pk
                )
                if key_hash:
                    previous = TradeMutationRequest.objects.filter(
                        owner_id=request.user.pk,
                        operation="trade.create",
                        key_hash=key_hash,
                    ).first()
                    if previous:
                        if previous.request_hash != request_hash:
                            return json_response({
                                "error": "این کلید تکرارپذیری قبلاً برای درخواست دیگری استفاده شده است"
                            }, 409)
                        return json_response(runtime.trade_payload(), 200)
                if (
                    payload.get("strategy_type", "covered_call") == "covered_call"
                    and payload.get("underlying_source_mode") == "new"
                ):
                    position = runtime.underlyings.create({
                        "market": payload.get("market"),
                        "asset": payload.get("asset") or quote.get("asset"),
                        "acquisition_method": "direct",
                        "entry_date": payload.get("entry_date"),
                        "entry_price": payload.get("entry_base_price"),
                        "quantity": trade_underlying_units(
                            payload, contract_size=quote.get("contract_size", 1)
                        ),
                        "quantity_kind": "unit",
                        "currency_unit": "rial",
                        "calculation_version": 8,
                        "commission": payload.get("underlying_purchase_commission"),
                        "commission_source": payload.get(
                            "underlying_purchase_commission_source"
                        ),
                        "suggested_price": quote.get("base_last"),
                        "suggested_price_fetched_at": dashboard["generated_at"],
                        "confirmed_price": payload.get("entry_base_price"),
                        "price_confirmed_at": payload.get("price_confirmed_at"),
                    })
                    payload["underlying_position_id"] = position["id"]
                validate_underlying_link(payload,runtime.underlyings.list(),runtime.trades.list(),quote)
                created_trade = runtime.trades.create(payload, quote)
                if key_hash:
                    TradeMutationRequest.objects.create(
                        owner_id=request.user.pk,
                        operation="trade.create",
                        key_hash=key_hash,
                        request_hash=request_hash,
                        trade_id=str(created_trade["id"]),
                    )
            return json_response(runtime.trade_payload(), 201)
        covered_option_basis = request.GET.get("covered_option_basis", "last")
        covered_base_basis = request.GET.get("covered_base_basis", "last")
        long_option_basis = request.GET.get("long_option_basis", "last")
        long_base_basis = request.GET.get("long_base_basis", "last")
        return json_response(runtime.trade_payload(
            covered_option_basis=(covered_option_basis if covered_option_basis in {"last", "bid", "ask"} else "last"),
            covered_base_basis=(covered_base_basis if covered_base_basis in {"last", "bid", "ask"} else "last"),
            long_option_basis=(long_option_basis if long_option_basis in {"last", "bid", "ask"} else "last"),
            long_base_basis=(long_base_basis if long_base_basis in {"last", "bid", "ask"} else "last"),
        ))
    except Exception as exc:
        return error_response(exc, operation="دریافت یا ثبت معاملات")


@require_POST
@personal_api_login_required
def api_trades_bulk_delete(request: HttpRequest) -> JsonResponse:
    try:
        payload = read_json(request)
        raw_ids = payload.get("ids")
        trade_status = str(payload.get("status") or "").strip()
        if trade_status not in {"open", "closed"}:
            raise ValueError("وضعیت معاملات برای حذف گروهی معتبر نیست")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValueError("حداقل یک معامله را برای حذف انتخاب کنید")
        if len(raw_ids) > 500:
            raise ValueError("در هر مرحله حداکثر ۵۰۰ معامله قابل حذف است")
        ids = list(dict.fromkeys(str(item or "").strip() for item in raw_ids))
        if any(not item or len(item) > 32 for item in ids):
            raise ValueError("شناسه یکی از معاملات معتبر نیست")
        queryset = TradeRecord.objects.filter(
            owner_id=request.user.pk,
            id__in=ids,
            status="closed" if trade_status == "closed" else "open",
        )
        with transaction.atomic():
            deleted = queryset.count()
            queryset.delete()
        return json_response({"bulk_deleted": deleted})
    except Exception as exc:
        return error_response(exc, operation="حذف گروهی معاملات")


@require_POST
@personal_api_login_required
def api_underlyings_bulk_delete(request: HttpRequest) -> JsonResponse:
    try:
        payload = read_json(request)
        raw_ids = payload.get("ids")
        position_status = str(payload.get("status") or "").strip()
        if position_status not in {"open", "closed"}:
            raise ValueError("وضعیت دارایی‌های پایه برای حذف گروهی معتبر نیست")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValueError("حداقل یک دارایی پایه را برای حذف انتخاب کنید")
        if len(raw_ids) > 500:
            raise ValueError("در هر مرحله حداکثر ۵۰۰ دارایی پایه قابل حذف است")
        ids = list(dict.fromkeys(str(item or "").strip() for item in raw_ids))
        if any(not item or len(item) > 32 for item in ids):
            raise ValueError("شناسه یکی از دارایی‌های پایه معتبر نیست")

        runtime = get_runtime(request.user.pk)
        positions = runtime.underlyings.list()
        matching = [
            item for item in positions
            if str(item.get("id") or "") in ids
            and ("closed" if item.get("status") == "closed" else "open") == position_status
        ]
        trades = runtime.trades.list()
        for item in matching:
            validate_underlying_position_change(
                str(item.get("id")), None, positions, trades, deleting=True,
            )
        matching_ids = [str(item.get("id")) for item in matching]
        with transaction.atomic():
            deleted, _ = UnderlyingPositionRecord.objects.filter(
                owner_id=request.user.pk,
                id__in=matching_ids,
                status=position_status,
            ).delete()
        return json_response({"bulk_deleted": deleted})
    except Exception as exc:
        return error_response(exc, operation="حذف گروهی دارایی‌های پایه")


@require_http_methods(["PUT", "DELETE"])
@personal_api_login_required
def api_trade_detail(request: HttpRequest, trade_id: str) -> JsonResponse:
    runtime = get_runtime(request.user.pk)
    try:
        if request.method == "DELETE":
            runtime.trades.delete(trade_id)
            return json_response(runtime.trade_payload())
        payload = read_json(request)
        existing = next(
            (item for item in runtime.trades.list() if item.get("id") == trade_id),
            None,
        )
        if existing is None:
            raise KeyError("معامله پیدا نشد")
        for key in ("quantity_kind", "currency_unit", "calculation_version"):
            if key in existing:
                payload[key] = existing[key]
        dashboard = runtime.cache.get()
        live_quote = runtime.cache.trade_quotes().get(
            quote_key(payload.get("market"), payload.get("option_symbol"))
        )
        quote = resolve_trade_quote(payload, live_quote)
        payload["option_symbol"] = quote.get("symbol") or payload.get("option_symbol")
        payload = confirmed_trade_prices(payload, quote, dashboard["generated_at"])
        validate_underlying_link(payload,runtime.underlyings.list(),runtime.trades.list(),quote,editing_trade_id=trade_id)
        runtime.trades.update(trade_id, payload, quote)
        return json_response(runtime.trade_payload())
    except Exception as exc:
        return error_response(exc, operation="ویرایش یا حذف معامله")


@require_POST
@personal_api_login_required
def api_trade_close(request: HttpRequest, trade_id: str) -> JsonResponse:
    runtime = get_runtime(request.user.pk)
    try:
        payload = read_json(request)
        current = next(
            (item for item in runtime.trades.list() if item.get("id") == trade_id), None
        )
        if not current:
            raise KeyError("معامله پیدا نشد")
        dashboard = runtime.cache.get()
        as_of = datetime.fromisoformat(dashboard["generated_at"]).date()
        quote = runtime.cache.trade_quotes().get(
            quote_key(current.get("market"), current.get("option_symbol"))
        )
        confirmation = payload.get("price_confirmed")
        was_closed=current.get("status")=="closed"
        closed_trade=runtime.trades.close(
            trade_id,
            quote,
            exit_date=parse_user_date(
                str(payload.get("exit_date") or format_jalali_date(as_of))
            ),
            exit_method=payload.get("exit_method", current.get("exit_method", "offset")),
            exit_base_price=payload.get("exit_base_price"),
            exit_option_price=payload.get("exit_option_price"),
            exit_commission=payload.get("exit_commission"),
            exit_commission_source=payload.get("exit_commission_source"),
            exit_note=payload.get("exit_note", ""),
            price_confirmed=(
                confirmation is True
                or str(confirmation).strip().lower() in {"1", "true", "on"}
            ),
            close_quantity=payload.get("close_quantity"),
            close_exercise_quantity=payload.get("close_exercise_quantity"),
            close_premium_trade_quantity=payload.get("close_premium_trade_quantity"),
            underlying_disposition=payload.get("underlying_disposition","sell"),
            expected_version=payload.get("mutation_version"),
        )
        if not was_closed:
            if closed_trade.get("strategy_type")=="long_call" and closed_trade.get("exit_method") in {"exercise","mixed"}:
                runtime.underlyings.create_from_exercise(closed_trade)
            elif closed_trade.get("strategy_type")=="covered_call" and closed_trade.get("underlying_position_id") and closed_trade.get("underlying_disposition")=="sell":
                units=trade_underlying_units(closed_trade)
                sale_price=float(closed_trade.get("strike") if closed_trade.get("exit_method")=="exercise" else closed_trade.get("exit_base_price"))
                runtime.underlyings.sell_quantity(
                    closed_trade["underlying_position_id"], units,
                    exit_date=parse_user_date(str(payload.get("exit_date") or format_jalali_date(as_of))),
                    exit_price=sale_price, source_trade_id=closed_trade.get("id"),
                    exclude_from_portfolio=True,
                )
            elif closed_trade.get("strategy_type")=="covered_call" and closed_trade.get("exit_method")=="offset" and closed_trade.get("underlying_position_id") and closed_trade.get("underlying_disposition")=="keep":
                other_allocated = sum(
                    trade_underlying_units(item)
                    for item in runtime.trades.list()
                    if item.get("status") != "closed"
                    and item.get("strategy_type") == "covered_call"
                    and item.get("underlying_position_id") == closed_trade["underlying_position_id"]
                )
                runtime.underlyings.rebase_released_quantity(
                    closed_trade["underlying_position_id"],
                    trade_underlying_units(closed_trade),
                    release_date=parse_user_date(str(closed_trade["exit_date"])),
                    release_price=float(closed_trade["exit_base_price"]),
                    other_allocated_quantity=other_allocated,
                    source_trade_id=closed_trade.get("id"),
                )
        return json_response(runtime.trade_payload())
    except Exception as exc:
        return error_response(exc, operation="بستن معامله")


@require_http_methods(["POST"])
@personal_api_login_required
def api_underlyings(request: HttpRequest) -> JsonResponse:
    try:
        runtime=get_runtime(request.user.pk)
        payload=confirmed_underlying_price(read_json(request), runtime)
        payload.update({
            "quantity_kind": "unit",
            "currency_unit": "rial",
            "calculation_version": 8,
        })
        payload=prepare_underlying_payload(payload,runtime.trades.list())
        runtime.underlyings.create(payload)
        return json_response(runtime.trade_payload(),201)
    except Exception as exc:
        return error_response(exc,operation="ثبت دارایی پایه")


@require_POST
@personal_api_login_required
def api_underlying_close(request: HttpRequest, position_id: str) -> JsonResponse:
    try:
        runtime = get_runtime(request.user.pk)
        payload = read_json(request)
        require_price_confirmation(payload)
        position = next(
            (item for item in runtime.underlyings.list() if item.get("id") == position_id),
            None,
        )
        if not position:
            raise KeyError("دارایی پایه پیدا نشد")
        from bambo_bot.trades import underlying_allocations
        allocated = underlying_allocations(runtime.trades.list()).get(position_id, 0.0)
        available = float(position.get("quantity") or 0) - allocated
        quantity = float(payload.get("quantity") or 0)
        if quantity > available + 1e-9:
            raise ValueError("فقط موجودی آزاد دارایی پایه قابل فروش است")
        dashboard = runtime.cache.get()
        from bambo_bot.trades import build_underlying_quote_map, underlying_quote_key
        base_quote = build_underlying_quote_map(runtime.cache.trade_quotes()).get(
            underlying_quote_key(position.get("market"), position.get("asset"))
        ) or {}
        runtime.underlyings.sell_quantity(
            position_id, quantity,
            exit_date=parse_user_date(str(payload.get("exit_date") or "")),
            exit_price=payload.get("exit_price"),
            exit_commission=payload.get("exit_commission"),
            exit_commission_source=payload.get("exit_commission_source"),
            suggested_exit_price=base_quote.get("last"),
            suggested_price_fetched_at=dashboard.get("generated_at"),
            price_confirmed_at=datetime.now().astimezone().isoformat(),
        )
        return json_response(runtime.trade_payload())
    except Exception as exc:
        return error_response(exc,operation="ثبت فروش دارایی پایه")


@require_http_methods(["PUT","DELETE"])
@personal_api_login_required
def api_underlying_detail(request: HttpRequest, position_id: str) -> JsonResponse:
    try:
        runtime=get_runtime(request.user.pk)
        if request.method=="DELETE":
            validate_underlying_position_change(
                position_id, None, runtime.underlyings.list(),
                runtime.trades.list(), deleting=True,
            )
            runtime.underlyings.delete(position_id)
        else:
            payload = confirmed_underlying_price(read_json(request), runtime)
            payload = prepare_underlying_payload(payload,runtime.trades.list())
            validate_underlying_position_change(
                position_id, payload, runtime.underlyings.list(),
                runtime.trades.list(),
            )
            runtime.underlyings.update(position_id,payload)
        return json_response(runtime.trade_payload())
    except Exception as exc:
        return error_response(exc,operation="ویرایش دارایی پایه")
