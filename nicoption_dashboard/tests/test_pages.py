import struct
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings

from django.utils import timezone

from nicoption_dashboard.models import AccountPreference, Article
from nicoption_dashboard.views import read_json


class DashboardPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="page-user")
        self.client.force_login(self.user)

    def test_all_dashboard_pages_use_the_existing_interface(self):
        for path in (
            "/dashboard", "/articles", "/market", "/tehran-options", "/trades",
            "/commodity-exchange", "/forecast", "/order-flow",
            "/economic-indicators", "/economic-comparison", "/statistical-center", "/central-bank", "/monetary-details",
            "/profit-recognition", "/closed-trades", "/calculator", "/settings",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, "nicoption")

    def test_health_identifies_django_runtime(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "framework": "django"})

    def test_referrer_policy_keeps_secure_csrf_posts_usable(self):
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "same-origin")

    def test_legacy_json_boundary_preserves_decimal_lexeme(self):
        request = RequestFactory().post(
            "/api/trades",
            data=b'{"entry_premium":0.123456789123456789}',
            content_type="application/json",
        )

        self.assertEqual(
            read_json(request)["entry_premium"],
            "0.123456789123456789",
        )


    def test_readiness_checks_database_connection(self):
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "database": "available"},
        )

    @patch("nicoption_dashboard.views.connection.cursor")
    def test_readiness_reports_database_failure(self, cursor):
        cursor.side_effect = RuntimeError("internal database detail")

        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"ok": False, "database": "unavailable"},
        )
        self.assertNotContains(
            response,
            "internal database detail",
            status_code=503,
        )

    def test_dashboard_sets_csrf_cookie(self):
        response = self.client.get("/dashboard")
        self.assertIn("csrftoken", response.cookies)

    def test_articles_api_returns_only_published_articles(self):
        published = Article.objects.create(
            title="راهنمای کاوردکال",
            slug="covered-call-guide",
            summary="خلاصه مقاله منتشرشده",
            body="متن مقاله",
            is_published=True,
            published_at=timezone.now(),
            author=self.user,
        )
        Article.objects.create(
            title="پیش‌نویس",
            slug="draft",
            summary="این مورد نباید منتشر شود",
            body="متن پیش‌نویس",
            is_published=False,
        )

        response = self.client.get("/api/articles")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["slug"] for item in response.json()["articles"]], [published.slug])

    def test_dashboard_article_section_is_rendered_only_when_articles_exist(self):
        response = self.client.get("/dashboard")
        self.assertNotContains(response, "آخرین مقالات")

        Article.objects.create(
            title="مقاله تازه",
            slug="latest-article",
            summary="خلاصه",
            body="متن",
            is_published=True,
            published_at=timezone.now(),
        )
        api_response = self.client.get("/api/articles")
        self.assertContains(api_response, "مقاله تازه")

    def test_articles_navigation_and_option_market_group_are_exposed(self):
        response = self.client.get("/articles")

        self.assertContains(response, 'href="/articles" data-page-link="articles" data-feature="articles"')
        self.assertContains(response, "بازار آپشن")
        self.assertContains(response, 'aria-controls="optionMarketNavigationMenu"')
        self.assertContains(response, 'data-page-view="articles"')

    def test_settings_exposes_separate_open_and_closed_csv_imports(self):
        response = self.client.get("/settings")

        self.assertContains(response, "ورود معاملات باز")
        self.assertContains(response, "ورود معاملات بسته‌شده")
        self.assertContains(response, 'data-import-status="open"')
        self.assertContains(response, 'data-import-status="closed"')
        self.assertContains(response, 'accept=".csv,text/csv"', count=2)

    def test_dashboard_uses_an_application_confirmation_dialog(self):
        response = self.client.get("/trades")

        self.assertContains(response, 'id="confirmationModal"')
        self.assertContains(response, 'role="alertdialog"')
        self.assertContains(response, "این عملیات قابل بازگشت نیست")

    def test_trade_pages_expose_bulk_selection_controls(self):
        open_page = self.client.get("/trades")
        closed_page = self.client.get("/closed-trades")

        for response in (open_page, closed_page):
            self.assertContains(response, 'data-trade-select-all="open"')
            self.assertContains(response, 'data-trade-bulk-delete="open"')
            self.assertContains(response, 'data-trade-select-all="closed"')
            self.assertContains(response, 'data-trade-bulk-delete="closed"')

    def test_trade_page_exposes_portfolio_asset_ledger(self):
        response = self.client.get("/trades")

        self.assertContains(response, 'id="portfolioAssetLedger"')
        self.assertContains(response, 'id="portfolioAssetLedgerList"')
        self.assertContains(response, "دفتر تخصیص دارایی")
        self.assertContains(response, "وثیقهٔ کاوردکال")
        self.assertContains(response, "دارایی پایه آزاد")
        self.assertContains(response, 'id="portfolioLedgerBaseTotal"')
        self.assertContains(response, 'id="portfolioLedgerCollateralBar"')
        self.assertContains(response, 'data-focus-account-cash')
        self.assertContains(response, 'class="portfolio-ledger-details"')

    def test_profit_recognition_page_exposes_complete_account_growth_workspace(self):
        response = self.client.get("/profit-recognition")

        self.assertContains(response, 'id="accountGrowthChart"')
        self.assertContains(response, 'id="accountGrowthTrendSummary"')
        self.assertContains(response, 'id="accountGrowthEvents"')
        self.assertContains(response, 'id="accountGrowthInvested"')
        self.assertContains(response, "رویدادهای مؤثر بر رشد حساب")
        self.assertContains(response, "تنظیم سرمایه اولیه و وجه نقد")
        self.assertContains(response, 'class="account-growth-secondary"')

    def test_profit_recognition_open_trade_summary_excludes_cash_and_free_underlying(self):
        response = self.client.get("/profit-recognition")

        self.assertContains(response, "کل نقدینگی درگیر دو استراتژی")
        self.assertContains(response, "سود تجمیعی نوسان قیمت")
        self.assertContains(response, "فقط کاوردکال + خرید اختیار خرید")
        self.assertNotContains(response, 'id="portfolioCashBalance"')
        self.assertNotContains(response, 'class="portfolio-summary-group underlying"')

    def test_trade_dashboard_sections_have_explicit_page_ownership(self):
        response = self.client.get("/trades")

        self.assertContains(response, 'id="tradeValuationControls"')
        self.assertContains(response, 'class="trade-valuation-heading"')
        self.assertContains(
            response,
            'class="portfolio-summary profit-performance-section" data-page-view="trades"',
        )
        self.assertContains(
            response,
            'class="account-growth-panel profit-performance-section" data-page-view="trades"',
        )

    def test_admin_can_disable_every_page_for_a_user(self):
        AccountPreference.objects.create(
            owner=self.user,
            show_overview=False,
            show_articles=False,
            show_market=False,
            show_tehran_options=False,
            show_order_flow=False,
            show_commodity_exchange=False,
            show_trades=False,
            show_closed_trades=False,
            show_profit_recognition=False,
            show_calculator=False,
            show_settings=False,
            show_forecast=False,
        )

        for path in (
            "/dashboard", "/articles", "/market", "/tehran-options", "/commodity-exchange",
            "/trades", "/closed-trades", "/profit-recognition", "/calculator",
            "/settings", "/order-flow", "/forecast",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 403)

    def test_admin_can_disable_option_market_as_one_group(self):
        AccountPreference.objects.create(owner=self.user, show_option_market=False)

        for path in (
            "/opportunities",
            "/market",
            "/tehran-options",
            "/commodity-exchange",
            "/order-flow",
            "/forecast",
            "/trades",
            "/closed-trades",
            "/profit-recognition",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

        self.assertEqual(self.client.get("/economic-indicators").status_code, 200)
        self.assertEqual(self.client.get("/articles").status_code, 200)

    def test_admin_can_disable_economic_data_independently(self):
        AccountPreference.objects.create(owner=self.user, show_economic_data=False)

        for path in (
            "/economic-indicators",
            "/economic-comparison",
            "/statistical-center",
            "/central-bank",
            "/monetary-details",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

        for path in (
            "/api/economic-indicators",
            "/api/economic-comparison-indicators",
            "/api/statistical-center-indicators",
            "/api/monetary-indicators",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

        self.assertEqual(self.client.get("/market").status_code, 200)
        self.assertEqual(self.client.get("/articles").status_code, 200)

    def test_superuser_cannot_be_locked_out_of_product_pages(self):
        admin = get_user_model().objects.create_superuser(
            username="site-admin",
            password="test-password",
            email="admin@example.com",
        )
        AccountPreference.objects.create(owner=admin, show_settings=False)
        self.client.force_login(admin)

        self.assertEqual(self.client.get("/settings").status_code, 200)

    def test_navigation_exposes_a_permission_key_for_every_page(self):
        response = self.client.get("/dashboard")

        for feature in (
            "overview", "articles", "market", "tehran_options", "trades", "economic_data",
            "profit_recognition", "calculator", "settings",
        ):
            self.assertContains(response, f'data-feature="{feature}"')
        self.assertContains(
            response,
            'data-feature-any="tehran_options,commodity_exchange,order_flow,forecast"',
        )
        self.assertContains(response, 'data-feature-any="trades,closed_trades"')

    def test_economic_indicators_page_is_deep_linkable_and_accessible(self):
        response = self.client.get("/economic-indicators")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-page-view="economic-indicators"')
        self.assertContains(response, "میز اقتصاد ایران")
        self.assertContains(response, "نبض اقتصاد و بازار")
        self.assertContains(response, "دلار، تتر، طلا، سکه و شاخص کل بورس تهران")
        self.assertContains(response, 'href="/economic-comparison"')
        self.assertNotContains(response, 'href="#economic-indicators-list"')
        self.assertContains(response, "داده‌های مرکز آمار")
        self.assertContains(response, "داده‌های بانک مرکزی")
        self.assertNotContains(response, 'id="economicNavigationMenu"')
        self.assertContains(response, 'href="/economic-indicators"')
        self.assertContains(response, 'href="/statistical-center"')
        self.assertContains(response, 'href="/central-bank"')

    def test_statistical_center_has_its_own_page(self):
        response = self.client.get("/statistical-center")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-page-view="statistical-center"')
        self.assertContains(response, 'id="statisticalCenterPageTitle"')
        self.assertContains(response, 'id="statisticalCenterApp"')
        self.assertContains(response, "فهرست کامل داده‌های قیمت و تورم")
        self.assertNotContains(response, 'id="statisticalCenterRefreshButton"')
        self.assertNotContains(response, "مشاهده منبع رسمی")
        self.assertContains(response, 'id="economicDetailDialog"')
        self.assertContains(response, 'role="dialog"')

    def test_economic_comparison_has_its_own_page_and_searchable_selectors(self):
        response = self.client.get("/economic-comparison")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-page-view="economic-comparison"')
        self.assertContains(response, 'id="economicComparisonPageTitle"')
        self.assertContains(response, 'id="economicComparisonApp"')
        self.assertContains(response, "مقایسه روندهای اقتصادی")

    def test_economic_comparison_catalog_includes_all_official_sources(self):
        response = self.client.get("/api/economic-comparison-indicators")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["central_bank"], 16)
        self.assertGreater(payload["summary"]["statistical_center"], 1000)
        self.assertEqual(payload["summary"]["total"], len(payload["indicators"]))
        self.assertTrue(any(item["comparison_source"] == "central_bank" for item in payload["indicators"]))
        self.assertTrue(any(item["comparison_source"] == "statistical_center" for item in payload["indicators"]))
        priorities = [item["is_primary"] for item in payload["indicators"]]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_central_bank_has_its_own_page_and_legacy_route(self):
        response = self.client.get("/central-bank")
        legacy = self.client.get("/monetary-details")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(legacy.status_code, 200)
        self.assertContains(response, 'data-page-view="central-bank"')
        self.assertContains(response, "داده‌های بانک مرکزی")
        self.assertContains(response, 'id="central-bank-data"')
        self.assertContains(response, 'id="centralBankCatalogTitle"')
        self.assertContains(response, "فهرست کامل شاخص‌های پولی و بانکی")
        self.assertContains(response, 'id="monetaryDetailsApp"')
        self.assertNotContains(response, 'id="monetaryDetailsSyncedAt"')
        self.assertNotContains(response, 'id="monetaryDetailsRefreshButton"')
        self.assertNotContains(response, "مشاهده منبع رسمی")

    def test_economic_indicators_api_has_stable_empty_schema(self):
        response = self.client.get("/api/economic-indicators")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), {"generated_at", "indicators", "upcoming_releases"})
        self.assertIsInstance(payload["generated_at"], str)
        self.assertEqual(payload["indicators"], [])
        self.assertEqual(payload["upcoming_releases"], [])
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    @override_settings(DEBUG=False)
    def test_economic_indicators_api_never_invents_production_data(self):
        response = self.client.get("/api/economic-indicators")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["indicators"], [])

    def test_economic_indicators_requires_authentication(self):
        self.client.logout()

        page = self.client.get("/economic-indicators")
        api = self.client.get("/api/economic-indicators")

        self.assertEqual(page.status_code, 302)
        self.assertIn("/login?next=%2Feconomic-indicators", page.url)
        self.assertEqual(api.status_code, 403)

    def test_economic_interface_includes_contract_states_and_safe_rendering(self):
        script = (settings.WEB_STATIC_DIR / "economic-indicators.js").read_text()

        self.assertIn("economicEsc", script)
        self.assertIn("AbortController", script)
        self.assertIn("در انتظار انتشار", script)
        self.assertIn("داده قدیمی", script)
        self.assertIn("نیازمند اشتراک", script)
        self.assertIn("بدون داده، فایل خالی ساخته نمی‌شود", script)
        self.assertIn("fa-IR-u-ca-persian", script)
        self.assertIn("Asia/Tehran", script)
        self.assertIn("data-economic-clear", script)
        self.assertIn("modalManager.open(dialog", script)
        self.assertIn("modalManager.close(dialog)", script)
        self.assertNotIn('document.querySelector(".page-shell")?.setAttribute("inert"', script)
        self.assertIn('x="44" y="12" width="402" height="184" fill="transparent"', script)
        self.assertIn("data-economic-chart-cursor", script)
        self.assertIn('hitbox.addEventListener("pointermove"', script)
        self.assertIn('node.addEventListener("focus"', script)
        self.assertIn("economicLatestPublishedAt", script)
        self.assertIn('data-economic-compare-slot="${index}"', script)
        self.assertIn('data-economic-compare-search="${index}"', script)
        self.assertIn('data-economic-compare-clear="${index}"', script)
        self.assertIn('document.body.dataset.page==="economic-comparison"', script)
        self.assertIn("bindEconomicComparisonChart", script)
        self.assertIn('code:"IR-INF_MOM",label:"تورم ماهانه"', script)
        self.assertIn('code:"IR_M2_MOM_GROWTH",label:"رشد ماهانه نقدینگی"', script)
        self.assertIn('code:"IR_USD_FREE_MARKET_MOM_CHANGE",label:"رشد ماهانه دلار"', script)
        self.assertIn('code:"IR_GOLD_18K_MOM_CHANGE",label:"رشد ماهانه طلا"', script)
        self.assertIn('code:"IR_TEDPIX_MOM_CHANGE",label:"رشد ماهانه بورس"', script)
        self.assertIn("economicKpis(indicators)", script)
        self.assertNotIn('class="economic-row-meta"', script)
        self.assertNotIn('<th scope="col">سیگنال</th>', script)
        self.assertIn('colspan="5" scope="rowgroup"', script)
        self.assertNotIn("غلبه روند صعودی", script)
        self.assertNotIn("رشد نقدینگی سالانه است", script)
        self.assertNotIn("economicCalendar", script)
        self.assertNotIn("انتشارهای پیش‌رو", script)
        self.assertNotIn("برای شروع، از فهرست زیر", script)
        self.assertNotIn("آخرین دریافت", script)
        self.assertNotIn("تجدیدنظر", script)
        self.assertNotIn("مشاهده امکانات اشتراک", script)
        self.assertNotIn("economic-detail-stats", script)
        self.assertIn("api/economic-comparison-indicators", script)
        self.assertIn('label="شاخص‌های اصلی"', script)
        self.assertIn("ابتدا نام، کد یا منبع را جست‌وجو کنید", script)
        self.assertIn("api/statistical-center-series", script)
        self.assertIn("economicStatisticalIndicator", script)
        self.assertIn("data-economic-statistical-detail", script)
        self.assertIn("economicComparisonDetailUrl", script)
        self.assertIn('aria-label="مشاهده جزئیات', script)
        self.assertIn('get("indicator")', script)

        statistical_script = (settings.WEB_STATIC_DIR / "statistical-center.js").read_text()
        self.assertIn("statisticalCenterNormalizeSearch", statistical_script)
        self.assertIn('payload.filters?.q||""', statistical_script)
        self.assertIn("payload.amar_mcp_series||[]", statistical_script)
        self.assertIn("statisticalCenterAmarMcpItems", statistical_script)
        self.assertIn('statisticalCenterRows(amarItems.filter', statistical_script)
        self.assertIn("searchWasFocused", statistical_script)
        self.assertIn("setSelectionRange(selectionStart,selectionEnd)", statistical_script)
        index_html = (settings.WEB_STATIC_DIR / "index.html").read_text()
        self.assertIn("statistical-center.js?v=20261107-amar-mcp-changes-8", index_html)
        self.assertIn('monetary-indicators.js?v=20261107-cbi-mcp-exchange-removed-open-market-1', index_html)
        self.assertIn('styles.css?v=20261107-cbi-exchange-removal-1', index_html)
        self.assertIn("AbortController", statistical_script)
        self.assertIn("compositionstart", statistical_script)
        self.assertIn("data-statistical-center-clear", statistical_script)
        self.assertIn("data-statistical-center-page", statistical_script)
        self.assertIn("api/statistical-center-series", statistical_script)
        self.assertIn("modalManager.open(dialog", statistical_script)
        self.assertIn("display_title_fa", statistical_script)
        self.assertIn("last_available_label_fa", statistical_script)
        self.assertIn("economicInstitutionalDetailMarkup", statistical_script)
        self.assertIn("economicInstitutionalSideMarkup", statistical_script)
        monetary_script = (settings.WEB_STATIC_DIR / "monetary-indicators.js").read_text()
        self.assertIn("snapshot?.series_catalog || []", monetary_script)
        self.assertIn('comparison_source:"cbi_mcp"', monetary_script)
        self.assertIn('results.innerHTML=monetaryCatalogResults(state.payload.indicators,state)', monetary_script)
        self.assertIn('setTimeout(()=>{state.q=search.value;updateResults();},300)', monetary_script)
        self.assertIn('comparison_source === "cbi_mcp"', monetary_script)
        self.assertIn("period_date: point.period_date || point.date", monetary_script)
        self.assertNotIn("function cbiMcpRates(data)", monetary_script)
        self.assertIn('item.key!=="balance_of_payments"', monetary_script)
        self.assertIn('statistics_time_series?.sections || []).filter', monetary_script)
        self.assertNotIn("تاریخچه نرخ رسمی دلار", monetary_script)
        self.assertIn('item.key!=="balance_of_payments"', monetary_script)
        self.assertIn("آخرین حراج بازخرید", monetary_script)
        self.assertIn("bindEconomicInstitutionalDetail", statistical_script)
        self.assertIn("data-statistical-center-preview", statistical_script)
        self.assertIn("data-statistical-center-analysis", statistical_script)
        self.assertIn("تغییر نسبت به دوره قبل", statistical_script)
        self.assertIn("تغییر نقطه‌به‌نقطه", statistical_script)
        self.assertNotIn('<th scope="col">تغییر ۳ماهه</th>', statistical_script)
        self.assertNotIn('<th scope="col">صدک ۲ساله</th>', statistical_script)
        self.assertNotIn('<th scope="col">سیگنال</th>', statistical_script)
        self.assertIn('document.body.dataset.page!=="statistical-center"', statistical_script)

        app_script = (settings.WEB_STATIC_DIR / "app.js").read_text()
        self.assertIn('"/statistical-center": "statistical-center"', app_script)
        self.assertIn('"/central-bank": "central-bank"', app_script)
        self.assertIn('"/monetary-details": "central-bank"', app_script)

    def test_monetary_interface_uses_calendar_growth_and_accessible_controls(self):
        script = (settings.WEB_STATIC_DIR / "monetary-indicators.js").read_text()

        self.assertIn("monthly_growth_percent", script)
        self.assertIn("yearly_growth_percent", script)
        self.assertIn("AbortController", script)
        self.assertIn('role="group"', script)
        self.assertIn("data-monetary-range", script)
        self.assertIn("data-monetary-select", script)
        self.assertIn("is_suspicious", script)
        self.assertIn('all: {payload: null', script)
        self.assertIn('id="monetaryCatalogFilters"', script)
        self.assertIn('data-monetary-clear', script)
        self.assertIn('scope === "all"', script)
        self.assertIn('scope === "all" ? "" : monetaryQuality(payload)', script)
        self.assertIn("داده کافی نیست", script)
        self.assertIn("openMonetaryDetail", script)
        self.assertIn("economicInstitutionalDetailMarkup", script)
        self.assertIn("economicInstitutionalSideMarkup", script)
        self.assertIn("description_fa", script)
        self.assertIn("data-monetary-preview", script)
        self.assertIn("data-monetary-analysis", script)
        self.assertIn("تغییر نسبت به دوره قبل", script)
        self.assertIn("تغییر نقطه‌به‌نقطه", script)
        self.assertNotIn('<th scope="col">تغییر ۳ماهه</th>', script)
        self.assertNotIn('<th scope="col">صدک ۲ساله</th>', script)
        self.assertNotIn('<th scope="col">سیگنال</th>', script)
        self.assertIn("compactSignal:true,latinRanges:true", script)

        shared_script = (settings.WEB_STATIC_DIR / "economic-indicators.js").read_text()
        self.assertIn("economicInstitutionalDetailMarkup", shared_script)
        self.assertIn("economicInstitutionalSideMarkup", shared_script)
        self.assertIn("institutional-side-note", shared_script)
        self.assertIn('data-institutional-range="${value}"', shared_script)
        self.assertIn('[["1y","1Y"],["3y","3Y"],["5y","5Y"],["10y","10Y"],["all","Max"]]', shared_script)
        self.assertIn("در حال رشد و شتاب‌گیری", shared_script)
        self.assertIn('dir="rtl" aria-label="${economicEsc(signalText)}"', shared_script)
        self.assertIn("institutional-signal-chip", shared_script)
        statistical_script = (settings.WEB_STATIC_DIR / "statistical-center.js").read_text()
        self.assertIn("compactSignal:true,latinRanges:true", statistical_script)

    def test_opportunities_uses_market_permission(self):
        response = self.client.get("/opportunities")
        self.assertEqual(response.status_code, 200)

        preferences, _ = AccountPreference.objects.get_or_create(owner=self.user)
        preferences.show_market = False
        preferences.save(update_fields=["show_market"])

        self.assertEqual(self.client.get("/opportunities").status_code, 403)

    def test_deployed_trade_and_performance_routes_use_dashboard_interface(self):
        for path in (
            "/trades/open",
            "/trades/closed",
            "/trades/example-trade-id",
            "/performance",
            "/performance/overview",
            "/performance/covered-call",
            "/performance/long-call",
            "/performance/realized-profit",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_trade_detail_uses_trades_permission(self):
        preferences, _ = AccountPreference.objects.get_or_create(owner=self.user)
        preferences.show_trades = False
        preferences.save(update_fields=["show_trades"])

        self.assertEqual(self.client.get("/trades/example-trade-id").status_code, 403)

    def test_methodology_is_a_distinct_calculation_reference(self):
        response = self.client.get("/methodology")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="methodology-page"')
        self.assertContains(response, "روش محاسبات")
        self.assertContains(response, "Capital × 0.40 × Holding days ÷ 365")

        preferences = AccountPreference.objects.get(owner=self.user)
        preferences.show_calculator = False
        preferences.save(update_fields=["show_calculator"])

        self.assertEqual(self.client.get("/methodology").status_code, 403)

class NotFoundPageTests(TestCase):
    @override_settings(DEBUG=False)
    def test_unknown_page_uses_owned_persian_404(self):
        response = self.client.get("/مسیر-نامعلوم")

        self.assertEqual(response.status_code, 404)
        self.assertContains(
            response,
            "این صفحه در nicoption وجود ندارد",
            status_code=404,
        )
        self.assertContains(response, "رفتن به داشبورد", status_code=404)
        self.assertContains(
            response,
            "صفحه پیدا نشد — nicoption",
            status_code=404,
        )
        self.assertIn("no-store", response["Cache-Control"])

    @override_settings(DEBUG=False)
    def test_unknown_api_path_stays_json(self):
        response = self.client.get("/api/unknown-resource")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "مسیر درخواستی پیدا نشد"})


