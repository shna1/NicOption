import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bambo_bot.config import Settings
from bambo_bot.long_underlying import LongUnderlyingOpportunity
from bambo_bot.models import Contract, Pick
from bambo_bot.scan import ScanResult
from bambo_bot.web import build_dashboard_payload, calculate_custom_covered_call


class StaticFilterScopeTests(unittest.TestCase):
    def test_open_trades_renderer_always_rejects_closed_rows(self):
        project_root = Path(__file__).resolve().parents[1]
        source = (project_root / "bambo_bot/web_static/open-trades-v2.js").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'allRows=(allRows||[]).filter(item=>item&&item.status!=="closed")',
            source,
        )

    def test_open_trades_script_is_versioned_with_filter_fix(self):
        project_root = Path(__file__).resolve().parents[1]
        source = (project_root / "bambo_bot/web_static/index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("open-trades-v2.js?v=20261104-remove-header-1", source)

    def test_financial_csv_serializer_loads_before_application(self):
        project_root = Path(__file__).resolve().parents[1]
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(
            encoding="utf-8"
        )
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(
            encoding="utf-8"
        )
        web_source = (project_root / "bambo_bot/web.py").read_text(encoding="utf-8")
        csv_script = '/financial-csv.js?v=20261018-cross-layer-1'
        app_script = '/app.js?v=20261104-performance-chart-proportions-1'

        self.assertIn(csv_script, html_source)
        self.assertLess(html_source.index(csv_script), html_source.index(app_script))
        self.assertIn('window.NicOptionFinancialCsv.money(item, key)', app_source)
        self.assertGreaterEqual(
            app_source.count("window.NicOptionFinancialCsv.render("), 3
        )
        self.assertIn('"/financial-csv.js": (', web_source)

    def test_all_jalali_pickers_use_centered_viewport_positioning(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")

        self.assertEqual(app_source.count('classList.add("floating-calendar","centered-calendar")'), 2)
        self.assertIn(".jalali-date-picker.centered-calendar", css_source)
        self.assertIn("transform: translate(-50%,-50%)", css_source)

    def test_trade_commissions_are_automatic_but_editable(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")

        self.assertIn("const COMMISSION_RATES", app_source)
        self.assertIn("function updateTradeEntryCommissions", app_source)
        self.assertIn("function updateTradeCloseCommissions", app_source)
        self.assertIn("function updateUnderlyingEntryCommission", app_source)
        self.assertIn("function updateUnderlyingCloseCommission", app_source)
        self.assertIn('id="tradeCloseOptionCommission"', html_source)
        self.assertIn('id="tradeCloseUnderlyingCommission"', html_source)
        self.assertNotIn('name="commission" type="number" min="0" step="any" value="0" readonly', html_source)

    def test_mobile_navigation_escapes_glass_containing_blocks(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")

        self.assertIn("document.body.append(navigationBackdrop, mainNavigation)", app_source)
        self.assertIn("navigationHome.parent.insertBefore(mainNavigation, navigationHome.next)", app_source)
        self.assertIn("body.nav-open #mainNavigation", css_source)
        self.assertNotIn("body.nav-open .app-header .main-navigation", css_source)

    def test_trade_submission_owns_modal_validation_and_duplicate_guard(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")

        self.assertIn('id="tradeEditModalMessage" class="trade-message hidden" role="alert" tabindex="-1"', html_source)
        self.assertIn("function validateTradeForm(form)", app_source)
        self.assertIn("function showTradeSubmissionError(form, message)", app_source)
        self.assertIn('if (form.dataset.submitting === "true") return;', app_source)
        self.assertIn('button.setAttribute("aria-busy", "true")', app_source)

    def test_long_call_close_form_allows_exit_reallocation(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")

        self.assertIn("می‌تواند با هدف اولیه معامله متفاوت باشد", html_source)
        self.assertIn("جمع اعمال و آفست نباید از مانده قراردادها بیشتر شود", html_source)
        self.assertIn('select.options[2].textContent = "خروج ترکیبی: بخشی اعمال و بخشی آفست"', app_source)
        self.assertIn("form.elements.close_exercise_quantity.max = item.quantity", app_source)
        self.assertIn("app.js?v=20261104-performance-chart-proportions-1", html_source)

    def test_expired_contracts_have_an_explicit_manual_entry_flow(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")

        self.assertIn('value="manual_expired">ورود دستی قرارداد منقضی‌شده', html_source)
        for name in ("manual_option_symbol", "manual_strike", "manual_expiry", "manual_contract_size"):
            self.assertIn(f'name="{name}"', html_source)
        self.assertIn("function syncTradeContractEntryMode()", app_source)
        self.assertIn('item.contract_entry_mode === "manual_expired" || !liveContract', app_source)
        self.assertIn("app.js?v=20261104-performance-chart-proportions-1", html_source)

    def test_drawdown_copy_discloses_event_point_scope(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")

        self.assertIn("افت سرمایه در نقاط ثبت‑شده", html_source)
        self.assertIn('drawdownMethod:"closed_exit_points"', app_source)
        self.assertIn('drawdownIsDaily:false', app_source)
        self.assertIn("افت روزانه بین نقاط ثبت‌شده محاسبه نشده است", app_source)
        self.assertIn("افت در خروج‌های ثبت‌شده", app_source)
        self.assertNotIn("بیشترین افت سرمایه (MDD)", html_source)

    def test_performance_trend_chart_is_interactive_and_motion_safe(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")

        self.assertIn('const plot={x:96,y:12,width:350,height:184}', app_source)
        self.assertIn('class="closed-performance-axis-label"', app_source)
        self.assertIn('x="${plot.x-12}"', app_source)
        self.assertIn('targetSize=Math.min(15,Math.max(13.5,renderedWidth/73.333))', app_source)
        self.assertIn('tooltipScale=1/scale', app_source)
        self.assertIn('--closed-performance-axis-font-size,15px', css_source)
        self.assertIn("data-closed-chart-cursor", app_source)
        self.assertIn('hitbox.addEventListener("pointermove"', app_source)
        self.assertIn('node.addEventListener("focus"', app_source)
        self.assertIn("requestAnimationFrame(animate)", app_source)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)").matches', app_source)

    def test_dashboard_opportunities_use_a_four_card_row(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")

        self.assertIn("opportunities.slice(0,4)", app_source)
        self.assertIn(".dashboard-panel.opportunities{grid-column:1/-1}", css_source)
        self.assertIn(
            ".dashboard-opportunity-list{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))",
            css_source,
        )
        self.assertIn(".dashboard-opportunity-list{grid-template-columns:1fr}", css_source)

    def test_dashboard_trend_chart_matches_the_interactive_animated_chart(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")

        self.assertIn('const plot={x:72,y:12,width:374,height:184}', app_source)
        self.assertIn("data-dashboard-chart-cursor", app_source)
        self.assertIn('hitbox.addEventListener("pointermove"', app_source)
        self.assertIn('node.addEventListener("focus"', app_source)
        self.assertIn("dashboardTrendAnimationFrame=requestAnimationFrame(animate)", app_source)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)").matches', app_source)
        self.assertIn("dashboardTrendResizeObserver=new ResizeObserver(sizeChartText)", app_source)
        self.assertIn("tooltipScale=1/scale", app_source)
        self.assertIn("targetSize=Math.min(10,Math.max(9,renderedWidth/110))", app_source)
        self.assertIn('class="dashboard-trend-axis-label"', app_source)
        self.assertIn("--dashboard-axis-font-size", css_source)
        self.assertIn(".dashboard-trend-chart.closed-performance-line .dashboard-trend-tooltip text{font-size:9px}", css_source)
        self.assertIn("#mainContent .dashboard-trend-chart .closed-chart-grid text { font-size:var(--dashboard-axis-font-size,9px) !important;", css_source)

    def test_dashboard_expiries_use_a_four_card_row(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")

        self.assertIn(".slice(0,4).map((item)=>{const days=Number(item.remaining_days)", app_source)
        self.assertIn(".dashboard-panel.expiries{grid-column:1/-1}", css_source)
        self.assertIn(".dashboard-timeline{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))", css_source)
        self.assertIn(".dashboard-opportunity-list,.dashboard-timeline{grid-template-columns:1fr}", css_source)

    def test_methodology_discloses_contract_multiplier_and_corporate_action_gap(self):
        project_root = Path(__file__).resolve().parents[1]
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")

        self.assertIn("پریمیوم خرید × تعداد قرارداد × اندازه قرارداد", html_source)
        self.assertIn("MDD روزانه نیست", html_source)
        self.assertIn("تعدیلات شرکتی:", html_source)
        self.assertIn("فعلاً خودکار اعمال نمی‌شوند", html_source)

    def test_shared_modal_manager_owns_focus_escape_and_background_isolation(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")

        self.assertIn("const modalManager = (() => {", app_source)
        self.assertIn("document.addEventListener(\"keydown\", handleKeydown, true)", app_source)
        self.assertIn("sibling.inert = true", app_source)
        self.assertIn("element.getClientRects().length > 0", app_source)
        self.assertGreaterEqual(app_source.count("modalManager.open("), 5)
        self.assertEqual(html_source.count('class="modal-backdrop hidden"'), 5)
        self.assertGreaterEqual(html_source.count('tabindex="-1"'), 5)

    def test_opportunities_are_paginated_and_only_render_one_responsive_view(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")

        self.assertIn("const pageSize=[10,25,50].includes(requestedPageSize)?requestedPageSize:25", app_source)
        self.assertIn("rows=rows.slice(pageStart,pageStart+pageSize)", app_source)
        self.assertIn("inactiveRepresentation?.remove()", app_source)
        self.assertIn('controls.setAttribute("aria-label","صفحه‌بندی فرصت‌ها")', app_source)
        self.assertIn('window.addEventListener("popstate"', app_source)
        self.assertIn(".opportunities-page-controls", css_source)

    def test_missing_chart_theme_reference_is_removed_and_unavailable_views_are_disabled(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")

        self.assertNotIn("chart-theme.js", html_source)
        self.assertIn("button.disabled=true", app_source)
        self.assertIn('document.createTextNode("به‌زودی")', app_source)

    def test_phase_three_performance_budgets_are_documented_and_enforced(self):
        project_root = Path(__file__).resolve().parents[1]
        contract_source = (project_root / "UX-CONTRACT.md").read_text(encoding="utf-8")
        browser_source = (project_root / "tests/browser_phase2_checks.js").read_text(encoding="utf-8")

        self.assertIn("سقف انتشار ۴۰ MiB", contract_source)
        self.assertIn("حداکثر ۱۵۰۰ node", contract_source)
        self.assertIn("apiReleaseCapBytes: 40 * 1024 * 1024", browser_source)
        self.assertIn("opportunityNodes: 1500", browser_source)
        self.assertIn("medianRenderMs: 50", browser_source)
        self.assertIn("maximumRenderMs: 100", browser_source)

    def test_editorial_is_the_canonical_runtime_profile(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")

        self.assertIn('document.documentElement.dataset.appearance = "glass"', app_source)
        for obsolete in ("rahavard", "editorial", "neon", "fundbase", "wallex", "enigma", "apple"):
            self.assertNotIn(f'data-appearance="{obsolete}"', css_source)

    def test_editorial_routes_share_the_nicoption_design_profile(self):
        project_root = Path(__file__).resolve().parents[1]
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")
        landing_source = (project_root / "bambo_bot/web_static/landing.html").read_text(encoding="utf-8")
        open_source = (project_root / "bambo_bot/web_static/open-trades-v2.js").read_text(encoding="utf-8")

        self.assertIn('document.documentElement.dataset.editorial = "true"', html_source)
        self.assertIn('data-editorial="true"', html_source)
        self.assertNotIn("const editorialPaths", html_source)
        self.assertIn("styles.css?v=20261107-cbi-exchange-removal-1", html_source)
        self.assertIn('href="/favicon.ico"', html_source)
        self.assertIn('href="/favicon.ico"', landing_source)
        self.assertNotIn("cenobar.com/favicon.ico", html_source)
        self.assertNotIn("cenobar.com/favicon.ico", landing_source)
        self.assertIn('html[data-editorial="true"]', css_source)
        self.assertIn('--bg:#f5f5f6', css_source)
        self.assertIn('--green:#0f6b3e', css_source)
        self.assertIn('--red:#b42318', css_source)
        self.assertIn('"JetBrains Mono"', css_source)
        self.assertIn(':has(> :last-child:nth-child(odd))', css_source)
        self.assertNotIn('<section class="open-kpi-grid"><button', open_source)
        self.assertIn('<section class="open-kpi-grid"><article', open_source)
        self.assertIn('grid-template-rows:minmax(20px,auto) minmax(42px,1fr) minmax(34px,auto)', css_source)
        self.assertIn('.dashboard-kpis span,.dashboard-kpis strong,.dashboard-kpis small{display:block;width:100%;margin:0}', css_source)
        self.assertIn('.dashboard-kpis small{align-self:center;color:var(--muted);font-size:11px;line-height:1.6;white-space:nowrap}', css_source)
        self.assertIn('html[data-editorial="true"] .dashboard-kpis>a { display:grid; grid-template-rows:', css_source)
        self.assertIn('#mainContent .dashboard-kpis>a>span { font-size:14px !important;', css_source)
        self.assertIn('.dashboard-kpis>a:nth-child(4)::before', css_source)
        self.assertIn('.dashboard-open-row>div:nth-child(2){justify-items:center;text-align:center}', css_source)
        self.assertIn('.open-kpi-grid>article{display:grid;align-content:start;justify-items:center', css_source)
        self.assertIn('color:var(--text);text-align:center;box-shadow:var(--shadow-soft)', css_source)
        self.assertIn('.dashboard-kpis strong { font-family:var(--font-sans); font-size:24px; font-weight:600; }', css_source)
        self.assertIn('.open-kpi-grid strong { font-family:var(--font-sans); font-size:24px; font-weight:600; }', css_source)
        self.assertIn('.open-kpi-grid>article:nth-child(4n) { border-inline-start:1px solid var(--line); }', css_source)
        self.assertIn(':is(.chain-state-options,.chain-queue-options) button.active {', css_source)
        self.assertIn('border-color: var(--ink);', css_source)
        self.assertIn('background: var(--surface);', css_source)

    def test_articles_and_dashboard_reuse_the_economic_hero(self):
        project_root = Path(__file__).resolve().parents[1]
        html_source = (project_root / "bambo_bot/web_static/index.html").read_text(encoding="utf-8")
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")

        self.assertIn('class="page-heading economic-hero shared-page-hero" data-page-view="articles"', html_source)
        self.assertIn('dashboardHero?.classList.add("economic-hero","shared-page-hero","shared-page-hero--dashboard")', app_source)
        self.assertIn('shared-page-hero shared-page-hero--option" data-page-view="tehran-options"', html_source)
        self.assertIn('shared-page-hero shared-page-hero--option" data-page-view="trades"', html_source)
        self.assertIn('opportunitiesHero?.classList.add("economic-hero","shared-page-hero","shared-page-hero--option"', app_source)
        self.assertIn('opportunities-market-status span:first-child', app_source)
        self.assertIn('host.querySelector(".opportunity-changes")?.remove()', app_source)
        self.assertIn('closed-performance-title > div:first-child")?.remove()', app_source)
        open_trades_source = (project_root / "bambo_bot/web_static/open-trades-v2.js").read_text(encoding="utf-8")
        self.assertNotIn('class="open-trades-page-header"', open_trades_source)
        self.assertNotIn("trimOpenTradesHeader", open_trades_source)
        self.assertIn('id="openTradesHeroMeta" class="open-header-meta open-trades-hero-meta"', html_source)
        self.assertIn("updateHeroMeta(rows.length+underlyings.length,generated)", open_trades_source)
        self.assertNotIn('<div class="open-header-meta"><span>${num(rows.length+underlyings.length)}', open_trades_source)
        self.assertIn("#mainContent .shared-page-hero", css_source)
        self.assertIn("min-height:226px", css_source)
        self.assertIn(".shared-page-hero--dashboard .dashboard-header-actions", css_source)

    def test_landing_monte_carlo_motion_is_canvas_based_and_motion_safe(self):
        project_root = Path(__file__).resolve().parents[1]
        landing_source = (project_root / "bambo_bot/web_static/landing.html").read_text(encoding="utf-8")
        script_source = (project_root / "bambo_bot/web_static/landing-simulation.js").read_text(encoding="utf-8")

        self.assertIn('id="landingMonteCarlo"', landing_source)
        self.assertIn('role="img"', landing_source)
        self.assertIn("landing-simulation.js?v=20261027-option-surface-2", landing_source)
        self.assertIn("const pathCount = 64", script_source)
        self.assertIn("volatility = 0.24", script_source)
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)")', script_source)
        self.assertIn("requestAnimationFrame(animate)", script_source)
        self.assertIn("new IntersectionObserver", script_source)
        self.assertIn("TERMINAL P&L", script_source)

    def test_requested_dashboard_and_economic_chart_refinements_are_present(self):
        project_root = Path(__file__).resolve().parents[1]
        app_source = (project_root / "bambo_bot/web_static/app.js").read_text(encoding="utf-8")
        css_source = (project_root / "bambo_bot/web_static/styles.css").read_text(encoding="utf-8")
        economic_source = (project_root / "bambo_bot/web_static/economic-indicators.js").read_text(encoding="utf-8")

        self.assertIn("urgent.slice(0,4)", app_source)
        self.assertIn("repeat(4,minmax(0,1fr))", css_source)
        self.assertIn('html[data-theme="light"] .tehran-chain-panel .chain-sort-button.active', css_source)
        self.assertIn("function economicComparisonDomain(items)", economic_source)
        self.assertIn("item.points.length<shortest.points.length", economic_source)
        self.assertIn("point.time>=minTime&&point.time<=maxTime", economic_source)
        self.assertIn(".economic-comparison-chart .economic-chart-date", css_source)
        self.assertIn("font-size:7px !important", css_source)
        self.assertIn('const points=item.series,base=', economic_source)
        self.assertIn('if(range==="all")return item.series', economic_source)
        self.assertIn('data-economic-range="all" aria-pressed="true"', economic_source)
        self.assertIn('economicDetailVisual(item,"all")', economic_source)
        self.assertIn("function economicComparisonScale(series)", economic_source)
        self.assertIn("Math.abs(rawMax)*.05", economic_source)
        self.assertIn("economic-comparison-tooltip-swatch", economic_source)
        self.assertIn("font-size:6px !important", css_source)
        self.assertIn("function economicComparisonTimeScale(minTime,maxTime)", economic_source)
        self.assertIn("padding=dataSpan*.05", economic_source)
        self.assertIn("point.time-axisMinTime", economic_source)
        self.assertIn('name_fa:"رشد ماهانه قیمت دلار بازار آزاد"', economic_source)
        self.assertIn('name_fa:"رشد سالانه قیمت سکه بهار آزادی"', economic_source)
        self.assertIn('name_fa:"رشد ماهانه قیمت طلای ۱۸ عیار"', economic_source)
        self.assertIn('return "مرکز آمار ایران"', economic_source)
        self.assertIn("item.source?.organization,economicSourceLabel(item)", economic_source)
        self.assertIn('id="economic-overview"', economic_source)
        self.assertIn('id="economic-indicators-list"', economic_source)
        self.assertIn('id="economic-comparison"', economic_source)
        self.assertIn('["economic-indicators","economic-comparison"].includes(currentPage)', app_source)
        self.assertIn('await loadEconomicIndicators(false)', app_source)


class DashboardPayloadTests(unittest.TestCase):
    def test_custom_covered_call_calculator_returns_score_and_assumptions(self):
        result = calculate_custom_covered_call(
            {"market": "tehran", "asset": "وبملت", "symbol": "ضملت-test",
             "base_price": 1000, "premium": 100, "strike": 950, "days": 30,
             "transaction_value": "", "option_last": 110},
            [10, 100, 1000], 40,
        )
        self.assertEqual(result["state"], "ITM")
        self.assertAlmostEqual(result["expiry_return"], 5.0)
        self.assertAlmostEqual(result["annual_return"], 60.83)
        self.assertAlmostEqual(result["monthly_return"], 60.83 / 12, places=2)
        self.assertAlmostEqual(result["buyback_percent"], 10.0)
        self.assertAlmostEqual(result["buyback_annual_percent"], 10 * 365 / 30)
        self.assertAlmostEqual(result["buyback_monthly_percent"], 10 * 365 / 30 / 12)
        self.assertTrue(result["liquidity_assumed"])
        self.assertTrue(result["passes_dashboard_rule"])
        self.assertGreaterEqual(result["covered_score"], 0)
        self.assertLessEqual(result["covered_score"], 100)

    def test_payload_reconciles_summary_and_marks_zero_value(self):
        contract = Contract(
            asset="کهربا",
            source_asset="کهربا",
            symbol="KA-CC",
            expiry="1405-06-01",
            days=40,
            state="ITM",
            transaction_value=0,
            annual_return=45,
            expiry_return=12,
            base_price=1000,
            option_bid=100,
            strike=1100,
            breakeven=900,
            itm_percent=2,
        )
        long_item = LongUnderlyingOpportunity(
            asset="کهربا",
            symbol="KA-LONG",
            expiry="1405-06-01",
            days=40,
            state="ITM",
            profit_percent=3,
            base_price=1000,
            option_bid=100,
            option_ask=120,
            strike=1100,
            breakeven=900,
            transaction_value=10,
            volume=2,
            itm_percent=7.5,
        )
        scan = ScanResult(
            generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=ZoneInfo("Asia/Tehran")),
            contracts=[contract],
            covered_call={
                ("کهربا", "1405-06-01"): [
                    Pick("ITM · بیشترین سود سالانه", "سود سالانه", contract)
                ]
            },
            long_underlying={("کهربا", "1405-06-01"): [long_item]},
            covered_call_last={
                ("کهربا", "1405-06-01"): [
                    Pick("ITM · بیشترین سود سالانه", "سود سالانه", contract)
                ]
            },
            long_underlying_last={("کهربا", "1405-06-01"): [long_item]},
            long_underlying_ask={("کهربا", "1405-06-01"): [long_item]},
        )
        payload = build_dashboard_payload(scan, Settings())
        self.assertEqual(payload["summary"]["covered_contracts"], 1)
        self.assertEqual(payload["summary"]["positive_contracts"], 1)
        self.assertEqual(payload["summary"]["zero_value_contracts"], 1)
        self.assertTrue(payload["covered_call"][0]["items"][0]["transaction_zero"])
        self.assertEqual(payload["long_underlying"][0]["items"][0]["volume"], 2)
        self.assertEqual(payload["covered_call"][0]["items"][0]["itm_percent"], 2)
        self.assertEqual(payload["long_underlying"][0]["items"][0]["itm_percent"], 7.5)
        covered_item = payload["covered_call"][0]["items"][0]
        long_payload_item = payload["long_underlying"][0]["items"][0]
        self.assertAlmostEqual(covered_item["monthly_return"], 45 / 12)
        self.assertAlmostEqual(covered_item["buyback_percent"], 10)
        self.assertAlmostEqual(covered_item["buyback_annual_percent"], 10 * 365 / 40)
        self.assertAlmostEqual(covered_item["buyback_monthly_percent"], 10 * 365 / 40 / 12)
        period_rate = 0.40 * 40 / 365
        adjusted_cost = 1100 + 100 - 1100 * period_rate
        self.assertAlmostEqual(
            long_payload_item["adjusted_exercise_plus_premium"], adjusted_cost
        )
        self.assertAlmostEqual(
            long_payload_item["adjusted_cost_vs_base_percent"],
            (adjusted_cost - 1000) / 1000 * 100,
        )
        self.assertAlmostEqual(
            long_payload_item["adjusted_cost_to_base_percent"],
            adjusted_cost / 1000 * 100 - 100,
        )
        self.assertAlmostEqual(
            long_payload_item["exercise_discount_percent"], period_rate * 100
        )
        self.assertAlmostEqual(
            long_payload_item["risk_free_adjusted_strike"], 1100 * (1 - period_rate)
        )
        self.assertIsNotNone(covered_item["option_delta"])
        self.assertAlmostEqual(
            covered_item["option_delta"] + covered_item["strategy_delta"], 1.0, places=4
        )
        self.assertIn("covered_score", covered_item)
        self.assertIn("liquidity", covered_item["covered_score_components"])
        self.assertGreaterEqual(covered_item["covered_score"], 0)
        self.assertLessEqual(covered_item["covered_score"], 100)
        self.assertEqual(long_payload_item["option_delta"], long_payload_item["strategy_delta"])
        self.assertEqual(payload["covered_call"][0]["market"], "goods")
        self.assertEqual(payload["top_opportunities"]["covered_call"]["goods"], [])
        self.assertEqual(payload["top_opportunities"]["long_underlying"]["goods"][0]["symbol"], "KA-LONG")
        self.assertAlmostEqual(
            payload["top_opportunities"]["long_underlying"]["goods"][0]["adjusted_exercise_plus_premium"],
            adjusted_cost,
        )
        self.assertEqual(
            payload["price_variants"]["covered_call"]["last"]["groups"][0]["items"][0]["price_basis"],
            "last",
        )
        self.assertEqual(
            payload["price_variants"]["long_underlying"]["bid"]["groups"][0]["items"][0]["calculation_price"],
            100,
        )
        self.assertEqual(
            payload["price_variants"]["long_underlying"]["ask"]["groups"][0]["items"][0]["calculation_price"],
            120,
        )
        self.assertEqual(
            payload["price_variants"]["long_underlying"]["ask"]["groups"][0]["items"][0]["price_basis"],
            "ask",
        )

    def test_tehran_market_is_included_in_filters_and_top_five(self):
        contract = Contract(
            asset="خودرو", source_asset="خودرو", symbol="ضخود7131",
            expiry="2026-09-16", days=60, state="ITM", transaction_value=10,
            annual_return=80, expiry_return=13, base_price=500, option_bid=60,
            strike=550, breakeven=440, itm_percent=-10,
        )
        scan = ScanResult(
            generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=ZoneInfo("Asia/Tehran")),
            contracts=[], covered_call={}, long_underlying={},
            tehran_contracts=[contract],
            tehran_covered_call={("خودرو", contract.expiry): [Pick("ITM · بیشترین سود سالانه", "سود سالانه", contract)]},
        )
        payload = build_dashboard_payload(scan, Settings())
        self.assertEqual(payload["covered_call"][0]["market"], "tehran")
        self.assertEqual(payload["covered_call"][0]["expiry_display"], "1405/06/25")
        self.assertEqual(payload["summary"]["by_market"]["tehran"]["covered_contracts"], 1)
        self.assertEqual(payload["top_opportunities"]["covered_call"]["tehran"][0]["symbol"], "ضخود7131")
        self.assertEqual(payload["top_opportunities"]["covered_call"]["tehran"][0]["expiry_display"], "1405/06/25")

    def test_complete_tehran_table_calculates_every_row_from_executable_quotes(self):
        scan = ScanResult(
            generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=ZoneInfo("Asia/Tehran")),
            contracts=[], covered_call={}, long_underlying={},
            tehran_trade_rows=[{
                "baseSymbol": "شستا", "symbolOption": "ضستا6050",
                "askPrice1Base": 2_500, "bestAskBase": 2_500, "bestBidBase": 2_490,
                "lastTradeBase": 2_480, "closingPriceBase": 2_490,
                "baseQueueStatus": "صف خرید", "bidPrice1Option": 300,
                "askPrice1Option": 310,
                "lastTradeOption": 290, "closingPriceOption": 295,
                "dueDatePrice": 2_400, "expiration_date": "2026-08-19",
                "days": 32, "volume": 12, "value": 3_600,
            }],
        )
        row = build_dashboard_payload(scan, Settings())["tehran_covered_call_table"][0]
        self.assertEqual(row["asset"], "شستا")
        self.assertEqual(row["base_best_ask"], 2_500)
        self.assertEqual(row["base_last"], 2_480)
        self.assertEqual(row["option_best_bid"], 300)
        self.assertEqual(row["base_queue_status"], "صف خرید")
        self.assertAlmostEqual(row["expiry_return"], 8.0)
        self.assertAlmostEqual(row["annual_return"], 91.25)
        self.assertAlmostEqual(row["monthly_return"], 91.25 / 12, places=2)
        self.assertAlmostEqual(row["premium_to_base_percent"], 300 / 2_500 * 100)
        self.assertAlmostEqual(row["buyback_percent"], 300 / 2_500 * 100)
        self.assertAlmostEqual(row["buyback_annual_percent"], 300 / 2_500 * 100 * 365 / 32)
        self.assertAlmostEqual(row["buyback_monthly_percent"], 300 / 2_500 * 100 * 365 / 32 / 12)
        self.assertIsNotNone(row["option_delta"])
        self.assertAlmostEqual(row["option_delta"] + row["strategy_delta"], 1, places=4)
        self.assertIsNotNone(row["covered_score"])
        self.assertIn("liquidity", row["covered_score_components"])
        self.assertIsNotNone(row["downside_protection_percent"])
        self.assertEqual(row["breakeven"], 2_200)
        self.assertEqual(row["option_bid"], 300)
        self.assertFalse(row["transaction_zero"])
        self.assertEqual(row["source_asset"], "شستا")
        last_row = build_dashboard_payload(scan, Settings())["covered_overview_candidates"]["last"]["tehran"][0]
        expected_last_expiry = (290 - 100) / 2_500 * 100
        self.assertEqual(last_row["calculation_price"], 290)
        self.assertEqual(last_row["price_basis"], "last")
        self.assertAlmostEqual(last_row["expiry_return"], expected_last_expiry, places=2)
        self.assertAlmostEqual(last_row["buyback_percent"], 290 / 2_500 * 100)
        variants = build_dashboard_payload(scan, Settings())["strategy_table_variants"]
        last_base_row = variants["covered_call"]["bid"]["last"]["tehran"][0]
        self.assertEqual(last_base_row["base_price"], 2_480)
        self.assertEqual(last_base_row["base_price_basis"], "last")
        self.assertAlmostEqual(
            last_base_row["expiry_return"], (300 - 80) / 2_480 * 100, places=2
        )
        ask_option_bid_base = variants["covered_call"]["ask"]["bid"]["tehran"][0]
        self.assertEqual(ask_option_bid_base["calculation_price"], 310)
        self.assertEqual(ask_option_bid_base["base_price"], 2_490)
        self.assertEqual(ask_option_bid_base["price_basis"], "ask")
        self.assertEqual(ask_option_bid_base["base_price_basis"], "bid")

    def test_strategy_tables_include_goods_and_interest_adjusted_long_view(self):
        goods_row = {
            "baseSymbol": "کهربا", "symbolOption": "KAMO06C1000",
            "askPrice1Base": 1_200, "bestAskBase": 1_200,
            "lastTradeBase": 1_190, "closingPriceBase": 1_195,
            "baseQueueStatus": "عادی", "askPrice1Option": 115,
            "bidPrice1Option": 100, "lastTradeOption": 110,
            "closingPriceOption": 108, "dueDatePrice": 1_000,
            "expiration_date": "2026-09-01", "days": 30,
            "volume": 20, "value": 2_000,
        }
        scan = ScanResult(
            generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=ZoneInfo("Asia/Tehran")),
            contracts=[], covered_call={}, long_underlying={}, goods_trade_rows=[goods_row],
        )
        tables = build_dashboard_payload(scan, Settings())["strategy_tables"]
        covered = tables["covered_call"]["goods"][0]
        long_row = tables["long_underlying"]["goods"][0]
        self.assertAlmostEqual(covered["expiry_return"], (100 - 200) / 1_200 * 100, places=2)
        self.assertEqual(long_row["calculation_price"], 110)
        expected_cost = 1_000 + 110 - 1_000 * 0.40 * 30 / 365
        self.assertAlmostEqual(long_row["adjusted_exercise_plus_premium"], expected_cost)
        self.assertAlmostEqual(long_row["advantage_percent"], (1_200 - expected_cost) / 1_200 * 100)
        self.assertAlmostEqual(long_row["premium_to_base_percent"], 110 / 1_200 * 100, places=2)
        self.assertAlmostEqual(long_row["leverage"], 1_200 / 110, places=2)
        self.assertEqual(long_row["recommendation"], "خرید اختیار")
        self.assertEqual(long_row["option_best_bid"], 100)
        self.assertEqual(long_row["option_best_ask"], 115)
        self.assertAlmostEqual(
            covered["option_gap_percent"], (110 - 100) / 110 * 100, places=2
        )
        self.assertAlmostEqual(
            long_row["option_gap_percent"], (115 - 110) / 110 * 100, places=2
        )
        variants = build_dashboard_payload(scan, Settings())["strategy_table_variants"]
        ask_option_last_base = variants["long_underlying"]["ask"]["last"]["goods"][0]
        self.assertEqual(ask_option_last_base["calculation_price"], 115)
        self.assertEqual(ask_option_last_base["base_price"], 1_190)
        expected_variant_cost = 1_000 + 115 - 1_000 * 0.40 * 30 / 365
        self.assertAlmostEqual(
            ask_option_last_base["advantage_percent"],
            (1_190 - expected_variant_cost) / 1_190 * 100,
        )


if __name__ == "__main__":
    unittest.main()