class LoginPageTests(TestCase):
    def test_landing_page_is_public_and_links_to_login(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "داده، تحلیل و پژوهش بازار")
        self.assertContains(response, "از اقتصاد کلان تا اختیار معامله")
        self.assertContains(response, "داده‌های اقتصادی")
        self.assertContains(response, "مقاله‌ها و یادداشت‌ها")
        self.assertContains(response, 'href="/login"')

    def test_about_and_contact_page_is_public_and_uses_support_channel(self):
        response = self.client.get("/about")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "درباره و ارتباط با ما")
        self.assertContains(response, "https://t.me/s_nad")
        self.assertContains(response, "رمز عبور یا کد تأیید را برای هیچ‌کس ارسال نکنید")

    def test_landing_exposes_canonical_open_graph_metadata(self):
        response = self.client.get("/")

        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'property="og:description"')
        self.assertContains(
            response,
            'property="og:image" content="https://nicoption.ir/assets/nicoption-og.png"',
        )
        self.assertContains(response, 'property="og:url" content="https://nicoption.ir/"')
        self.assertContains(response, 'property="og:type" content="website"')
        self.assertContains(response, 'name="twitter:card" content="summary_large_image"')
        self.assertContains(response, 'rel="canonical" href="https://nicoption.ir/"')
        self.assertContains(response, 'href="/favicon.ico"')

    def test_brand_assets_and_dana_fonts_have_web_formats(self):
        static_root = settings.WEB_STATIC_DIR
        favicon = (static_root / "favicon.ico").read_bytes()
        og_image = (static_root / "assets" / "nicoption-og.png").read_bytes()

        self.assertEqual(favicon[:4], b"\x00\x00\x01\x00")
        self.assertEqual(og_image[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", og_image[16:24]), (1200, 630))
        for weight in ("Regular", "DemiBold", "Bold"):
            font = static_root / "fonts" / f"Dana-{weight}.woff2"
            self.assertEqual(font.read_bytes()[:4], b"wOF2")
            self.assertFalse((static_root / "fonts" / f"Dana-{weight}.ttf").exists())

    @override_settings(PUBLIC_SITE_ORIGIN="https://nicoption.ir")
    def test_robots_and_sitemap_only_advertise_the_public_landing_page(self):
        robots = self.client.get("/robots.txt")
        sitemap = self.client.get("/sitemap.xml")

        self.assertEqual(robots.status_code, 200)
        self.assertEqual(robots["Content-Type"], "text/plain; charset=utf-8")
        self.assertContains(robots, "Disallow: /dashboard")
        self.assertContains(robots, "Disallow: /api/")
        self.assertContains(robots, "Disallow: /signup")
        self.assertContains(robots, "Sitemap: https://nicoption.ir/sitemap.xml")
        self.assertEqual(sitemap.status_code, 200)
        self.assertEqual(sitemap["Content-Type"], "application/xml; charset=utf-8")
        self.assertContains(sitemap, "<loc>https://nicoption.ir/</loc>")
        self.assertNotContains(sitemap, "/dashboard")

    def test_private_html_routes_are_noindex(self):
        login = self.client.get("/login")
        self.assertEqual(login["X-Robots-Tag"], "noindex, nofollow")
        signup = self.client.get("/signup")
        self.assertEqual(signup["X-Robots-Tag"], "noindex, nofollow")

        user = get_user_model().objects.create_user(username="private-page-user")
        self.client.force_login(user)
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard["X-Robots-Tag"], "noindex, nofollow")
        self.assertContains(dashboard, 'name="robots" content="noindex, nofollow"')

    def test_anonymous_dashboard_request_redirects_to_login(self):
        response = self.client.get("/trades")

        self.assertRedirects(
            response,
            "/login?next=%2Ftrades",
            fetch_redirect_response=False,
        )

    def test_anonymous_opportunities_request_preserves_next_path(self):
        response = self.client.get("/opportunities")

        self.assertRedirects(
            response,
            "/login?next=%2Fopportunities",
            fetch_redirect_response=False,
        )

    def test_anonymous_methodology_request_preserves_next_path(self):
        response = self.client.get("/methodology")

        self.assertRedirects(
            response,
            "/login?next=%2Fmethodology",
            fetch_redirect_response=False,
        )

    def test_login_page_is_available_without_authentication(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ورود به nicoption")
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, 'href="/signup"')

    def test_signup_page_is_available_without_authentication(self):
        response = self.client.get("/signup")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ساخت حساب nicoption")
        self.assertContains(response, "برای ورود اولیه فقط نام کاربری و رمز عبور لازم است")
        self.assertNotContains(response, 'type="email"')
        self.assertNotContains(response, 'type="tel"')
        self.assertContains(response, 'autocomplete="new-password"', count=2)
        self.assertContains(response, 'id="humanAnswer"')
        self.assertContains(response, 'id="humanQuestion"')
        self.assertContains(response, 'novalidate')
        self.assertContains(response, 'href="/login"')

    def test_unverified_user_sees_manual_telegram_activation_page(self):
        user = get_user_model().objects.create_user(
            username="pending-page-user",
            email="pending-page@example.com",
        )
        user.access_profile.email_verified_at = None
        user.access_profile.save(update_fields=("email_verified_at", "updated_at"))
        self.client.force_login(user)

        response = self.client.get("/verify-email")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "در تلگرام پیام بدهید")
        self.assertContains(response, "@s_nad")
        self.assertContains(response, 'href="https://t.me/s_nad"')
        self.assertContains(response, 'id="checkActivation"')
        self.assertContains(response, "رمز عبور را برای هیچ‌کس ارسال نکنید")

    def test_authenticated_user_is_redirected_away_from_login(self):
        user = get_user_model().objects.create_user(username="signed-in-user")
        self.client.force_login(user)

        response = self.client.get("/login")

        self.assertRedirects(response, "/dashboard", fetch_redirect_response=False)

    def test_authenticated_user_is_redirected_away_from_signup(self):
        user = get_user_model().objects.create_user(username="already-signed-in-user")
        self.client.force_login(user)

        response = self.client.get("/signup")

        self.assertRedirects(response, "/dashboard", fetch_redirect_response=False)
