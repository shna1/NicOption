const PAGE_BY_PATH = {
  "/dashboard": "overview", "/index.html": "overview",
  "/articles": "articles",
  "/opportunities": "market", "/opportunities/covered-call": "market", "/opportunities/long-call": "market",
  "/market": "tehran-options", "/market/covered-call": "tehran-options", "/market/long-call": "tehran-options",
  "/tehran-options": "tehran-options", "/commodity-exchange": "commodity-exchange", "/order-flow": "order-flow", "/forecast": "forecast", "/economic-indicators": "economic-indicators", "/economic-comparison": "economic-comparison", "/statistical-center": "statistical-center", "/central-bank": "central-bank", "/monetary-details": "central-bank",
  "/trades": "trades", "/trades/open": "trades", "/trades/closed": "closed-trades", "/trades/new": "trades", "/closed-trades": "closed-trades",
  "/performance": "profit-recognition", "/performance/overview": "profit-recognition", "/performance/covered-call": "profit-recognition", "/performance/long-call": "profit-recognition", "/performance/realized-profit": "profit-recognition",
  "/profit-recognition": "profit-recognition", "/calculator": "calculator", "/settings": "settings", "/methodology": "methodology", "/help": "settings"
};
function pageForPath(pathname) {
  if (PAGE_BY_PATH[pathname]) return PAGE_BY_PATH[pathname];
  if (pathname.startsWith("/articles/")) return "articles";
  if (pathname.startsWith("/opportunities/")) return "market";
  if (pathname.startsWith("/market/contracts/")) return "tehran-options";
  if (pathname.startsWith("/trades/")) return "trades";
  return "overview";
}
const currentPage = pageForPath(window.location.pathname);
if (window.location.pathname === "/trades") {
  window.history.replaceState(window.history.state, "", `/trades/open${window.location.search}${window.location.hash}`);
}
const PAGE_TITLES = {overview: "داشبورد", articles: "مقالات", market: "فرصت‌ها", "tehran-options": "داده‌های بازار", "commodity-exchange": "بورس کالا", "order-flow": "جریان سفارشات", forecast: "پیش‌بینی", "economic-indicators": "داده‌های اقتصادی", "economic-comparison": "مقایسه روندها", "statistical-center": "داده‌های مرکز آمار", "central-bank": "داده‌های بانک مرکزی", trades: "معاملات باز", "profit-recognition": "گزارش عملکرد", "closed-trades": "معاملات بسته‌شده", calculator: "ماشین‌حساب", methodology: "روش محاسبات", settings: "تنظیمات"};
const USER_SETTINGS_STORAGE_KEY = "nicoption.user-settings.v3";
const DEFAULT_USER_SETTINGS = Object.freeze({textScale:100, theme:"system", appearance:"glass", refreshMinutes:10});
const storedMarketPricing = loadStoredObject("nicoption.market-pricing.v1");
const DEFAULT_PAGE_ACCESS = Object.freeze({show_overview:true,show_articles:true,show_option_market:true,show_economic_data:true,show_market:true,show_tehran_options:true,show_commodity_exchange:true,show_trades:true,show_closed_trades:true,show_profit_recognition:true,show_calculator:true,show_settings:true,show_order_flow:true,show_forecast:true});
const marketDataParams = new URLSearchParams(location.search);
const requestedMarketDataView = marketDataParams.get("view");
const initialMarketDataView = ["all","covered_call","long_underlying"].includes(requestedMarketDataView) ? requestedMarketDataView : "all";
const state = { data: null, articles: [], forecast: null, commodityFx: null, orderFlowCatalog: [], orderFlowMarket: "tehran", orderFlowType: "option", orderFlowTimer: null, trades: [], tradeContracts: [], underlyingPositions: [], underlyingQuotes: [], account: {}, strategy: "all", market: "all", asset: "all", status: "all", search: "", profitMode: "with_underlying", coveredBasis: ["bid","ask","last"].includes(storedMarketPricing.covered_option_basis) ? storedMarketPricing.covered_option_basis : "bid", coveredBaseBasis: ["bid","ask","last"].includes(storedMarketPricing.covered_base_basis) ? storedMarketPricing.covered_base_basis : "ask", longBasis: ["bid","ask","last"].includes(storedMarketPricing.long_option_basis) ? storedMarketPricing.long_option_basis : "ask", longBaseBasis: ["bid","ask","last"].includes(storedMarketPricing.long_base_basis) ? storedMarketPricing.long_base_basis : "ask", longInterestRate: null, coveredRanking: "score", marketDataView: initialMarketDataView, chainStrategy: initialMarketDataView === "long_underlying" ? "long_underlying" : "covered_call", chainMarket: marketDataParams.get("market") || "tehran", chainSearch: marketDataParams.get("q") || "", chainState: marketDataParams.get("moneyness") || "all", chainItmOperator: "gte", chainItmValue: null, chainQueue: "all", chainTransactionOperator: "gte", chainTransactionValue: 0, chainDaysOperator: "gt", chainDaysMin: null, chainAnnualMin: null, chainSortKey: initialMarketDataView === "all" ? "symbol" : initialMarketDataView === "covered_call" ? "annual_return" : "advantage_percent", chainSortDirection: "desc", chainColumnOrders: loadStoredObject("nicoption.chain-column-orders.v2"), chainHiddenColumns: loadStoredObject("nicoption.chain-hidden-columns.v2"), chainSavedViews: loadStoredObject("nicoption.chain-saved-views.v1"), chainAllColumnKeys: [], chainVisibleColumnKeys: [], chainDraggedColumn: null, tradeFullView: false, closedTradeFullView: false, tradeStrategyFilter: {open:"all",closed:"all"}, tradePricing: {covered_option_basis:"last",covered_base_basis:"last",long_option_basis:"last",long_base_basis:"last"}, serverPreferences: {...DEFAULT_PAGE_ACCESS}, userSettings: loadUserSettings(), details: new Map() };
state.marketStrikeMin=numericFilterValue(marketDataParams.get("strike_min"));state.marketStrikeMax=numericFilterValue(marketDataParams.get("strike_max"));state.marketVolumeMin=numericFilterValue(marketDataParams.get("volume_min"));state.marketOpenInterestMin=numericFilterValue(marketDataParams.get("oi_min"));state.marketValidQuotesOnly=marketDataParams.get("valid_quotes")==="1";
state.dashboardStrategy = new URLSearchParams(location.search).get("dashboard_strategy") || "all";
state.dashboardRange = new URLSearchParams(location.search).get("dashboard_range") || "3m";
const selectedTradeIds = new Set();
const selectedUnderlyingIds = new Set();
const $ = (id) => document.getElementById(id);
// Default brokerage rates. Amounts are suggestions only: every visible
// Commission remains editable by the user. New option trades use contract
// count, so the calculator converts it to underlying units exactly once.
const COMMISSION_RATES = Object.freeze({
  tehran: Object.freeze({underlyingBuy:0.003712, underlyingSell:0.0088, optionBuy:0.00103, optionSell:0.00103, optionExercise:0.0005}),
  goods: Object.freeze({underlyingBuy:0.003712, underlyingSell:0.0088, optionBuy:0.0012, optionSell:0.0012, optionExercise:0.0012}),
});
const commissionRate = (market, key) => (COMMISSION_RATES[market] || COMMISSION_RATES.tehran)[key] || 0;
const calculatedCommission = (price, quantity, rate) => Math.max(0, Math.round(Number(price || 0) * Number(quantity || 0) * Number(rate || 0)));
function setAutomaticCommission(input, value, {force=false}={}) {
  if (!input || (!force && input.dataset.commissionManual === "true")) return;
  input.value = String(value || 0);
  input.dataset.commissionManual = "false";
}
function markCommissionManual(event) {
  if (event.isTrusted) event.currentTarget.dataset.commissionManual = "true";
}
const commissionSourceLabel = (source) => source === "estimated" ? "برآورد سامانه" : source === "actual" ? "ثبت کاربر" : "نامشخص";
const esc = (value) => String(value ?? "—").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const csrfToken = () => document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("csrftoken="))?.split("=").slice(1).join("=") || "";
const apiFetch = (resource, options = {}) => {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRFToken", decodeURIComponent(token));
  }
  return fetch(resource, {...options, headers, credentials:"same-origin"});
};
async function loadIdentity() {
  const response = await apiFetch("/api/v1/me", {cache:"no-store"});
  if (response.status === 401 || response.status === 403) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
    return;
  }
  if (!response.ok) throw new Error("دریافت اطلاعات حساب ناموفق بود");
  const user = await response.json();
  $("currentUsername").textContent = user.username;
  if (user.is_superuser) $("currentUsername").title = "مدیر کل سایت";
  return true;
}

function applyServerPreferences() {
  document.querySelectorAll("[data-feature]").forEach((item) => {
    item.hidden = !state.serverPreferences[`show_${item.dataset.feature}`];
  });
  document.querySelectorAll("[data-feature-any]").forEach((item) => {
    const features = item.dataset.featureAny.split(",").map((feature) => feature.trim()).filter(Boolean);
    item.hidden = !features.some((feature) => state.serverPreferences[`show_${feature}`]);
  });
  const tradesPrimaryLink = $("tradesPrimaryLink");
  if (tradesPrimaryLink) tradesPrimaryLink.href = state.serverPreferences.show_trades ? "/trades/open" : "/trades/closed";
  const marketPrimaryLink = $("marketPrimaryLink");
  if (marketPrimaryLink) {
    const firstMarketRoute = [
      ["show_tehran_options", "/market"],
      ["show_commodity_exchange", "/commodity-exchange"],
      ["show_order_flow", "/order-flow"],
      ["show_forecast", "/forecast"],
    ].find(([permission]) => state.serverPreferences[permission]);
    if (firstMarketRoute) marketPrimaryLink.href = firstMarketRoute[1];
  }
  const navigation = $("mainNavigation");
  if (navigation) {
    navigation.querySelectorAll(".nav-section").forEach((section) => {
      const visibleChild = [...section.querySelectorAll(":scope > .nav-children > li > a")].some((link) => !link.hidden);
      // Preferences arrive asynchronously; always recompute visibility so a
      // previously hidden section cannot return as an empty dropdown.
      section.hidden = !visibleChild;
    });
    const visibleCount = [...navigation.querySelectorAll("[data-feature]")].filter((item) => !item.hidden).length;
    navigation.style.setProperty("--visible-nav-count", String(Math.max(1, visibleCount)));
  }
}

async function loadServerPreferences() {
  const response = await apiFetch("/api/v1/preferences", {cache:"no-store"});
  if (!response.ok) throw new Error("دریافت تنظیمات حساب ناموفق بود");
  state.serverPreferences = {...DEFAULT_PAGE_ACCESS,...await response.json()};
  applyServerPreferences();
}

function articleBodyMarkup(body) {
  const value = String(body || "");
  if (/<(p|div|h2|h3|blockquote|ul|ol|figure|img)\b/i.test(value)) return value;
  return value.split(/\n{2,}/).map((paragraph) => `<p>${esc(paragraph).replace(/\n/g,"<br>")}</p>`).join("");
}

function articleSourceMarkup(source) {
  if (!source || source.kind !== "x" || !source.url) return "";
  return `<aside class="article-source" aria-labelledby="articleSourceTitle"><div><small id="articleSourceTitle">منبع و متن اصلی</small><strong>${esc(source.label || "X")}</strong><span>${esc(source.translation_notice || "ترجمه فارسی")}</span></div><blockquote dir="ltr" lang="en">${esc(source.original_text || "")}</blockquote><a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">مشاهده پست اصلی در X</a></aside>`;
}

function renderArticlesPage() {
  const host = $("articlesPage");
  if (!host || currentPage !== "articles") return;
  const requestedSlug = decodeURIComponent(location.pathname.replace(/^\/articles\/?/, ""));
  if (requestedSlug) {
    const article = state.articles.find((item) => item.slug === requestedSlug);
    host.innerHTML = article
      ? `<article class="article-detail"><a class="article-back" href="/articles">بازگشت به مقالات</a><header>${article.source ? `<span class="article-source-badge">ترجمه از ${esc(article.source.label)}</span>` : ""}<small>${esc(article.published_at_display)} · ${esc(article.author)}</small><h1>${esc(article.title)}</h1><p>${esc(article.summary)}</p></header><div class="article-body">${articleBodyMarkup(article.body)}</div>${articleSourceMarkup(article.source)}</article>`
      : '<div class="articles-empty"><strong>مقاله موردنظر پیدا نشد.</strong><p>ممکن است مقاله منتشر نشده یا نشانی آن تغییر کرده باشد.</p><a href="/articles">مشاهده همه مقالات</a></div>';
  } else if (state.articles.length) {
    host.innerHTML = `<div class="articles-list">${state.articles.map((article, index) => `<article class="article-card${index===0?" featured":""}">${article.source ? `<span class="article-source-badge">ترجمه از ${esc(article.source.label)}</span>` : ""}<small>${esc(article.published_at_display)} · ${esc(article.author)}</small><h3><a href="/articles/${encodeURIComponent(article.slug)}">${esc(article.title)}</a></h3><p>${esc(article.summary)}</p><a class="article-read-link" href="/articles/${encodeURIComponent(article.slug)}">مطالعه مطلب</a></article>`).join("")}</div>`;
  } else {
    host.innerHTML = '<div class="articles-empty"><strong>هنوز مقاله‌ای منتشر نشده است.</strong><p>مقاله‌های تازه پس از انتشار در این صفحه نمایش داده می‌شوند.</p></div>';
  }
  host.setAttribute("aria-busy", "false");
}

async function loadArticles() {
  const response = await apiFetch("/api/articles?limit=50", {cache:"no-store"});
  if (!response.ok) throw new Error("دریافت مقالات ناموفق بود");
  const payload = await response.json();
  state.articles = Array.isArray(payload.articles) ? payload.articles : [];
  renderArticlesPage();
}

function tradeImportFileError(file) {
  if (!file) return "ابتدا فایل CSV را انتخاب کنید.";
  if (!file.name.toLowerCase().endsWith(".csv")) return "پسوند فایل باید CSV باشد.";
  if (file.size === 0) return "فایل انتخاب‌شده خالی است.";
  if (file.size > 2 * 1024 * 1024) return "حجم فایل نباید بیشتر از ۲ مگابایت باشد.";
  return "";
}

function renderTradeImportResult(form, payload, tone = "") {
  const result = form.querySelector(".trade-import-result");
  result.className = `trade-import-result ${tone}`.trim();
  if (tone === "loading") {
    result.innerHTML = "<strong>در حال بررسی فایل…</strong><span>تا پایان بررسی چیزی در حساب ثبت نمی‌شود.</span>";
    return;
  }
  if (payload.errors?.length) {
    const rows = payload.errors.map((item) => `<li>ردیف ${num(item.row)}: ${esc(item.detail)}</li>`).join("");
    result.innerHTML = `<strong>${esc(payload.detail || "فایل نیاز به اصلاح دارد.")}</strong><ul>${rows}</ul>`;
    return;
  }
  if (payload.mode === "preview") {
    const breakdown = payload.valid_underlyings
      ? ` شامل ${num(payload.valid_trades)} معامله اختیار و ${num(payload.valid_underlyings)} دارایی پایه`
      : "";
    result.innerHTML = `<strong>${num(payload.valid)} موقعیت معتبر آماده ثبت است${breakdown}.</strong><span>هیچ داده‌ای هنوز ذخیره نشده است.</span>`;
    return;
  }
  const breakdown = payload.imported_underlyings
    ? ` · ${num(payload.imported_underlyings)} دارایی پایه و ${num(payload.imported_trades)} معامله اختیار`
    : "";
  result.innerHTML = `<strong>${num(payload.imported)} موقعیت ثبت شد${breakdown}.</strong><span>${num(payload.skipped)} موقعیت تکراری نادیده گرفته شد.</span><a href="${payload.status === "closed" ? "/closed-trades" : "/trades"}">مشاهده موقعیت‌ها</a>`;
}

async function submitTradeImport(form, confirmImport) {
  const input = form.elements.file;
  const file = input.files?.[0];
  const error = tradeImportFileError(file);
  const confirmButton = form.querySelector(".trade-import-confirm");
  const buttons = form.querySelectorAll("button");
  if (error) {
    renderTradeImportResult(form, {detail:error, errors:[{row:"—",detail:error}]}, "error");
    input.setAttribute("aria-invalid", "true");
    input.focus();
    return;
  }
  input.removeAttribute("aria-invalid");
  buttons.forEach((button) => { button.disabled = true; });
  renderTradeImportResult(form, {mode:"preview",valid:"…"}, "loading");
  const data = new FormData();
  data.append("file", file);
  data.append("status", form.dataset.importStatus);
  data.append("confirm", String(confirmImport));
  try {
    const response = await apiFetch("/api/v1/trade-imports", {method:"POST",body:data});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const errors = payload.errors || [{row:"—",detail:payload.detail || "بررسی فایل ناموفق بود."}];
      renderTradeImportResult(form, {...payload,errors}, "error");
      confirmButton.classList.add("hidden");
      return;
    }
    renderTradeImportResult(form, payload, payload.mode === "import" ? "success" : "ready");
    confirmButton.classList.toggle("hidden", payload.mode !== "preview" || payload.invalid > 0);
    if (payload.mode === "import") {
      input.value = "";
      form.querySelector(".trade-import-file").textContent = "ثبت انجام شد؛ برای ورود فایل دیگر آن را انتخاب کنید.";
    }
  } catch (requestError) {
    renderTradeImportResult(form, {errors:[{row:"—",detail:"ارتباط با سرور برقرار نشد؛ فایل حفظ شده و می‌توانید دوباره تلاش کنید."}]}, "error");
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

async function logoutCurrentUser() {
  const button = $("logoutButton");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    const response = await apiFetch("/api/v1/auth/logout", {method:"POST"});
    if (!response.ok) throw new Error("خروج از حساب ناموفق بود");
    window.location.assign("/login");
  } catch (error) {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    setStatus("error", error.message || "خروج از حساب ناموفق بود");
  }
}

const PASSWORD_ERROR_TARGETS = {
  old_password: "currentPasswordError",
  new_password1: "newPasswordError",
  new_password2: "confirmPasswordError",
};

function clearPasswordChangeErrors(form) {
  Object.values(PASSWORD_ERROR_TARGETS).forEach((id) => { $(id).textContent = ""; });
  form.querySelectorAll("input").forEach((input) => input.removeAttribute("aria-invalid"));
  const message = $("passwordChangeMessage");
  message.className = "password-change-message";
  message.textContent = "";
}

function setPasswordChangeMessage(tone, text) {
  const message = $("passwordChangeMessage");
  message.className = `password-change-message ${tone}`;
  message.textContent = text;
}

function showPasswordChangeErrors(form, errors = {}) {
  let firstInvalid = null;
  Object.entries(errors).forEach(([field, messages]) => {
    const targetId = PASSWORD_ERROR_TARGETS[field];
    if (!targetId) return;
    const input = form.elements[field];
    $(targetId).textContent = Array.isArray(messages) ? messages.join(" ") : String(messages);
    input.setAttribute("aria-invalid", "true");
    firstInvalid ||= input;
  });
  firstInvalid?.focus();
}

async function submitPasswordChange(form) {
  clearPasswordChangeErrors(form);
  const values = Object.fromEntries(new FormData(form).entries());
  const localErrors = {};
  if (!values.old_password) localErrors.old_password = ["رمز عبور فعلی را وارد کنید."];
  if (!values.new_password1) localErrors.new_password1 = ["رمز عبور جدید را وارد کنید."];
  if (!values.new_password2) localErrors.new_password2 = ["تکرار رمز عبور جدید را وارد کنید."];
  else if (values.new_password1 !== values.new_password2) localErrors.new_password2 = ["دو رمز عبور جدید یکسان نیستند."];
  if (Object.keys(localErrors).length) {
    setPasswordChangeMessage("error", "لطفاً خطاهای مشخص‌شده را اصلاح کنید.");
    showPasswordChangeErrors(form, localErrors);
    return;
  }

  const submitButton = form.querySelector("button[type='submit']");
  submitButton.disabled = true;
  submitButton.setAttribute("aria-busy", "true");
  const originalLabel = submitButton.textContent;
  submitButton.textContent = "در حال تغییر…";
  try {
    const response = await apiFetch("/api/v1/auth/password", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(values),
    });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401 || response.status === 403) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    if (!response.ok) {
      setPasswordChangeMessage("error", payload.detail || "تغییر رمز عبور انجام نشد.");
      showPasswordChangeErrors(form, payload.errors || {});
      return;
    }
    form.reset();
    setPasswordChangeMessage("success", payload.detail || "رمز عبور با موفقیت تغییر کرد.");
  } catch (error) {
    setPasswordChangeMessage("error", "ارتباط با سرور برقرار نشد؛ دوباره تلاش کنید.");
  } finally {
    submitButton.disabled = false;
    submitButton.removeAttribute("aria-busy");
    submitButton.textContent = originalLabel;
  }
}
const num = (value, digits = 0) => value == null ? "—" : Number(value).toLocaleString("fa-IR", {maximumFractionDigits: digits, minimumFractionDigits: digits});
const qty = (value) => value == null ? "—" : Number(value).toLocaleString("fa-IR", {maximumFractionDigits: 2, minimumFractionDigits: 0});
const pct = (value, threshold) => value == null ? "—" : `${value < threshold ? '<span class="warning">⚠️ ' : ""}${num(value, 2)}٪${value < threshold ? "</span>" : ""}`;
const quoteGap = (value) => value == null ? "—" : `${Number(value) > 0 ? "+" : ""}${num(value, 2)}٪`;
const deltaValue = (value) => value == null ? "—" : num(value, 3);
const deltaDisplay = (item, key = "option_delta") => item?.[key] == null ? "—" : `${item.delta_estimated ? "≈" : ""}${deltaValue(item[key])}`;
const scoreValue = (item) => item?.covered_score == null ? "—" : num(item.covered_score, 1);
const valueTone = (value) => Number(value) < 0 ? "negative-value" : "positive-value";
const premiumToBasePercent = (item) => {
  if (item?.premium_to_base_percent != null) return Number(item.premium_to_base_percent);
  const premium = Number(item?.calculation_price), base = Number(item?.base_price);
  return Number.isFinite(premium) && Number.isFinite(base) && base > 0 ? premium / base * 100 : null;
};
const leverageRatio = (item) => {
  if (item?.leverage != null) return Number(item.leverage);
  const premium = Number(item?.calculation_price), base = Number(item?.base_price);
  return Number.isFinite(premium) && premium > 0 && Number.isFinite(base) ? base / premium : null;
};
const buybackPercent = (item) => item?.buyback_percent == null ? premiumToBasePercent(item) : Number(item.buyback_percent);
const buybackAnnualPercent = (item) => {
  if (item?.buyback_annual_percent != null) return Number(item.buyback_annual_percent);
  const period = buybackPercent(item), days = Number(item?.days);
  return period == null || !Number.isFinite(days) || days <= 0 ? null : period * 365 / days;
};
const buybackMonthlyPercent = (item) => item?.buyback_monthly_percent == null
  ? (buybackAnnualPercent(item) == null ? null : buybackAnnualPercent(item) / 12)
  : Number(item.buyback_monthly_percent);
const scoreComponentLabels = {return: "بازده", protection: "حاشیه امن", liquidity: "نقدشوندگی", delta: "دلتا", time: "سررسید", quote: "کیفیت قیمت"};
const badge = (status) => `<span class="badge ${status === "ITM" ? "itm" : "otm"}">${esc(status)}</span>`;
const marketLabel = (market) => market === "tehran" ? "بورس تهران" : "بورس کالا";
const faNorm = (value) => String(value ?? "").normalize("NFKC").replaceAll("ي", "ی").replaceAll("ك", "ک").replace(/[_\s‌]+/g, " ").trim().toLowerCase();
const LEVERAGED_ASSETS = new Set(["اهرم", "توان", "موج"]);
const isLeveragedFund = (asset) => LEVERAGED_ASSETS.has(String(asset || "").trim());
const CHAIN_COLUMN_STORAGE_KEY = "nicoption.chain-column-orders.v2";
const CHAIN_HIDDEN_STORAGE_KEY = "nicoption.chain-hidden-columns.v2";
const CHAIN_SAVED_VIEWS_STORAGE_KEY = "nicoption.chain-saved-views.v1";
const CHAIN_DEFAULT_VISIBLE_COLUMNS = Object.freeze({
  all: ["asset","symbol","contract_type","expiry","days","strike","itm_percent","option_best_bid","option_best_ask","option_last","option_price","spread_percent","option_volume","transaction_value","open_interest","updated_at","operations"],
  covered_call: ["asset","symbol","base_price","calculation_price","strike","expiry","days","market_premium_return","market_premium_return_yoy","market_strike_distance","breakeven","market_max_profit","downside_protection_percent","market_assignment_probability","market_foregone_upside","market_position_status"],
  long_underlying: ["asset","symbol","base_price","calculation_price","days","strike","itm_percent","option_queue_status","breakeven","adjusted_cost_to_base_percent"],
});
let refreshTimer = null;
let tradeJumpObserver = null;
let entryCalendarView = null;
let underlyingCalendarView = null;
let tradeDetailZIndex = 70;
let tradeDetailDrag = null;

function loadUserSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(USER_SETTINGS_STORAGE_KEY) || "{}");
    return {
      textScale: Math.min(130,Math.max(80,Number(saved.textScale) || DEFAULT_USER_SETTINGS.textScale)),
      theme: ["light","dark","system"].includes(saved.theme) ? saved.theme : DEFAULT_USER_SETTINGS.theme,
      appearance: "glass",
      refreshMinutes: Math.min(10,Math.max(1,Number(saved.refreshMinutes) || DEFAULT_USER_SETTINGS.refreshMinutes)),
    };
  } catch { return {...DEFAULT_USER_SETTINGS}; }
}

function saveUserSettings() {
  try { localStorage.setItem(USER_SETTINGS_STORAGE_KEY,JSON.stringify({...state.userSettings,visualSystemVersion:4})); }
  catch { /* Settings still apply for the current session. */ }
}

function applyUserSettings({announce=false}={}) {
  const systemDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true;
  const resolvedTheme = state.userSettings.theme === "system" ? (systemDark ? "dark" : "light") : state.userSettings.theme;
  document.documentElement.dataset.theme = resolvedTheme;
  document.documentElement.dataset.appearance = "glass";
  delete document.documentElement.dataset.applePalette;
  document.documentElement.style.fontSize = `${state.userSettings.textScale}%`;
  $("textScaleSetting").value = state.userSettings.textScale;
  $("textScaleValue").textContent = `${num(state.userSettings.textScale)}٪`;
  $("refreshIntervalSetting").value = state.userSettings.refreshMinutes;
  $("refreshIntervalValue").textContent = `${num(state.userSettings.refreshMinutes)} دقیقه`;
  const darkMode = resolvedTheme === "dark";
  const themeToggle = $("themeToggle");
  themeToggle.setAttribute("aria-pressed", String(darkMode));
  themeToggle.setAttribute("aria-label", darkMode ? "فعال‌کردن حالت روشن" : "فعال‌کردن حالت تاریک");
  themeToggle.title = darkMode ? "حالت روشن" : "حالت تاریک";
  if (announce) {
    const themeLabel = state.userSettings.theme === "system" ? "هماهنگ با سیستم" : darkMode ? "تیره" : "روشن";
    $("settingsMessage").textContent = `ذخیره شد · تم ${themeLabel} · متن ${num(state.userSettings.textScale)}٪ · تازه‌سازی هر ${num(state.userSettings.refreshMinutes)} دقیقه`;
  }
}

function updateUserSettings(changes) {
  state.userSettings = {...state.userSettings,...changes};
  saveUserSettings();
  applyUserSettings({announce:true});
  if (Object.prototype.hasOwnProperty.call(changes,"refreshMinutes")) {
    scheduleAutoRefresh();
    if (state.data) {
      renderRules(state.data);
      setDataLoadedStatus();
    }
  }
}

function scheduleAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  if (currentPage === "order-flow") return scheduleOrderFlowRefresh();
  refreshTimer = setInterval(()=>currentPage === "forecast" ? loadForecast(true) : currentPage === "commodity-exchange" ? loadCommodityFx(true) : loadData(true),state.userSettings.refreshMinutes*60*1000);
}

function loadStoredObject(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch { return {}; }
}

function saveChainColumnOrders() {
  try { localStorage.setItem(CHAIN_COLUMN_STORAGE_KEY, JSON.stringify(state.chainColumnOrders)); }
  catch { /* The table remains usable when browser storage is disabled. */ }
}

function saveChainHiddenColumns() {
  try { localStorage.setItem(CHAIN_HIDDEN_STORAGE_KEY, JSON.stringify(state.chainHiddenColumns)); }
  catch { /* The table remains usable when browser storage is disabled. */ }
}

function saveChainViews() {
  try { localStorage.setItem(CHAIN_SAVED_VIEWS_STORAGE_KEY, JSON.stringify(state.chainSavedViews)); }
  catch { /* Named views remain usable for the current session. */ }
}

function initializePageNavigation() {
  document.body.dataset.page = currentPage;
  document.title = `${PAGE_TITLES[currentPage]} · nicoption`;
  document.querySelectorAll("[data-page-view]").forEach((section) => section.classList.toggle("page-hidden", section.dataset.pageView !== currentPage));
  document.querySelectorAll("[data-page-link],[data-path-link]").forEach((link) => {
    const aliases = (link.dataset.pageLinkAlias || "").split(",").filter(Boolean);
    const active = link.dataset.pathLink
      ? window.location.pathname === link.dataset.pathLink
      : link.dataset.pageLink === currentPage || aliases.includes(currentPage);
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  document.body.classList.add("page-ready");
}

applyUserSettings();
initializePageNavigation();

function setStatus(kind, message) {
  const banner = $("statusBanner");
  if (["economic-indicators","economic-comparison","statistical-center","central-bank"].includes(currentPage)) return;
  if (!banner) return;
  banner.className = `status-banner ${kind}`;
  banner.innerHTML = `${kind === "loading" ? '<span class="spinner"></span>' : ""}<span>${esc(message)}</span>`;
}

function setDataLoadedStatus() {
  if (currentPage === "tehran-options") {
    setStatus("success", `اطلاعات با موفقیت دریافت شد . تازه‌سازی بعدی تا ${num(state.userSettings.refreshMinutes)} دقیقه دیگر`);
    return;
  }
  const banner = $("statusBanner");
  banner.className = "status-banner hidden";
  banner.replaceChildren();
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fa-IR-u-ca-persian", {dateStyle: "short", timeStyle: "short", timeZone: "Asia/Tehran"}).format(new Date(iso));
}

function solarDate(value) {
  if (!value) return "—";
  const raw = String(value).trim();
  const normalized = raw.replaceAll("-", "/");
  const parts = normalized.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
  if (parts && Number(parts[1]) < 1700) {
    return `${parts[1]}/${parts[2].padStart(2, "0")}/${parts[3].padStart(2, "0")}`.replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);
  }
  const gregorian = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (gregorian) {
    const date = new Date(`${gregorian[1]}-${gregorian[2]}-${gregorian[3]}T12:00:00Z`);
    return new Intl.DateTimeFormat("fa-IR-u-ca-persian", {year: "numeric", month: "2-digit", day: "2-digit", timeZone: "Asia/Tehran"}).format(date);
  }
  return normalized.replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);
}

const JALALI_MONTH_NAMES = ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور","مهر","آبان","آذر","دی","بهمن","اسفند"];
const JALALI_WEEKDAYS = ["ش","ی","د","س","چ","پ","ج"];

function latinDigits(value) {
  return String(value ?? "")
    .replace(/[۰-۹]/g, (digit) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit)))
    .replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)));
}

function parseJalaliDate(value) {
  const match = latinDigits(value).trim().replaceAll("-", "/").match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
  if (!match) return null;
  const result = {year:Number(match[1]), month:Number(match[2]), day:Number(match[3])};
  return result.month >= 1 && result.month <= 12 && result.day >= 1 && result.day <= jalaliMonthLength(result.year, result.month) ? result : null;
}

function formatJalaliInput({year, month, day}) {
  return `${year}/${String(month).padStart(2,"0")}/${String(day).padStart(2,"0")}`;
}

function currentJalaliDate() {
  const parts = new Intl.DateTimeFormat("en-US-u-ca-persian", {year:"numeric",month:"numeric",day:"numeric",timeZone:"Asia/Tehran"}).formatToParts(new Date());
  const values = Object.fromEntries(parts.filter((part) => ["year","month","day"].includes(part.type)).map((part) => [part.type,Number(part.value)]));
  return values;
}

const calendarDiv = (value, divisor) => Math.trunc(value / divisor);
const calendarMod = (value, divisor) => value - Math.trunc(value / divisor) * divisor;

function jalaliCalendar(year) {
  const breaks = [-61,9,38,199,426,686,756,818,1111,1181,1210,1635,2060,2097,2192,2262,2324,2394,2456,3178];
  const gregorianYear = year + 621;
  let leapJ = -14;
  let previous = breaks[0];
  let jump = 0;
  if (year < previous || year >= breaks[breaks.length - 1]) throw new Error("سال شمسی خارج از محدوده تقویم است");
  for (let index = 1; index < breaks.length; index += 1) {
    const next = breaks[index];
    jump = next - previous;
    if (year < next) break;
    leapJ += calendarDiv(jump,33) * 8 + calendarDiv(calendarMod(jump,33),4);
    previous = next;
  }
  const offset = year - previous;
  leapJ += calendarDiv(offset,33) * 8 + calendarDiv(calendarMod(offset,33) + 3,4);
  if (calendarMod(jump,33) === 4 && jump - offset === 4) leapJ += 1;
  const leapG = calendarDiv(gregorianYear,4) - calendarDiv((calendarDiv(gregorianYear,100) + 1) * 3,4) - 150;
  return {gregorianYear, marchDay:20 + leapJ - leapG};
}

function gregorianToJdn(year, month, day) {
  const shiftedYear = year + calendarDiv(month - 8,6) + 100100;
  return calendarDiv(shiftedYear * 1461,4)
    + calendarDiv(153 * calendarMod(month + 9,12) + 2,5)
    + day - 34840408
    - calendarDiv(calendarDiv(shiftedYear,100) * 3,4)
    + 752;
}

function jalaliToJdn(year, month, day) {
  const calendar = jalaliCalendar(year);
  return gregorianToJdn(calendar.gregorianYear,3,calendar.marchDay)
    + (month - 1) * 31 - calendarDiv(month,7) * (month - 7) + day - 1;
}

function jalaliMonthLength(year, month) {
  if (month <= 6) return 31;
  if (month <= 11) return 30;
  return jalaliToJdn(year + 1,1,1) - jalaliToJdn(year,12,1);
}

function renderEntryDatePicker() {
  const picker = $("entryDatePicker");
  if (!picker || !entryCalendarView) return;
  const {year,month} = entryCalendarView;
  const selected = parseJalaliDate($("tradeForm").elements.entry_date.value);
  const today = currentJalaliDate();
  const firstWeekday = calendarMod(jalaliToJdn(year,month,1) + 2,7);
  const days = jalaliMonthLength(year,month);
  const blanks = Array.from({length:firstWeekday}, () => '<span class="jalali-empty" aria-hidden="true"></span>').join("");
  const dayButtons = Array.from({length:days}, (_,index) => {
    const day = index + 1;
    const isSelected = selected?.year === year && selected?.month === month && selected?.day === day;
    const isToday = today.year === year && today.month === month && today.day === day;
    return `<button type="button" data-jalali-day="${day}" class="${isSelected ? "selected" : ""} ${isToday ? "today" : ""}" aria-pressed="${isSelected}">${num(day)}</button>`;
  }).join("");
  const displayYear = String(year).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);
  picker.innerHTML = `<header><button type="button" data-jalali-nav="-1" aria-label="ماه قبل">‹</button><strong>${JALALI_MONTH_NAMES[month-1]} ${displayYear}</strong><button type="button" data-jalali-nav="1" aria-label="ماه بعد">›</button></header><div class="jalali-weekdays">${JALALI_WEEKDAYS.map((day) => `<span>${day}</span>`).join("")}</div><div class="jalali-days">${blanks}${dayButtons}</div><footer><button type="button" data-jalali-today>انتخاب امروز</button></footer>`;
}

function closeEntryDatePicker() {
  const picker = $("entryDatePicker");
  if (!picker) return;
  picker.classList.add("hidden");
  picker.classList.remove("open-upward","floating-calendar","centered-calendar");
  for (const property of ["top","right","bottom","left","transform"]) picker.style.removeProperty(property);
  $("entryDatePickerButton")?.setAttribute("aria-expanded","false");
}

function positionEntryDatePicker() {
  const picker = $("entryDatePicker");
  if (!picker || picker.classList.contains("hidden")) return;
  picker.classList.remove("open-upward");
  picker.classList.add("floating-calendar","centered-calendar");
}

function openEntryDatePicker() {
  const picker = $("entryDatePicker");
  if (!picker) return;
  const selected = parseJalaliDate($("tradeForm").elements.entry_date.value) || currentJalaliDate();
  entryCalendarView = {year:selected.year,month:selected.month};
  renderEntryDatePicker();
  picker.classList.remove("hidden");
  positionEntryDatePicker();
  $("entryDatePickerButton").setAttribute("aria-expanded","true");
}

function shiftEntryCalendar(months) {
  if (!entryCalendarView) entryCalendarView = currentJalaliDate();
  let month = entryCalendarView.month + months;
  let year = entryCalendarView.year;
  if (month < 1) { month = 12; year -= 1; }
  if (month > 12) { month = 1; year += 1; }
  entryCalendarView = {year,month};
  renderEntryDatePicker();
}

function renderUnderlyingDatePicker() {
  const picker = $("underlyingDatePicker");
  if (!picker || !underlyingCalendarView) return;
  const {year,month} = underlyingCalendarView;
  const selected = parseJalaliDate($("underlyingForm").elements.entry_date.value);
  const today = currentJalaliDate();
  const firstWeekday = calendarMod(jalaliToJdn(year,month,1) + 2,7);
  const days = jalaliMonthLength(year,month);
  const blanks = Array.from({length:firstWeekday}, () => '<span class="jalali-empty" aria-hidden="true"></span>').join("");
  const dayButtons = Array.from({length:days}, (_,index) => {
    const day = index + 1;
    const isSelected = selected?.year === year && selected?.month === month && selected?.day === day;
    const isToday = today.year === year && today.month === month && today.day === day;
    return `<button type="button" data-underlying-jalali-day="${day}" class="${isSelected ? "selected" : ""} ${isToday ? "today" : ""}" aria-pressed="${isSelected}">${num(day)}</button>`;
  }).join("");
  const displayYear = String(year).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);
  picker.innerHTML = `<header><button type="button" data-underlying-jalali-nav="-1" aria-label="ماه قبل">‹</button><strong>${JALALI_MONTH_NAMES[month-1]} ${displayYear}</strong><button type="button" data-underlying-jalali-nav="1" aria-label="ماه بعد">›</button></header><div class="jalali-weekdays">${JALALI_WEEKDAYS.map((day) => `<span>${day}</span>`).join("")}</div><div class="jalali-days">${blanks}${dayButtons}</div><footer><button type="button" data-underlying-jalali-today>انتخاب امروز</button></footer>`;
}

function positionUnderlyingDatePicker() {
  const picker = $("underlyingDatePicker");
  if (!picker || picker.classList.contains("hidden")) return;
  picker.classList.remove("open-upward");
  picker.classList.add("floating-calendar","centered-calendar");
}

function closeUnderlyingDatePicker() {
  const picker = $("underlyingDatePicker");
  if (!picker) return;
  picker.classList.add("hidden"); picker.classList.remove("open-upward","floating-calendar","centered-calendar");
  for (const property of ["top","right","bottom","left","transform"]) picker.style.removeProperty(property);
  $("underlyingDatePickerButton")?.setAttribute("aria-expanded","false");
}

function openUnderlyingDatePicker() {
  const picker = $("underlyingDatePicker");
  if (!picker) return;
  const selected = parseJalaliDate($("underlyingForm").elements.entry_date.value) || currentJalaliDate();
  underlyingCalendarView = {year:selected.year,month:selected.month};
  renderUnderlyingDatePicker(); picker.classList.remove("hidden"); positionUnderlyingDatePicker();
  $("underlyingDatePickerButton").setAttribute("aria-expanded","true");
}

function shiftUnderlyingCalendar(months) {
  if (!underlyingCalendarView) underlyingCalendarView = currentJalaliDate();
  let month=underlyingCalendarView.month+months, year=underlyingCalendarView.year;
  if(month<1){month=12;year-=1;} if(month>12){month=1;year+=1;}
  underlyingCalendarView={year,month}; renderUnderlyingDatePicker();
}

function fillSummary(data) {
  if ($("coveredCount")) $("coveredCount").textContent = num(data.summary.covered_contracts);
  if ($("positiveCount")) $("positiveCount").textContent = num(data.summary.positive_contracts);
  if ($("zeroCount")) $("zeroCount").textContent = num(data.summary.zero_value_contracts);
  if ($("assetCount")) $("assetCount").textContent = num(data.summary.active_assets);
  $("updatedAt").textContent = formatDate(data.generated_at);
  updateAssetFilter();
}

function syncMarketControls() {
  if ($("marketFilter")) $("marketFilter").value = state.market;
  document.querySelectorAll("[data-overview-market]").forEach((card) => {
    const selected = card.dataset.overviewMarket === state.market;
    card.classList.toggle("active", selected);
    card.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  document.querySelectorAll("[data-market-card]").forEach((card) => {
    const selected = card.dataset.marketCard === state.market;
    card.classList.toggle("active", selected);
    card.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  document.querySelectorAll("[data-covered-basis]").forEach((button)=>button.classList.toggle("active",button.dataset.coveredBasis === state.coveredBasis));
  document.querySelectorAll("[data-covered-base-basis]").forEach((button)=>button.classList.toggle("active",button.dataset.coveredBaseBasis === state.coveredBaseBasis));
  document.querySelectorAll("[data-long-basis]").forEach((button)=>button.classList.toggle("active",button.dataset.longBasis === state.longBasis));
  document.querySelectorAll("[data-long-base-basis]").forEach((button)=>button.classList.toggle("active",button.dataset.longBaseBasis === state.longBaseBasis));
  document.querySelectorAll("[data-state-filter]").forEach((button)=>{
    const selected=button.dataset.stateFilter === state.status;
    button.classList.toggle("active",selected); button.setAttribute("aria-pressed",String(selected));
  });
  document.querySelectorAll("[data-covered-ranking]").forEach((button)=>{
    const selected=button.dataset.coveredRanking === state.coveredRanking;
    button.classList.toggle("active",selected); button.setAttribute("aria-pressed",String(selected));
  });
}

function setMarket(value) {
  state.market = value;
  syncMarketControls();
  updateAssetFilter();
  render();
}

function applyPricingBasis() {
  if (!state.data?.strategy_table_variants) return;
  const coveredTables = selectedStrategyTables("covered_call");
  const longTables = selectedStrategyTables("long_underlying");
  state.data.strategy_tables.covered_call = coveredTables;
  state.data.strategy_tables.long_underlying = longTables;
  const minimumReturn = Number(state.data.rules?.covered_min_annual_return ?? 40);
  const coveredGroups = groupStrategyRows(Object.values(coveredTables).flat().filter((item) => item.state === "ITM" && Number(item.annual_return) >= minimumReturn), "covered_call");
  const longGroups = groupStrategyRows(Object.values(longTables).flat().filter((item) => Number(item.advantage_percent) > 0), "long_underlying");
  state.data.covered_call = coveredGroups;
  state.data.long_underlying = longGroups;
  state.data.top_opportunities.covered_call = Object.fromEntries(["tehran","goods"].map((market)=>[market,coveredTables[market].filter((x)=>x.is_top_five)]));
  state.data.top_opportunities.long_underlying = Object.fromEntries(["tehran","goods"].map((market)=>[market,longTables[market].filter((x)=>x.is_top_five)]));
  const coveredItems = coveredGroups.flatMap((group) => group.items);
  const longItems = longGroups.flatMap((group) => group.items);
  state.data.assets = [...new Set([...coveredGroups, ...longGroups].map((group) => group.asset))];
  state.data.summary.covered_contracts = coveredItems.length;
  state.data.summary.positive_contracts = longItems.length;
  state.data.summary.zero_value_contracts = [...coveredItems, ...longItems].filter((item) => item.transaction_zero).length;
  state.data.summary.active_assets = state.data.assets.length;
}

function selectedStrategyTables(strategy) {
  const optionBasis = strategy === "covered_call" ? state.coveredBasis : state.longBasis;
  const baseBasis = strategy === "covered_call" ? state.coveredBaseBasis : state.longBaseBasis;
  return state.data?.strategy_table_variants?.[strategy]?.[optionBasis]?.[baseBasis]
    || state.data?.strategy_tables?.[strategy]
    || {tehran:[],goods:[]};
}

function groupStrategyRows(rows, strategy) {
  const groups = new Map();
  rows.forEach((item) => {
    const key = `${item.market}|${item.asset}|${item.expiry}`;
    if (!groups.has(key)) groups.set(key,{market:item.market,asset:item.asset,expiry:item.expiry,expiry_display:item.expiry_display,days:item.days,items:[]});
    groups.get(key).items.push(item);
  });
  return [...groups.values()].map((group) => {
    group.items.sort((a,b) => strategy === "covered_call"
      ? Number(b.covered_score ?? -1)-Number(a.covered_score ?? -1) || Number(b.annual_return ?? -1)-Number(a.annual_return ?? -1)
      : Number(b.advantage_percent ?? -1)-Number(a.advantage_percent ?? -1));
    if (strategy === "covered_call") group.items = group.items.slice(0,4).map((item)=>({...item,labels:["بهترین فرصت زنجیره"]}));
    return group;
  });
}

function saveMarketPricing() {
  try { localStorage.setItem("nicoption.market-pricing.v1",JSON.stringify({covered_option_basis:state.coveredBasis,covered_base_basis:state.coveredBaseBasis,long_option_basis:state.longBasis,long_base_basis:state.longBaseBasis})); } catch { /* Current session still works. */ }
}

function calculateLongCost(item, daysOverride = null) {
  const base = Number(item.base_price);
  const strike = Number(item.strike);
  const premium = Number(item.calculation_price);
  const days = Math.max(0, Number(daysOverride ?? item.days ?? 0));
  if (![base, strike, premium].every(Number.isFinite) || base <= 0) return;
  const periodRate = Math.max(0, Number(state.longInterestRate) || 0) / 100 * days / 365;
  const interestCost = strike * periodRate;
  const adjustedCost = strike + premium - interestCost;
  const difference = (adjustedCost - base) / base * 100;
  item.days = days;
  item.period_interest_rate_percent = periodRate * 100;
  item.risk_free_adjusted_strike = strike - interestCost;
  item.exercise_discount_percent = periodRate * 100;
  item.exercise_interest_cost = interestCost;
  item.adjusted_exercise_plus_premium = adjustedCost;
  item.adjusted_cost_to_base_percent = adjustedCost / base * 100 - 100;
  item.adjusted_cost_vs_base_percent = difference;
  item.advantage_percent = -difference;
  item.profit_percent = -difference;
  item.premium_to_base_percent = premium / base * 100;
  item.leverage = premium > 0 ? base / premium : null;
  item.recommendation = item.advantage_percent > 0 ? "خرید اختیار" : "خرید دارایی پایه";
}

function applyLongInterestRate() {
  if (!state.data || state.longInterestRate == null) return;
  state.data.rules.long_interest_rate = state.longInterestRate;
  const seen = new Set();
  const applyItems = (items, days = null) => (items || []).forEach((item) => {
    if (!item || seen.has(item)) return;
    seen.add(item);
    calculateLongCost(item, days);
  });
  Object.values(state.data.strategy_tables?.long_underlying || {}).forEach((items) => applyItems(items));
  Object.values(state.data.strategy_table_variants?.long_underlying || {}).forEach((byBase) => {
    Object.values(byBase || {}).forEach((byMarket) => Object.values(byMarket || {}).forEach((items) => applyItems(items)));
  });
  Object.values(state.data.price_variants?.long_underlying || {}).forEach((variant) => {
    (variant.groups || []).forEach((group) => applyItems(group.items, group.days));
    Object.values(variant.top || {}).forEach((items) => applyItems(items));
  });
  (state.data.long_underlying || []).forEach((group) => applyItems(group.items, group.days));
  Object.values(state.data.top_opportunities?.long_underlying || {}).forEach((items) => applyItems(items));
}

function syncLongInterestRateControls() {
  const value = Number(state.longInterestRate ?? 40);
  $("longInterestRateFilter").value = value;
  $("chainLongInterestRate").value = value;
  $("chainInterestRateField").classList.toggle("hidden", state.marketDataView !== "long_underlying");
  $("chainAnnualReturnField").classList.toggle("hidden", state.marketDataView !== "covered_call");
  document.querySelectorAll(".chain-covered-pricing").forEach((element)=>element.classList.toggle("hidden",state.marketDataView !== "covered_call"));
  document.querySelectorAll(".chain-long-pricing").forEach((element)=>element.classList.toggle("hidden",state.marketDataView !== "long_underlying"));
}

function syncChainFilterCards() {
  document.querySelectorAll("[data-chain-filter-target]").forEach((button) => {
    const control = $(button.dataset.chainFilterTarget);
    const active = control && String(control.value) === String(button.dataset.chainFilterValue);
    button.classList.toggle("active", Boolean(active));
    button.setAttribute("aria-pressed", String(Boolean(active)));
  });
}

function updateLongInterestRate(rawValue) {
  const value = Math.min(200, Math.max(0, Number(rawValue) || 0));
  state.longInterestRate = value;
  syncLongInterestRateControls();
  applyLongInterestRate();
  if (state.data) {
    renderRules(state.data);
    fillSummary(state.data);
    render();
  }
}

function updateAssetFilter() {
  if (!state.data) return;
  const groups = [...state.data.covered_call, ...state.data.long_underlying]
    .filter((group) => state.market === "all" || group.market === state.market);
  const secondaryAssets = secondaryCoveredRows({ignoreAsset:true, ignoreStatus:true, ignoreSearch:true}).map((item) => item.asset);
  const assets = [...new Set([...groups.map((group) => group.asset), ...secondaryAssets])].sort((a, b) => a.localeCompare(b, "fa"));
  const select = $("assetFilter");
  const current = state.asset;
  select.innerHTML = '<option value="all">همه دارایی‌ها</option>' + assets.map((asset) => `<option value="${esc(asset)}">${esc(asset)}</option>`).join("");
  state.asset = assets.includes(current) ? current : "all";
  select.value = state.asset;
}

function renderRules(data) {
  $("rulesPanel").innerHTML = [
    `کاوردکال: فقط <b>ITM</b> و سود سالانه حداقل <b>${num(data.rules.covered_min_annual_return)}٪</b>`,
    `کاوردکال حالت دوم: ITM از <b>۵−٪ تا ۵+٪</b> · حداکثر <b>۵ پیشنهاد</b> برای هر دارایی · ارزش معاملات مثبت`,
    `استراتژی خرید: هزینه نهایی با لحاظ نرخ بهره کمتر از پایه و حجم <b>بیشتر از صفر</b>`,
    `مبنای قیمت هر استراتژی از <b>فیلتر مستقل</b> انتخاب می‌شود`,
    `کنترل صف: سفارش سمت مقابل فقط در صورت قرارداشتن داخل <b>دامنه مجاز نوسان</b> وارد محاسبه می‌شود`,
    `نرخ بهره محاسباتی قابل‌تغییر <b>${num(state.longInterestRate ?? data.rules.long_interest_rate)}٪</b>`,
    `کنترل کیفیت بورس کالا: <b>${esc(data.rules.goods_data_policy)}</b>`,
    `دلتا: <b>بلک–شولز</b> · علامت ≈ یعنی برآورد با IV مرجع ۳۵٪`,
    `امتیاز کاوردکال: بازده <b>۳۰</b> · حاشیه امن <b>۲۰</b> · نقدشوندگی نسبی بازار <b>۲۰</b> · دلتا <b>۱۵</b> · سررسید <b>۱۰</b> · کیفیت قیمت <b>۵</b>`,
    `تازه‌سازی خودکار هر <b>${num(state.userSettings.refreshMinutes)} دقیقه</b>`,
  ].map((text) => `<span class="rule-chip">${text}</span>`).join("");
}

function filteredGroups(groups) {
  return groups.map((group) => ({...group, items: group.items.filter((item) => {
    if (state.market !== "all" && group.market !== state.market) return false;
    if (state.asset !== "all" && group.asset !== state.asset) return false;
    if (state.status !== "all" && item.state !== state.status) return false;
    if (state.search && !item.symbol.toLowerCase().includes(state.search.toLowerCase())) return false;
    return true;
  })})).filter((group) => group.items.length);
}

function secondaryCoveredRows({ignoreAsset=false, ignoreStatus=false, ignoreSearch=false}={}) {
  if (!state.data) return [];
  const markets = state.market === "all" ? ["tehran", "goods"] : [state.market];
  const minimumReturn = Number(state.data.rules?.covered_min_annual_return ?? 40);
  const tables = selectedStrategyTables("covered_call");
  return markets.flatMap((market) => tables[market] || []).filter((item) => {
    const itm = Number(item.itm_percent);
    if (!(itm >= -5 && itm <= 5)) return false;
    if (!(Number(item.transaction_value) > 0)) return false;
    if (!(Number(item.annual_return) >= minimumReturn)) return false;
    if (!ignoreAsset && state.asset !== "all" && item.asset !== state.asset) return false;
    if (!ignoreStatus && state.status !== "all" && item.state !== state.status) return false;
    if (!ignoreSearch && state.search && !String(item.symbol || "").toLowerCase().includes(state.search.toLowerCase())) return false;
    return true;
  });
}

function secondaryCoveredGroups() {
  const grouped = new Map();
  secondaryCoveredRows().forEach((item) => {
    const key = `${item.market}|${item.asset}`;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push({...item, is_secondary_covered:true, labels:["حالت دوم · ITM از ‎−۵٪ تا ‎+۵٪"]});
  });
  return [...grouped.values()].map((items) => {
    items.sort((a, b) => state.coveredRanking === "score"
      ? Number(b.covered_score ?? -1) - Number(a.covered_score ?? -1) || Number(b.annual_return) - Number(a.annual_return)
      : Number(b.annual_return) - Number(a.annual_return) || Number(b.transaction_value) - Number(a.transaction_value));
    const selected = items.slice(0, 5);
    return {market:selected[0].market, asset:selected[0].asset, items:selected};
  });
}

function detailButton(strategy, market, asset, item) {
  const key = `${strategy}|${market}|${item.symbol}`;
  state.details.set(key, {strategy, market, asset, ...item});
  return `<button class="analysis-button" type="button" data-detail="${esc(key)}">نمودار و جزئیات</button>`;
}

function openAnalysisByKey(key) {
  let item = state.details.get(key);
  if (!item && state.data) {
    const [strategy, market, symbol] = String(key).split("|");
    const row = (selectedStrategyTables(strategy)[market] || []).find((candidate) => String(candidate.symbol) === symbol);
    if (row) item = {strategy, market, asset:row.asset, ...row};
  }
  if (item) openAnalysis(item);
  else setStatus("error", "جزئیات این فرصت در داده‌های فعلی پیدا نشد؛ داده‌ها را تازه‌سازی کنید.");
}

function coveredTopItems(market, series = "itm") {
  const source = selectedStrategyTables("covered_call")[market] || [];
  const minimumReturn = Number(state.data.rules?.covered_min_annual_return ?? 40);
  return source.filter((item) => {
    const itm = Number(item.itm_percent);
    if (!(Number(item.transaction_value) > 0)) return false;
    if (!(Number(item.annual_return) >= minimumReturn)) return false;
    if (series === "near" ? !(itm >= -5 && itm <= 10) : item.state !== "ITM") return false;
    if (state.asset !== "all" && item.asset !== state.asset) return false;
    if (state.status !== "all" && item.state !== state.status) return false;
    if (state.search && !item.symbol.toLowerCase().includes(state.search.toLowerCase())) return false;
    return true;
  }).sort((a, b) => state.coveredRanking === "score"
    ? Number(b.covered_score ?? -1) - Number(a.covered_score ?? -1) || Number(b.annual_return) - Number(a.annual_return)
    : Number(b.annual_return) - Number(a.annual_return) || Number(b.transaction_value) - Number(a.transaction_value)
  ).slice(0, 5);
}

function selectedTopItems(strategy, market, series = null) {
  if (strategy === "covered_call") return coveredTopItems(market, series || "itm");
  const source = selectedStrategyTables("long_underlying")[market] || [];
  return source.filter((item) => {
    if (state.asset !== "all" && item.asset !== state.asset) return false;
    if (state.status !== "all" && item.state !== state.status) return false;
    if (state.search && !item.symbol.toLowerCase().includes(state.search.toLowerCase())) return false;
    return Number(item.advantage_percent) > 0;
  }).sort((a,b) => Number(b.advantage_percent)-Number(a.advantage_percent)).slice(0, 5);
}

function selectedBaseQuote(item, basis) {
  return Number(basis === "last" ? item.base_last : basis === "bid" ? item.base_best_bid : item.base_best_ask);
}

function coveredQuoteScenario(item, basis, baseBasis = state.coveredBaseBasis) {
  const premium = Number(
    basis === "last" ? item.option_last
    : basis === "ask" ? item.option_best_ask
    : (item.option_best_bid ?? item.option_bid)
  );
  const base = selectedBaseQuote(item,baseBasis), strike = Number(item.strike), days = Math.max(0, Number(item.days));
  if (![premium, base, strike].every(Number.isFinite) || premium <= 0 || base <= 0) return null;
  const expiryReturn = (premium - Math.max(base - strike, 0)) / base * 100;
  const annualReturn = days > 0 ? expiryReturn * 365 / days : null;
  const buyback = premium / base * 100;
  return {premium, expiryReturn, annualReturn, buyback, buybackAnnual:days > 0 ? buyback * 365 / days : null};
}

function normalCdf(value) {
  const x = Number(value);
  if (!Number.isFinite(x)) return null;
  const t = 1 / (1 + .2316419 * Math.abs(x));
  const density = .3989422804014327 * Math.exp(-x * x / 2);
  const tail = density * t * (.319381530 + t * (-.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return x >= 0 ? 1 - tail : tail;
}

function coveredMarketMetrics(item) {
  const scenario = coveredQuoteScenario(item,state.coveredBasis,state.coveredBaseBasis);
  const base = selectedBaseQuote(item,state.coveredBaseBasis);
  const premium = scenario?.premium;
  const strike = Number(item.strike);
  const days = Math.max(0,Number(item.days)||0);
  if (![base,premium,strike].every(Number.isFinite) || base <= 0 || premium < 0 || strike <= 0) return null;
  const capital = base - premium;
  const premiumReturn = capital > 0 ? premium / capital * 100 : null;
  const volatility = Number(item.implied_volatility);
  let assignmentProbability = null;
  if (days <= 0) assignmentProbability = base > strike ? 100 : base < strike ? 0 : 50;
  else if (Number.isFinite(volatility) && volatility > 0) {
    const years = days / 365;
    const rate = Math.max(0,Number(state.data?.rules?.long_interest_rate ?? 40)) / 100;
    const sigma = volatility / 100;
    const d2 = (Math.log(base / strike) + (rate - .5 * sigma * sigma) * years) / (sigma * Math.sqrt(years));
    assignmentProbability = normalCdf(d2) * 100;
  }
  return {
    base,premium,strike,days,
    netPremium:premium,
    premiumReturn,
    premiumReturnYoy:premiumReturn == null || days <= 0 ? null : premiumReturn * 365 / days,
    strikeDistance:((strike-base)/base)*100,
    breakeven:base-premium,
    maxProfit:strike-base+premium,
    downsideProtection:premium/base*100,
    assignmentProbability,
    foregoneUpside:Math.max(0,base-strike),
    model:"Black–Scholes N(d2), q=0",
    volatility,
    estimated:Boolean(item.delta_estimated),
  };
}

function strikeDistanceText(value) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  const distance=Math.abs(Number(value));
  if (distance < .005) return "هم‌سطح قیمت سهم · ATM";
  return Number(value)<0
    ? `${num(distance,2)}٪ پایین‌تر از سهم · ITM`
    : `${num(distance,2)}٪ بالاتر از سهم · OTM`;
}

function coveredMarketIndicators(item,{compact=false}={}) {
  const metric = coveredMarketMetrics(item);
  if (!metric) {
    const unavailable = `<div class="market-covered-indicators-body"><p>برای محاسبه شاخص‌های کاوردکال، قیمت معتبر پایه و اختیار لازم است.</p></div>`;
    return compact
      ? `<details class="market-covered-indicators compact unavailable"><summary><span><b>شاخص‌های کاوردکال</b><small>اطلاعات محاسبه کامل نیست</small></span><b><i>نمایش</i><i>بستن</i></b></summary>${unavailable}</details>`
      : `<section class="market-covered-indicators unavailable">${unavailable}</section>`;
  }
  const rows = [
    ["قیمت سهم",num(metric.base,2),""],["قیمت اعمال",num(metric.strike,2),""],["روز تا سررسید",`${num(metric.days)} روز`,""],
    ["پرمیوم خالص هر واحد",num(metric.netPremium,2),""],["بازده پرمیوم / سرمایه",formatPercent(metric.premiumReturn),valueTone(metric.premiumReturn)],
    ["فاصله سهم تا اعمال",strikeDistanceText(metric.strikeDistance),""],["بازده سالانه پرمیوم",formatPercent(metric.premiumReturnYoy),valueTone(metric.premiumReturnYoy)],
    ["نقطه سربه‌سر",num(metric.breakeven,2),""],["حداکثر سود هر واحد",num(metric.maxProfit,2),valueTone(metric.maxProfit)],
    ["پوشش نزول با پرمیوم",formatPercent(metric.downsideProtection),""],["احتمال تقریبی اعمال",metric.assignmentProbability==null?"داده ناکافی":formatPercent(metric.assignmentProbability),""],
    ["رشد ازدست‌رفته فعلی",num(metric.foregoneUpside,2),metric.foregoneUpside>0?"profit-negative":""],["وضعیت","نامزد ورود",""]
  ];
  const content = `<div class="market-covered-indicators-body"><header><div><small>بر مبنای قیمت انتخابی تابلو</small><h4>شاخص‌های کاوردکال</h4></div><span>نامزد ورود</span></header><dl>${rows.map(([label,value,tone])=>`<div><dt>${label}</dt><dd class="${tone}">${value}</dd></div>`).join("")}</dl><p><b>احتمال اعمال:</b> ${metric.model}؛ احتمال ریسک‌خنثی اروپایی، نه پیش‌بینی قطعی. ${metric.estimated?"نوسان ۳۵٪ برآوردی است.":`IV برابر ${num(metric.volatility,2)}٪ است.`}</p></div>`;
  return compact
    ? `<details class="market-covered-indicators compact"><summary><span><b>شاخص‌های کاوردکال</b><small>تحلیل بازده، ریسک و احتمال اعمال</small></span><b><i>نمایش</i><i>بستن</i></b></summary>${content}</details>`
    : `<section class="market-covered-indicators">${content}</section>`;
}

function longQuoteScenario(item, basis, baseBasis = state.longBaseBasis) {
  const premium = Number(basis === "last" ? item.option_last : basis === "bid" ? item.option_best_bid : item.option_best_ask);
  const base = selectedBaseQuote(item,baseBasis), strike = Number(item.strike), days = Math.max(0, Number(item.days));
  if (![premium, base, strike].every(Number.isFinite) || premium <= 0 || base <= 0) return null;
  const periodRate = Math.max(0, Number(state.longInterestRate) || 0) / 100 * days / 365;
  const adjustedCost = strike + premium - strike * periodRate;
  return {premium, adjustedCost, advantage:(base - adjustedCost) / base * 100};
}

function quoteValue(value, digits = 2, suffix = "") {
  return Number.isFinite(Number(value)) ? `${num(value, digits)}${suffix}` : "ناموجود";
}

function optionBasisLabel(basis) {
  return basis === "ask" ? "بهترین پیشنهاد فروش اختیار" : basis === "bid" ? "بهترین پیشنهاد خرید اختیار" : "آخرین معامله اختیار";
}

function baseBasisLabel(basis) {
  return basis === "ask" ? "بهترین پیشنهاد فروش پایه" : basis === "bid" ? "بهترین پیشنهاد خرید پایه" : "آخرین معامله پایه";
}

function coveredQuotePanel(item, basis, label) {
  const value = coveredQuoteScenario(item, basis);
  if (!value) return `<section class="quote-scenario unavailable"><h4>${label}</h4><p>قیمت معتبر در تابلو موجود نیست</p></section>`;
  return `<section class="quote-scenario ${basis}">
    <h4>${label}</h4>
    <dl>
      <div><dt>پرمیوم</dt><dd>${quoteValue(value.premium, 0)}</dd></div>
      <div><dt>سود کاوردکال</dt><dd class="${value.expiryReturn < 0 ? "profit-negative" : "profit-positive"}">${quoteValue(value.expiryReturn, 2, "٪")}</dd></div>
      <div><dt>سود سالانه</dt><dd class="${value.annualReturn < 0 ? "profit-negative" : "profit-positive"}">${quoteValue(value.annualReturn, 2, "٪")}</dd></div>
      <div><dt>بازخرید | سالانه</dt><dd>${quoteValue(value.buyback, 2, "٪")} | ${quoteValue(value.buybackAnnual, 2, "٪")}</dd></div>
    </dl>
  </section>`;
}

function longQuotePanel(item, basis, label) {
  const value = longQuoteScenario(item, basis);
  if (!value) return `<section class="quote-scenario unavailable"><h4>${label}</h4><p>قیمت معتبر در تابلو موجود نیست</p></section>`;
  return `<section class="quote-scenario ${basis}">
    <h4>${label}</h4>
    <dl>
      <div><dt>پرمیوم</dt><dd>${quoteValue(value.premium, 0)}</dd></div>
      <div><dt>مزیت نسبی</dt><dd class="${value.advantage < 0 ? "profit-negative" : "profit-positive"}">${signed(value.advantage)}٪</dd></div>
      <div><dt>اعمال تعدیل‌شده + پرمیوم</dt><dd>${quoteValue(value.adjustedCost, 0)}</dd></div>
    </dl>
  </section>`;
}

function selectedTopBlocks() {
  if (!state.data) return [];
  const markets = state.market === "all" ? ["tehran", "goods"] : [state.market];
  const strategies = state.strategy === "covered" ? ["covered_call"] : state.strategy === "long" ? ["long_underlying"] : ["covered_call", "long_underlying"];
  return strategies.flatMap((strategy) => markets.flatMap((market) => strategy === "covered_call"
    ? ["itm", "near"].map((series) => ({strategy, market, series, items: selectedTopItems(strategy, market, series)}))
    : [{strategy, market, series:null, items:selectedTopItems(strategy, market)}]
  )).filter((block) => block.items.length);
}

function coveredTopOpportunityCard(item, index, series) {
  const riskTags = [
    series === "near" ? '<span class="risk-tag moderate">کمی پرریسک</span>' : "",
    isLeveragedFund(item.asset) ? '<span class="risk-tag leveraged">پرریسک + صندوق اهرمی</span>' : "",
  ].join("");
  return `<article class="opportunity-card covered-overview-card">
    <div class="opportunity-card-head"><span class="top-rank">${num(index + 1)}</span><div class="risk-tags">${riskTags}</div></div>
    <div class="covered-symbol-pair"><strong>${esc(item.asset)}</strong><strong>${esc(item.symbol)}</strong></div>
    <div class="covered-itm-row"><span>میزان ITM</span><strong class="${Number(item.itm_percent) < 0 ? "itm-negative" : "itm-positive"}">${signed(item.itm_percent)}٪</strong></div>
    <div class="quote-scenario-grid covered-quotes">
      ${coveredQuotePanel(item, state.coveredBasis, `${optionBasisLabel(state.coveredBasis)} · ${baseBasisLabel(state.coveredBaseBasis)}`)}
      ${coveredQuotePanel(item, state.coveredBasis === "last" ? "bid" : "last", `${optionBasisLabel(state.coveredBasis === "last" ? "bid" : "last")} · ${baseBasisLabel(state.coveredBaseBasis)}`)}
    </div>
    <dl class="covered-overview-metrics"><div class="metric-time"><dt>روز تا سررسید</dt><dd class="${Number(item.days) < 5 ? "expiry-near" : ""}">${num(item.days)} روز</dd></div></dl>
    ${coveredMarketIndicators(item,{compact:true})}
    <footer>${detailButton("covered_call", item.market, item.asset, item)}</footer>
  </article>`;
}

function longTopOpportunityCard(item, index) {
  const riskTag = isLeveragedFund(item.asset) ? '<span class="risk-tag leveraged">پرریسک + صندوق اهرمی</span>' : "";
  return `<article class="opportunity-card long-overview-card">
    <div class="opportunity-card-head"><span class="top-rank">${num(index + 1)}</span><div class="risk-tags">${riskTag}</div></div>
    <div class="covered-symbol-pair"><strong>${esc(item.asset)}</strong><strong>${esc(item.symbol)}</strong></div>
    <dl class="long-overview-metrics">
      <div class="metric-itm"><dt>درصد ITM</dt><dd class="${Number(item.itm_percent) < 0 ? "itm-negative" : "itm-positive"}">${signed(item.itm_percent)}٪</dd></div>
      <div class="metric-rate"><dt>نرخ دوره</dt><dd>${num(item.period_interest_rate_percent, 2)}٪</dd></div>
      <div class="metric-time"><dt>روز تا سررسید</dt><dd class="${Number(item.days) < 5 ? "expiry-near" : ""}">${num(item.days)} روز</dd></div>
    </dl>
    <div class="quote-scenario-grid long-quotes">
      ${longQuotePanel(item, state.longBasis, `${optionBasisLabel(state.longBasis)} · ${baseBasisLabel(state.longBaseBasis)}`)}
      ${longQuotePanel(item, state.longBasis === "last" ? "ask" : "last", `${optionBasisLabel(state.longBasis === "last" ? "ask" : "last")} · ${baseBasisLabel(state.longBaseBasis)}`)}
    </div>
    <footer>${detailButton("long_underlying", item.market, item.asset, item)}</footer>
  </article>`;
}

function topCard(strategy, market, series = null) {
  const items = selectedTopItems(strategy, market, series);
  if (!items.length) return "";
  const isCovered = strategy === "covered_call";
  const coveredTitle = series === "near" ? "کاوردکال · ITM از ‎−۵٪ تا ‎+۱۰٪" : "کاوردکال · فقط ITM";
  const cards = isCovered
    ? items.map((item, index) => coveredTopOpportunityCard(item, index, series)).join("")
    : items.map((item, index) => longTopOpportunityCard(item, index)).join("");
  const pricing = isCovered
    ? `${optionBasisLabel(state.coveredBasis)} · ${baseBasisLabel(state.coveredBaseBasis)}`
    : `${optionBasisLabel(state.longBasis)} · ${baseBasisLabel(state.longBaseBasis)}`;
  return `<section class="top-market ${isCovered ? `covered-series ${series}` : ""}"><header><div><span>برترین‌ها</span><h3>${isCovered ? coveredTitle : "خرید اختیار یا پایه"} · ${marketLabel(market)}</h3></div><small>${isCovered ? `${state.coveredRanking === "score" ? "رتبه‌بندی با امتیاز جامع" : "رتبه‌بندی با سود سالانه"} · ${pricing}` : `رتبه‌بندی با ${pricing}`}</small></header><div class="top-card-grid">${cards}</div></section>`;
}

function topOpportunityReason(item, isCovered) {
  if (!isCovered) return `هزینه تعدیل‌شده این قرارداد ${num(item.advantage_percent, 2)}٪ پایین‌تر از خرید مستقیم پایه است.`;
  const parts = item.covered_score_components || {};
  const strongest = Object.entries(parts).sort((a, b) => Number(b[1]) - Number(a[1]))[0];
  const driver = strongest ? scoreComponentLabels[strongest[0]] : "ترکیب بازده و نقدشوندگی";
  return `با امتیاز ${scoreValue(item)} از ۱۰۰، بازده سالانه ${num(item.annual_return, 2)}٪ و نقطه قوت ${driver} در جمع برترین‌هاست.`;
}

function renderTehranChain() {
  if (!state.data) return;
  syncChainFilterCards();
  const source = state.data.strategy_tables?.[state.chainStrategy]?.[state.chainMarket] || [];
  const covered = state.chainStrategy === "covered_call";
  const rawView = state.marketDataView === "all";
  const layoutKey = rawView ? "all" : state.chainStrategy;
  const query = faNorm(state.chainSearch);
  const marketNumber = (value, digits = 0) => value == null || !Number.isFinite(Number(value)) || Number(value) <= 0 ? "—" : num(value,digits);
  const spreadPercent = (item) => {
    const bid=Number(item.option_best_bid),ask=Number(item.option_best_ask);
    return bid>0&&ask>0&&ask>=bid ? (ask-bid)/ask*100 : null;
  };
  const commonColumns = [
    {key:"asset", label:covered ? "نماد پایه" : "نام دارایی پایه", value:(x)=>x.asset, render:(x)=>`<strong>${esc(x.asset)}</strong>`},
    {key:"base_price", label:covered ? `قیمت مبنای پایه (${baseBasisLabel(state.coveredBaseBasis).replace(" پایه","")})` : "قیمت دارایی پایه", value:(x)=>x.base_price, render:(x)=>num(x.base_price)},
    {key:"base_best_ask", label:"قیمت پایه (بهترین فروش)", render:(x)=>num(x.base_best_ask)},
    {key:"base_best_bid", label:"قیمت پایه (بهترین خرید)", render:(x)=>num(x.base_best_bid)},
    {key:"base_last", label:"آخرین پایه", render:(x)=>num(x.base_last)},
    {key:"symbol", label:covered ? "نماد آپشن" : "نام اختیار", value:(x)=>x.symbol, render:(x)=>`<button class="chain-symbol-button" type="button" data-chain-detail data-chain-strategy="${esc(state.chainStrategy)}" data-chain-market="${esc(x.market)}" data-chain-symbol="${esc(x.symbol)}" aria-label="نمایش جزئیات ${esc(x.symbol)}">${x.is_top_five ? '<span class="top-star" title="پنج فرصت برتر">★</span>' : ""}<span class="chain-symbol">${esc(x.symbol)}</span></button>`},
    {key:"contract_type", label:"نوع قرارداد", value:(x)=>x.option_type??x.contract_type, render:(x)=>x.option_type||x.contract_type?`<span class="market-contract-type">${esc(x.option_type??x.contract_type)}</span>`:"—"},
    {key:"option_price", label:"قیمت پایانی آپشن", render:(x)=>marketNumber(x.option_price)},
    {key:"option_best_bid", label:"بهترین خرید", value:(x)=>x.option_best_bid, render:(x)=>marketNumber(x.option_best_bid)},
    {key:"option_best_ask", label:"بهترین فروش", value:(x)=>x.option_best_ask, render:(x)=>marketNumber(x.option_best_ask)},
    {key:"option_last", label:"آخرین معامله", render:(x)=>marketNumber(x.option_last)},
    {key:"calculation_price", label:covered ? `قیمت مبنای آپشن (${optionBasisLabel(state.coveredBasis).replace(" اختیار","")})` : "قیمت اختیار", render:(x)=>num(x.calculation_price)},
    {key:"transaction_value", label:"ارزش معاملات آپشن", render:(x)=>`<span class="${x.transaction_zero ? "warning" : ""}">${x.transaction_zero ? "⚠️ " : ""}${num(x.transaction_value)}</span>`},
    {key:"option_volume", label:"حجم معاملات", value:(x)=>x.option_volume, render:(x)=>marketNumber(x.option_volume)},
    {key:"open_interest", label:"موقعیت باز", value:(x)=>x.open_interest, render:(x)=>marketNumber(x.open_interest)},
    {key:"spread_percent", label:"اسپرد خرید و فروش", value:(x)=>spreadPercent(x), render:(x)=>spreadPercent(x)==null?"—":formatPercent(spreadPercent(x))},
    {key:"strike", label:"قیمت اعمال", render:(x)=>num(x.strike)},
    {key:"itm_percent", label:covered ? "میزان ITM" : "وضعیت ITM / OTM / ATM", render:(x)=>`${badge(x.state)}<small>${formatPercent(x.itm_percent)}</small>`},
    {key:"strategy_delta", label:covered ? "دلتا کاوردکال" : "دلتا استراتژی", render:(x)=>`<span class="delta-cell">${deltaDisplay(x,"strategy_delta")}</span>`},
    {key:"option_delta", label:"دلتا آپشن", render:(x)=>`<span class="delta-cell">${deltaDisplay(x)}</span>`},
    {key:"days", label:"روز تا سررسید", render:(x)=>num(x.days)},
    {key:"expiry", label:"تاریخ سررسید", value:(x)=>x.expiry, render:(x)=>esc(solarDate(x.expiry_display || x.expiry))},
    {key:"breakeven", label:"نقطه سربه‌سر", render:(x)=>num(x.breakeven)},
    {key:"base_queue_status", label:"وضعیت صف پایه", value:(x)=>x.base_queue_status, render:(x)=>`<span class="queue-badge ${x.base_queue_status === "صف خرید" ? "buy" : x.base_queue_status === "صف فروش" ? "sell" : ""}">${esc(x.base_queue_status)}</span>`},
    {key:"option_queue_status", label:"وضعیت صف آپشن", value:(x)=>x.option_queue_status, render:(x)=>`<span class="queue-badge ${x.option_queue_status === "صف خرید" ? "buy" : x.option_queue_status === "صف فروش" ? "sell" : ""}">${esc(x.option_queue_status)}</span>`},
    {key:"quote_quality_valid", label:"کنترل دامنه قیمت", value:(x)=>x.quote_quality_valid ? 1 : 0, render:(x)=>x.quote_quality_valid ? '<span class="profit-positive">معتبر</span>' : '<span class="warning">سفارش خارج دامنه حذف شد</span>'},
    {key:"updated_at", label:"زمان آخرین داده", value:(x)=>x.updated_at??state.data.generated_at, render:(x)=>esc(x.updated_at||formatDate(state.data.generated_at)||"—")},
    {key:"operations", label:"عملیات", value:(x)=>x.symbol, render:(x)=>`<button class="chain-row-action" type="button" data-chain-detail data-chain-strategy="${esc(state.chainStrategy)}" data-chain-market="${esc(x.market)}" data-chain-symbol="${esc(x.symbol)}">جزئیات قرارداد</button>`},
  ];
  const metricColumns = rawView ? [] : covered ? [
    {key:"market_premium_return", label:"بازده پرمیوم / سرمایه درگیر", value:(x)=>coveredMarketMetrics(x)?.premiumReturn, render:(x)=>formatPercent(coveredMarketMetrics(x)?.premiumReturn)},
    {key:"market_premium_return_yoy", label:"بازده سالانه‌شده پرمیوم", value:(x)=>coveredMarketMetrics(x)?.premiumReturnYoy, render:(x)=>formatPercent(coveredMarketMetrics(x)?.premiumReturnYoy)},
    {key:"market_strike_distance", label:"فاصله قیمت سهم تا اعمال", value:(x)=>coveredMarketMetrics(x)?.strikeDistance, render:(x)=>strikeDistanceText(coveredMarketMetrics(x)?.strikeDistance)},
    {key:"market_max_profit", label:"حداکثر سود هر واحد", value:(x)=>coveredMarketMetrics(x)?.maxProfit, render:(x)=>num(coveredMarketMetrics(x)?.maxProfit,2)},
    {key:"market_assignment_probability", label:"احتمال تقریبی اعمال", value:(x)=>coveredMarketMetrics(x)?.assignmentProbability, render:(x)=>{const m=coveredMarketMetrics(x);return `<span>${formatPercent(m?.assignmentProbability)}</span><small>Black–Scholes N(d2) · q=0${m?.estimated?" · IV برآوردی":""}</small>`;}},
    {key:"market_foregone_upside", label:"رشد ازدست‌رفته فعلی هر واحد", value:(x)=>coveredMarketMetrics(x)?.foregoneUpside, render:(x)=>num(coveredMarketMetrics(x)?.foregoneUpside,2)},
    {key:"market_position_status", label:"وضعیت موقعیت", value:()=>"نامزد ورود", render:()=>'<span class="market-candidate-status">نامزد ورود</span>'},
    {key:"buyback_percent", label:"درصد بازخرید", value:(x)=>buybackPercent(x), render:(x)=>`<span>${formatPercent(buybackPercent(x))}</span>`},
    {key:"expiry_return", label:"سود کاوردکال", render:(x)=>`<span class="return-cell ${valueTone(x.expiry_return)}">${formatPercent(x.expiry_return)}</span>`},
    {key:"annual_return", label:"سود سالانه", render:(x)=>`<span class="return-cell ${valueTone(x.annual_return)}">${formatPercent(x.annual_return)}</span>`},
    {key:"buyback_annual_percent", label:"بازخرید سالانه", value:(x)=>buybackAnnualPercent(x), render:(x)=>`<span>${formatPercent(buybackAnnualPercent(x))}</span>`},
    {key:"monthly_return", label:"سود ماهانه", render:(x)=>`<span class="return-cell ${valueTone(x.monthly_return)}">${formatPercent(x.monthly_return)}</span>`},
    {key:"buyback_monthly_percent", label:"بازخرید ماهانه", value:(x)=>buybackMonthlyPercent(x), render:(x)=>`<span>${formatPercent(buybackMonthlyPercent(x))}</span>`},
    {key:"covered_score", label:"امتیاز سیستم", render:(x)=>`<span class="score-pill">${scoreValue(x)}</span><small>${esc(x.covered_score_label || "فاقد قیمت")}</small>`},
  ] : [
    {key:"adjusted_cost_to_base_percent", label:"درصد سود", value:(x)=>x.adjusted_cost_to_base_percent, render:(x)=>`<span class="return-cell ${valueTone(-Number(x.adjusted_cost_to_base_percent))}">${formatPercent(x.adjusted_cost_to_base_percent)}</span>`},
    {key:"exercise_discount_percent", label:"درصد تنزیل قیمت اعمال", value:(x)=>x.exercise_discount_percent, render:(x)=>formatPercent(x.exercise_discount_percent)},
    {key:"risk_free_adjusted_strike", label:"قیمت اعمال تعدیل‌شده", render:(x)=>num(x.risk_free_adjusted_strike)},
    {key:"adjusted_exercise_plus_premium", label:"اعمال تعدیل‌شده + پرمیوم", render:(x)=>num(x.adjusted_exercise_plus_premium)},
    {key:"adjusted_cost_vs_base_percent", label:"اختلاف هزینه با پایه", render:(x)=>formatPercent(x.adjusted_cost_vs_base_percent)},
    {key:"leverage", label:"اهرم (پایه ÷ پرمیوم)", value:(x)=>leverageRatio(x), render:(x)=>`<span>${num(leverageRatio(x), 2)}</span>`},
    {key:"advantage_percent", label:"فاصله هزینه اختیار با پایه · محاسبه‌شده", render:(x)=>`<span class="return-cell ${valueTone(x.advantage_percent)}">${formatPercent(x.advantage_percent)}</span>`},
  ];
  const allColumns = [...commonColumns, ...metricColumns];
  const savedLayout = state.chainColumnOrders[layoutKey];
  const defaultVisibleKeys = CHAIN_DEFAULT_VISIBLE_COLUMNS[layoutKey] || [];
  const requestedOrder = Array.isArray(savedLayout) && savedLayout.length ? savedLayout : defaultVisibleKeys;
  const savedOrder = [...new Set(requestedOrder.map((key)=>key === "option_volume" ? "transaction_value" : key))];
  const knownKeys = new Set(allColumns.map((column)=>column.key));
  const orderedKeys = [...savedOrder.filter((key)=>knownKeys.has(key)), ...allColumns.map((column)=>column.key).filter((key)=>!savedOrder.includes(key))];
  const columnByKey = new Map(allColumns.map((column)=>[column.key,column]));
  state.chainAllColumnKeys = orderedKeys;
  const hasSavedVisibility = Object.prototype.hasOwnProperty.call(state.chainHiddenColumns,layoutKey);
  const defaultHiddenKeys = allColumns.map((column)=>column.key).filter((key)=>!defaultVisibleKeys.includes(key));
  const hiddenKeys = new Set((hasSavedVisibility ? state.chainHiddenColumns[layoutKey] || [] : defaultHiddenKeys).filter((key)=>knownKeys.has(key)));
  if (hiddenKeys.size >= orderedKeys.length) {
    hiddenKeys.delete(orderedKeys[0]);
    state.chainHiddenColumns[layoutKey] = [...hiddenKeys];
    saveChainHiddenColumns();
  }
  const columns = orderedKeys.filter((key)=>!hiddenKeys.has(key)).map((key)=>columnByKey.get(key));
  state.chainVisibleColumnKeys = columns.map((column)=>column.key);
  if (!columns.some((column)=>column.key === state.chainSortKey)) {
    const preferredSortKey = rawView ? "symbol" : covered ? "annual_return" : "advantage_percent";
    state.chainSortKey = columns.some((column)=>column.key === preferredSortKey) ? preferredSortKey : columns[0].key;
    state.chainSortDirection = "desc";
  }
  const rows = source.filter((item) => {
    if (query && !faNorm(`${item.asset} ${item.symbol}`).includes(query)) return false;
    if (state.chainState !== "all" && item.state !== state.chainState) return false;
    if (!matchesNumericFilter(item.itm_percent, state.chainItmOperator, state.chainItmValue)) return false;
    if (state.chainQueue !== "all" && item.base_queue_status !== state.chainQueue) return false;
    if (!matchesNumericFilter(item.transaction_value || 0, state.chainTransactionOperator, state.chainTransactionValue)) return false;
    if (!matchesNumericFilter(item.days, state.chainDaysOperator, state.chainDaysMin)) return false;
    if (state.marketStrikeMin != null && Number(item.strike) < state.marketStrikeMin) return false;
    if (state.marketStrikeMax != null && Number(item.strike) > state.marketStrikeMax) return false;
    if (state.marketVolumeMin != null && Number(item.option_volume || 0) < state.marketVolumeMin) return false;
    if (state.marketOpenInterestMin != null && Number(item.open_interest || 0) < state.marketOpenInterestMin) return false;
    if (state.marketValidQuotesOnly && !(Number(item.option_best_bid)>0&&Number(item.option_best_ask)>0)) return false;
    if (covered && state.chainAnnualMin != null && !(item.annual_return != null && Number(item.annual_return) > state.chainAnnualMin)) return false;
    return true;
  }).sort((a, b) => compareChainRows(a, b, columns));
  const marketName = marketLabel(state.chainMarket);
  $("chainSourceLabel").textContent = state.chainMarket === "tehran" ? "داده رسمی TSETMC" : "داده رسمی بورس کالای ایران";
  $("tehranChainTitle").textContent = `داده‌های بازار · ${marketName}`;
  $("chainDescription").textContent = rawView ? "مشاهده، جست‌وجو و مقایسه قراردادهای اختیار معامله" : `${covered ? "نمای تحلیلی کاوردکال" : "نمای تحلیلی خرید اختیار خرید"}؛ بدون رتبه‌بندی یا توصیه معامله.`;
  $("chainMethodNote").textContent = rawView ? "مقادیر ناموجود با خط تیره نمایش داده می‌شوند. داده‌های محاسبه‌شده از قیمت‌های واقعی بازار متمایز هستند." : covered
    ? `مبنای محاسبه انتخابی: ${optionBasisLabel(state.coveredBasis)} و ${baseBasisLabel(state.coveredBaseBasis)}. ردیف فاقد قیمت انتخابی، بازده قابل محاسبه ندارد.`
    : `مبنای محاسبه انتخابی: ${optionBasisLabel(state.longBasis)} و ${baseBasisLabel(state.longBaseBasis)}؛ نرخ بدون ریسک سالانه ${num(state.data.rules.long_interest_rate,2)}٪. درصد سود = {[(قیمت اعمال تعدیل‌شده + پرمیوم) ÷ قیمت دارایی پایه] × ۱۰۰} − ۱۰۰.`;
  syncLongInterestRateControls();
  document.querySelectorAll("[data-market-data-view]").forEach((button)=>{const selected=button.dataset.marketDataView===state.marketDataView;button.classList.toggle("active",selected);button.setAttribute("aria-selected",String(selected));button.tabIndex=selected?0:-1;});
  const validQuotes=rows.filter((item)=>Number(item.option_best_bid)>0&&Number(item.option_best_ask)>0);
  const liquidQuotes=validQuotes.filter((item)=>spreadPercent(item)<=10);
  $("marketDataAssetCount").textContent=num(new Set(rows.map((item)=>item.asset).filter(Boolean)).size);
  $("marketDataValidQuotes").textContent=num(validQuotes.length);
  $("marketDataValidQuotesNote").textContent=rows.length?`${num(validQuotes.length/rows.length*100,1)}٪ از نتایج`:"—";
  $("marketDataLiquidCount").textContent=num(liquidQuotes.length);
  $("marketDataUpdated").textContent=state.data.generated_at?formatDate(state.data.generated_at):"—";
  const generatedAt=Date.parse(state.data.generated_at||"");
  const stale=Number.isFinite(generatedAt)&&Date.now()-generatedAt>state.userSettings.refreshMinutes*2*60*1000;
  $("marketDataStatus").textContent=stale?"داده قدیمی":"وضعیت بازار اعلام نشده";
  $("marketDataStatus").className=`market-data-status ${stale?"warning":"neutral"}`;
  const url=new URL(location.href);url.searchParams.set("view",state.marketDataView);url.searchParams.set("market",state.chainMarket);state.chainSearch?url.searchParams.set("q",state.chainSearch):url.searchParams.delete("q");state.chainState!=="all"?url.searchParams.set("moneyness",state.chainState):url.searchParams.delete("moneyness");[["strike_min",state.marketStrikeMin],["strike_max",state.marketStrikeMax],["volume_min",state.marketVolumeMin],["oi_min",state.marketOpenInterestMin]].forEach(([key,value])=>value==null?url.searchParams.delete(key):url.searchParams.set(key,value));state.marketValidQuotesOnly?url.searchParams.set("valid_quotes","1"):url.searchParams.delete("valid_quotes");history.replaceState(history.state,"",url);
  $("strategyTableHead").innerHTML = `<tr>${columns.map((column)=>`<th class="${column.key === "symbol" ? "sticky-option-symbol" : ""}" draggable="true" data-column-key="${esc(column.key)}" aria-sort="${state.chainSortKey === column.key ? (state.chainSortDirection === "asc" ? "ascending" : "descending") : "none"}" title="برای جابه‌جایی، عنوان ستون را بکشید"><div class="chain-header-control"><button type="button" class="chain-sort-button ${state.chainSortKey === column.key ? "active" : ""}" data-chain-sort="${esc(column.key)}" aria-label="مرتب‌سازی بر اساس ${esc(column.label)}${state.chainSortKey === column.key ? (state.chainSortDirection === "asc" ? "، صعودی" : "، نزولی") : ""}">${esc(column.label)}<span aria-hidden="true">${state.chainSortKey === column.key ? (state.chainSortDirection === "asc" ? "↑" : "↓") : "↕"}</span></button></div></th>`).join("")}</tr>`;
  $("tehranChainCount").textContent = num(rows.length);
  $("tehranChainBody").innerHTML = rows.length ? rows.map((item) => `<tr>${columns.map((column)=>`<td data-label="${esc(column.label)}" data-column-key="${esc(column.key)}" class="${column.key === "symbol" ? "sticky-option-symbol" : ""}">${column.render(item)}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${columns.length}" class="chain-empty">قراردادی با این فیلترها پیدا نشد. <button type="button" data-clear-market-filters>پاک کردن فیلترها</button></td></tr>`;
  renderChainColumnManager(orderedKeys.map((key)=>columnByKey.get(key)), hiddenKeys);
}

function formatPercent(value) { return value == null ? "—" : `${num(value,2)}٪`; }

function compareChainRows(a, b, columns) {
  const column = columns.find((item)=>item.key === state.chainSortKey);
  const getter = column?.value || ((item)=>item[state.chainSortKey]);
  const av = getter(a), bv = getter(b);
  if (av == null && bv == null) return String(a.symbol).localeCompare(String(b.symbol),"fa");
  if (av == null) return 1;
  if (bv == null) return -1;
  const compared = typeof av === "number" && typeof bv === "number"
    ? av - bv : String(av).localeCompare(String(bv),"fa",{numeric:true});
  return (state.chainSortDirection === "asc" ? compared : -compared) || String(a.symbol).localeCompare(String(b.symbol),"fa");
}

function activeChainLayoutKey() { return state.marketDataView === "all" ? "all" : state.chainStrategy; }

function moveChainColumn(key, targetIndex) {
  const visible = [...state.chainVisibleColumnKeys];
  const sourceIndex = visible.indexOf(key);
  const boundedTarget = Math.max(0, Math.min(visible.length - 1, targetIndex));
  if (sourceIndex < 0 || sourceIndex === boundedTarget) return;
  const targetKey = visible[boundedTarget];
  const order = [...state.chainAllColumnKeys];
  const first = order.indexOf(key), second = order.indexOf(targetKey);
  [order[first],order[second]] = [order[second],order[first]];
  state.chainColumnOrders[activeChainLayoutKey()] = order;
  saveChainColumnOrders();
  renderTehranChain();
}

function setChainColumnVisibility(key, visible) {
  const hidden = new Set(state.chainHiddenColumns[activeChainLayoutKey()] || []);
  if (visible) hidden.delete(key);
  else {
    if (state.chainVisibleColumnKeys.length <= 1) {
      setChainViewMessage("حداقل یک ستون باید در جدول باقی بماند.", "error");
      renderTehranChain();
      return;
    }
    hidden.add(key);
  }
  state.chainHiddenColumns[activeChainLayoutKey()] = [...hidden];
  saveChainHiddenColumns();
  renderTehranChain();
}

function setChainViewMessage(message, kind = "success") {
  const element = $("chainViewMessage");
  element.textContent = message;
  element.dataset.kind = kind;
}

function renderChainColumnManager(columns, hiddenKeys) {
  $("chainColumnManagerStatus").textContent = `${num(columns.length - hiddenKeys.size)} از ${num(columns.length)} ستون فعال`;
  $("chainColumnChecklist").innerHTML = columns.map((column)=>`<label class="chain-column-option"><input type="checkbox" data-column-visibility="${esc(column.key)}" ${hiddenKeys.has(column.key) ? "" : "checked"} /><span>${esc(column.label)}</span></label>`).join("");
  const views = state.chainSavedViews[activeChainLayoutKey()] || {};
  const selected = $("savedChainViews").value;
  const names = Object.keys(views).sort((a,b)=>a.localeCompare(b,"fa"));
  $("savedChainViews").innerHTML = `<option value="">یک نما را انتخاب کنید</option>${names.map((name)=>`<option value="${esc(name)}">${esc(name)}</option>`).join("")}`;
  if (names.includes(selected)) $("savedChainViews").value = selected;
  $("loadChainView").disabled = !$("savedChainViews").value;
  $("deleteChainView").disabled = !$("savedChainViews").value;
}

function saveCurrentChainView() {
  const name = $("chainViewName").value.trim();
  if (!name) { setChainViewMessage("ابتدا یک نام برای نما وارد کنید.", "error"); return; }
  const strategyViews = state.chainSavedViews[activeChainLayoutKey()] || {};
  strategyViews[name] = {order:[...state.chainAllColumnKeys], hidden:[...(state.chainHiddenColumns[activeChainLayoutKey()] || [])]};
  state.chainSavedViews[activeChainLayoutKey()] = strategyViews;
  saveChainViews();
  $("chainViewName").value = "";
  renderTehranChain();
  $("savedChainViews").value = name;
  $("loadChainView").disabled = false;
  $("deleteChainView").disabled = false;
  setChainViewMessage(`نمای «${name}» ذخیره شد.`);
}

function loadSelectedChainView() {
  const name = $("savedChainViews").value;
  const view = state.chainSavedViews[activeChainLayoutKey()]?.[name];
  if (!view) { setChainViewMessage("یک نمای ذخیره‌شده انتخاب کنید.", "error"); return; }
  state.chainColumnOrders[activeChainLayoutKey()] = Array.isArray(view.order) ? [...view.order] : [];
  state.chainHiddenColumns[activeChainLayoutKey()] = Array.isArray(view.hidden) ? [...view.hidden] : [];
  saveChainColumnOrders();
  saveChainHiddenColumns();
  renderTehranChain();
  $("savedChainViews").value = name;
  $("loadChainView").disabled = false;
  $("deleteChainView").disabled = false;
  setChainViewMessage(`نمای «${name}» بارگذاری شد.`);
}

function deleteSelectedChainView() {
  const name = $("savedChainViews").value;
  if (!name || !state.chainSavedViews[activeChainLayoutKey()]?.[name]) { setChainViewMessage("یک نمای ذخیره‌شده انتخاب کنید.", "error"); return; }
  delete state.chainSavedViews[activeChainLayoutKey()][name];
  saveChainViews();
  renderTehranChain();
  setChainViewMessage(`نمای «${name}» حذف شد.`);
}

function numericFilterValue(value) {
  return String(value ?? "").trim() === "" ? null : Number(value);
}

function matchesNumericFilter(rawValue, operator, target) {
  if (target == null) return true;
  const value = Number(rawValue), expected = Number(target);
  if (!Number.isFinite(value) || !Number.isFinite(expected)) return false;
  if (operator === "gt") return value > expected;
  if (operator === "lt") return value < expected;
  if (operator === "lte") return value <= expected;
  if (operator === "eq") return Math.abs(value - expected) < 1e-9;
  return value >= expected;
}

function renderTopOpportunities() {
  const panel = $("topOpportunities");
  if (!state.data) return;
  const blocks = selectedTopBlocks().map(({strategy, market, series}) => topCard(strategy, market, series));
  panel.innerHTML = blocks.join("");
  panel.classList.toggle("hidden", blocks.length === 0);
}

function canvasRoundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}

function fitCanvasText(ctx, value, maxWidth) {
  const text = String(value ?? "—");
  if (ctx.measureText(text).width <= maxWidth) return text;
  let shortened = text;
  while (shortened.length > 1 && ctx.measureText(`${shortened}…`).width > maxWidth) shortened = shortened.slice(0, -1);
  return `${shortened}…`;
}

function canvasText(ctx, value, x, y, size, color = "#f6f8ff", weight = 600, align = "right") {
  ctx.font = `${weight} ${size}px "Dana", "Vazirmatn", Tahoma, Arial, sans-serif`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.direction = "rtl";
  ctx.fillText(String(value), x, y);
}

async function buildBestOpportunitiesCanvas() {
  if (!state.data) throw new Error("هنوز داده‌ای برای ساخت تصویر دریافت نشده است.");
  const blocks = selectedTopBlocks();
  if (!blocks.length) throw new Error("با فیلترهای فعلی فرصت برتری برای تصویر وجود ندارد.");
  if (document.fonts?.ready) await document.fonts.ready;

  const width = 1600, outer = 64, headerHeight = 190, blockHeight = 278, footerHeight = 82;
  const height = headerHeight + blocks.length * blockHeight + footerHeight;
  const canvas = document.createElement("canvas");
  canvas.width = width; canvas.height = height;
  const ctx = canvas.getContext("2d");
  const background = ctx.createLinearGradient(0, 0, width, height);
  background.addColorStop(0, "#070a12"); background.addColorStop(1, "#10182a");
  ctx.fillStyle = background; ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "rgba(37,48,71,.45)"; ctx.lineWidth = 1;
  for (let x = 20; x < width; x += 28) for (let y = 20; y < height; y += 28) { ctx.beginPath(); ctx.arc(x, y, 1, 0, Math.PI * 2); ctx.stroke(); }

  canvasRoundRect(ctx, outer, 42, width - outer * 2, 116, 22);
  ctx.fillStyle = "rgba(18,201,255,.055)"; ctx.fill();
  ctx.strokeStyle = "#253047"; ctx.stroke();
  canvasText(ctx, "بهترین فرصت‌های اختیار معامله", width - outer - 34, 94, 36, "#f6f8ff", 800);
  canvasText(ctx, `به‌روزرسانی ${formatDate(state.data.generated_at)} · مطابق فیلترهای فعلی داشبورد`, width - outer - 34, 132, 18, "#929db2", 500);
  const coveredBasis = state.coveredBasis === "last" ? "آخرین معامله" : "بهترین پیشنهاد خرید";
  const longBasis = state.longBasis === "last" ? "آخرین معامله" : state.longBasis === "ask" ? "بهترین پیشنهاد فروش" : "بهترین پیشنهاد خرید";
  canvasText(ctx, `مبنای قیمت: کاوردکال ${coveredBasis}  ·  استراتژی خرید ${longBasis}`, outer + 32, 107, 17, "#7fe4ff", 600, "left");

  blocks.forEach((block, blockIndex) => {
    const y = headerHeight + blockIndex * blockHeight;
    const covered = block.strategy === "covered_call";
    const coveredSeriesTitle = block.series === "near" ? "کاوردکال کمی پرریسک · ITM از −۵٪ تا +۱۰٪" : "کاوردکال · فقط ITM";
    canvasText(ctx, `${covered ? coveredSeriesTitle : "خرید اختیار یا پایه"} · ${marketLabel(block.market)}`, width - outer, y + 32, 23, "#f6f8ff", 800);
    canvasText(ctx, covered ? "رتبه‌بندی بر اساس سود سالانه" : "رتبه‌بندی بر اساس بیشترین درصد پایین‌تر از پایه", outer, y + 32, 15, "#929db2", 500, "left");
    const gap = 14, cardWidth = (width - outer * 2 - gap * 4) / 5, cardHeight = 202;
    block.items.forEach((item, index) => {
      const x = width - outer - cardWidth - index * (cardWidth + gap), cardY = y + 52;
      canvasRoundRect(ctx, x, cardY, cardWidth, cardHeight, 16);
      ctx.fillStyle = "rgba(20,28,43,.96)"; ctx.fill();
      ctx.strokeStyle = covered ? "rgba(255,0,188,.30)" : "rgba(18,201,255,.34)"; ctx.stroke();
      canvasText(ctx, num(index + 1), x + cardWidth - 18, cardY + 31, 16, "#12c9ff", 800);
      canvasText(ctx, item.state, x + 18, cardY + 31, 13, item.state === "ITM" ? "#70f000" : "#e9ff00", 800, "left");
      ctx.font = '700 19px "Dana", "Vazirmatn", Tahoma, Arial, sans-serif';
      canvasText(ctx, fitCanvasText(ctx, item.asset, cardWidth - 36), x + cardWidth - 18, cardY + 68, 19, "#f6f8ff", 800);
      canvasText(ctx, fitCanvasText(ctx, item.symbol, cardWidth - 36), x + cardWidth - 18, cardY + 95, 14, "#aebbd0", 700);
      const coveredRisk = `${block.series === "near" ? "کمی پرریسک" : "فقط ITM"}${isLeveragedFund(item.asset) ? " · پرریسک + صندوق اهرمی" : ""}`;
      canvasText(ctx, covered ? coveredRisk : `ITM ${num(item.itm_percent, 2)}٪ · Δ ${deltaDisplay(item)}`, x + cardWidth - 18, cardY + 124, 13, covered && (block.series === "near" || isLeveragedFund(item.asset)) ? "#e9ff00" : "#70f000", 700);
      ctx.strokeStyle = "#253047"; ctx.beginPath(); ctx.moveTo(x + 18, cardY + 140); ctx.lineTo(x + cardWidth - 18, cardY + 140); ctx.stroke();
      const returnValue = covered ? `ماهانه ${num(item.monthly_return, 2)}٪ | سالانه ${num(item.annual_return, 2)}٪` : `${num(item.advantage_percent, 2)}٪ کمتر از قیمت پایه`;
      canvasText(ctx, fitCanvasText(ctx, returnValue, cardWidth - 36), x + cardWidth - 18, cardY + 171, covered ? 18 : 14, "#12c9ff", 800);
      const expiryText = covered
        ? `بازخرید ماهانه ${num(buybackMonthlyPercent(item), 2)}٪ | سالانه ${num(buybackAnnualPercent(item), 2)}٪`
        : `سررسید ${solarDate(item.expiry_display || item.expiry)} · ${num(item.days)} روز`;
      canvasText(ctx, expiryText, x + cardWidth - 18, cardY + 193, 11, covered && item.days < 5 ? "#ff6b7f" : "#929db2", 500);
    });
  });

  canvasText(ctx, "این تصویر خروجی ابزار غربالگری است و پیشنهاد خرید یا فروش نیست.", width - outer, height - 34, 15, "#929db2", 500);
  canvasText(ctx, "NI Option", outer, height - 34, 14, "#12c9ff", 800, "left");
  return canvas;
}

function downloadImageBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
  setStatus("success", "تصویر بهترین فرصت‌ها ساخته و ذخیره شد.");
}

async function shareBestOpportunitiesImage() {
  const button = $("shareImageButton");
  button.disabled = true;
  const original = button.innerHTML;
  button.innerHTML = '<span class="spinner"></span> در حال ساخت تصویر…';
  try {
    const canvas = await buildBestOpportunitiesCanvas();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png", .96));
    if (!blob) throw new Error("ساخت فایل تصویر ناموفق بود.");
    const filename = `best-options-${new Date().toISOString().slice(0, 10)}.png`;
    const file = new File([blob], filename, {type: "image/png"});
    if (navigator.share && navigator.canShare?.({files: [file]})) {
      try {
        await navigator.share({title: "بهترین فرصت‌های اختیار معامله", text: "خروجی بهترین فرصت‌های اختیار معامله", files: [file]});
      } catch (error) {
        if (error?.name === "AbortError") throw error;
        downloadImageBlob(blob, filename);
      }
    } else {
      downloadImageBlob(blob, filename);
    }
  } catch (error) {
    if (error?.name !== "AbortError") setStatus("error", error.message || "ساخت تصویر ناموفق بود");
  } finally {
    button.innerHTML = original;
    button.disabled = !state.data;
  }
}

function coveredContractCard(group, item, warningThreshold) {
  const itm = Number(item.itm_percent);
  const days = Number(item.days ?? group.days);
  const expiry = item.expiry_display || item.expiry || group.expiry_display || group.expiry;
  const riskTags = [
    item.is_secondary_covered
      ? '<span class="risk-tag moderate">حالت دوم · کمی پرریسک</span>'
      : itm >= -5 && itm <= 10 ? '<span class="risk-tag moderate">کمی پرریسک</span>' : "",
    isLeveragedFund(group.asset) ? '<span class="risk-tag leveraged">پرریسک + صندوق اهرمی</span>' : "",
  ].join("");
  return `<article class="contract-card covered-contract covered-overview-card market-covered-card">
    <div class="contract-context"><span>${marketLabel(group.market)}</span><span>سررسید ${esc(solarDate(expiry))} · ${num(days)} روز</span></div>
    <div class="opportunity-card-head"><div class="risk-tags">${riskTags}</div>${badge(item.state)}</div>
    <div class="covered-symbol-pair"><strong>${esc(group.asset)}</strong><strong>${esc(item.symbol)}</strong></div>
    <div class="covered-itm-row"><span>میزان ITM</span><strong class="${itm < 0 ? "itm-negative" : "itm-positive"}">${signed(item.itm_percent)}٪</strong></div>
    <dl class="covered-overview-metrics">
      <div class="metric-profit"><dt>سود کاوردکال</dt><dd class="${Number(item.expiry_return) < 0 ? "profit-negative" : "profit-positive"}">${num(item.expiry_return, 2)}٪</dd></div>
      <div class="metric-profit"><dt>سود سالانه کاوردکال</dt><dd class="${Number(item.annual_return) < 0 ? "profit-negative" : "profit-positive"}">${num(item.annual_return, 2)}٪</dd></div>
      <div class="metric-buyback"><dt>درصد بازخرید</dt><dd>${num(buybackPercent(item), 2)}٪</dd></div>
      <div class="metric-buyback"><dt>درصد بازخرید (سالانه)</dt><dd>${num(buybackAnnualPercent(item), 2)}٪</dd></div>
      <div class="metric-time"><dt>روز تا سررسید</dt><dd class="${days < 5 ? "expiry-near" : ""}">${num(days)} روز</dd></div>
    </dl>
    <dl class="card-technical-strip">
      <div><dt>دلتا اختیار</dt><dd>${deltaDisplay(item)}</dd></div>
      <div><dt>دلتا استراتژی</dt><dd>${deltaDisplay(item, "strategy_delta")}</dd></div>
      <div><dt>امتیاز جامع</dt><dd>${scoreValue(item)}<small>/۱۰۰</small></dd></div>
    </dl>
    ${coveredMarketIndicators({...item,days,expiry:item.expiry || group.expiry,expiry_display:expiry},{compact:true})}
    <footer>${detailButton("covered_call", group.market, group.asset, {...item, days, expiry:item.expiry || group.expiry, expiry_display:expiry})}</footer>
  </article>`;
}

function longContractCard(group, item) {
  const days = Number(item.days ?? group.days);
  const expiry = item.expiry_display || item.expiry || group.expiry_display || group.expiry;
  const riskTag = isLeveragedFund(group.asset) ? '<span class="risk-tag leveraged">پرریسک + صندوق اهرمی</span>' : "";
  return `<article class="contract-card long-contract long-overview-card market-long-card">
    <div class="contract-context"><span>${marketLabel(group.market)}</span><span>سررسید ${esc(solarDate(expiry))} · ${num(days)} روز</span></div>
    <div class="opportunity-card-head"><div class="risk-tags">${riskTag}</div>${badge(item.state)}</div>
    <div class="covered-symbol-pair"><strong>${esc(group.asset)}</strong><strong>${esc(item.symbol)}</strong></div>
    <dl class="long-overview-metrics">
      <div class="metric-itm"><dt>درصد ITM</dt><dd class="${Number(item.itm_percent) < 0 ? "itm-negative" : "itm-positive"}">${signed(item.itm_percent)}٪</dd></div>
      <div class="metric-advantage"><dt>مزیت نسبی</dt><dd class="${Number(item.advantage_percent) < 0 ? "advantage-negative" : "advantage-positive"}">${signed(item.advantage_percent)}٪</dd></div>
      <div class="metric-rate"><dt>نرخ دوره</dt><dd>${num(item.period_interest_rate_percent, 2)}٪</dd></div>
      <div class="metric-time"><dt>روز تا سررسید</dt><dd class="${days < 5 ? "expiry-near" : ""}">${num(days)} روز</dd></div>
    </dl>
    <dl class="card-technical-strip single">
      <div><dt>دلتا اختیار</dt><dd>${deltaDisplay(item)}</dd></div>
    </dl>
    <footer>${detailButton("long_underlying", group.market, group.asset, {...item, days, expiry:item.expiry || group.expiry, expiry_display:expiry})}</footer>
  </article>`;
}

function strategyBox(kind, groups, warningThreshold) {
  if (!groups.length) return "";
  const isCovered = kind !== "long";
  const isSecondary = kind === "covered-secondary";
  const count = groups.reduce((sum, group) => sum + group.items.length, 0);
  const cards = groups.flatMap((group) => group.items.map((item) => isCovered ? coveredContractCard(group, item, warningThreshold) : longContractCard(group, item))).join("");
  const title = isSecondary ? "کاوردکال حالت دوم" : isCovered ? "کاوردکال" : "خرید اختیار خرید یا خرید سهم";
  const hint = isSecondary ? "ITM از ‎−۵٪ تا ‎+۵٪" : "استراتژی";
  return `<section class="strategy-box ${isCovered ? "covered-strategy" : "long-strategy"} ${isSecondary ? "secondary-covered-strategy" : ""}"><header><div><small>${hint}</small><h4>${title}</h4></div><span>${num(count)} پیشنهاد</span></header><div class="contract-grid">${cards}</div></section>`;
}

function assetResultBox(asset, coveredGroups, secondaryGroups, longGroups, warningThreshold) {
  const allGroups = [...coveredGroups, ...secondaryGroups, ...longGroups];
  const total = allGroups.reduce((sum, group) => sum + group.items.length, 0);
  const markets = [...new Set(allGroups.map((group) => marketLabel(group.market)))];
  return `<article class="group-card asset-result-box" data-asset="${esc(asset)}"><header class="asset-box-header"><div><small>دارایی پایه</small><h3>${esc(asset)}</h3></div><div class="asset-box-summary"><span>${markets.map(esc).join(" · ")}</span><b>${num(total)} موقعیت</b></div></header><div class="asset-strategy-grid">${strategyBox("covered", coveredGroups, warningThreshold)}${strategyBox("covered-secondary", secondaryGroups, warningThreshold)}${strategyBox("long", longGroups, warningThreshold)}</div></article>`;
}

function renderAssetNav() {
  const nav = $("assetNav");
  if (!nav) return;
  const cards = [...document.querySelectorAll("#results .group-card[data-asset]")];
  const assets = [];
  const targets = new Map();
  cards.forEach((card) => {
    const asset = card.dataset.asset;
    if (targets.has(asset)) return;
    const id = `asset-result-${targets.size + 1}`;
    card.id = id;
    targets.set(asset, id);
    assets.push(asset);
  });
  nav.innerHTML = assets.map((asset, index) => {
    const card = cards.find((item) => item.dataset.asset === asset);
    const count = card?.querySelectorAll(".contract-card").length || 0;
    return `<button type="button" data-scroll-target="${targets.get(asset)}" class="${index === 0 ? "active" : ""}"><span class="asset-nav-name">${esc(asset)}</span><b class="asset-nav-count">${num(count)}</b></button>`;
  }).join("");
  document.querySelector(".asset-rail")?.classList.toggle("hidden", assets.length === 0);
}

function render() {
  if (!state.data) return;
  syncMarketControls();
  state.details.clear();
  const covered = filteredGroups(state.data.covered_call);
  const secondaryCovered = secondaryCoveredGroups();
  const longRows = filteredGroups(state.data.long_underlying);
  const shownCovered = state.strategy === "long" ? [] : covered;
  const shownSecondary = state.strategy === "long" ? [] : secondaryCovered;
  const shownLong = state.strategy === "covered" ? [] : longRows;
  const availableAssets = new Set([...shownCovered, ...shownSecondary, ...shownLong].map((group) => group.asset));
  const orderedAssets = [...availableAssets].sort((a, b) => {
    const ai = state.data.assets.indexOf(a), bi = state.data.assets.indexOf(b);
    return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi) || a.localeCompare(b, "fa");
  });
  const boxes = orderedAssets.map((asset) => assetResultBox(asset, shownCovered.filter((group) => group.asset === asset), shownSecondary.filter((group) => group.asset === asset), shownLong.filter((group) => group.asset === asset), state.data.rules.warning_return));
  $("results").innerHTML = boxes.join("");
  renderOpportunitiesDashboard();
  renderAssetNav();
  $("emptyState").classList.toggle("hidden", boxes.length > 0);
  renderTopOpportunities();
  renderTehranChain();
}

function opportunityDashboardRows() {
  if (!state.data) return [];
  const flatten=(groups,strategy)=>(groups||[]).flatMap((group)=>group.items.map((item)=>({...item,asset:item.asset||group.asset,market:item.market||group.market,strategy})));
  return [...flatten(state.data.covered_call,"covered_call"),...flatten(state.data.long_underlying,"long_call")].filter((item)=>item.symbol).map((item)=>{
    const covered=item.strategy==="covered_call",liquidity=Number(item.transaction_value||0)>0?"مناسب":"پایین";
    const reasons=(covered?[Number.isFinite(Number(item.annual_return))?`بازده سالانه ${num(item.annual_return,1)}٪`:null,liquidity==="مناسب"?"نقدشوندگی قابل‌قبول":null,item.state?`فاصله اعمال در وضعیت ${item.state}`:null]:[Number.isFinite(Number(item.advantage_percent))?`مزیت نسبی ${num(item.advantage_percent,1)}٪`:null,Number(item.days)>30?"زمان کافی تا سررسید":null,liquidity==="مناسب"?"نقدشوندگی قابل‌قبول":null]).filter(Boolean).slice(0,3);
    const risks=(covered?[Number(item.days)<10?"فاصله کم تا سررسید":null,item.state==="ITM"?"احتمال اعمال و محدودشدن رشد سهم":null,liquidity==="پایین"?"نقدشوندگی پایین":null]:[Number(item.days)<20?"فرسایش زمانی نزدیک سررسید":null,Number(item.implied_volatility)>60?"نوسان ضمنی بالا":null,liquidity==="پایین"?"نقدشوندگی پایین":null]).filter(Boolean);
    const pricing=[item.base_price,item.calculation_price].every((value)=>Number.isFinite(Number(value))&&Number(value)>0)?"market":"insufficient";
    return {...item,status:"active",liquidity,reasons,risks,pricing,score:finiteNumber(item.covered_score??item.score),id:`${item.strategy}|${item.market}|${item.symbol}`};
  });
}

const opportunitiesMobileMedia = window.matchMedia("(max-width: 767px)");

function renderOpportunitiesDashboard() {
  const host=$("opportunitiesDashboard"); if(!host||!state.data)return;
  const params=new URLSearchParams(location.search),status="active",market=params.get("market")||"all",strategy=params.get("strategy")||"all",asset=params.get("asset")||"all",money=params.get("money")||"all",sort=params.get("sort")||"priority",query=faNorm(params.get("q")||"");
  const source=opportunityDashboardRows();
  const marketRows=source.filter((row)=>market==="all"||row.market===market);
  const assets=[...new Set(marketRows.map((row)=>row.asset).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"fa"));
  let rows=status==="active"?source:[];
  rows=rows.filter((row)=>(market==="all"||row.market===market)&&(strategy==="all"||row.strategy===strategy)&&(asset==="all"||row.asset===asset)&&(money==="all"||row.state===money)&&(!query||faNorm(`${row.asset} ${row.symbol}`).includes(query)));
  rows.sort((a,b)=>sort==="expiry"?Number(a.days)-Number(b.days):sort==="liquidity"?Number(b.transaction_value||0)-Number(a.transaction_value||0):sort==="return"?Number(b.annual_return||-Infinity)-Number(a.annual_return||-Infinity):Number(b.score??-1)-Number(a.score??-1)||Number(b.transaction_value||0)-Number(a.transaction_value||0));
  const requestedPageSize=Number(params.get("page_size"));
  const pageSize=[10,25,50].includes(requestedPageSize)?requestedPageSize:25;
  const totalRows=rows.length;
  const pageCount=Math.max(1,Math.ceil(totalRows/pageSize));
  const requestedPage=Math.max(1,Number.parseInt(params.get("page")||"1",10)||1);
  const page=Math.min(requestedPage,pageCount);
  const pageStart=(page-1)*pageSize;
  rows=rows.slice(pageStart,pageStart+pageSize);
  const covered=source.filter((row)=>row.strategy==="covered_call").length,long=source.filter((row)=>row.strategy==="long_call").length,valid=source.filter((row)=>row.pricing==="market").length,low=source.filter((row)=>row.liquidity==="پایین").length,generated=state.data.generated_at?formatDate(state.data.generated_at):"—";
  const option=(value,label,current)=>`<option value="${value}" ${value===current?"selected":""}>${label}</option>`;
  const reasonMarkup=(row)=>`<div class="opportunity-reasons">${row.reasons.map((reason)=>`<span>${esc(reason)}</span>`).join("")||'<span class="review">نیازمند بررسی داده</span>'}<div class="opportunity-reason-popover" role="tooltip"><b>منطق شناسایی سامانه</b>${row.reasons.map((reason)=>`<p>✓ ${esc(reason)}</p>`).join("")}<small>امتیاز، احتمال سود یا تضمین موفقیت نیست.</small></div></div>`;
  const metric=(row)=>row.strategy==="covered_call"?`${metricOrDash(row.annual_return,1,"٪")} سالانه`:`${metricOrDash(row.advantage_percent,1,"٪")} مزیت نسبی`;
  const rowsMarkup=rows.map((row)=>{state.details.set(row.id,{...row,strategy:row.strategy==="long_call"?"long_underlying":"covered_call"});return `<tr><td data-label="نماد"><button type="button" class="opportunity-symbol" data-opportunity-detail="${esc(row.id)}"><strong>${esc(row.asset)}</strong><small dir="ltr">${esc(row.symbol)}</small></button></td><td data-label="استراتژی"><span class="strategy-chip ${row.strategy==="long_call"?"long":"covered"}">${row.strategy==="long_call"?"خرید Call":"کاوردکال"}</span></td><td data-label="وضعیت"><span class="opportunity-status active">فعال</span></td><td data-label="قیمت پایه"><b dir="ltr">${metricOrDash(row.base_price,0)}</b><small class="data-source market">بازار</small></td><td data-label="اعمال" dir="ltr">${metricOrDash(row.strike,0)}</td><td data-label="سررسید"><b>${num(row.days)} روز</b><small dir="ltr">${esc(solarDate(row.expiry_display||row.expiry))}</small></td><td data-label="چرا شناسایی شد؟">${reasonMarkup(row)}</td><td data-label="معیار اصلی"><b dir="ltr">${metric(row)}</b><small class="data-source system">معیار سامانه</small></td><td data-label="نقدشوندگی"><span class="liquidity ${row.liquidity==="پایین"?"low":"good"}">${esc(row.liquidity)}</span></td><td data-label="قیمت‌گذاری"><span class="pricing ${row.pricing}">${row.pricing==="market"?"قیمت بازار":"داده ناکافی"}</span></td><td data-label="اقدام"><button type="button" class="primary-button compact" data-opportunity-detail="${esc(row.id)}">مشاهده تحلیل</button></td></tr>`;}).join("");
  const mobileMarkup=rows.map((row)=>`<article class="opportunity-mobile-card ${row.strategy==="long_call"?"long":"covered"}"><header><div><strong>${esc(row.asset)}</strong><small dir="ltr">${esc(row.symbol)}</small></div><span class="strategy-chip ${row.strategy==="long_call"?"long":"covered"}">${row.strategy==="long_call"?"خرید Call":"کاوردکال"}</span></header>${reasonMarkup(row)}<dl><div><dt>معیار اصلی</dt><dd dir="ltr">${metric(row)}</dd></div><div><dt>سررسید</dt><dd>${num(row.days)} روز</dd></div><div><dt>نقدشوندگی</dt><dd>${esc(row.liquidity)}</dd></div><div><dt>وضعیت قیمت</dt><dd>${row.pricing==="market"?"بازار":"داده ناکافی"}</dd></div></dl><details><summary>جزئیات و ریسک‌ها</summary><p>${row.risks.length?row.risks.map(esc).join(" · "):"ریسک ویژه‌ای از داده فعلی استخراج نشد؛ تحلیل کامل را بررسی کنید."}</p><small>اعمال ${metricOrDash(row.strike,0)} · پایه ${metricOrDash(row.base_price,0)} · ${generated}</small></details><button type="button" class="primary-button" data-opportunity-detail="${esc(row.id)}">مشاهده تحلیل کامل</button></article>`).join("");
  const empty=source.length?`<div class="opportunities-empty"><strong>فرصتی مطابق فیلترهای انتخاب‌شده پیدا نشد.</strong><p>${status!=="active"?"تاریخچه تغییر وضعیت فرصت‌ها هنوز توسط منبع داده ثبت نمی‌شود.":"فیلترها را تغییر دهید یا پاک کنید."}</p><button type="button" data-opportunity-reset>پاک‌کردن فیلترها</button></div>`:'<div class="opportunities-empty"><strong>در حال حاضر هیچ فرصتی مطابق معیارهای سامانه شناسایی نشده است.</strong><a href="/market">مشاهده داده‌های بازار</a></div>';
  host.innerHTML=`<header class="opportunities-header"><div><small>فرصت شناسایی‌شده توسط سامانه</small><h2>فرصت‌ها</h2><p>قراردادهای عبورکرده از قواعد قابل توضیح؛ نه پیشنهاد خرید و نه تضمین بازده.</p><div class="opportunities-market-status"><span>وضعیت بازار از منبع داده اعلام نشده</span><span>آخرین داده ${generated}</span></div></div><div><strong>${num(source.length)}</strong><span>فرصت فعال</span><button type="button" data-opportunity-refresh>تازه‌سازی داده‌ها</button><a href="/methodology">روش شناسایی فرصت‌ها</a></div></header><section class="opportunity-transparency"><div><small>شفافیت موتور تحلیل</small><h3>این فرصت‌ها چگونه شناسایی می‌شوند؟</h3><p>سامانه نقدشوندگی، فاصله قیمت اعمال یا سربه‌سر، بازده، روزهای باقی‌مانده و شرایط قیمت‌گذاری را بررسی می‌کند.</p></div><ul><li><b>کاوردکال:</b> بازده پریمیوم، پوشش نزول، فاصله اعمال و نقدشوندگی</li><li><b>خرید Call:</b> مزیت ورود، فاصله سربه‌سر، زمان، IV و نقدشوندگی</li></ul><footer><span>آخرین اجرای تحلیل ${generated}</span><span>${num(source.length)} قرارداد منتخب</span><a href="/methodology">مشاهده روش کامل</a></footer></section><section class="opportunities-kpis"><article><span>فرصت‌های فعال</span><strong>${num(source.length)}</strong><small>کاوردکال ${num(covered)} · خرید Call ${num(long)}</small></article><article><span>فرصت‌های جدید</span><strong>—</strong><small>تاریخچه بازدید در داده فعلی موجود نیست</small></article><article><span>فرصت‌های تغییرکرده</span><strong>—</strong><small>ثبت رویداد تغییر نیازمند پشتیبانی API است</small></article><article><span>کیفیت داده</span><strong>${source.length?num(valid/source.length*100,0):"—"}٪</strong><small>${num(low)} مورد با نقدشوندگی پایین</small></article></section><section class="opportunity-changes"><header><div><small>رویدادهای قابل پیگیری</small><h3>تغییرات از آخرین بازدید شما</h3></div></header><p>تاریخچه تغییر فرصت‌ها هنوز ثبت نمی‌شود؛ فرصت‌های فعال بر اساس آخرین داده بازار دوباره محاسبه شده‌اند.</p></section><nav class="opportunity-tabs" aria-label="وضعیت فرصت‌ها">${[["active","فعال",source.length],["new","جدید",null],["changed","تغییرکرده",null],["expired","منقضی",null]].map(([value,label,count])=>`<button type="button" data-opportunity-status="${value}" aria-pressed="${status===value}">${label}<span>${count==null?"—":num(count)}</span></button>`).join("")}</nav><details class="opportunity-filter-sheet" open><summary><span>فیلترها و مرتب‌سازی</span><b>${num(rows.length)} نتیجه</b></summary><form class="opportunity-filterbar"><label><span>جست‌وجو</span><span class="opportunity-search"><input name="q" type="search" value="${esc(params.get("q")||"")}" placeholder="نماد پایه یا اختیار"><button type="button" data-opportunity-clear aria-label="پاک‌کردن جست‌وجو">×</button></span></label><label><span>استراتژی</span><select name="strategy">${option("all","همه",strategy)}${option("covered_call","کاوردکال",strategy)}${option("long_call","خرید Call",strategy)}</select></label><label><span>دارایی پایه</span><select name="asset">${option("all","همه",asset)}${assets.map((value)=>option(value,value,asset)).join("")}</select></label><label><span>وضعیت اعمال</span><select name="money">${option("all","همه",money)}${option("ITM","ITM",money)}${option("ATM","ATM",money)}${option("OTM","OTM",money)}</select></label><label><span>مرتب‌سازی</span><select name="sort">${option("priority","اولویت سامانه",sort)}${option("expiry","نزدیک‌ترین سررسید",sort)}${option("liquidity","بیشترین نقدشوندگی",sort)}${option("return","بیشترین بازده پریمیوم",sort)}</select></label><button type="button" data-opportunity-reset>پاک‌کردن همه</button></form></details>${rows.length?`<section class="opportunities-table-panel"><header><div><h3>فرصت‌های قابل بررسی</h3><small>امتیاز تطابق، احتمال سود یا سیگنال قطعی نیست.</small></div><span>${num(rows.length)} نتیجه</span></header><div class="opportunities-table-wrap"><table><thead><tr><th>نماد</th><th>استراتژی</th><th>وضعیت</th><th>قیمت پایه</th><th>اعمال</th><th>سررسید</th><th>چرا شناسایی شد؟</th><th>معیار اصلی</th><th>نقدشوندگی</th><th>قیمت‌گذاری</th><th>اقدام</th></tr></thead><tbody>${rowsMarkup}</tbody></table></div><div class="opportunities-mobile-list">${mobileMarkup}</div></section><footer class="opportunities-pagination"><span>نمایش ۱ تا ${num(rows.length)} از ${num(rows.length)}</span><span>تمام نتایج فعلی نمایش داده شده‌اند</span></footer>`:empty}`;
  const opportunitiesHero=host.querySelector(".opportunities-header");
  opportunitiesHero?.classList.add("economic-hero","shared-page-hero","shared-page-hero--option","shared-page-hero--option-actions");
  opportunitiesHero?.firstElementChild?.classList.add("economic-hero-copy");
  opportunitiesHero?.lastElementChild?.classList.add("shared-page-hero-actions");
  opportunitiesHero?.querySelector(".opportunities-market-status span:first-child")?.remove();
  opportunitiesHero?.querySelector('.shared-page-hero-actions a[href="/methodology"]')?.remove();
  host.querySelector(".opportunity-changes")?.remove();
  const inactiveRepresentation=host.querySelector(opportunitiesMobileMedia.matches?".opportunities-table-wrap":".opportunities-mobile-list");
  inactiveRepresentation?.remove();
  host.querySelector(".opportunity-filter-sheet > summary b")?.replaceChildren(document.createTextNode(`${num(totalRows)} نتیجه`));
  const panelCount=host.querySelector(".opportunities-table-panel > header > span");
  if(panelCount) panelCount.textContent=`${num(rows.length)} از ${num(totalRows)} نتیجه`;
  host.querySelectorAll("[data-opportunity-status]").forEach((button)=>{
    if(button.dataset.opportunityStatus==="active") return;
    button.disabled=true;
    button.setAttribute("aria-disabled","true");
    button.title="این نما پس از اضافه‌شدن تاریخچه فرصت‌ها فعال می‌شود";
    button.querySelector("span")?.replaceChildren(document.createTextNode("به‌زودی"));
  });
  const unavailableKpis=host.querySelectorAll(".opportunities-kpis article:nth-child(2),.opportunities-kpis article:nth-child(3)");
  unavailableKpis.forEach((card)=>{
    card.querySelector("strong")?.replaceChildren(document.createTextNode("به‌زودی"));
    card.querySelector("small")?.replaceChildren(document.createTextNode("تاریخچه فرصت‌ها هنوز در API موجود نیست"));
  });
  const changes=host.querySelector(".opportunity-changes");
  if(changes){changes.querySelector("h3").textContent="پیگیری تغییرات به‌زودی";changes.querySelector("p").textContent="تا زمان اضافه‌شدن تاریخچه API، فقط فرصت‌های فعال و تازه‌محاسبه‌شده نمایش داده می‌شوند.";}
  const pager=host.querySelector(".opportunities-pagination");
  if(pager){
    const range=document.createElement("span");
    const rangeEnd=Math.min(totalRows,pageStart+rows.length);
    range.textContent=totalRows?`نمایش ${num(pageStart+1)} تا ${num(rangeEnd)} از ${num(totalRows)}`:"بدون نتیجه";
    const controls=document.createElement("nav");
    controls.className="opportunities-page-controls";
    controls.setAttribute("aria-label","صفحه‌بندی فرصت‌ها");
    const previous=document.createElement("button");
    previous.type="button";previous.dataset.opportunityPage=String(page-1);previous.disabled=page<=1;previous.textContent="صفحه قبل";
    const indicator=document.createElement("span");
    indicator.setAttribute("aria-current","page");indicator.textContent=`صفحه ${num(page)} از ${num(pageCount)}`;
    const next=document.createElement("button");
    next.type="button";next.dataset.opportunityPage=String(page+1);next.disabled=page>=pageCount;next.textContent="صفحه بعد";
    const sizeLabel=document.createElement("label");
    const sizeText=document.createElement("span");sizeText.textContent="تعداد در صفحه";
    const sizeSelect=document.createElement("select");sizeSelect.name="page_size";sizeSelect.setAttribute("aria-label","تعداد فرصت در هر صفحه");
    [10,25,50].forEach((value)=>{const choice=document.createElement("option");choice.value=String(value);choice.textContent=num(value);choice.selected=value===pageSize;sizeSelect.append(choice);});
    sizeLabel.append(sizeText,sizeSelect);controls.append(previous,indicator,next,sizeLabel);pager.replaceChildren(range,controls);
  }
  const filterbar=host.querySelector(".opportunity-filterbar");
  const strategyField=filterbar?.querySelector('select[name="strategy"]')?.closest("label");
  if(filterbar&&strategyField){
    const marketField=document.createElement("label"),marketCaption=document.createElement("span"),marketSelect=document.createElement("select");
    marketCaption.textContent="بازار";
    marketSelect.name="market";
    marketSelect.setAttribute("aria-label","فیلتر بازار فرصت‌ها");
    [["all","هر دو بازار"],["tehran","بورس تهران"],["goods","بورس کالا"]].forEach(([value,label])=>{
      const choice=document.createElement("option");
      choice.value=value;choice.textContent=label;choice.selected=value===market;
      marketSelect.append(choice);
    });
    marketField.append(marketCaption,marketSelect);
    filterbar.insertBefore(marketField,strategyField);
  }
  host.setAttribute("aria-busy","false");
  const update=(name,value,{replace=name==="q"}={})=>{const next=new URLSearchParams(location.search);value&&value!=="all"?next.set(name,value):next.delete(name);if(name==="market")next.delete("asset");if(name!=="page")next.delete("page");history[replace?"replaceState":"pushState"](null,"",`${location.pathname}${next.size?`?${next}`:""}`);renderOpportunitiesDashboard();if(name==="q")requestAnimationFrame(()=>{const input=$("opportunitiesDashboard")?.querySelector('input[name="q"]');input?.focus();input?.setSelectionRange(input.value.length,input.value.length);});};
  host.querySelectorAll("[data-opportunity-status]").forEach((button)=>button.addEventListener("click",()=>update("status",button.dataset.opportunityStatus)));
  host.querySelectorAll(".opportunity-filterbar select").forEach((control)=>control.addEventListener("change",()=>update(control.name,control.value)));
  const search=host.querySelector('input[name="q"]');let timer;search?.addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(()=>update("q",search.value.trim()),300);});
  host.querySelector("[data-opportunity-clear]")?.addEventListener("click",()=>update("q",""));
  host.querySelectorAll("[data-opportunity-reset]").forEach((button)=>button.addEventListener("click",()=>{const next=new URLSearchParams(location.search);["status","market","strategy","asset","money","sort","q","page"].forEach((key)=>next.delete(key));history.pushState(null,"",`${location.pathname}${next.size?`?${next}`:""}`);renderOpportunitiesDashboard();}));
  host.querySelectorAll("[data-opportunity-page]").forEach((button)=>button.addEventListener("click",()=>update("page",button.dataset.opportunityPage)));
  host.querySelector('.opportunities-page-controls select[name="page_size"]')?.addEventListener("change",(event)=>update("page_size",event.currentTarget.value));
  host.querySelector("[data-opportunity-refresh]")?.addEventListener("click",()=>loadData(true));
  host.querySelectorAll("[data-opportunity-detail]").forEach((button)=>button.addEventListener("click",()=>{const id=button.dataset.opportunityDetail,next=new URLSearchParams(location.search);next.set("opportunity",id);history.pushState({opportunity:id},"",`${location.pathname}?${next}`);openAnalysisByKey(id);}));
}

opportunitiesMobileMedia.addEventListener?.("change",()=>renderOpportunitiesDashboard());
window.addEventListener("popstate",()=>{
  if(currentPage!=="market" || location.pathname!=="/opportunities") return;
  renderOpportunitiesDashboard();
});

function historyChart(points, strike, breakeven) {
  if (!points.length) return "";
  const width = 900, height = 330, padX = 58, padY = 30;
  const values = points.map((point) => point.price).concat([strike, breakeven].filter((v) => v != null));
  let min = Math.min(...values), max = Math.max(...values);
  const margin = Math.max(1, (max - min) * .08); min -= margin; max += margin;
  const x = (index) => padX + index / Math.max(1, points.length - 1) * (width - padX * 2);
  const y = (value) => padY + (max - value) / Math.max(1, max - min) * (height - padY * 2);
  const line = points.map((point, index) => `${x(index).toFixed(1)},${y(point.price).toFixed(1)}`).join(" ");
  const ref = (value, label, className) => value == null ? "" : `<line x1="${padX}" y1="${y(value)}" x2="${width-padX}" y2="${y(value)}" class="${className}" stroke-width="2" stroke-dasharray="8 6"/><text x="${width-padX-4}" y="${y(value)-6}" text-anchor="end" class="${className}">${label}: ${num(value)}</text>`;
  return `<div class="history-chart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="نمودار قیمت تاریخی دارایی پایه"><line x1="${padX}" y1="${padY}" x2="${padX}" y2="${height-padY}" class="axis"/><line x1="${padX}" y1="${height-padY}" x2="${width-padX}" y2="${height-padY}" class="axis"/><polyline points="${line}" fill="none" class="price-line" stroke-width="3" vector-effect="non-scaling-stroke"/>${ref(strike,"اعمال","strike-reference")}${ref(breakeven,"سربه‌سر","breakeven-reference")}<text x="${padX}" y="${height-7}" text-anchor="start">${esc(solarDate(points[0].date))}</text><text x="${width-padX}" y="${height-7}" text-anchor="end">${esc(solarDate(points.at(-1).date))}</text><text x="${padX-8}" y="${padY+5}" text-anchor="end">${num(max)}</text><text x="${padX-8}" y="${height-padY}" text-anchor="end">${num(min)}</text></svg></div>`;
}

function coveredDailyLimit(item) {
  const rules = state.data?.rules || {};
  if (item.market === "goods") return {rate: Number(rules.goods_daily_limit_percent ?? 10) / 100, label: "دارایی بورس کالا"};
  if (LEVERAGED_ASSETS.has(item.asset)) return {rate: Number(rules.leveraged_daily_limit_percent ?? 4) / 100, label: "صندوق اهرمی"};
  return {rate: Number(rules.tehran_daily_limit_percent ?? 3) / 100, label: "سهام یا صندوق عادی بورس تهران"};
}

function rollingMonthBounds(points) {
  if (!points.length) return null;
  const latest = new Date(`${points.at(-1).date}T00:00:00Z`).getTime();
  const cutoff = latest - 29 * 24 * 60 * 60 * 1000;
  const month = points.filter((point) => new Date(`${point.date}T00:00:00Z`).getTime() >= cutoff);
  return {
    high: Math.max(...month.map((point) => Number(point.high ?? point.price))),
    low: Math.min(...month.map((point) => Number(point.low ?? point.price))),
    from: month[0]?.date,
    to: month.at(-1)?.date,
  };
}

function scenarioPrices(item, history) {
  const base = Number(item.base_price), days = Math.max(0, Number(item.days) || 0);
  if (!Number.isFinite(base)) return null;
  const limit = coveredDailyLimit(item);
  const bounds = rollingMonthBounds(history.points || []);
  const scenarios = [
    {tone: "up", title: "حداکثر دامنه مثبت متوالی", price: base * Math.pow(1 + limit.rate, days), detail: `${num(limit.rate * 100)}٪ مثبت در هر روز باقی‌مانده`},
    {tone: "down", title: "حداکثر دامنه منفی متوالی", price: base * Math.pow(1 - limit.rate, days), detail: `${num(limit.rate * 100)}٪ منفی در هر روز باقی‌مانده`},
  ];
  if (bounds) {
    scenarios.push(
      {tone: "low", title: "Low کندل ماهانه", price: bounds.low, detail: `کمترین قیمت از ${esc(solarDate(bounds.from))} تا ${esc(solarDate(bounds.to))}`},
      {tone: "high", title: "High کندل ماهانه", price: bounds.high, detail: `بیشترین قیمت از ${esc(solarDate(bounds.from))} تا ${esc(solarDate(bounds.to))}`},
    );
  }
  return {days, limit, scenarios};
}

function scenarioSummary(label, results) {
  const wins = results.filter((result) => result.profit > 0);
  const losses = results.filter((result) => result.profit < 0);
  const neutral = results.length - wins.length - losses.length;
  return `<div class="scenario-summary-row"><strong>${esc(label)}</strong><span class="scenario-win-count">${num(wins.length)} از ${num(results.length)} سناریو سودده</span><span class="scenario-loss-list">${losses.length ? `زیان در: ${losses.map((result) => esc(result.title)).join("، ")}` : "سناریوی زیان‌ده ندارد"}${neutral ? ` · ${num(neutral)} سناریو سربه‌سر` : ""}</span></div>`;
}

function coveredScenarioPanel(item, history) {
  if (item.strategy !== "covered_call") return "";
  const base = Number(item.base_price), premium = Number(item.calculation_price), strike = Number(item.strike);
  if (![base, premium, strike].every(Number.isFinite)) return "";
  const scenarioData = scenarioPrices(item, history);
  if (!scenarioData) return "";
  const {days, limit, scenarios} = scenarioData;
  const netCost = base - premium;
  const results = scenarios.map((scenario) => {
    const expiryValue = Math.min(scenario.price, strike);
    const profit = expiryValue - netCost;
    const profitPercent = netCost > 0 ? profit / netCost * 100 : null;
    const profitClass = profit >= 0 ? "scenario-profit" : "scenario-loss";
    return {title: scenario.title, profit, card: `<article class="scenario-card ${scenario.tone}"><header><strong>${scenario.title}</strong><small>${scenario.detail}</small></header><dl><div><dt>قیمت پایه در سررسید</dt><dd>${num(scenario.price)}</dd></div><div><dt>سود/زیان هر واحد کاوردکال</dt><dd class="${profitClass}">${profit >= 0 ? "+" : ""}${num(profit)} <span>(${profitPercent == null ? "—" : `${profitPercent >= 0 ? "+" : ""}${num(profitPercent, 2)}٪`})</span></dd></div></dl></article>`};
  });
  return `<section class="scenario-panel"><div class="scenario-heading"><div><small>سناریوهای نظری روز سررسید</small><h3>تحلیل دامنه نوسان و کندل ماهانه</h3></div><div class="scenario-facts"><span>${limit.label}</span><b>دامنه روزانه ±${num(limit.rate * 100)}٪</b><b>سررسید ${esc(solarDate(item.expiry_display || item.expiry))}</b><b>${num(days)} روز باقی‌مانده</b></div></div><div class="scenario-summary">${scenarioSummary("کاوردکال", results)}</div><div class="scenario-grid">${results.map((result) => result.card).join("")}</div><p class="scenario-note">مبنای محاسبه: هزینه خالص اولیه = قیمت دارایی پایه منهای وجه دریافتی اختیار. ارزش نهایی کاوردکال برابر حداقل قیمت پایه در سررسید و قیمت اعمال است. High و Low از پنجره متحرک ۳۰ روز تقویمی تا آخرین داده محاسبه شده‌اند. این اعداد سناریوی نظری‌اند و پیش‌بینی بازار نیستند.</p></section>`;
}

function longScenarioPanel(item, history) {
  if (item.strategy !== "long_underlying") return "";
  const base = Number(item.base_price), premium = Number(item.calculation_price), strike = Number(item.strike);
  if (![base, premium, strike].every(Number.isFinite) || base <= 0) return "";
  const scenarioData = scenarioPrices(item, history);
  if (!scenarioData) return "";
  const {days, limit, scenarios} = scenarioData;
  const interestRate = Number(state.data?.rules?.long_interest_rate || 0) / 100;
  const dailyInterestRate = interestRate / 365;
  const investedDifference = base - premium;
  const investedDifferenceAtExpiry = investedDifference * Math.pow(1 + dailyInterestRate, days);
  const interestIncome = investedDifferenceAtExpiry - investedDifference;
  const optionResults = [];
  const underlyingResults = [];
  const cards = scenarios.map((scenario) => {
    const optionFinalValue = investedDifferenceAtExpiry + Math.max(scenario.price - strike, 0);
    const optionProfit = optionFinalValue - scenario.price;
    const underlyingProfit = scenario.price - base;
    optionResults.push({title: scenario.title, profit: optionProfit});
    underlyingResults.push({title: scenario.title, profit: underlyingProfit});
    const optionClass = optionProfit >= 0 ? "scenario-profit" : "scenario-loss";
    const underlyingClass = underlyingProfit >= 0 ? "scenario-profit" : "scenario-loss";
    return `<article class="scenario-card long-scenario ${scenario.tone}"><header><strong>${scenario.title}</strong><small>${scenario.detail}</small></header><dl><div><dt>قیمت پایه در سررسید</dt><dd>${num(scenario.price)}</dd></div><div><dt>مزیت/زیان اختیار نسبت به خرید پایه</dt><dd class="${optionClass}">${optionProfit >= 0 ? "+" : ""}${num(optionProfit)} <span>(${strike > 0 ? `${optionProfit >= 0 ? "+" : ""}${num(optionProfit / strike * 100, 2)}٪` : "—"})</span></dd></div><div><dt>سود/زیان خرید مستقیم پایه</dt><dd class="${underlyingClass}">${underlyingProfit >= 0 ? "+" : ""}${num(underlyingProfit)} <span>(${underlyingProfit >= 0 ? "+" : ""}${num(underlyingProfit / base * 100, 2)}٪)</span></dd></div></dl></article>`;
  }).join("");
  return `<section class="scenario-panel"><div class="scenario-heading"><div><small>سناریوهای نظری روز سررسید</small><h3>مقایسه خرید اختیار و خرید مستقیم پایه</h3></div><div class="scenario-facts"><span>${limit.label}</span><b>دامنه روزانه ±${num(limit.rate * 100)}٪</b><b>نرخ بهره روزانه ${num(dailyInterestRate * 100, 4)}٪</b><b>سود بهره تا سررسید ${num(interestIncome)}</b><b>سررسید ${esc(solarDate(item.expiry_display || item.expiry))}</b><b>${num(days)} روز باقی‌مانده</b></div></div><div class="scenario-summary">${scenarioSummary("خرید اختیار به‌جای دارایی پایه", optionResults)}${scenarioSummary("خرید مستقیم دارایی پایه", underlyingResults)}</div><div class="scenario-grid">${cards}</div><p class="scenario-note">سرمایه اولیه در هر دو انتخاب برابر قیمت امروز دارایی پایه است. در روش اختیار، بهای اختیار پرداخت و اختلاف وجه با نرخ روزانه مرکب سرمایه‌گذاری می‌شود. مزیت/زیان اختیار نسبت به خرید پایه = [ارزش وجه سرمایه‌گذاری‌شده در سررسید + max(قیمت سناریو − اعمال، صفر)] − قیمت پایه در همان سناریو. وقتی قیمت سناریو بالاتر از اعمال باشد، این مقدار به «وجه سرمایه‌گذاری‌شده در سررسید − قیمت اعمال» ساده می‌شود و با تغییر قیمت سناریو ثابت می‌ماند. درصد مزیت مطابق معیار این استراتژی نسبت به قیمت اعمال محاسبه شده است. High و Low از پنجره متحرک ۳۰ روز تقویمی‌اند؛ این اعداد سناریوی نظری‌اند و پیش‌بینی بازار نیستند.</p></section>`;
}

function scenarioPanel(item, history) {
  return coveredScenarioPanel(item, history) || longScenarioPanel(item, history);
}

function analysisValue(value, digits = 2, suffix = "") {
  return value == null || !Number.isFinite(Number(value)) ? "—" : `${num(value,digits)}${suffix}`;
}

function analysisTooltip(label, text) {
  const id = `analysis-tip-${String(label).replace(/[^a-zA-Z0-9\u0600-\u06ff]+/g,"-")}`;
  return `<span class="analysis-tooltip"><button type="button" aria-label="توضیح ${esc(label)}" aria-describedby="${id}">i</button><span id="${id}" role="tooltip">${esc(text)}</span></span>`;
}

function coveredPayoffChart(item, metric) {
  const base=metric.base, costBase=Number(metric.costBase??base), strike=metric.strike, premium=metric.netPremium, breakeven=metric.breakeven;
  if (![base,costBase,strike,premium,breakeven].every(Number.isFinite)) return '<div class="covered-analysis-empty">داده کافی برای رسم نمودار سود و زیان وجود ندارد.</div>';
  const width=760,height=270,padX=54,padY=30;
  const minPrice=Math.max(0,Math.min(base,breakeven,strike)*.72),maxPrice=Math.max(base,strike)*1.28;
  const points=Array.from({length:81},(_,i)=>{const price=minPrice+(maxPrice-minPrice)*i/80;return {price,profit:Math.min(price,strike)-costBase+premium};});
  const profits=points.map(x=>x.profit).concat([0]);let minProfit=Math.min(...profits),maxProfit=Math.max(...profits);const margin=Math.max(1,(maxProfit-minProfit)*.12);minProfit-=margin;maxProfit+=margin;
  const x=v=>padX+(v-minPrice)/Math.max(1,maxPrice-minPrice)*(width-padX*2),y=v=>padY+(maxProfit-v)/Math.max(1,maxProfit-minProfit)*(height-padY*2);
  const line=points.map(p=>`${x(p.price).toFixed(1)},${y(p.profit).toFixed(1)}`).join(" ");
  const marker=(value,label,tone)=>`<line x1="${x(value)}" y1="${padY}" x2="${x(value)}" y2="${height-padY}" class="${tone}"/><text x="${x(value)}" y="${height-8}" text-anchor="middle" class="${tone}">${label} · ${num(value)}</text>`;
  return `<div class="covered-payoff" role="img" aria-label="نمودار سود و زیان کاوردکال؛ سربه‌سر ${num(breakeven)}، قیمت فعلی ${num(base)} و قیمت اعمال ${num(strike)}"><svg viewBox="0 0 ${width} ${height}"><line x1="${padX}" y1="${y(0)}" x2="${width-padX}" y2="${y(0)}" class="payoff-zero"/><polygon points="${padX},${y(0)} ${line.split(" ").filter((_,i)=>points[i]?.profit<0).join(" ")} ${x(breakeven)},${y(0)}" class="payoff-loss-area"/><polyline points="${line}" class="payoff-line"/>${marker(breakeven,"سربه‌سر","payoff-breakeven")}${marker(base,"قیمت فعلی","payoff-current")}${marker(strike,"اعمال","payoff-strike")}<text x="${width-padX}" y="${y(metric.maxProfit)-8}" text-anchor="end" class="payoff-max">حداکثر سود ${num(metric.maxProfit)}</text></svg></div>`;
}

function coveredDecisionRange(metric) {
  const values=[metric.breakeven,metric.base,metric.strike].filter(Number.isFinite),min=Math.min(...values)*.97,max=Math.max(...values)*1.03;
  const pos=value=>Math.max(2,Math.min(98,(value-min)/Math.max(1,max-min)*100));
  return `<div class="covered-decision-range" aria-label="محدوده تصمیم"><header><span>محدوده تصمیم</span><small>جایگاه قیمت‌های کلیدی</small></header><div class="decision-track"><i></i><b class="decision-point breakeven" style="--position:${pos(metric.breakeven)}%"><span>سربه‌سر</span><em dir="ltr">${num(metric.breakeven)}</em></b><b class="decision-point current" style="--position:${pos(metric.base)}%"><span>فعلی</span><em dir="ltr">${num(metric.base)}</em></b><b class="decision-point strike" style="--position:${pos(metric.strike)}%"><span>اعمال</span><em dir="ltr">${num(metric.strike)}</em></b></div></div>`;
}

function longCallMetric(item) {
  const n=value=>value==null||value===""?null:(Number.isFinite(Number(value))?Number(value):null);
  const base=n(item.base_price),premium=n(item.calculation_price),strike=n(item.strike);
  if (![base,premium,strike].every(Number.isFinite) || base<=0 || premium<0 || strike<=0) return null;
  const breakeven=n(item.breakeven)??strike+premium;
  const rawContractSize=n(item.contract_size),contractSize=rawContractSize>0?rawContractSize:null,multiplier=contractSize||1;
  const days=Math.max(0,n(item.days)||0),growthToBreakeven=(breakeven-base)/base*100,growthToStrike=(strike-base)/base*100;
  const bid=n(item.option_best_bid??item.option_bid),ask=n(item.option_best_ask??item.option_ask),last=n(item.option_last);
  const fairCandidates=[item.theoretical_price,item.fair_value,item.model_price];
  const fair=n(fairCandidates.find((value)=>value!=null&&Number.isFinite(Number(value))));
  const spread=Number.isFinite(ask)&&Number.isFinite(bid)&&ask>0?(ask-bid)/ask*100:null;
  const fairGap=Number.isFinite(fair)&&fair>0?(premium-fair)/fair*100:null;
  return {base,premium,strike,breakeven,contractSize,multiplier,days,growthToBreakeven,growthToStrike,bid,ask,last,fair,spread,fairGap,totalPremium:premium*multiplier,theta:n(item.theta),delta:n(item.option_delta??item.delta),gamma:n(item.gamma),vega:n(item.vega),rho:n(item.rho),iv:n(item.implied_volatility)};
}

function longCallPayoffChart(metric) {
  if (!metric) return '<div class="covered-analysis-empty">داده کافی برای رسم نمودار سود و زیان وجود ندارد.</div>';
  const {base,premium,strike,breakeven,multiplier}=metric,width=760,height=270,padX=58,padY=30;
  const minPrice=Math.max(0,Math.min(base,strike)*.7),maxPrice=Math.max(base,breakeven,strike)*1.35;
  const points=Array.from({length:81},(_,i)=>{const price=minPrice+(maxPrice-minPrice)*i/80;return {price,profit:(Math.max(price-strike,0)-premium)*multiplier};});
  const profits=points.map(x=>x.profit).concat([0]);let minProfit=Math.min(...profits),maxProfit=Math.max(...profits);const margin=Math.max(1,(maxProfit-minProfit)*.12);minProfit-=margin;maxProfit+=margin;
  const x=v=>padX+(v-minPrice)/Math.max(1,maxPrice-minPrice)*(width-padX*2),y=v=>padY+(maxProfit-v)/Math.max(1,maxProfit-minProfit)*(height-padY*2);
  const line=points.map(p=>`${x(p.price).toFixed(1)},${y(p.profit).toFixed(1)}`).join(" ");
  const marker=(value,label,tone)=>`<line x1="${x(value)}" y1="${padY}" x2="${x(value)}" y2="${height-padY}" class="${tone}"/><text x="${x(value)}" y="${height-8}" text-anchor="middle" class="${tone}">${label} · ${num(value)}</text>`;
  return `<div class="covered-payoff long-call-payoff" role="img" aria-label="نمودار سود و زیان خرید اختیار خرید در سررسید؛ حداکثر زیان ${num(metric.totalPremium)} و سربه‌سر ${num(breakeven)}"><svg viewBox="0 0 ${width} ${height}"><line x1="${padX}" y1="${y(0)}" x2="${width-padX}" y2="${y(0)}" class="payoff-zero"/><polygon points="${padX},${y(0)} ${line.split(" ").filter((_,i)=>points[i]?.profit<0).join(" ")} ${x(breakeven)},${y(0)}" class="payoff-loss-area"/><polyline points="${line}" class="payoff-line"/>${marker(base,"قیمت فعلی","payoff-current")}${marker(strike,"اعمال","payoff-strike")}${marker(breakeven,"سربه‌سر","payoff-breakeven")}<text x="${padX+4}" y="${y(-metric.totalPremium)-8}" class="payoff-loss-label">حداکثر زیان ${num(metric.totalPremium)}</text><text x="${width-padX}" y="${y(points.at(-1).profit)-8}" text-anchor="end" class="payoff-max">سود با رشد سهم ادامه دارد ←</text></svg></div>`;
}

function longCallBreakEvenPath(metric,target=metric?.base) {
  if (!metric) return "";
  const values=[metric.base,metric.strike,metric.breakeven,target].filter(Number.isFinite),min=Math.max(0,Math.min(...values)*.96),max=Math.max(...values)*1.04;
  const pos=value=>Math.max(2,Math.min(98,(value-min)/Math.max(1,max-min)*100));
  return `<section class="long-call-path"><header><div><h4>مسیر سهم تا سوددهی</h4><small>فاصله قیمت فعلی تا اعمال و سربه‌سر در روز سررسید</small></div><strong>${metric.growthToBreakeven>0?`نیاز به ${num(metric.growthToBreakeven,2)}٪ رشد`:`${num(Math.abs(metric.growthToBreakeven),2)}٪ بالاتر از سربه‌سر`}</strong></header><div class="long-call-path-track" data-path-min="${min}" data-path-max="${max}"><i></i><b class="path-point current" style="--position:${pos(metric.base)}%"><span>فعلی</span><em dir="ltr">${num(metric.base)}</em></b><b class="path-point strike" style="--position:${pos(metric.strike)}%"><span>اعمال</span><em dir="ltr">${num(metric.strike)}</em></b><b class="path-point breakeven" style="--position:${pos(metric.breakeven)}%"><span>سربه‌سر</span><em dir="ltr">${num(metric.breakeven)}</em></b><b class="path-point target" data-long-path-target style="--position:${pos(target)}%"><span>سناریو</span><em dir="ltr">${num(target)}</em></b></div></section>`;
}

function updateLongCallScenario(input) {
  const workspace=input.closest(".long-call-analysis"),metric=workspace?._longCallMetric;
  if (!workspace||!metric) return;
  const target=Math.max(0,Number(input.value)||0),intrinsic=Math.max(target-metric.strike,0)*metric.multiplier,profit=intrinsic-metric.totalPremium,percent=metric.totalPremium>0?profit/metric.totalPremium*100:null;
  workspace.querySelector('[data-long-result="value"]').textContent=num(intrinsic,0);
  const profitNode=workspace.querySelector('[data-long-result="profit"]');profitNode.textContent=signed(profit,0);profitNode.className=profitTone(profit);
  workspace.querySelector('[data-long-result="return"]').textContent=percent==null?"—":`${signed(percent)}٪`;
  workspace.querySelector('[data-long-result="intrinsic"]').textContent=num(intrinsic,0);
  workspace.querySelector('[data-long-result="time"]').textContent="۰";
  workspace.querySelector('[data-long-result="state"]').textContent=target>=metric.breakeven?"بالاتر از سربه‌سر":target>=metric.strike?"اعمال‌پذیر، اما هنوز زیر سربه‌سر":"پایین‌تر از قیمت اعمال";
  const path=workspace.querySelector("[data-long-path-target]"),track=path?.closest("[data-path-min]");
  if(path&&track){const min=Number(track.dataset.pathMin),max=Number(track.dataset.pathMax),pos=Math.max(2,Math.min(98,(target-min)/Math.max(1,max-min)*100));path.style.setProperty("--position",`${pos}%`);path.querySelector("em").textContent=num(target);}
}

function setLongCallScenario(button,multiplier) {
  const workspace=button.closest(".long-call-analysis"),input=workspace?.querySelector("[data-long-scenario-price]");
  if(!workspace||!input) return;input.value=String(Math.round(workspace._longCallMetric.base*Number(multiplier)));updateLongCallScenario(input);input.focus();
}

function longCallAnalysisWorkspace(item,history,basisLabel) {
  const metric=longCallMetric(item);
  if (!metric) return '<div class="covered-analysis-empty">قیمت معتبر دارایی پایه، اختیار و اعمال برای تحلیل خرید اختیار موجود نیست.</div>';
  const fmt=(v,d=2,s="")=>analysisValue(v,d,s),info=(label,text)=>analysisTooltip(label,text),expiry=`${solarDate(item.expiry_display||item.expiry)} — ${num(metric.days)} روز مانده`;
  const moneyness=metric.base>metric.strike?"ITM — قیمت سهم بالاتر از قیمت اعمال است":metric.base<metric.strike?"OTM — قیمت سهم پایین‌تر از قیمت اعمال است":"ATM — قیمت سهم و اعمال تقریباً برابرند";
  const liquidity=!Number.isFinite(metric.ask)||!Number.isFinite(metric.bid)?"داده ناکافی":metric.spread>15?"نقدشوندگی پایین":metric.spread>7?"نقدشوندگی متوسط":"نقدشوندگی مناسب";
  const status=metric.days<=7?"زمان کم تا سررسید":liquidity==="نقدشوندگی پایین"?liquidity:Number.isFinite(metric.fairGap)?(metric.fairGap>5?"پریمیوم گران":Math.abs(metric.fairGap)<=3?"قیمت منصفانه":"مناسب بررسی"):"داده ناکافی";
  const statusTone=status==="نقدشوندگی پایین"||status==="زمان کم تا سررسید"||status==="پریمیوم گران"?"warning":status==="قیمت منصفانه"?"positive":"";
  const thetaTotal=Number.isFinite(metric.theta)?metric.theta*metric.multiplier:null,thetaPercent=Number.isFinite(metric.theta)&&metric.premium!==0?metric.theta/metric.premium*100:null;
  const optionalLiquidity=[["حجم معاملات",item.option_volume??item.volume],["ارزش معاملات",item.transaction_value],["موقعیت‌های باز",item.open_interest]].filter(([,v])=>v!=null&&Number.isFinite(Number(v)));
  const detailsOpen=localStorage.getItem("nicoption-long-analysis-details")==="open";
  const workspace=`<div class="covered-analysis-workspace long-call-analysis">
    <section class="covered-analysis-head"><div><small>تحلیل خرید اختیار خرید</small><h3><span class="symbol">${esc(item.asset)}</span> / <span class="symbol">${esc(item.symbol)}</span> — اختیار خرید</h3><p>${marketLabel(item.market)} · ${item.updated_at?`به‌روزرسانی ${esc(item.updated_at)}`:"بر پایه آخرین داده دریافت‌شده"}</p></div><span class="analysis-status ${statusTone}">${status}</span></section>
    <section class="covered-kpi-grid long-call-kpis">
      <article><span>سرمایه در معرض ریسک</span><strong dir="ltr">${fmt(metric.totalPremium,0)}</strong><small><b class="negative-mark">حداکثر زیان</b> در صورت انقضای بی‌ارزش · ${metric.contractSize?`ضریب ${fmt(metric.contractSize,0)}`:"به‌ازای هر واحد؛ اندازه قرارداد موجود نیست"}</small></article>
      <article><span>نقطه سربه‌سر ${info("نقطه سربه‌سر","قیمت اعمال به‌علاوه پریمیوم پرداختی هر سهم؛ کارمزد فقط در صورت وجود داده معتبر اضافه می‌شود.")}</span><strong dir="ltr">${fmt(metric.breakeven,0)}</strong><small>رشد لازم سهم <b dir="ltr">${fmt(metric.growthToBreakeven,2,"٪")}</b></small></article>
      <article><span>زمان و فرسایش ${info("Theta","کاهش تقریبی روزانه ارزش زمانی طبق داده مدل؛ در صورت نبود داده عددی ساخته نمی‌شود.")}</span><strong dir="ltr">${fmt(metric.days,0," روز")}</strong><small>Theta روزانه <b class="model-value" dir="ltr">${fmt(thetaTotal,2)}</b> · ${fmt(thetaPercent,2,"٪")}</small></article>
      <article><span>وضعیت ارزش‌گذاری</span><strong class="model-value" dir="ltr">${Number.isFinite(metric.fairGap)?fmt(metric.fairGap,2,"٪"):"—"}</strong><small>${Number.isFinite(metric.fairGap)?(metric.fairGap>0?"بالاتر از قیمت محاسباتی":"پایین‌تر از قیمت محاسباتی"):"قیمت مدل معتبر در داده موجود نیست"} · IV ${fmt(metric.iv,2,"٪")}</small></article>
    </section>
    ${longCallBreakEvenPath(metric)}
    <section class="covered-decision-grid long-call-main-grid">
      <article class="covered-spec-panel"><header><h4>مشخصات قرارداد</h4><small>اطلاعات یکتای قرارداد و بازار</small></header><dl><div><dt>قیمت فعلی سهم</dt><dd dir="ltr">${fmt(metric.base,0)}</dd></div><div><dt>قیمت اعمال</dt><dd dir="ltr">${fmt(metric.strike,0)}</dd></div><div class="wide"><dt>وضعیت قرارداد</dt><dd>${moneyness}</dd></div><div class="wide"><dt>سررسید</dt><dd dir="ltr">${expiry}</dd></div><div><dt>بهترین فروش اختیار</dt><dd dir="ltr">${fmt(metric.ask,0)}</dd></div><div><dt>بهترین خرید اختیار</dt><dd dir="ltr">${fmt(metric.bid,0)}</dd></div><div><dt>آخرین معامله</dt><dd dir="ltr">${fmt(metric.last,0)}</dd></div><div><dt>قیمت مبنای محاسبه</dt><dd dir="ltr">${fmt(metric.premium,0)}<small>${esc(basisLabel)}</small></dd></div><div><dt>اندازه قرارداد</dt><dd dir="ltr">${fmt(metric.contractSize,0)}</dd></div><div><dt>احتمال ITM ${info("احتمال ITM","احتمال پایان قرارداد بالاتر از قیمت اعمال است و با احتمال سوددهی یکسان نیست.")}</dt><dd class="model-value">—<small>در API فعلی موجود نیست</small></dd></div></dl></article>
      <article class="covered-payoff-panel"><header><div><h4>نمودار سود و زیان در سررسید</h4><small>زیان محدود به پریمیوم؛ سود با رشد دارایی پایه محدود نمی‌شود${metric.contractSize?"":" · مقادیر به‌ازای هر واحد"}</small></div></header>${longCallPayoffChart(metric)}<section class="long-call-scenario"><header><div><h4>بررسی سناریوی معامله</h4><small>فقط سناریوی روز سررسید؛ پیش‌بینی قیمت نیست</small></div></header><div class="long-scenario-controls"><label><span>قیمت فرضی سهم</span><input data-long-scenario-price type="number" min="0" step="1" value="${metric.base}"></label><div class="long-scenario-quick"><button type="button" data-long-scenario-factor=".9">۱۰٪ کاهش</button><button type="button" data-long-scenario-factor="1">بدون تغییر</button><button type="button" data-long-scenario-factor="1.1">۱۰٪ افزایش</button></div></div><div class="long-scenario-results" aria-live="polite"><div><span>ارزش اختیار در سررسید</span><b data-long-result="value">${fmt(Math.max(metric.base-metric.strike,0)*metric.multiplier,0)}</b></div><div><span>سود یا زیان</span><b data-long-result="profit">—</b></div><div><span>بازده روی پریمیوم</span><b data-long-result="return">—</b></div><div><span>ارزش ذاتی</span><b data-long-result="intrinsic">—</b></div><div><span>ارزش زمانی باقی‌مانده</span><b data-long-result="time">۰</b></div><div><span>وضعیت نسبت به سربه‌سر</span><b data-long-result="state">—</b></div></div></section></article>
    </section>
    <section class="covered-analysis-panels">
      <article><header><h4>قیمت و نقدشوندگی</h4><small>قیمت‌های واقعی قابل مشاهده بازار</small></header><dl><div><dt>بهترین خرید</dt><dd dir="ltr">${fmt(metric.bid,0)}</dd></div><div><dt>بهترین فروش</dt><dd dir="ltr">${fmt(metric.ask,0)}</dd></div>${metric.spread==null?"":`<div><dt>فاصله Bid/Ask</dt><dd dir="ltr">${fmt(metric.spread,2,"٪")}</dd></div>`}<div><dt>آخرین قیمت</dt><dd dir="ltr">${fmt(metric.last,0)}</dd></div><div><dt>قیمت محاسباتی ${info("قیمت محاسباتی","خروجی مدل ارزش‌گذاری مستقل از مظنه بازار؛ در صورت نبود داده با خط تیره نمایش داده می‌شود.")}</dt><dd class="model-value" dir="ltr">${fmt(metric.fair,0)}</dd></div>${optionalLiquidity.map(([l,v])=>`<div><dt>${l}</dt><dd dir="ltr">${fmt(v,0)}</dd></div>`).join("")}<div><dt>وضعیت</dt><dd><span class="liquidity-state ${liquidity==="نقدشوندگی پایین"?"warning":liquidity==="نقدشوندگی مناسب"?"positive":""}">${liquidity}</span></dd></div></dl></article>
      <article><header><h4>Greeks و حساسیت</h4><small>مقادیر مدل‌شده؛ نه نتیجه قطعی</small></header><dl><div><dt>Delta ${info("Delta","تغییر تقریبی قیمت اختیار با یک واحد تغییر قیمت سهم؛ منبع، مدل تحلیلی قرارداد است.")}</dt><dd class="model-value" dir="ltr">${fmt(metric.delta,4)}</dd></div><div><dt>Theta ${info("Theta","کاهش تقریبی روزانه ارزش زمانی، با ثابت‌بودن سایر متغیرها.")}</dt><dd class="model-value" dir="ltr">${fmt(metric.theta,4)}</dd></div><div><dt>Vega ${info("Vega","حساسیت تقریبی قیمت اختیار به تغییر نوسان ضمنی.")}</dt><dd class="model-value" dir="ltr">${fmt(metric.vega,4)}</dd></div><div><dt>نوسان ضمنی ${info("نوسان ضمنی","نوسان استخراج‌شده از قیمت اختیار؛ پیش‌بینی قطعی نوسان آینده نیست.")}</dt><dd class="model-value" dir="ltr">${fmt(metric.iv,2,"٪")}</dd></div></dl></article>
      <article><header><h4>ریسک و احتمال</h4><small>فاصله‌های قیمتی و سرمایه در معرض ریسک</small></header><dl><div><dt>احتمال ITM</dt><dd class="model-value">—</dd></div><div><dt>احتمال رسیدن به سربه‌سر</dt><dd class="model-value">—</dd></div><div><dt>رشد لازم تا اعمال</dt><dd dir="ltr">${fmt(metric.growthToStrike,2,"٪")}</dd></div><div><dt>رشد لازم تا سربه‌سر</dt><dd dir="ltr">${fmt(metric.growthToBreakeven,2,"٪")}</dd></div><div><dt>حداکثر زیان</dt><dd dir="ltr">${fmt(metric.totalPremium,0)}</dd></div><div><dt>سهم پریمیوم از قیمت پایه</dt><dd dir="ltr">${fmt(metric.premium/metric.base*100,2,"٪")}</dd></div></dl></article>
    </section>
    <details class="covered-advanced" aria-expanded="${detailsOpen?"true":"false"}" ${detailsOpen?"open":""}><summary><span><b>نمایش جزئیات محاسبات</b><small>Greeks تکمیلی، ورودی‌های مدل و محدودیت داده</small></span><i aria-hidden="true">⌄</i></summary><div><dl><div><dt>Gamma</dt><dd class="model-value" dir="ltr">${fmt(metric.gamma,4)}</dd></div><div><dt>Vega</dt><dd class="model-value" dir="ltr">${fmt(metric.vega,4)}</dd></div><div><dt>Rho</dt><dd class="model-value" dir="ltr">${fmt(metric.rho,4)}</dd></div><div><dt>ارزش ذاتی فعلی</dt><dd dir="ltr">${fmt(Math.max(metric.base-metric.strike,0),0)}</dd></div><div><dt>ارزش زمانی فعلی</dt><dd dir="ltr">${fmt(Math.max(metric.premium-Math.max(metric.base-metric.strike,0),0),0)}</dd></div><div><dt>نرخ بدون ریسک</dt><dd class="model-value" dir="ltr">${fmt(state.data?.rules?.risk_free_rate??state.data?.rules?.long_interest_rate,2,"٪")}</dd></div><div><dt>مدل قیمت‌گذاری</dt><dd class="model-value">${Number.isFinite(metric.fair)?"مدل ثبت‌شده در منبع":"داده موجود نیست"}</dd></div><div><dt>زمان محاسبه</dt><dd>${esc(item.updated_at||"آخرین دریافت داده")}</dd></div></dl><p>احتمال ITM با احتمال سوددهی یکسان نیست. مدل‌سازی قیمت در تاریخ‌های قبل از سررسید در داده فعلی وجود ندارد؛ بنابراین سناریوساز فقط سود و زیان سررسید را نمایش می‌دهد و مقدار ساختگی تولید نمی‌کند.</p></div></details>
    ${history.points?.length?`<details class="covered-history"><summary>نمایش تاریخچه قیمت دارایی پایه</summary>${historyChart(history.points,metric.strike,metric.breakeven)}<p class="chart-note">${num(history.points.length)} روز معاملاتی · منبع: ${esc(history.source||"—")}</p></details>`:""}
  </div>`;
  return workspace;
}

function coveredAnalysisWorkspace(item,history,basisLabel,executableQuote) {
  const metric=coveredMarketMetrics(item);
  if (!metric) return '<div class="covered-analysis-empty">قیمت معتبر دارایی پایه و اختیار برای تحلیل کاوردکال موجود نیست.</div>';
  const fmt=(v,d=2,s="")=>analysisValue(v,d,s), tone=v=>Number(v)<0?"negative":Number(v)>0?"positive":"";
  const expiry=`${solarDate(item.expiry_display||item.expiry)} — ${num(metric.days)} روز مانده`;
  const fair=Number(item.calculation_price),bid=Number(executableQuote),last=Number(item.option_last),ask=Number(item.option_best_ask??item.option_ask);
  const fairGap=Number.isFinite(bid)&&Number.isFinite(fair)&&fair!==0?(bid-fair)/fair*100:null;
  const spread=Number.isFinite(ask)&&Number.isFinite(bid)&&ask>0?(ask-bid)/ask*100:null;
  const invested=metric.base-metric.netPremium, maxReturn=invested>0?metric.maxProfit/invested*100:null;
  const annualizedReturn=Number.isFinite(Number(item.annual_return))?Number(item.annual_return):metric.premiumReturnYoy;
  const expiryReturn=Number.isFinite(Number(item.expiry_return))?Number(item.expiry_return):maxReturn;
  const score=Number(item.covered_score), status=Number.isFinite(score)?(score>=70?"مناسب ورود":score>=45?"نیازمند بررسی":"نامناسب"):"نیازمند بررسی";
  const statusTone=status==="مناسب ورود"?"positive":status==="نامناسب"?"negative":"warning";
  const optionalRows=[["حجم معاملات",item.option_volume],["تعداد معاملات",item.option_trade_count??item.transaction_count],["موقعیت‌های باز",item.open_interest]].filter(([,v])=>v!=null&&Number.isFinite(Number(v)));
  const liquidityValue=Number(item.transaction_value),liquidityLabel=!Number.isFinite(liquidityValue)?"نامشخص":liquidityValue<=0?"ضعیف":item.liquidity_assumed?"متوسط":"مناسب";
  const detailsOpen=localStorage.getItem("nicoption-covered-analysis-details")==="open";
  const info=(label,text)=>analysisTooltip(label,text);
  return `<div class="covered-analysis-workspace">
    <section class="covered-analysis-head"><div><small>تحلیل کاوردکال</small><h3><span class="symbol">${esc(item.asset)}</span> / <span class="symbol">${esc(item.symbol)}</span></h3><p>${marketLabel(item.market)} · ${item.updated_at?`به‌روزرسانی ${esc(item.updated_at)}`:"بر پایه آخرین داده دریافت‌شده"}</p></div><span class="analysis-status ${statusTone}">${status}</span></section>
    <section class="covered-kpi-grid">
      <article><span>بازده سالانه‌شده ${info("بازده سالانه‌شده","تعمیم ریاضی بازده دوره بر مبنای روزهای باقی‌مانده است و تکرار آن در طول سال تضمین نمی‌شود.")}</span><strong class="${tone(annualizedReturn)}" dir="ltr">${fmt(annualizedReturn,2,"٪")}</strong><small>بر اساس روزهای باقی‌مانده</small></article>
      <article><span>حداکثر بازده تا سررسید</span><strong class="${tone(expiryReturn)}" dir="ltr">${fmt(expiryReturn,2,"٪")}</strong><small>حداکثر سود هر واحد: <b dir="ltr">${fmt(metric.maxProfit,0)}</b></small></article>
      <article><span>پوشش نزول ${info("پوشش نزول","پریمیوم خالص تقسیم بر قیمت سهم؛ نشان می‌دهد پریمیوم چه درصدی از افت اولیه سهم را پوشش می‌دهد.")}</span><strong dir="ltr">${fmt(metric.downsideProtection,2,"٪")}</strong><small>سربه‌سر <b dir="ltr">${fmt(metric.breakeven,0)}</b></small></article>
      <article><span>پریمیوم قابل دریافت</span><strong dir="ltr">${fmt(metric.netPremium,0)}</strong><small>بازده پریمیوم <b dir="ltr">${fmt(metric.premiumReturn,2,"٪")}</b></small></article>
    </section>
    <section class="covered-decision-grid">
      <article class="covered-spec-panel"><header><h4>مشخصات معامله</h4><small>داده‌های بازار و قرارداد</small></header><dl><div><dt>قیمت سهم</dt><dd dir="ltr">${fmt(metric.base,0)}</dd></div><div><dt>قیمت اعمال</dt><dd dir="ltr">${fmt(metric.strike,0)}</dd></div><div class="wide"><dt>سررسید</dt><dd dir="ltr">${esc(expiry)}</dd></div><div><dt>بهترین خرید اختیار</dt><dd dir="ltr">${fmt(bid,0)}</dd></div><div><dt>قیمت محاسباتی ${info("قیمت محاسباتی","قیمت انتخاب‌شده در کنترل مبنای محاسبه؛ منبع آن در زیر مقدار مشخص شده است.")}</dt><dd class="model-value" dir="ltr">${fmt(fair,0)}<small>${esc(basisLabel)}</small></dd></div><div><dt>آخرین معامله</dt><dd dir="ltr">${fmt(last,0)}</dd></div><div><dt>فاصله سهم تا اعمال</dt><dd>${strikeDistanceText(metric.strikeDistance)}</dd></div><div><dt>احتمال اعمال ${info("احتمال اعمال","احتمال ریسک‌خنثی با مدل Black–Scholes N(d2)؛ پیش‌بینی قطعی بازار نیست.")}</dt><dd class="model-value" dir="ltr">${fmt(metric.assignmentProbability,2,"٪")}</dd></div></dl></article>
      <article class="covered-payoff-panel"><header><div><h4>نمودار سود و زیان در سررسید</h4><small>محور افقی قیمت دارایی پایه؛ محور عمودی سود/زیان هر واحد</small></div></header>${coveredDecisionRange(metric)}${coveredPayoffChart(item,metric)}</article>
    </section>
    <section class="covered-analysis-panels">
      <article><header><h4>قیمت‌گذاری اختیار</h4><small>مقایسه قیمت‌های قابل مشاهده بازار</small></header><dl><div><dt>قیمت محاسباتی</dt><dd class="model-value" dir="ltr">${fmt(fair,0)}</dd></div><div><dt>بهترین خرید</dt><dd dir="ltr">${fmt(bid,0)}</dd></div><div><dt>آخرین معامله</dt><dd dir="ltr">${fmt(last,0)}</dd></div><div><dt>اختلاف خرید با ارزش مبنا</dt><dd dir="ltr">${fmt(fairGap,2,"٪")}</dd></div>${spread==null?"":`<div><dt>فاصله Bid/Ask</dt><dd dir="ltr">${fmt(spread,2,"٪")}</dd></div>`}</dl></article>
      <article><header><h4>احتمال و ریسک</h4><small>ریسک‌های اصلی موقعیت</small></header><dl><div><dt>احتمال اعمال</dt><dd class="model-value" dir="ltr">${fmt(metric.assignmentProbability,2,"٪")}</dd></div><div><dt>فاصله سهم تا اعمال</dt><dd>${strikeDistanceText(metric.strikeDistance)}</dd></div><div><dt>حداکثر زیان نظری ${info("حداکثر زیان نظری","در صورت سقوط ارزش سهم به صفر، زیان نظری برابر هزینه خالص خرید سهم پس از کسر پریمیوم است.")}</dt><dd class="negative" dir="ltr">${fmt(-invested,0)}</dd></div><div><dt>سرمایه درگیر هر واحد</dt><dd dir="ltr">${fmt(invested,0)}</dd></div><div><dt>سود بالقوه / سرمایه</dt><dd dir="ltr">${fmt(maxReturn,2,"٪")}</dd></div></dl></article>
      <article><header><h4>نقدشوندگی</h4><small>فقط داده‌های موجود در منبع</small></header><dl><div><dt>ارزش معاملات اختیار</dt><dd dir="ltr">${fmt(item.transaction_value,0)}</dd></div>${optionalRows.map(([l,v])=>`<div><dt>${l}</dt><dd dir="ltr">${fmt(v,0)}</dd></div>`).join("")}<div><dt>وضعیت نقدشوندگی</dt><dd><span class="liquidity-state ${liquidityLabel==="ضعیف"?"negative":liquidityLabel==="مناسب"?"positive":"warning"}">${liquidityLabel}</span></dd></div></dl></article>
    </section>
    <details class="covered-advanced" aria-expanded="${detailsOpen?"true":"false"}" ${detailsOpen?"open":""}><summary><span><b>نمایش جزئیات محاسبات</b><small>یونانی‌ها، فرضیات و محدودیت‌های مدل</small></span><i aria-hidden="true">⌄</i></summary><div><dl><div><dt>احتمال ITM</dt><dd dir="ltr">${fmt(item.itm_percent,2,"٪")}</dd></div><div><dt>دلتا اختیار</dt><dd class="model-value" dir="ltr">${deltaDisplay(item)}</dd></div><div><dt>دلتا استراتژی</dt><dd class="model-value" dir="ltr">${deltaDisplay(item,"strategy_delta")}</dd></div><div><dt>تتا</dt><dd class="model-value" dir="ltr">${fmt(item.theta,4)}</dd></div><div><dt>گاما</dt><dd class="model-value" dir="ltr">${fmt(item.gamma,4)}</dd></div><div><dt>وگا</dt><dd class="model-value" dir="ltr">${fmt(item.vega,4)}</dd></div><div><dt>نوسان ضمنی</dt><dd class="model-value" dir="ltr">${fmt(metric.volatility,2,"٪")}</dd></div><div><dt>نرخ بدون ریسک</dt><dd class="model-value" dir="ltr">${fmt(state.data?.rules?.risk_free_rate??state.data?.rules?.long_interest_rate,2,"٪")}</dd></div></dl><p><b>روش احتمال اعمال:</b> ${esc(metric.model)}، با فرض سود نقدی صفر. مقادیر بنفش خروجی یا ورودی مدل هستند. مدل اروپایی است و اثر اعمال زودهنگام، هزینه‌های معاملاتی آتی و جهش قیمت را به‌طور کامل پوشش نمی‌دهد.${metric.estimated?" نوسان ۳۵٪ به‌صورت برآوردی استفاده شده است.":""}</p></div></details>
    ${history.points?.length?`<details class="covered-history"><summary>نمایش تاریخچه قیمت دارایی پایه</summary>${historyChart(history.points,metric.strike,metric.breakeven)}<p class="chart-note">${num(history.points.length)} روز معاملاتی · منبع: ${esc(history.source||"—")}</p></details>`:""}
  </div>`;
}

let analysisTrigger = null;
let analysisRetryItem = null;

function retryAnalysis() {
  if (analysisRetryItem) openAnalysis(analysisRetryItem);
}

async function openAnalysis(item) {
  const modal = $("analysisModal");
  const content = $("analysisContent");
  analysisTrigger = document.activeElement;
  analysisRetryItem = item;
  $("analysisTitle").textContent = `${item.asset} · ${item.symbol}`;
  $("analysisEyebrow").textContent = item.strategy === "covered_call" ? "تحلیل کاوردکال" : "تحلیل خرید اختیار خرید";
  content.innerHTML = `<div class="covered-analysis-skeleton" aria-label="در حال بارگذاری ${item.strategy === "covered_call"?"تحلیل کاوردکال":"تحلیل خرید اختیار خرید"}"><i></i><div><b></b><b></b><b></b><b></b></div><section><b></b><b></b></section><div><b></b><b></b><b></b></div></div>`;
  modalManager.open(modal, {trigger:analysisTrigger, initialFocus:$("analysisClose"), close:closeAnalysis});
  try {
    const params = new URLSearchParams({asset: item.asset, source_asset: item.source_asset || item.asset});
    const response = await apiFetch(`/api/history?${params}`, {cache: "no-store"});
    const history = await response.json();
    if (!response.ok) throw new Error(history.detail || history.error);
    const metric = item.strategy === "covered_call" ? `ماهانه ${num(item.monthly_return, 2)}٪ | سالانه ${num(item.annual_return, 2)}٪` : `${num(item.advantage_percent, 2)}٪ کمتر از قیمت پایه با لحاظ نرخ بهره`;
    const buybackMetric = item.strategy === "covered_call" ? `<div><span>درصد بازخرید</span><strong>${num(buybackPercent(item), 2)}٪</strong></div><div><span>بازخرید ماهانه | سالانه</span><strong>${num(buybackMonthlyPercent(item), 2)}٪ | ${num(buybackAnnualPercent(item), 2)}٪</strong></div>` : "";
    const basisLabel = item.price_basis === "last" ? "آخرین معامله" : item.price_basis === "ask" ? "بهترین پیشنهاد فروش" : "بهترین پیشنهاد خرید";
    const deltaMetrics = item.strategy === "covered_call" ? `<div><span>دلتا اختیار خرید</span><strong>${deltaDisplay(item)}</strong></div><div><span>دلتا استراتژی کاوردکال</span><strong>${deltaDisplay(item, "strategy_delta")}</strong></div><div><span>امتیاز جامع کاوردکال</span><strong>${scoreValue(item)}/۱۰۰ · ${esc(item.covered_score_label)}</strong></div><div><span>حاشیه امن پرمیوم</span><strong>${num(item.downside_protection_percent, 2)}٪</strong></div>` : `<div><span>دلتا اختیار خرید</span><strong>${deltaDisplay(item)}</strong></div>`;
    const scoreDetails = item.strategy === "covered_call" && Object.keys(item.covered_score_components || {}).length
      ? `<div class="analysis-score-components"><span>اجزای امتیاز جامع</span><strong>${Object.entries(item.covered_score_components).map(([key, value]) => `${scoreComponentLabels[key] || key}: ${num(value, 1)}`).join(" · ")}</strong></div>` : "";
    const selectionDetails = (item.labels || []).length ? `<div><span>دلیل انتخاب</span><strong>${(item.labels || []).map(esc).join(" · ")}</strong></div>` : "";
    const strategyDetails = item.strategy === "covered_call"
      ? `${selectionDetails}${scoreDetails}`
      : `<div><span>بهترین فروش اختیار</span><strong>${num(item.option_best_ask)}</strong></div><div><span>هزینه بهره اعمال</span><strong>${num(item.exercise_interest_cost, 2)}</strong></div><div><span>اعمال تعدیل‌شده + پرمیوم</span><strong>${num(item.adjusted_exercise_plus_premium, 2)}</strong></div><div><span>اهرم (پایه ÷ پرمیوم)</span><strong>${num(leverageRatio(item), 2)}</strong></div><div><span>انتخاب کم‌هزینه‌تر</span><strong>${esc(item.recommendation)}</strong></div>`;
    const isCovered = item.strategy === "covered_call";
    const executableQuoteLabel = isCovered ? "بهترین خرید اختیار" : "بهترین فروش اختیار";
    const executableQuote = isCovered
      ? (item.option_bid ?? item.option_best_bid)
      : item.option_best_ask;
    const gapLabel = isCovered
      ? "شکاف آخرین معامله تا بهترین خرید"
      : "شکاف بهترین فروش تا آخرین معامله";
    content.innerHTML = isCovered
      ? coveredAnalysisWorkspace(item,history,basisLabel,executableQuote)
      : longCallAnalysisWorkspace(item,history,basisLabel);
    const longWorkspace=content.querySelector(".long-call-analysis");
    if(longWorkspace){longWorkspace._longCallMetric=longCallMetric(item);const input=longWorkspace.querySelector("[data-long-scenario-price]");if(input)updateLongCallScenario(input);}
    const advanced=content.querySelector(".covered-advanced");
    advanced?.addEventListener("toggle",()=>{advanced.setAttribute("aria-expanded",String(advanced.open));localStorage.setItem(isCovered?"nicoption-covered-analysis-details":"nicoption-long-analysis-details",advanced.open?"open":"closed");});
  } catch (error) {
    content.innerHTML = `<div class="covered-analysis-error" role="alert"><strong>دریافت تحلیل ناموفق بود</strong><p>${esc(error.message || "دریافت تاریخچه قیمت ناموفق بود")}</p><button type="button" data-analysis-retry>تلاش دوباره</button></div>`;
  }
}

const modalManager = (() => {
  const stack = [];
  const originalInert = new Map();
  const focusableSelector = [
    'a[href]:not([hidden])',
    'button:not([disabled]):not([hidden])',
    'input:not([disabled]):not([type="hidden"]):not([hidden])',
    'select:not([disabled]):not([hidden])',
    'textarea:not([disabled]):not([hidden])',
    '[contenteditable="true"]',
    '[tabindex]:not([tabindex="-1"]):not([hidden])',
  ].join(",");

  const visibleControls = (modal) => [...modal.querySelectorAll(focusableSelector)].filter((element) => {
    const style = getComputedStyle(element);
    return element.getClientRects().length > 0 && style.display !== "none" && style.visibility !== "hidden" && !element.closest('[aria-hidden="true"]');
  });

  const triggerSelector = (trigger) => {
    if (!(trigger instanceof HTMLElement)) return null;
    if (trigger.id) return `#${CSS.escape(trigger.id)}`;
    const marker = [...trigger.attributes].find(({name}) => name.startsWith("data-"));
    if (!marker) return null;
    return marker.value
      ? `[${marker.name}="${CSS.escape(marker.value)}"]`
      : `[${marker.name}]`;
  };

  function restoreManagedInert() {
    originalInert.forEach((value, element) => { element.inert = value; });
    originalInert.clear();
  }

  function isolate(activeModal) {
    restoreManagedInert();
    if (!activeModal) return;
    let branch = activeModal;
    while (branch && branch !== document.body) {
      const parent = branch.parentElement;
      if (!parent) break;
      [...parent.children].forEach((sibling) => {
        if (sibling === branch || sibling.contains(activeModal)) return;
        if (!originalInert.has(sibling)) originalInert.set(sibling, sibling.inert);
        sibling.inert = true;
      });
      branch = parent;
    }
  }

  function sync() {
    const active = stack.at(-1)?.modal || null;
    document.body.classList.toggle("modal-open", Boolean(active));
    stack.forEach(({modal}) => { modal.dataset.modalActive = String(modal === active); });
    isolate(active);
  }

  function open(modal, {trigger=document.activeElement, initialFocus=null, close=null}={}) {
    if (!(modal instanceof HTMLElement)) return;
    const existing = stack.findIndex((entry) => entry.modal === modal);
    if (existing >= 0) stack.splice(existing, 1);
    modal.classList.remove("hidden");
    stack.push({
      modal,
      trigger:trigger instanceof HTMLElement ? trigger : null,
      triggerSelector:triggerSelector(trigger),
      close,
    });
    sync();
    requestAnimationFrame(() => {
      if (stack.at(-1)?.modal !== modal) return;
      const target = typeof initialFocus === "string"
        ? modal.querySelector(initialFocus)
        : initialFocus instanceof HTMLElement ? initialFocus : visibleControls(modal)[0];
      (target || modal).focus({preventScroll:true});
    });
  }

  function close(modal, {restoreFocus=true}={}) {
    const index = stack.findIndex((entry) => entry.modal === modal);
    if (index < 0) {
      modal?.classList.add("hidden");
      return;
    }
    const [entry] = stack.splice(index, 1);
    modal.classList.add("hidden");
    delete modal.dataset.modalActive;
    sync();
    const resolveReturnTarget = () => entry.trigger?.isConnected
      ? entry.trigger
      : entry.triggerSelector ? document.querySelector(entry.triggerSelector) : null;
    if (restoreFocus && resolveReturnTarget() instanceof HTMLElement) {
      const restore = () => {
        const returnTarget = resolveReturnTarget();
        const activeModal = stack.at(-1)?.modal || null;
        if (returnTarget instanceof HTMLElement && returnTarget.isConnected && (!activeModal || activeModal.contains(returnTarget))) {
          returnTarget.focus({preventScroll:true});
        }
      };
      restore();
      // Moving an edited form back to its page slot can reset focus after the
      // synchronous close. Repeat once after layout settles.
      requestAnimationFrame(restore);
    }
  }

  function handleKeydown(event) {
    const entry = stack.at(-1);
    if (!entry) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
      entry.close?.();
      return;
    }
    if (event.key !== "Tab") return;
    const controls = visibleControls(entry.modal);
    if (!controls.length) {
      event.preventDefault();
      entry.modal.focus();
      return;
    }
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && (document.activeElement === first || !entry.modal.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !entry.modal.contains(document.activeElement))) {
      event.preventDefault();
      first.focus();
    }
  }

  document.addEventListener("keydown", handleKeydown, true);
  return {open, close, active:() => stack.at(-1)?.modal || null, size:() => stack.length};
})();

let assetTradesTrigger=null;
function assetTradeRecord(item){const underlying=item.strategy_type==="underlying"||!item.option_symbol,strategy=underlying?"دارایی پایه":item.strategy_type==="long_call"?"خرید اختیار خرید":"کاوردکال",status=item.status==="closed"?"بسته":"باز",date=underlying?(item.purchase_date_display||item.entry_date_display||item.purchase_date||item.entry_date):item.entry_date_display,quantity=underlying?(item.quantity??item.available_quantity):item.quantity,capital=item.invested_capital??item.total_cost??(Number(item.entry_price||0)*Number(quantity||0)),profit=underlying?item.profit:(item.status==="closed"?item.realized_profit:(item.strategy_type==="long_call"?item.long_offset_profit:item.covered_liquidation_profit));return `<article class="asset-trade-record"><header><div><span class="asset-trade-kind ${underlying?"underlying":item.strategy_type==="long_call"?"long":"covered"}">${strategy}</span><strong>${esc(item.option_symbol||item.asset||"—")}</strong></div><span class="trade-status ${status==="بسته"?"closed":"open"}">${status}</span></header><dl><div><dt>تاریخ خرید/ورود</dt><dd>${esc(date||"—")}</dd></div><div><dt>تعداد</dt><dd>${qty(quantity||0)}</dd></div><div><dt>سرمایه ثبت‌شده</dt><dd>${num(capital||0,0)}</dd></div><div><dt>سود/زیان</dt><dd class="${profitTone(profit)}">${profit==null?"—":signed(profit,0)}</dd></div></dl></article>`;}
function openAssetTrades(asset,trigger=null){const normalized=faNorm(asset),trades=state.trades.filter((i)=>faNorm(i.asset)===normalized),underlyings=state.underlyingPositions.filter((i)=>faNorm(i.asset)===normalized).map((i)=>({...i,strategy_type:"underlying"}));assetTradesTrigger=trigger||document.activeElement;$("assetTradesTitle").textContent=asset;$("assetTradesDescription").textContent=`${num(underlyings.length)} معامله دارایی پایه · ${num(trades.filter((i)=>i.strategy_type!=="long_call").length)} کاوردکال · ${num(trades.filter((i)=>i.strategy_type==="long_call").length)} خرید اختیار خرید`;const records=[...underlyings,...trades].sort((a,b)=>String(b.exit_date||b.entry_date||b.purchase_date||"").localeCompare(String(a.exit_date||a.entry_date||a.purchase_date||"")));$("assetTradesModalBody").innerHTML=records.length?records.map(assetTradeRecord).join(""):'<div class="trades-empty">معامله‌ای برای این نماد پیدا نشد.</div>';modalManager.open($("assetTradesModal"),{trigger:assetTradesTrigger,initialFocus:$("assetTradesDismiss"),close:closeAssetTrades});}
function closeAssetTrades(){if($("assetTradesModal").classList.contains("hidden"))return;modalManager.close($("assetTradesModal"));assetTradesTrigger=null;}

let confirmationResolve = null;
let confirmationTrigger = null;

function requestConfirmation({title, description, actionLabel = "حذف"}) {
  if (confirmationResolve) closeConfirmation(false);
  confirmationTrigger = document.activeElement;
  $("confirmationTitle").textContent = title;
  $("confirmationDescription").textContent = description;
  $("confirmationAccept").textContent = actionLabel;
  modalManager.open($("confirmationModal"), {trigger:confirmationTrigger, initialFocus:$("confirmationCancel"), close:() => closeConfirmation(false)});
  return new Promise((resolve) => { confirmationResolve = resolve; });
}

function closeConfirmation(accepted = false) {
  if ($("confirmationModal").classList.contains("hidden")) return;
  const resolve = confirmationResolve;
  confirmationResolve = null;
  modalManager.close($("confirmationModal"));
  confirmationTrigger = null;
  resolve?.(accepted);
}

function closeAnalysis() {
  if ($("analysisModal").classList.contains("hidden")) return;
  modalManager.close($("analysisModal"));
  analysisTrigger = null;
}

function renderCalculatorResult(item) {
  const result = $("calculatorResult");
  const components = Object.entries(item.covered_score_components || {}).map(([key, value]) => `<div><span>${scoreComponentLabels[key] || key}</span><b>${num(value, 1)}</b><i><em style="width:${Math.min(100, Number(value) / ({return:30,protection:20,liquidity:20,delta:15,time:10,quote:5}[key] || 1) * 100)}%"></em></i></div>`).join("");
  result.innerHTML = `<div class="calculator-score-head"><div><small>${esc(item.asset)} · <span class="symbol">${esc(item.symbol)}</span> · ${badge(item.state)}</small><h3>${scoreValue(item)}<span>/۱۰۰</span></h3><b>${esc(item.covered_score_label)}</b></div><span class="${item.passes_dashboard_rule ? "calculator-pass" : "calculator-fail"}">${item.passes_dashboard_rule ? "واجد شرط فعلی داشبورد" : "خارج از شرط فعلی داشبورد"}</span></div><div class="calculator-metrics"><div><span>سود ماهانه</span><strong>${num(item.monthly_return, 2)}٪</strong></div><div><span>سود سالانه</span><strong>${num(item.annual_return, 2)}٪</strong></div><div><span>سود تا سررسید</span><strong>${num(item.expiry_return, 2)}٪</strong></div><div><span>درصد بازخرید</span><strong>${num(buybackPercent(item), 2)}٪</strong></div><div><span>بازخرید ماهانه</span><strong>${num(buybackMonthlyPercent(item), 2)}٪</strong></div><div><span>بازخرید سالانه</span><strong>${num(buybackAnnualPercent(item), 2)}٪</strong></div><div><span>حاشیه امن</span><strong>${num(item.downside_protection_percent, 2)}٪</strong></div><div><span>نقطه سربه‌سر</span><strong>${num(item.breakeven)}</strong></div><div><span>درصد ITM</span><strong>${num(item.itm_percent, 2)}٪</strong></div><div><span>دلتا اختیار</span><strong>${deltaDisplay(item)}</strong></div><div><span>دلتا کاوردکال</span><strong>${deltaDisplay(item, "strategy_delta")}</strong></div><div><span>روز تا سررسید</span><strong>${num(item.days)}</strong></div></div><div class="calculator-components"><h4>اجزای امتیاز</h4>${components}</div><p class="calculator-note">${item.liquidity_assumed ? "ارزش معاملات وارد نشد؛ میانه همان بازار برای بخش نقدشوندگی استفاده شد. " : ""}${item.delta_estimated ? "دلتا با IV مرجع ۳۵٪ برآورد شده است. " : "دلتا از نوسان ضمنی قیمت واردشده استخراج شد. "}این نتیجه ابزار مقایسه است و پیشنهاد معامله نیست.</p>`;
  result.classList.remove("hidden");
}

async function calculateCoveredCall(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const payload = Object.fromEntries(new FormData(form).entries());
  button.disabled = true; button.textContent = "در حال محاسبه…";
  try {
    const response = await apiFetch("/api/covered-score", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "محاسبه ناموفق بود");
    renderCalculatorResult(data);
  } catch (error) {
    $("calculatorResult").innerHTML = `<div class="calculator-error">${esc(error.message || "محاسبه ناموفق بود")}</div>`;
    $("calculatorResult").classList.remove("hidden");
  } finally {
    button.disabled = false; button.textContent = "محاسبه و امتیازدهی";
  }
}

function calculateLongCallManual(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form).entries());
  const base = Number(values.base_price), premium = Number(values.premium), strike = Number(values.strike);
  const days = Number(values.days), annualRate = Number(values.interest_rate);
  const result = $("longCalculatorResult");
  if (![base,premium,strike,days,annualRate].every(Number.isFinite) || base <= 0 || premium <= 0 || strike <= 0 || days < 0 || annualRate < 0) {
    result.innerHTML = '<div class="calculator-error">همه اعداد را به‌صورت معتبر و مثبت وارد کنید.</div>';
    result.classList.remove("hidden");
    return;
  }
  const periodRate = annualRate / 100 * days / 365;
  const interestCost = strike * periodRate;
  const adjustedCost = strike + premium - interestCost;
  const costGapPercent = (adjustedCost - base) / base * 100;
  const advantagePercent = -costGapPercent;
  const itmPercent = (base - strike) / base * 100;
  const breakeven = strike + premium;
  const leverage = base / premium;
  const recommendation = advantagePercent > 0 ? "خرید اختیار کم‌هزینه‌تر است" : advantagePercent < 0 ? "خرید دارایی پایه کم‌هزینه‌تر است" : "هزینه دو انتخاب برابر است";
  result.innerHTML = `<div class="calculator-score-head"><div><small>${esc(values.asset)} · <span class="symbol">${esc(values.symbol)}</span></small><h3>${num(leverage,2)}<span>× اهرم</span></h3><b>${esc(recommendation)}</b></div><span class="${advantagePercent >= 0 ? "calculator-pass" : "calculator-fail"}">${advantagePercent >= 0 ? "مزیت به نفع اختیار" : "مزیت به نفع پایه"}</span></div><div class="calculator-metrics"><div><span>هزینه تعدیل‌شده اعمال + پرمیوم</span><strong>${num(adjustedCost,2)}</strong></div><div><span>مزیت اختیار نسبت به پایه</span><strong class="${valueTone(advantagePercent)}">${signed(advantagePercent)}٪</strong></div><div><span>درصد ITM</span><strong>${signed(itmPercent)}٪</strong></div><div><span>نقطه سربه‌سر</span><strong>${num(breakeven,2)}</strong></div><div><span>اهرم (پایه ÷ پرمیوم)</span><strong>${num(leverage,2)}</strong></div><div><span>نرخ دوره</span><strong>${num(periodRate*100,2)}٪</strong></div><div><span>هزینه بهره اعمال</span><strong>${num(interestCost,2)}</strong></div><div><span>اختلاف هزینه با پایه</span><strong class="${valueTone(-costGapPercent)}">${signed(costGapPercent)}٪</strong></div></div><p class="calculator-note">فرمول هزینه تعدیل‌شده: اعمال + پرمیوم − (اعمال × نرخ سالانه × روز ÷ ۳۶۵). اهرم برابر قیمت دارایی پایه تقسیم بر پرمیوم است.</p>`;
  result.classList.remove("hidden");
}

function signed(value, digits = 2) {
  if (value == null) return "—";
  return `${Number(value) > 0 ? "+" : ""}${num(value, digits)}`;
}

function profitTone(value) {
  return value == null ? "" : Number(value) >= 0 ? "profit-up" : "profit-down";
}

function tradeReturnBox(title, actionLabel, profit, percent, yoy, highlighted = false, fulfillment = undefined, winner = false) {
  const fulfillmentLine = fulfillment === undefined ? "" : `<small class="trade-fulfillment">تحقق از سود انتظاری: <b class="${profitTone(fulfillment)}">${fulfillment == null ? "قابل محاسبه نیست" : `${num(fulfillment, 2)}٪`}</b></small>`;
  return `<div class="trade-return-box ${highlighted ? "highlight" : ""} ${winner ? "best-profit" : ""}"><span>${esc(title)}</span><em>${esc(actionLabel)}</em><strong class="${profitTone(profit)}">${signed(profit, 0)}</strong><small>بازده ${signed(percent)}٪ · سالانه‌شده ${signed(yoy)}٪</small>${fulfillmentLine}</div>`;
}

function decisionReturnBox(title, actionLabel, profit, percent, detail = "", winner = false, review = false) {
  return `<div class="trade-return-box ${winner || review ? "best-profit highlight" : ""}"><span>${esc(title)}${review ? '<b class="trade-review-tag">بررسی شود</b>' : ""}</span><em>${esc(actionLabel)}</em><strong class="${profitTone(profit)}">${signed(profit, 0)}</strong><small>بازده ${signed(percent)}٪${detail ? ` · ${esc(detail)}` : ""}</small></div>`;
}

function compactDecisionReturnBox(title, profit, percent, {review = false} = {}) {
  return `<div class="compact-return-box ${review ? "review-profit" : ""}"><span>${esc(title)}${review ? '<b class="trade-review-tag">بررسی شود</b>' : ""}</span><strong class="${profitTone(profit)}">${signed(profit,0)} (${signed(percent)}٪)</strong></div>`;
}

function riskFreeComparisonBox(item) {
  const multiple = item.strategy_to_risk_free_multiple;
  const strategyProfit = item.strategy_profit_for_risk_free;
  const multipleText = multiple == null
    ? (Number(item.risk_free_days || 0) === 0 ? "هنوز یک روز کامل سپری نشده" : "قابل محاسبه نیست")
    : `${signed(multiple, 2)} برابر`;
  return `<section class="risk-free-comparison"><header><div><span>مقایسه با صندوق درآمد ثابت</span><strong>نرخ سالانه ${num(item.risk_free_annual_rate, 0)}٪</strong></div><small>${num(item.risk_free_days, 0)} روز سپری‌شده</small></header><div class="risk-free-metrics"><div><span>سود بدون‌ریسک در این مدت</span><b class="profit-up">${signed(item.risk_free_profit, 0)}</b><small>بازده ${signed(item.risk_free_return_percent, 2)}٪</small></div><div><span>سود فعلی استراتژی</span><b class="${profitTone(strategyProfit)}">${signed(strategyProfit, 0)}</b><small>${esc(item.strategy_profit_for_risk_free_basis || "مبنای جاری استراتژی")}</small></div><div><span>نسبت سود استراتژی به بدون‌ریسک</span><b class="${profitTone(multiple)}">${multipleText}</b><small>سود استراتژی ÷ سود صندوق درآمد ثابت</small></div></div></section>`;
}

function coveredFulfillmentChart(item, {centerZero = false} = {}) {
  const fulfillment = Number(item.total_profit_fulfillment_percent);
  const expected = Number(item.expected_profit);
  const current = Number(item.total_profit);
  if (!Number.isFinite(fulfillment) || !Number.isFinite(expected) || expected <= 0 || !Number.isFinite(current)) {
    return `<section class="covered-fulfillment-chart unavailable"><header><div><span>تحقق سود کاوردکال با خروج امروز</span><strong>قابل محاسبه نیست</strong></div><p>برای محاسبه، سود انتظاری باید مثبت و قیمت‌های جاری در دسترس باشند.</p></header></section>`;
  }
  const centeredBound = Math.max(100, Math.ceil(Math.abs(fulfillment) / 25) * 25);
  const domainMin = centerZero ? -centeredBound : Math.min(0, Math.floor(fulfillment / 25) * 25);
  const domainMax = centerZero ? centeredBound : Math.max(100, Math.ceil(fulfillment / 25) * 25);
  const span = domainMax - domainMin || 100;
  const position = (value) => Math.max(0, Math.min(100, (value - domainMin) / span * 100));
  const zeroPosition = position(0);
  const currentPosition = position(fulfillment);
  const targetPosition = position(100);
  const segmentStart = Math.min(zeroPosition, currentPosition);
  const segmentWidth = Math.abs(currentPosition - zeroPosition);
  const tone = fulfillment < 0 ? "negative" : fulfillment >= 100 ? "complete" : "progress";
  const explanation = fulfillment < 0
    ? `خروج امروز نسبت به سود هدف کاوردکال ${num(Math.abs(fulfillment), 2)}٪ عقب‌تر است.`
    : fulfillment >= 100
    ? `خروج امروز ${num(fulfillment - 100, 2)}٪ بیشتر از سود هدف کاوردکال ایجاد می‌کند.`
    : `با آفست اختیار و فروش دارایی پایه در امروز، ${num(fulfillment, 2)}٪ از سود کاوردکال محقق می‌شود.`;
  const aria = `تحقق سود خروج امروز ${num(fulfillment, 2)} درصد؛ هدف سود کاوردکال ۱۰۰ درصد`;
  return `<section class="covered-fulfillment-chart ${tone} ${centerZero ? "center-zero" : ""}"><header><div><span>تحقق سود کاوردکال با خروج امروز</span><strong class="${profitTone(fulfillment)}">${signed(fulfillment)}٪</strong></div><p>سود خروج امروز ${signed(current, 0)} از سود هدف ${signed(expected, 0)}</p></header><div class="fulfillment-plot" role="img" aria-label="${esc(aria)}"><div class="fulfillment-axis"><i class="fulfillment-segment" style="inset-inline-start:${segmentStart}%;width:${segmentWidth}%"></i><b class="fulfillment-zero" style="inset-inline-start:${zeroPosition}%"><em>۰٪</em></b><b class="fulfillment-target" style="inset-inline-start:${targetPosition}%"><em>هدف ۱۰۰٪</em></b><b class="fulfillment-current" style="inset-inline-start:${currentPosition}%"></b></div><div class="fulfillment-scale"><span>${num(domainMin)}٪</span><span>${num(domainMax)}٪</span></div></div><p class="fulfillment-explanation">${esc(explanation)}</p></section>`;
}

function longCallReturnBoxes(item) {
  const closed = item.status === "closed";
  const comparison = Number(item.exercise_premium_vs_base_percent);
  const relativeAdvantage = Number.isFinite(comparison) ? -comparison : null;
  const relativeAdvantageText = relativeAdvantage == null
    ? "قابل محاسبه نیست"
    : relativeAdvantage > 0
    ? `${num(relativeAdvantage, 2)}٪ به نفع اختیار`
    : relativeAdvantage < 0
    ? `${num(Math.abs(relativeAdvantage), 2)}٪ به نفع دارایی پایه`
    : "برابر با دارایی پایه";
  const relativeAdvantageBox = `<div class="trade-return-box premium-base-comparison"><span>مزیت نسبی خرید اختیار</span><em>با لحاظ نرخ بهره بدون ریسک</em><strong class="${profitTone(relativeAdvantage)}">${relativeAdvantageText}</strong><small>اعمال تعدیل‌شده + پرمیوم، در مقایسه با قیمت دارایی پایه هنگام ورود</small></div>`;
  if (closed && item.exit_method === "exercise") {
    return `<div class="trade-return-box highlight"><span>سود یا زیان اعمال قرارداد</span><em>نقدینگی اعمال ${num(item.long_exercise_required_cash, 0)}</em><strong class="${profitTone(item.realized_profit)}">${signed(item.realized_profit, 0)}</strong><small>بازده قطعی ${signed(item.realized_profit_percent)}٪ · سالانه‌شده ${signed(item.realized_profit_yoy)}٪</small></div><div class="trade-return-box premium-base-comparison"><span>نحوه تسویه</span><em>اختیار آفست نشده است</em><strong>اعمال قرارداد</strong><small>قیمت پایه هنگام اعمال ${num(item.exit_base_price, 2)} · قیمت اعمال ${num(item.strike, 2)}</small></div>${relativeAdvantageBox}`;
  }
  const offset = decisionReturnBox(
    "فروش اختیار خرید",
    `فروش با ${item.option_valuation_basis || "مبنای انتخابی"}`,
    item.long_offset_profit,
    item.long_offset_profit_percent,
    `پرمیوم جاری ${num(item.current_option_exit_price, 2)}`,
  );
  const exercise = decisionReturnBox(
    "اعمال اختیار خرید",
    `نقدینگی موردنیاز اعمال ${num(item.long_exercise_required_cash, 0)}`,
    item.long_exercise_profit,
    item.long_exercise_profit_percent,
    `سربه‌سر ${num(item.long_exercise_breakeven, 2)} | پایه فعلی ${num(item.current_base_price, 2)}`,
  );
  const allocation = `<div class="trade-return-box highlight"><span>نتیجه بر اساس تخصیص ثبت‌شده</span><em>${qty(item.exercise_quantity)} اعمال · ${qty(item.premium_trade_quantity)} نوسان‌گیری</em><strong class="${profitTone(item.long_combined_profit)}">${signed(item.long_combined_profit,0)}</strong><small>بازده ${signed(item.long_combined_profit_percent)}٪</small></div>`;
  return `${offset}${exercise}${allocation}${relativeAdvantageBox}`;
}

function tradeAnalyticsSnapshot(item, prefix, title) {
  const itm = item[`${prefix}_itm_percent`];
  const optionDelta = item[`${prefix}_option_delta`];
  const strategyDelta = item[`${prefix}_strategy_delta`];
  if (itm == null && optionDelta == null && strategyDelta == null) return "";
  const estimated = Boolean(item[`${prefix}_delta_estimated`]);
  const prefixMark = estimated ? "≈" : "";
  const stateLabel = item[`${prefix}_moneyness`] || "—";
  return `<section class="trade-analytics-snapshot ${prefix}"><header><strong>${esc(title)}</strong><span class="${Number(itm) >= 0 ? "profit-up" : "profit-down"}">${esc(stateLabel)} · ${signed(itm)}٪</span></header><dl><div><dt>دلتا اختیار</dt><dd>${optionDelta == null ? "—" : `${prefixMark}${num(optionDelta, 3)}`}</dd></div><div><dt>دلتا استراتژی</dt><dd>${strategyDelta == null ? "—" : `${prefixMark}${num(strategyDelta, 3)}`}</dd></div><div><dt>نوسان ضمنی</dt><dd>${item[`${prefix}_implied_volatility`] == null ? "—" : `${num(item[`${prefix}_implied_volatility`], 2)}٪`}</dd></div><div><dt>روز تا سررسید</dt><dd>${num(item[`${prefix}_days_to_expiry`])}</dd></div><div><dt>قیمت پایه</dt><dd>${num(item[`${prefix}_base_price_snapshot`], 2)}</dd></div><div><dt>قیمت اختیار</dt><dd>${num(item[`${prefix}_option_price_snapshot`], 2)}</dd></div></dl>${estimated ? '<small>دلتا با نوسان مرجع برآورد شده است.</small>' : ""}</section>`;
}

function exportClosedTradesCsv() {
  const closed = state.trades.filter((item) => item.status === "closed");
  if (!closed.length) return;
  const csvMoney = (item, key) => window.NicOptionFinancialCsv.money(item, key);
  const columns = [
    ["استراتژی", (item) => item.strategy_type === "long_call" ? "خرید اختیار خرید" : "کاوردکال"],
    ["بازار", (item) => marketLabel(item.market)], ["دارایی پایه", (item) => item.asset], ["نماد اختیار", (item) => item.option_symbol],
    ["تاریخ ورود", (item) => item.entry_date_display], ["تاریخ خروج", (item) => item.exit_date_display], ["روش خروج", (item) => item.exit_method_label],
    ["تعداد کل", (item) => item.quantity], ["تعداد با هدف اعمال", (item) => item.exercise_quantity], ["تعداد نوسان‌گیری پرمیوم", (item) => item.premium_trade_quantity], ["قیمت پایه ورود", (item) => csvMoney(item, "entry_base_price")], ["پرمیوم ورود", (item) => csvMoney(item, "entry_premium")], ["قیمت اعمال", (item) => csvMoney(item, "strike")],
    ["قیمت پایه خروج", (item) => csvMoney(item, "exit_base_price")], ["قیمت اختیار خروج", (item) => csvMoney(item, "exit_option_price")],
    ["ITM ورود (درصد)", (item) => item.entry_itm_percent], ["ITM خروج (درصد)", (item) => item.exit_itm_percent],
    ["دلتا اختیار ورود", (item) => item.entry_option_delta], ["دلتا اختیار خروج", (item) => item.exit_option_delta],
    ["دلتا استراتژی ورود", (item) => item.entry_strategy_delta], ["دلتا استراتژی خروج", (item) => item.exit_strategy_delta],
    ["IV ورود (درصد)", (item) => item.entry_implied_volatility], ["IV خروج (درصد)", (item) => item.exit_implied_volatility],
    ["روز تا سررسید در ورود", (item) => item.entry_days_to_expiry], ["روز تا سررسید در خروج", (item) => item.exit_days_to_expiry],
    ["سود یا زیان قطعی", (item) => csvMoney(item, "realized_profit")], ["بازده قطعی (درصد)", (item) => item.realized_profit_percent],
    ["بازده سالانه‌شده (درصد)", (item) => item.realized_profit_yoy], ["روز نگهداری", (item) => item.invested_days],
    ["کارمزد ورود", (item) => csvMoney(item, "commission")], ["منبع کارمزد ورود", (item) => commissionSourceLabel(item.commission_source)],
    ["کارمزد خروج", (item) => csvMoney(item, "exit_commission")], ["منبع کارمزد خروج", (item) => commissionSourceLabel(item.exit_commission_source)],
    ["نسخه محاسبه", (item) => item.calculation_version], ["واحد پول", (item) => item.currency_unit],
    ["روش بهره", (item) => item.interest_convention], ["مبنای شمارش روز", (item) => item.interest_day_count], ["یادداشت", (item) => item.exit_note],
  ];
  const csv = window.NicOptionFinancialCsv.render(columns, closed);
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob(["\ufeff", csv], {type: "text/csv;charset=utf-8"}));
  link.download = `nicoption-closed-trades-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
}

function exportOpenTradesCsv() {
  const open = state.trades.filter((item) => item.status !== "closed");
  if (!open.length) return;
  const csvMoney = (item, key) => window.NicOptionFinancialCsv.money(item, key);
  const totalCapital = Number(state.lastTradesPayload?.summary?.total?.invested_capital || 0);
  const columns = [
    ["استراتژی", (item) => item.strategy_type === "long_call" ? "خرید اختیار خرید" : "کاوردکال"],
    ["بازار", (item) => marketLabel(item.market)], ["دارایی پایه", (item) => item.asset], ["نماد اختیار", (item) => item.option_symbol],
    ["تاریخ ورود", (item) => item.entry_date_display], ["تاریخ سررسید", (item) => item.expiry_display], ["روز باقی‌مانده", (item) => item.remaining_days],
    ["تعداد کل", (item) => item.quantity], ["تعداد با هدف اعمال", (item) => item.exercise_quantity], ["تعداد نوسان‌گیری پرمیوم", (item) => item.premium_trade_quantity],
    ["قیمت پایه ورود", (item) => csvMoney(item, "entry_base_price")], ["قیمت پایه جاری", (item) => csvMoney(item, "current_base_price")], ["تغییر پایه (درصد)", (item) => item.base_price_change_percent],
    ["پرمیوم ورود", (item) => csvMoney(item, "entry_premium")], ["پرمیوم جاری", (item) => csvMoney(item, "current_option_exit_price")], ["تغییر پرمیوم (درصد)", (item) => item.premium_price_change_percent],
    ["قیمت اعمال", (item) => csvMoney(item, "strike")], ["ITM ورود (درصد)", (item) => item.entry_itm_percent], ["ITM فعلی (درصد)", (item) => item.current_itm_percent],
    ["دلتا اختیار ورود", (item) => item.entry_option_delta], ["دلتا اختیار فعلی", (item) => item.current_option_delta],
    ["دلتا استراتژی ورود", (item) => item.entry_strategy_delta], ["دلتا استراتژی فعلی", (item) => item.current_strategy_delta],
    ["سرمایه درگیر", (item) => csvMoney(item, "invested_capital")], ["سهم از کل سرمایه (درصد)", (item) => totalCapital > 0 ? Number(csvMoney(item, "invested_capital") || 0) / totalCapital * 100 : null],
    ["سود نگهداری کاوردکال", (item) => csvMoney(item, "covered_hold_profit")], ["سود آفست و فروش پایه", (item) => csvMoney(item, "covered_liquidation_profit")],
    ["سود فروش اختیار خرید", (item) => csvMoney(item, "long_offset_profit")], ["سود اعمال اختیار خرید", (item) => csvMoney(item, "long_exercise_profit")],
    ["مبنای قیمت اختیار", (item) => item.option_valuation_basis], ["مبنای قیمت پایه", (item) => item.base_valuation_basis], ["کارمزد ورود", (item) => csvMoney(item, "commission")],
    ["منبع کارمزد ورود", (item) => commissionSourceLabel(item.commission_source)], ["نسخه محاسبه", (item) => item.calculation_version],
    ["واحد پول", (item) => item.currency_unit], ["روش بهره", (item) => item.interest_convention], ["مبنای شمارش روز", (item) => item.interest_day_count],
  ];
  const csv = window.NicOptionFinancialCsv.render(columns, open);
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob(["\ufeff", csv], {type: "text/csv;charset=utf-8"}));
  link.download = `nicoption-open-trades-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
}

const liquidityPalette = ["var(--chart-primary)", "var(--chart-warning)", "var(--chart-secondary)", "var(--chart-positive)", "var(--chart-negative)"];

function liquidityDonut(segments = [], {center = "", compact = false, ariaLabel = "ترکیب نقدینگی", emptyLabel = "داده نقدینگی موجود نیست", centerSub = "از کل"} = {}) {
  const valid = segments.filter((item) => Number(item.value) > 0);
  const total = valid.reduce((sum, item) => sum + Number(item.value), 0);
  if (total <= 0) return `<div class="liquidity-chart-empty">${esc(emptyLabel)}</div>`;
  let offset = 0;
  const circles = valid.map((item, index) => {
    const share = Number(item.value) / total * 100;
    const circle = `<circle cx="50" cy="50" r="37" pathLength="100" fill="none" stroke="${item.color || liquidityPalette[index % liquidityPalette.length]}" stroke-width="16" stroke-dasharray="${share} ${100 - share}" stroke-dashoffset="${-offset}" transform="rotate(-90 50 50)"><title>${esc(item.label)}: ${num(share,2)}٪</title></circle>`;
    offset += share;
    return circle;
  }).join("");
  return `<div class="liquidity-donut ${compact ? "compact" : ""}"><svg viewBox="0 0 100 100" role="img" aria-label="${esc(ariaLabel)}"><circle cx="50" cy="50" r="37" fill="none" stroke="var(--line)" stroke-width="16"/>${circles}</svg><div><strong>${esc(center)}</strong><small>${esc(centerSub)}</small></div></div>`;
}

function assetLiquidityComposition(rows = [], closed = false) {
  const positive = rows.filter((item) => Number(item.invested_capital) > 0);
  if (!positive.length) return "";
  if (closed) return assetMetricLineChart(positive, {title:"نقدینگی معاملات بسته به تفکیک نماد",subtitle:"نام هر نماد را برای مشاهده همه معاملات آن انتخاب کنید.",value:(item)=>Number(item.invested_capital||0),valueLabel:"نقدینگی درگیر"});
  const visible = positive.slice(0, 4).map((item) => ({label: item.asset || "نامشخص", value: Number(item.invested_capital)}));
  const remainder = positive.slice(4).reduce((sum, item) => sum + Number(item.invested_capital || 0), 0);
  if (remainder > 0) visible.push({label: "سایر", value: remainder});
  const total = visible.reduce((sum, item) => sum + item.value, 0);
  const legend = visible.map((item, index) => `<li><i style="background:${liquidityPalette[index % liquidityPalette.length]}"></i><span>${esc(item.label)}</span><b>${num(item.value / total * 100,2)}٪</b></li>`).join("");
  const title = closed ? "ترکیب نقدینگی معاملات بسته" : "ترکیب نقدینگی معاملات باز";
  return `<section class="asset-liquidity-composition"><header><div><strong>${title}</strong><small>سهم هر دارایی از کل نقدینگی همین صفحه</small></div><span>${num(positive.length)} دارایی</span></header><div class="asset-liquidity-chart">${liquidityDonut(visible,{center:"۱۰۰٪"})}<ul>${legend}</ul></div></section>`;
}

function assetProfitComposition(rows = [], closed = false) {
  const profitKey = closed ? "net_profit" : "selected_profit";
  const available = rows
    .map((item) => ({label:item.asset || "نامشخص", signedValue:Number(item[profitKey] || 0)}))
    .filter((item) => Number.isFinite(item.signedValue) && item.signedValue !== 0)
    .sort((a,b) => Math.abs(b.signedValue) - Math.abs(a.signedValue));
  if (!available.length) return "";
  if (closed) return assetMetricLineChart(available, {title:"سود و زیان قطعی معاملات بسته",subtitle:"خط مبنا صفر است؛ نقاط بالای خط سود و نقاط پایین آن زیان‌اند.",value:(item)=>Number(item.signedValue||0),valueLabel:"سود یا زیان قطعی"});
  const visible = available.slice(0,3);
  const remainderRows = available.slice(3);
  const remainderProfit = remainderRows.filter((item) => item.signedValue > 0).reduce((sum,item) => sum + item.signedValue,0);
  const remainderLoss = remainderRows.filter((item) => item.signedValue < 0).reduce((sum,item) => sum + item.signedValue,0);
  if (remainderProfit > 0) visible.push({label:"سایر سودها",signedValue:remainderProfit});
  if (remainderLoss < 0) visible.push({label:"سایر زیان‌ها",signedValue:remainderLoss});
  const magnitudeTotal = visible.reduce((sum,item) => sum + Math.abs(item.signedValue),0);
  const segments = visible.map((item) => ({label:item.label,value:Math.abs(item.signedValue)}));
  const legend = visible.map((item,index) => {
    const share = magnitudeTotal > 0 ? Math.abs(item.signedValue) / magnitudeTotal * 100 : 0;
    return `<li><i style="background:${liquidityPalette[index % liquidityPalette.length]}"></i><span>${esc(item.label)}</span><b class="${profitTone(item.signedValue)}">${signed(item.signedValue,0)} · ${num(share,1)}٪</b></li>`;
  }).join("");
  const title = closed ? "ترکیب سود و زیان معاملات بسته" : "ترکیب سود و زیان معاملات باز";
  const subtitle = closed ? "سهم هر دارایی از قدرمطلق سود و زیان قطعی" : "سهم هر دارایی از قدرمطلق سود منتخب";
  return `<section class="asset-liquidity-composition asset-profit-composition"><header><div><strong>${title}</strong><small>${subtitle}</small></div><span>${num(available.length)} دارایی</span></header><div class="asset-liquidity-chart">${liquidityDonut(segments,{center:"۱۰۰٪",ariaLabel:title,emptyLabel:"داده سود موجود نیست",centerSub:"قدر مطلق"})}<ul>${legend}</ul></div></section>`;
}

function compactCurrency(value){const amount=Number(value||0),a=Math.abs(amount);if(a>=1e9)return `${num(amount/1e9,1)} میلیارد`;if(a>=1e6)return `${num(amount/1e6,1)} میلیون`;if(a>=1e3)return `${num(amount/1e3,1)} هزار`;return num(amount,0);}
function portfolioClassAllocationChart(items=[]){
 const palette={cash:"var(--green)",free:"var(--blue)",collateral:"var(--violet)",options:"var(--magenta)"},total=items.reduce((sum,item)=>sum+Math.max(0,Number(item.value||0)),0);
 const normalized=items.map((item)=>({...item,value:Math.max(0,Number(item.value||0)),share:total>0?Math.max(0,Number(item.value||0))/total*100:0}));
 const segments=total>0?normalized.filter((item)=>item.value>0).map((item)=>`<i class="${item.key}" style="width:${item.share}%" title="${esc(item.label)}: ${num(item.value,0)} (${num(item.share,1)}٪)"></i>`).join(""):'<i class="empty" style="width:100%"></i>';
 const legend=normalized.map((item)=>`<li><span><i style="background:${palette[item.key]}"></i>${esc(item.label)}</span><b>${num(item.value,0)}</b><small>${num(item.share,1)}٪</small></li>`).join("");
 return `<section class="portfolio-class-composition"><header><div><strong>ترکیب دارایی‌های حساب</strong><small>طول هر بخش متناسب با بهای ثبت‌شده همان کلاس دارایی است.</small></div><b>${num(total,0)}</b></header><div class="portfolio-class-track" role="img" aria-label="ترکیب وجه نقد، دارایی پایه آزاد، وثیقه کاوردکال و اختیارهای خرید">${segments}</div><ul>${legend}</ul></section>`;
}
function assetMetricHistogram(rows=[],{title,subtitle,value,valueLabel,includeCash=false,cash=0}={}){
 const points=rows.map((item)=>({asset:item.asset||item.label||"نامشخص",value:Math.max(0,Number(value(item)||0))}));if(includeCash)points.unshift({asset:"وجه نقد",value:Math.max(0,Number(cash||0)),cash:true});if(!points.length)return '<div class="liquidity-chart-empty">داده‌ای برای رسم نمودار موجود نیست.</div>';
 const max=Math.max(1,...points.map((p)=>p.value)),width=Math.max(620,points.length*112),height=268,padX=54,padTop=36,padBottom=18,plotH=height-padTop-padBottom,slot=(width-padX*2)/points.length,barW=Math.min(72,slot*.68);
 const grid=[1,.5,0].map((ratio)=>{const y=padTop+(1-ratio)*plotH;return `<g><line x1="${padX}" y1="${y}" x2="${width-padX}" y2="${y}" class="asset-hist-grid"/><text x="${padX-8}" y="${y+4}" text-anchor="end">${num(max*ratio,0)}</text></g>`}).join("");
 const bars=points.map((p,i)=>{const exactH=p.value/max*plotH,visualH=Math.max(34,exactH),x=padX+i*slot+(slot-barW)/2,y=padTop+plotH-visualH,content=`<rect x="${x}" y="${y}" width="${barW}" height="${visualH}" rx="7"><title>${esc(p.asset)} · ${esc(valueLabel)} ${num(p.value,0)}</title></rect><text class="asset-hist-value" x="${x+barW/2}" y="${Math.max(17,y-9)}" text-anchor="middle">${esc(compactCurrency(p.value))}</text><text class="asset-hist-name" x="${x+barW/2}" y="${y+visualH-12}" text-anchor="middle">${esc(p.asset)}</text>`;return p.cash?`<g class="asset-hist-bar cash">${content}</g>`:`<a href="/trades/open?asset=${encodeURIComponent(p.asset)}" class="asset-hist-bar-link" data-asset-trades="${esc(p.asset)}" aria-label="نمایش معاملات ${esc(p.asset)}"><g class="asset-hist-bar">${content}</g></a>`}).join("");
 return `<section class="asset-line-composition asset-histogram"><header><div><strong>${esc(title)}</strong><small>${esc(subtitle)}</small></div><span>${num(points.length)} مورد</span></header><div class="asset-line-scroll"><div class="asset-line-canvas" style="--asset-chart-width:${width}px"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title>${grid}${bars}</svg></div></div></section>`;
}
function assetMetricLineChart(rows=[],{title,subtitle,value,valueLabel,includeCash=false,cash=0}={}){
 const points=rows.map((item)=>({asset:item.asset||item.label||"نامشخص",value:Number(value(item)||0)}));if(includeCash)points.unshift({asset:"وجه نقد",value:Number(cash||0),cash:true});if(!points.length)return '<div class="liquidity-chart-empty">داده‌ای برای رسم نمودار موجود نیست.</div>';
 const width=Math.max(620,points.length*112),height=248,padX=56,padTop=24,padBottom=54,values=points.map((p)=>p.value);let min=Math.min(0,...values),max=Math.max(0,...values);if(min===max){min-=1;max+=1;}const range=max-min,x=(i)=>points.length===1?width/2:padX+i*(width-padX*2)/(points.length-1),y=(v)=>padTop+(max-v)/range*(height-padTop-padBottom),zeroY=y(0),line=points.map((p,i)=>`${x(i)},${y(p.value)}`).join(" ");
 const grid=[max,max-range/2,min].map((v)=>`<g><line x1="${padX}" y1="${y(v)}" x2="${width-padX}" y2="${y(v)}" class="asset-line-grid"/><text x="${padX-8}" y="${y(v)+4}" text-anchor="end">${num(v,0)}</text></g>`).join("");
 const markers=points.map((p,i)=>`<g class="asset-line-point ${profitTone(p.value)}"><circle cx="${x(i)}" cy="${y(p.value)}" r="5"><title>${esc(p.asset)} · ${esc(valueLabel)} ${signed(p.value,0)}</title></circle><text x="${x(i)}" y="${Math.max(16,y(p.value)-12)}" text-anchor="middle">${esc(compactCurrency(p.value))}</text></g>`).join("");
 const labels=points.map((p)=>p.cash?`<span class="asset-line-label static"><b>${esc(p.asset)}</b><small>${num(p.value,0)}</small></span>`:`<button type="button" class="asset-line-label" data-asset-trades="${esc(p.asset)}"><b>${esc(p.asset)}</b><small>${num(p.value,0)}</small></button>`).join("");
 return `<section class="asset-line-composition"><header><div><strong>${esc(title)}</strong><small>${esc(subtitle)}</small></div><span>${num(points.length)} مورد</span></header><div class="asset-line-scroll"><div class="asset-line-canvas" style="--asset-chart-width:${width}px"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(title)}"><title>${esc(title)}</title>${grid}<line x1="${padX}" y1="${zeroY}" x2="${width-padX}" y2="${zeroY}" class="asset-line-zero"/><polyline points="${line}" class="asset-line-path"/>${markers}</svg><div class="asset-line-labels" style="grid-template-columns:repeat(${points.length},minmax(88px,1fr))">${labels}</div></div></div></section>`;
}

function renderAssetPortfolioBreakdown(targetId, rows = [], {closed = false} = {}) {
  const target = $(targetId);
  if (!target) return;
  if (!rows.length) {
    target.innerHTML = `<div class="trades-empty">${closed ? "معامله بسته‌شده‌ای ثبت نشده است." : "معامله بازی ثبت نشده است."}</div>`;
    return;
  }
  const cards = rows.map((item) => {
    const profit = closed ? item.net_profit : item.selected_profit;
    const percent = closed ? item.profit_percent : item.selected_profit_percent;
    const profitLabel = closed ? "سود قطعی" : "سود منتخب";
    const strategyMix = [
      Number(item.covered_count || 0) ? `${num(item.covered_count)} کاوردکال` : "",
      Number(item.long_call_count || 0) ? `${num(item.long_call_count)} خرید اختیار` : "",
      Number(item.underlying_count || 0) ? `${num(item.underlying_count)} دارایی پایه آزاد` : "",
    ].filter(Boolean).join(" · ") || "بدون تفکیک استراتژی";
    return `<article class="asset-portfolio-row"><header><strong>${esc(item.asset || "نامشخص")}</strong><span>${num(item.count || 0)} معامله</span></header><div><section><span>نقدینگی درگیر</span><b>${num(item.invested_capital || 0, 0)}</b><small>${num(item.liquidity_share_percent, 2)}٪ از کل نقدینگی</small></section><section><span>${profitLabel}</span><b class="${profitTone(profit)}">${signed(profit || 0, 0)} <small>(${signed(percent)}٪)</small></b></section></div><footer>${esc(strategyMix)} · ${num(item.valued_count || 0)} معامله ارزش‌گذاری‌شده</footer></article>`;
  }).join("");
  target.innerHTML = `${assetLiquidityComposition(rows,closed)}${assetProfitComposition(rows,closed)}${cards}`;
}

function renderPortfolioAssetLedger(ledger = {}) {
  const rows = ledger.rows || [];
  const base = ledger.base || {};
  const free = ledger.free || {};
  const collateral = ledger.collateral || {};
  const longCalls = ledger.long_calls || {};
  const freeShare = Number(base.free_share_percent || 0);
  const collateralShare = Number(base.collateral_share_percent || 0);
  $("portfolioLedgerCash").textContent = num(ledger.cash || 0, 0);
  $("portfolioLedgerFreeBase").textContent = num(free.cost || 0, 0);
  $("portfolioLedgerCollateral").textContent = num(collateral.cost || 0, 0);
  $("portfolioLedgerLongCalls").textContent = num(longCalls.cost || 0, 0);
  $("portfolioLedgerTrackedTotal").textContent = num(ledger.tracked_total_cost || 0, 0);
  $("portfolioLedgerBaseTotal").textContent = num(base.cost || 0, 0);
  $("portfolioLedgerBaseTotalNote").textContent = `${num(base.asset_count || 0)} دارایی پایه · ${qty(base.quantity || 0)} واحد`;
  $("portfolioLedgerFreeSplit").textContent = `${num(free.cost || 0, 0)} · ${num(freeShare, 1)}٪`;
  $("portfolioLedgerCollateralSplit").textContent = `${num(collateral.cost || 0, 0)} · ${num(collateralShare, 1)}٪`;
  $("portfolioLedgerFreeBar").style.width = `${Math.max(0, Math.min(100, freeShare))}%`;
  $("portfolioLedgerCollateralBar").style.width = `${Math.max(0, Math.min(100, collateralShare))}%`;
  $("portfolioLedgerCashNote").textContent = Number(ledger.cash || 0) > 0 ? "مانده قابل استفاده ثبت‌شده در حساب" : "هنوز وجه نقدی ثبت نشده است";
  $("portfolioLedgerFreeBaseNote").textContent = `${num(free.asset_count || 0)} دارایی · ${qty(free.quantity || 0)} واحد`;
  $("portfolioLedgerCollateralNote").textContent = `${num(collateral.asset_count || 0)} دارایی · ${qty(collateral.quantity || 0)} واحد · ${num(collateral.covered_call_count || 0)} کاوردکال`;
  $("portfolioLedgerLongCallsNote").textContent = `${num(longCalls.trade_count || 0)} معامله باز`;
  $("portfolioClassAllocationChart").innerHTML=portfolioClassAllocationChart([
    {key:"free",label:"دارایی پایه آزاد",value:free.cost},{key:"cash",label:"وجه نقد",value:ledger.cash},{key:"collateral",label:"وثیقه کاوردکال",value:collateral.cost},{key:"options",label:"خرید اختیار خرید",value:longCalls.cost},
  ]);
  const chartRows=rows.map((row)=>({asset:row.asset,amount:Number(row.free_cost||0)+Number(row.collateral_cost||0)+Number(row.long_call_cost||0)})).filter((row)=>row.amount>0);
  $("portfolioAssetLineChart").innerHTML=assetMetricHistogram(chartRows,{title:"میزان دارایی‌های حساب به تفکیک نماد",subtitle:"نمایش ستونی بر پایه بهای ثبت‌شده؛ نام نماد را برای دیدن تمام معاملات انتخاب کنید.",value:(item)=>item.amount,valueLabel:"بهای ثبت‌شده",includeCash:true,cash:ledger.cash});

  const list = $("portfolioAssetLedgerList");
  if (!rows.length) {
    list.innerHTML = '<div class="portfolio-asset-ledger-empty"><strong>هنوز دارایی ثبت نشده است</strong><span>خریدهای دارایی پایه یا اختیار خرید پس از ثبت، بدون ادغام سوابق خرید در اینجا خلاصه می‌شوند.</span></div>';
    return;
  }

  list.innerHTML = rows.map((row) => {
    const rowFreeShare = Number(row.base_cost || 0) > 0 ? Number(row.free_cost || 0) / Number(row.base_cost) * 100 : 0;
    const rowCollateralShare = Number(row.base_cost || 0) > 0 ? Number(row.collateral_cost || 0) / Number(row.base_cost) * 100 : 0;
    const bar = Number(row.base_quantity || 0) > 0
      ? `<div class="portfolio-allocation" aria-label="${num(rowFreeShare, 1)} درصد آزاد و ${num(rowCollateralShare, 1)} درصد وثیقه"><div class="portfolio-allocation-labels"><span>آزاد <b>${num(row.free_cost || 0, 0)} · ${num(rowFreeShare, 1)}٪</b></span><span>وثیقه <b>${num(row.collateral_cost || 0, 0)} · ${num(rowCollateralShare, 1)}٪</b></span></div><div class="portfolio-allocation-track" role="img" aria-label="تقسیم بهای ${esc(row.asset)} بین دارایی آزاد و وثیقه کاوردکال"><i class="free" style="width:${Math.max(0, Math.min(100, rowFreeShare))}%"></i><i class="collateral" style="width:${Math.max(0, Math.min(100, rowCollateralShare))}%"></i></div></div>`
      : '<div class="portfolio-allocation no-base"><span>برای این دارایی فقط اختیار خرید ثبت شده است.</span></div>';
    const collateralSource = Number(row.legacy_collateral_trade_count || 0) > 0
      ? `${num(row.legacy_collateral_trade_count)} معامله قدیمی از اطلاعات ثبت‌شدهٔ خود معامله`
      : `${num(row.covered_call_count || 0)} معامله متصل به موجودی پایه`;
    const positionLabel = Number(row.base_quantity || 0) > 0
      ? `${qty(row.base_quantity)} واحد پایه`
      : `${num(row.long_call_count || 0)} اختیار`;
    return `<details class="portfolio-asset-allocation-card"><summary><div><strong>${esc(row.asset)}</strong><small>${marketLabel(row.market)} · ${num(row.base_lot_count || 0)} خرید پایه · ${num(row.covered_call_count || 0)} کاوردکال · ${num(row.long_call_count || 0)} خرید اختیار</small></div><div class="portfolio-asset-summary-meta"><span>${positionLabel}</span><b><i>بیشتر</i><i>کمتر</i></b></div></summary><div class="portfolio-asset-allocation-body">${bar}<div class="portfolio-asset-allocation-metrics"><section><span>دارایی آزاد</span><b>${qty(row.free_quantity || 0)} واحد</b><small>بهای تمام‌شده ${num(row.free_cost || 0, 0)} · میانگین ${num(row.free_average_cost, 2)}</small></section><section><span>وثیقهٔ کاوردکال</span><b>${qty(row.collateral_quantity || 0)} واحد</b><small>بهای تمام‌شده ${num(row.collateral_cost || 0, 0)} · میانگین ${num(row.collateral_average_cost, 2)}</small></section><section><span>ارزش روز دارایی پایه</span><b>${Number(row.valued_free_quantity || 0) + Number(row.valued_collateral_quantity || 0) > 0 ? num(row.base_current_value || 0, 0) : "—"}</b><small>${qty(Number(row.valued_free_quantity || 0) + Number(row.valued_collateral_quantity || 0))} واحد قیمت‌گذاری‌شده</small></section><section><span>اختیارهای خرید</span><b>${num(row.long_call_cost || 0, 0)}</b><small>${num(row.long_call_count || 0)} معامله · ${qty(row.long_call_quantity || 0)} قرارداد</small></section></div><footer class="portfolio-price-profit"><div><span>سود/زیان تغییر قیمت پایه آزاد</span><b class="${profitTone(row.free_price_profit)}">${Number(row.valued_free_quantity || 0) > 0 ? `${signed(row.free_price_profit, 0)} (${signed(row.free_price_profit_percent)}٪)` : "—"}</b></div><div><span>سود/زیان تغییر قیمت وثیقه</span><b class="${profitTone(row.collateral_price_profit)}">${Number(row.valued_collateral_quantity || 0) > 0 ? `${signed(row.collateral_price_profit, 0)} (${signed(row.collateral_price_profit_percent)}٪)` : "—"}</b></div><small>${esc(collateralSource)} · سود وثیقه فقط داخل نتیجهٔ کاوردکال است.</small></footer></div></details>`;
  }).join("");
}

function focusAccountCash() {
  if (currentPage !== "profit-recognition") {
    window.location.assign("/profit-recognition#account-settings");
    return;
  }
  const secondary = document.querySelector(".account-growth-secondary");
  const settings = document.querySelector(".account-growth-settings");
  if (secondary) secondary.open = true;
  if (settings) settings.open = true;
  const input = $("accountCapitalForm")?.elements?.cash_balance;
  if (!input) return;
  input.scrollIntoView({behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center"});
  window.setTimeout(() => input.focus({preventScroll:true}), 250);
}

function renderOpenTradesSummary(summary = {}) {
  const covered = summary.covered_call || {};
  const longCall = summary.long_call || {};
  const total = summary.total || {};
  const setProfit = (id, value) => {
    const element = $(id);
    element.textContent = signed(value, 0);
    element.className = profitTone(value);
  };
  $("portfolioTotalCount").textContent = `${num(total.count || 0)} معامله`;
  $("portfolioCoveredCount").textContent = `${num(covered.count || 0)} معامله`;
  $("portfolioLongCount").textContent = `${num(longCall.count || 0)} معامله`;
  $("portfolioTotalCapital").textContent = num(total.invested_capital || 0, 0);
  $("portfolioCoveredCapital").textContent = num(covered.invested_capital || 0, 0);
  $("portfolioLongCapital").textContent = num(longCall.invested_capital || 0, 0);
  const totalCapital = Number(total.invested_capital || 0);
  const coveredLiquidityShare = totalCapital > 0 ? Number(covered.invested_capital || 0) / totalCapital * 100 : 0;
  const longLiquidityShare = totalCapital > 0 ? Number(longCall.invested_capital || 0) / totalCapital * 100 : 0;
  $("portfolioCoveredLiquidityShare").textContent = `${num(coveredLiquidityShare, 2)}٪ از کل نقدینگی`;
  $("portfolioLongLiquidityShare").textContent = `${num(longLiquidityShare, 2)}٪ از کل نقدینگی`;
  $("portfolioCoveredLiquidityChart").innerHTML = liquidityDonut([
    {label:"کاوردکال",value:coveredLiquidityShare,color:liquidityPalette[0]},
    {label:"سایر",value:Math.max(0,100-coveredLiquidityShare),color:"var(--line-strong)"},
  ],{center:`${num(coveredLiquidityShare,1)}٪`,compact:true});
  $("portfolioLongLiquidityChart").innerHTML = liquidityDonut([
    {label:"خرید اختیار",value:longLiquidityShare,color:liquidityPalette[0]},
    {label:"سایر",value:Math.max(0,100-longLiquidityShare),color:"var(--line-strong)"},
  ],{center:`${num(longLiquidityShare,1)}٪`,compact:true});
  $("portfolioLongAllocatedExerciseCash").textContent = num(longCall.exercise_allocation_required_cash || 0, 0);
  $("portfolioLongAllExerciseCash").textContent = num(longCall.exercise_required_cash || 0, 0);
  setProfit("portfolioTotalProfit", total.selected_profit || 0);
  const totalSelectedPercent = total.selected_profit_percent != null
    ? total.selected_profit_percent
    : totalCapital > 0 ? Number(total.selected_profit || 0) / totalCapital * 100 : null;
  $("portfolioTotalProfit").textContent = `${signed(total.selected_profit || 0, 0)} (${signed(totalSelectedPercent)}٪)`;
  const coveredHeroProfit = Number(covered.fluctuation_profit || 0);
  const longHeroProfit = Number(longCall.fluctuation_profit ?? longCall.offset_profit ?? 0);
  setProfit("portfolioCoveredExpected", coveredHeroProfit);
  setProfit("portfolioCoveredSelectedLiquidation", covered.selected_liquidation_profit || 0);
  setProfit("portfolioCoveredOptionOnly", covered.option_only_profit || 0);
  setProfit("portfolioLongProfit", longCall.combined_profit || 0);
  setProfit("portfolioLongOffset", longHeroProfit);
  setProfit("portfolioLongExercise", longCall.exercise_decision_profit || 0);
  $("portfolioCoveredExpected").textContent = `${signed(coveredHeroProfit, 0)} (${signed(covered.fluctuation_percent)}٪)`;
  $("portfolioLongOffset").textContent = `${signed(longHeroProfit, 0)} (${signed(longCall.fluctuation_percent)}٪)`;
  $("portfolioLongOffsetNote").textContent = `تغییر قیمت اختیار · ${num(longCall.fluctuation_valued_count || 0)} از ${num(longCall.count || 0)} معامله قیمت‌گذاری‌شده`;
  $("portfolioLongExerciseNote").textContent = `بازده ${signed(longCall.exercise_decision_percent)}٪ · سالانه ${signed(longCall.exercise_decision_yoy)}٪`;
  $("portfolioCoveredSelectedLiquidationNote").textContent = `بازده ${signed(covered.selected_liquidation_percent)}٪ · سالانه ${signed(covered.selected_liquidation_yoy)}٪`;
  $("portfolioCoveredExpectedNote").textContent = `تغییر قیمت اختیار + تغییر قیمت دارایی پایه · ${num(covered.fluctuation_valued_count || 0)} از ${num(covered.count || 0)} معامله`;
  $("portfolioCoveredOptionOnlyNote").textContent = `بازده ${signed(covered.option_only_percent)}٪ · سالانه ${signed(covered.option_only_yoy)}٪`;
  $("portfolioLongProfitNote").textContent = `بازده سالانه ${signed(longCall.combined_yoy)}٪ · پرمیوم ${signed(longCall.premium_profit,0)} · اعمال ${signed(longCall.exercise_profit,0)}`;
  $("portfolioTotalProfitNote").textContent = `اختیار خرید: نوسان پرمیوم · کاوردکال: نوسان اختیار + پایه · ${num(total.valued_count || 0)} از ${num(total.count || 0)} معامله`;
  const coveredDecisionCards = [
    ["portfolioCoveredSelectedLiquidation", covered.selected_liquidation_profit],
    ["portfolioCoveredOptionOnly", covered.option_only_profit],
  ];
  $("portfolioCoveredExpected").parentElement.classList.remove("best-profit");
  coveredDecisionCards.forEach(([id]) => $(id).parentElement.classList.remove("best-profit"));
  const valuedCoveredDecisions = coveredDecisionCards.filter(([, value]) => value != null && Number.isFinite(Number(value)));
  if (valuedCoveredDecisions.length) {
    const winnerId = valuedCoveredDecisions.reduce((best, item) => Number(item[1]) > Number(best[1]) ? item : best)[0];
    $(winnerId).parentElement.classList.add("best-profit");
  }
  renderAssetPortfolioBreakdown("openPortfolioByAsset", summary.by_asset || []);
}

function renderUnderlyingPositions(payload = {}) {
  state.underlyingPositions = payload.underlying_positions || [];
  state.underlyingQuotes = payload.underlying_quotes || [];
  const open = state.underlyingPositions.filter((item) => item.status !== "closed" && Number(item.available_quantity || 0) > 0);
  const closed = state.underlyingPositions.filter((item) => item.status === "closed");
  const summary = payload.underlying_summary || {};
  const closedSummary = payload.closed_underlying_summary || {};
  const summaryHtml = (item,closedMode=false) => `<div><span>${closedMode ? "سرمایه تاریخی" : "نقدینگی مستقل"}</span><strong>${num(item.invested_capital || 0,0)}</strong></div><div><span>${closedMode ? "سود قطعی" : "سود شناور"}</span><strong class="${profitTone(item.profit)}">${signed(item.profit || 0,0)} (${signed(item.profit_percent)}٪)</strong></div>`;
  $("underlyingSummary").innerHTML = summaryHtml(summary);
  $("closedUnderlyingSummary").innerHTML = summaryHtml(closedSummary,true);
  $("underlyingClosedCount").textContent = `${num(closed.length)} موقعیت`;
  const card = (item,closedMode=false) => {
    const actions = closedMode
      ? `<button class="trade-action danger" type="button" data-underlying-action="delete" data-position-id="${esc(item.id)}">حذف</button>`
      : `<button class="trade-action" type="button" data-underlying-action="sell" data-position-id="${esc(item.id)}">ثبت فروش</button><button class="trade-action" type="button" data-underlying-action="edit" data-position-id="${esc(item.id)}">ویرایش</button><button class="trade-action danger" type="button" data-underlying-action="delete" data-position-id="${esc(item.id)}">حذف</button>`;
    const excluded = closedMode && item.portfolio_excluded ? '<small class="previous-price-tag">سود پایه داخل نتیجه کاوردکال محاسبه شده</small>' : "";
    return `<article class="underlying-card" data-underlying-id="${esc(item.id)}"><header><div><strong>${esc(item.asset)}</strong><small>${marketLabel(item.market)} · ${item.acquisition_method === "exercise" ? "خرید از طریق اعمال" : "خرید مستقیم"}</small></div><span>${qty(closedMode ? item.quantity : item.available_quantity)} واحد</span></header><div><section><span>قیمت خرید/سربه‌سر</span><b>${num(item.entry_price,2)}</b></section><section><span>${closedMode ? "قیمت فروش" : "قیمت فعلی"}</span><b>${num(closedMode ? item.exit_price : item.current_price,2)}</b>${item.last_is_previous_day ? '<small class="previous-price-tag">قیمت روز قبل</small>' : ""}</section><section><span>${closedMode ? "سود قطعی" : "سود شناور"}</span><b class="${profitTone(item.profit)}">${signed(item.profit,0)}</b><small class="${profitTone(item.profit_percent)}">${signed(item.profit_percent)}٪ · سالانه ${signed(item.profit_yoy)}٪</small>${excluded}</section><section><span>${closedMode ? "مدت نگهداری" : "تخصیص به کاوردکال"}</span><b>${closedMode ? `${num(item.holding_days)} روز` : `${qty(item.allocated_quantity)} واحد`}</b></section></div><footer>${closedMode ? `خروج ${esc(item.exit_date_display)}` : `ورود ${esc(item.entry_date_display)}`}<div><label class="trade-select-control"><input type="checkbox" data-underlying-select="${esc(item.id)}" aria-label="انتخاب دارایی پایه ${esc(item.asset)}" /><span>انتخاب</span></label>${actions}</div></footer></article>`;
  };
  const groupedOpen=[...open.reduce((groups,item)=>{
    const key=`${item.market}|${faNorm(item.asset).replace(/[\u200c_\s]+/g,"")}`;
    if(!groups.has(key)) groups.set(key,[]);
    groups.get(key).push(item);
    return groups;
  },new Map()).values()];
  $("underlyingOpenCount").textContent = `${num(groupedOpen.length)} دارایی · ${num(open.length)} خرید`;
  const groupedCard=(lots)=>{
    const first=lots[0];
    const totalQuantity=lots.reduce((sum,item)=>sum+Number(item.available_quantity||0),0);
    const weightedEntry=totalQuantity>0?lots.reduce((sum,item)=>sum+Number(item.entry_price||0)*Number(item.available_quantity||0),0)/totalQuantity:null;
    const invested=lots.reduce((sum,item)=>sum+Number(item.invested_capital||0),0);
    const valued=lots.filter((item)=>item.profit!=null);
    const totalProfit=valued.length===lots.length?lots.reduce((sum,item)=>sum+Number(item.profit||0),0):null;
    const profitPercent=totalProfit!=null&&invested>0?totalProfit/invested*100:null;
    const capitalDays=lots.reduce((sum,item)=>sum+Number(item.invested_capital||0)*Math.max(1,Number(item.holding_days||1)),0);
    const profitYoy=totalProfit!=null&&capitalDays>0?totalProfit*365/capitalDays*100:null;
    const allocated=lots.reduce((sum,item)=>sum+Number(item.allocated_quantity||0),0);
    const current=lots.find((item)=>item.current_price!=null)?.current_price??null;
    const methods=[...new Set(lots.map((item)=>item.acquisition_method==="exercise"?"اعمال اختیار خرید":"خرید مستقیم"))];
    const lotRows=lots.slice().sort((a,b)=>String(b.entry_date||"").localeCompare(String(a.entry_date||""))).map((item,index)=>{
      const method=item.acquisition_method==="exercise"?"خرید از طریق اعمال اختیار":"خرید مستقیم";
      const source=item.source_option_symbol?` · قرارداد ${esc(item.source_option_symbol)}`:"";
      return `<article class="underlying-lot" data-underlying-id="${esc(item.id)}"><header><strong>بخش ${num(index+1)} · ${method}</strong><span>${qty(item.available_quantity)} واحد</span></header><div><span>تاریخ خرید <b>${esc(item.entry_date_display)}</b></span><span>قیمت ورود <b>${num(item.entry_price,2)}</b></span><span>قیمت فعلی <b>${num(item.current_price,2)}</b></span><span>سود این بخش <b class="${profitTone(item.profit)}">${signed(item.profit,0)} (${signed(item.profit_percent)}٪)</b></span></div>${source?`<p>${source.slice(3)}</p>`:""}<footer><label class="trade-select-control"><input type="checkbox" data-underlying-select="${esc(item.id)}" aria-label="انتخاب خرید ${esc(item.asset)}" /><span>انتخاب</span></label><button class="trade-action" type="button" data-underlying-action="sell" data-position-id="${esc(item.id)}">ثبت فروش</button><button class="trade-action" type="button" data-underlying-action="edit" data-position-id="${esc(item.id)}">ویرایش</button><button class="trade-action danger" type="button" data-underlying-action="delete" data-position-id="${esc(item.id)}">حذف</button></footer></article>`;
    }).join("");
    return `<article class="underlying-card underlying-group-card"><header><div><strong>${esc(first.asset)}</strong><small>${marketLabel(first.market)} · ${methods.join(" و ")} · ${num(lots.length)} بخش خرید</small></div><span>${qty(totalQuantity)} واحد</span></header><div><section><span>میانگین وزنی قیمت ورود</span><b>${num(weightedEntry,2)}</b></section><section><span>قیمت فعلی</span><b>${num(current,2)}</b>${lots.some((item)=>item.last_is_previous_day)?'<small class="previous-price-tag">قیمت روز قبل</small>':""}</section><section><span>سود شناور مجموع</span><b class="${profitTone(totalProfit)}">${signed(totalProfit,0)}</b><small class="${profitTone(profitPercent)}">${signed(profitPercent)}٪ · سالانه ${signed(profitYoy)}٪</small></section><section><span>تخصیص به کاوردکال</span><b>${qty(allocated)} واحد</b></section></div><details class="underlying-lots"><summary>بیشتر · جزئیات ${num(lots.length)} خرید</summary><div>${lotRows}</div></details></article>`;
  };
  $("underlyingList").innerHTML = groupedOpen.length ? groupedOpen.map(groupedCard).join("") : '<div class="trades-empty">دارایی پایه آزادی ثبت نشده است؛ دارایی متصل به کاوردکال عمداً در این فهرست نشان داده نمی‌شود.</div>';
  $("closedUnderlyingList").innerHTML = closed.length ? closed.map((item)=>card(item,true)).join("") : '<div class="trades-empty">فروش دارایی پایه‌ای ثبت نشده است.</div>';
  const datalist = $("underlyingAssetOptions");
  if (datalist) datalist.innerHTML = [...new Set(state.underlyingQuotes.map((item)=>item.asset).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"fa")).map((asset)=>`<option value="${esc(asset)}"></option>`).join("");
  syncUnderlyingSelectionUi();
}

function renderClosedCoveredEvaluation(summary = {}) {
  const host = $("closedCoveredEvaluation");
  if (!host) return;
  const data = summary.covered_call || {};
  if (!Number(data.count)) {
    host.innerHTML = '<div class="trades-empty">برای ارزیابی تجمیعی کاوردکال، معامله بسته‌شده‌ای ثبت نشده است.</div>';
    return;
  }
  const chartItems = [
    {label:"بازده سهم",value:Number(data.share_return||0),className:"share",operator:"+"},
    {label:"درآمد خالص آپشن",value:Number(data.option_income||0),className:"option",operator:"−"},
    {label:"سود ازدست‌رفته از سقف قیمت",value:-Math.abs(Number(data.foregone_upside||0)),className:"cap",operator:"="},
  ];
  const maxValue = Math.max(1,...chartItems.map(item=>Math.abs(item.value)),Math.abs(Number(data.reconstructed_return||0)));
  const bars = chartItems.map((item,index)=>`<article class="covered-equation-item ${item.className}"><header><span>${esc(item.label)}</span><b class="${profitTone(item.value)}">${signed(item.value,0)}</b></header><div class="covered-equation-track"><i style="--bar:${Math.abs(item.value)/maxValue*100}%"></i></div><em>${item.operator}</em></article>`).join("");
  const metric = (label,value,note="",tone="") => `<div><span>${label}</span><strong class="${tone}">${value}</strong>${note?`<small>${note}</small>`:""}</div>`;
  host.innerHTML = `<header><div><small>فقط معاملات بسته‌شده کاوردکال</small><h2>ارزیابی کل استراتژی کاوردکال</h2><p>درآمد اختیار در کنار بازده سهم و هزینه محدودشدن رشد، جداگانه نمایش داده شده است.</p></div><span>${num(data.count)} دوره</span></header><div class="closed-covered-kpis">${metric("مجموع پریمیوم دریافتی",num(data.total_premium_received,0),"پریمیوم ناخالص ورود")}${metric("درصد پریمیوم حفظ‌شده",formatPercent(data.premium_retained_percent),"درآمد خالص اختیار ÷ پریمیوم دریافتی",valueTone(data.premium_retained_percent))}${metric("نرخ اعمال‌شدن",formatPercent(data.assignment_rate_percent),"تعداد اعمال ÷ معاملات کاوردکال")}${metric("نرخ معاملات رول‌شده",formatPercent(data.rolled_rate_percent),"فقط رول‌های ثبت‌شده")}${metric("میانگین بازده هر دوره",formatPercent(data.average_period_return_percent),"میانگین ساده بازده دوره‌ها",valueTone(data.average_period_return_percent))}${metric("میانگین مدت نگهداری",`${num(data.average_holding_days,1)} روز`,"ورود تا خروج")}${metric("کاوردکال در برابر نگهداری سهم",signed(data.covered_vs_holding,0),`کاوردکال ${signed(data.covered_return,0)} · سهم ${signed(data.holding_return,0)}`,profitTone(data.covered_vs_holding))}${metric("کاهش افت نسبت به نگهداری سهم",data.drawdown_reduction_percent==null?"داده کافی نیست":`${signed(data.drawdown_reduction,0)} · ${signed(data.drawdown_reduction_percent,1)}٪`,"تقریب بر اساس دوره‌های بسته زیان‌ده؛ نه MDD روزانه",profitTone(data.drawdown_reduction))}</div><section class="covered-equation-chart"><header><div><small>معادله عملکرد واقعی</small><h3>بازده سهم + درآمد آپشن − سود ازدست‌رفته</h3></div><strong class="${profitTone(data.reconstructed_return)}">${signed(data.reconstructed_return,0)}</strong></header><div class="covered-equation-grid">${bars}<article class="covered-equation-total"><span>بازده بازسازی‌شده کاوردکال</span><strong class="${profitTone(data.reconstructed_return)}">${signed(data.reconstructed_return,0)}</strong><small>برای کنترل: سود ثبت‌شده ${signed(data.covered_return,0)}</small></article></div><p>«کاهش افت» با داده ورود و خروج دوره‌های بسته محاسبه شده است. برای محاسبه افت سرمایه روزانه (MDD) به مسیر قیمت روزانه هر موقعیت نیاز است.</p></section>`;
}

function longTradeProfitComparison(item = {}, {title = "مقایسه سود تا امروز"} = {}) {
  const rows = [
    {label: "سود تا امروز از تغییر پرمیوم", value: item.long_offset_profit, percent: item.long_offset_profit_percent, tone: "premium"},
    {label: "سود تا امروز بر اساس اعمال", value: item.long_exercise_profit, percent: item.long_exercise_profit_percent, tone: "exercise"},
  ];
  const availableValues = rows.map((row) => row.value).filter((value) => value != null && Number.isFinite(Number(value))).map(Number);
  const maxAbsolute = Math.max(1, ...availableValues.map(Math.abs));
  const rowHtml = rows.map((row) => {
    const available = row.value != null && Number.isFinite(Number(row.value));
    const value = available ? Number(row.value) : null;
    const percent = row.percent != null && Number.isFinite(Number(row.percent)) ? Number(row.percent) : null;
    const width = available ? Math.abs(value) / maxAbsolute * 50 : 0;
    const position = value == null || value >= 0 ? `left:50%;width:${width}%` : `right:50%;width:${width}%`;
    return `<div class="long-profit-row"><div><span>${esc(row.label)}</span><div class="long-profit-value"><strong class="${profitTone(value)}">${signed(value, 0)}</strong><small class="${profitTone(percent)}">${signed(percent, 2)}٪</small></div></div><div class="long-profit-track"><i class="${row.tone} ${value != null && value < 0 ? "negative" : "positive"}" style="${position}"></i><b aria-hidden="true"></b></div></div>`;
  }).join("");
  return `<section class="long-profit-comparison trade-profit-comparison" aria-label="مقایسه سود فعلی ${esc(item.option_symbol || "اختیار خرید")}"><header><div><small>همین معامله · محور صفر مشترک</small><h4>${esc(title)}</h4></div><span>مبالغ به ریال</span></header><div class="long-profit-rows">${rowHtml}</div></section>`;
}

function compactChartValue(value) {
  const absolute = Math.abs(Number(value) || 0);
  if (absolute >= 1_000_000_000) return `${num(value / 1_000_000_000, 1)} میلیارد`;
  if (absolute >= 1_000_000) return `${num(value / 1_000_000, 1)} میلیون`;
  if (absolute >= 1_000) return `${num(value / 1_000, 1)} هزار`;
  return num(value, 0);
}

function renderAccountGrowth(growth = {}, generatedAt = null) {
  const total = Number(growth.total_profit || 0);
  const realized = Number(growth.realized_profit || 0);
  const openMark = Number(growth.open_mark_profit || 0);
  const capital = Number(growth.initial_capital || 0);
  const equity = Number(growth.current_equity || capital + total);
  const setSignedMetric = (id, value, suffix = "") => {
    const element = $(id);
    if (!element) return;
    element.textContent = `${signed(value, suffix ? 2 : 0)}${suffix}`;
    element.className = profitTone(value);
  };
  $("accountCurrentEquity").textContent = num(equity, 0);
  setSignedMetric("accountGrowthRealized", realized);
  setSignedMetric("accountGrowthOpen", openMark);
  setSignedMetric("accountGrowthReturn", Number(growth.return_percent || 0), "٪");
  setSignedMetric("accountAverageMonthly", growth.average_monthly_return_percent, "٪");
  setSignedMetric("accountAverageAnnual", growth.average_annual_return_percent, "٪");
  $("accountGrowthCapital").textContent = `${growth.initial_capital_source === "user" ? "سرمایه ثبت‌شده" : "سرمایه برآوردی"} ${num(capital, 0)}`;
  $("accountGrowthTotalNote").textContent = `سود و زیان فعلی ${signed(total, 0)}`;
  $("accountTrackingDays").textContent = `${num(growth.tracking_days || 0)} روز از شروع ثبت معاملات`;
  $("accountGrowthOpenNote").textContent = `${num(growth.valued_open_count || 0)} از ${num(growth.open_count || 0)} معامله باز قیمت‌گذاری‌شده`;
  $("accountGrowthUpdated").textContent = generatedAt ? `ارزش‌گذاری ${formatDate(generatedAt)}` : "—";
  $("accountGrowthInvested").textContent = num(growth.invested_capital || 0, 0);
  $("accountGrowthCounts").textContent = `${num(growth.open_count || 0)} باز · ${num(growth.closed_count || 0)} بسته`;
  const holding = (value) => value == null ? "—" : `${num(value, 1)} روز`;
  $("accountAverageHolding").textContent = holding(growth.average_holding_days);
  $("accountAverageCoveredHolding").textContent = holding(growth.average_holding_days_covered_call);
  $("accountAverageLongHolding").textContent = holding(growth.average_holding_days_long_call);
  $("accountAverageUnderlyingHolding").textContent = holding(growth.average_holding_days_underlying);
  const mdd = Number(growth.max_drawdown_percent || 0);
  $("accountMddLabel").textContent = growth.drawdown_scope_label || "افت سرمایه در نقاط ثبت‑شده";
  $("accountMddCard").classList.toggle("hidden", !(mdd > 0));
  $("accountMdd").textContent = mdd > 0 ? `−${num(mdd, 2)}٪` : "—";
  $("accountMddNote").textContent = mdd > 0
    ? `${num(growth.max_drawdown_amount || 0, 0)} افت · ${solarDate(growth.max_drawdown_peak_date)} تا ${solarDate(growth.max_drawdown_trough_date)} · ${growth.drawdown_limitation || "افت روزانه بین نقاط ثبت‌شده محاسبه نشده است"}` : "—";
  const capitalInput = $("accountCapitalForm").elements.initial_capital;
  const cashInput = $("accountCapitalForm").elements.cash_balance;
  if (document.activeElement !== capitalInput) capitalInput.value = state.account?.initial_capital ?? "";
  if (document.activeElement !== cashInput) cashInput.value = state.account?.cash_balance ?? "";
  $("accountCapitalSource").textContent = growth.initial_capital_source === "user"
    ? `سرمایه ثبت‌شده مبنای نمودار است. سرمایه برآوردی از معاملات: ${num(growth.inferred_initial_capital || 0, 0)}`
    : `سرمایه اولیه از بیشترین نقدینگی هم‌زمان درگیر برآورد شده است: ${num(growth.inferred_initial_capital || 0, 0)}`;

  const tradeCount = Number(growth.open_count || 0) + Number(growth.closed_count || 0);
  const points = Array.isArray(growth.points) ? growth.points.filter((point)=>point?.date && Number.isFinite(Number(point.value))) : [];
  const firstPoint = points[0], lastPoint = points.at(-1);
  $("accountGrowthPeriod").textContent = firstPoint && lastPoint
    ? `${solarDate(firstPoint.date)} تا ${solarDate(lastPoint.date)}` : "—";
  $("accountGrowthPointCount").textContent = `${num(points.length)} نقطه · ${num(tradeCount)} معامله`;
  const direction = total > 0 ? "رشد" : total < 0 ? "کاهش" : "بدون تغییر";
  $("accountGrowthTrendSummary").textContent = tradeCount
    ? `حساب در ${num(growth.tracking_days || 0)} روز، ${direction} ${signed(Math.abs(Number(growth.return_percent || 0)), 2).replace("+", "")}٪ داشته و ارزش فعلی آن ${num(equity, 0)} است؛ ${signed(realized, 0)} قطعی و ${signed(openMark, 0)} مربوط به معاملات باز است.`
    : "برای محاسبه روند، ابتدا یک معامله ثبت کنید.";
  const eventBody = $("accountGrowthEvents");
  if (eventBody) {
    eventBody.innerHTML = points.length ? points.slice().reverse().map((point) => {
      const labels = [];
      if (Number(point.entries || 0) > 0) labels.push(`${num(point.entries)} ورود`);
      if (Number(point.exits || 0) > 0) labels.push(`${num(point.exits)} خروج`);
      if (point.is_current) labels.push("ارزش‌گذاری امروز");
      if (!labels.length) labels.push("به‌روزرسانی حساب");
      return `<tr${point.is_current ? ' class="current"' : ""}><td>${esc(solarDate(point.date))}</td><td>${esc(labels.join(" · "))}</td><td class="${profitTone(point.realized_delta)}">${signed(point.realized_delta || 0, 0)}</td><td>${num(point.equity ?? (capital + Number(point.value || 0)), 0)}</td></tr>`;
    }).join("") : '<tr><td colspan="4">هنوز رویدادی ثبت نشده است.</td></tr>';
  }
  if (!tradeCount || !points.length) {
    $("accountGrowthChart").innerHTML = '<div class="trades-empty">برای نمایش نمودار، ابتدا یک معامله ثبت کنید.</div>';
    return;
  }

  const width = 1200, height = 240, padLeft = 120, padRight = 30, padTop = 24, padBottom = 40;
  const timestamps = points.map((point)=>Date.parse(`${point.date}T12:00:00Z`));
  const validTimes = timestamps.filter(Number.isFinite);
  const minTime = Math.min(...validTimes), maxTime = Math.max(...validTimes);
  const pointEquity = (point) => Number(point.equity ?? (capital + Number(point.value || 0)));
  const values = points.map(pointEquity).concat([capital]);
  let minValue = Math.min(...values), maxValue = Math.max(...values);
  const rawRange = maxValue - minValue;
  const padding = rawRange > 0 ? rawRange * .12 : Math.max(1, Math.abs(maxValue) * .12);
  minValue -= padding;
  maxValue += padding;
  const range = maxValue - minValue || 1;
  const x = (timestamp, index) => maxTime === minTime ? (padLeft + width - padRight) / 2 : padLeft + (timestamp - minTime) / (maxTime - minTime) * (width - padLeft - padRight);
  const y = (value) => padTop + (maxValue - value) / range * (height - padTop - padBottom);
  const coords = points.map((point,index)=>({point,x:x(timestamps[index],index),y:y(pointEquity(point))}));
  const stepPath = coords.reduce((path,current,index)=>{
    if (!index) return `M ${current.x.toFixed(2)} ${current.y.toFixed(2)}`;
    return `${path} H ${current.x.toFixed(2)} V ${current.y.toFixed(2)}`;
  },"");
  const tickCount = 4;
  const grid = Array.from({length:tickCount+1},(_,index)=>{
    const value = maxValue - range * index / tickCount;
    const yy = y(value);
    return `<line x1="${padLeft}" y1="${yy}" x2="${width-padRight}" y2="${yy}" class="account-grid"/><text x="${padLeft-10}" y="${yy+4}" text-anchor="end">${esc(compactChartValue(value))}</text>`;
  }).join("");
  const initialY = y(capital);
  const areaPath = coords.length
    ? `${stepPath} L ${coords.at(-1).x.toFixed(2)} ${initialY.toFixed(2)} L ${coords[0].x.toFixed(2)} ${initialY.toFixed(2)} Z`
    : "";
  const markers = coords.map(({point,x:cx,y:cy},index)=>{
    const pointValue = pointEquity(point);
    const title = `${solarDate(point.date)} · ارزش حساب ${num(pointValue,0)} · سود و زیان ${signed(point.value,0)} · ${num(point.entries || 0)} ورود · ${num(point.exits || 0)} خروج${point.is_current ? " · شامل ارزش‌گذاری معاملات باز" : ""}`;
    return `<g class="account-growth-point" tabindex="0" role="img" aria-label="${esc(title)}"><circle cx="${cx}" cy="${cy}" r="12" class="account-point-hit"/><circle cx="${cx}" cy="${cy}" r="${point.is_current ? 6 : 4}" class="${point.is_current ? "account-current-point" : "account-event-point"}"><title>${esc(title)}</title></circle></g>${index === coords.length-1 ? `<text x="${Math.max(padLeft+64,cx-8)}" y="${Math.max(padTop+14,cy-14)}" text-anchor="end" class="account-last-label">${esc(num(pointValue,0))}</text>` : ""}`;
  }).join("");
  $("accountGrowthChart").innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="group" aria-label="روند ارزش حساب بر اساس معاملات ثبت‌شده"><title>${esc($("accountGrowthTrendSummary").textContent)}</title><g>${grid}</g><text x="${padLeft}" y="14" text-anchor="start" class="account-axis-unit">ارزش حساب · ریال</text><line x1="${padLeft}" y1="${initialY}" x2="${width-padRight}" y2="${initialY}" class="account-zero-line"><title>سرمایه اولیه ${num(capital,0)}</title></line><path d="${areaPath}" class="account-growth-area ${total < 0 ? "negative" : "positive"}"/><path d="${stepPath}" class="account-growth-line ${total < 0 ? "negative" : "positive"}"/>${markers}<text x="${padLeft}" y="${height-14}" text-anchor="start">${esc(solarDate(firstPoint.date))}</text><text x="${width-padRight}" y="${height-14}" text-anchor="end">${esc(solarDate(lastPoint.date))}</text></svg>`;
}

function renderProfitRecognition(summary = {}, accountGrowth = {}) {
  const content = $("profitRecognitionContent");
  if (!content) return;
  const tradeCount = Number(summary.trade_count || 0);
  $("profitRecognitionBadge").textContent = `${num(tradeCount)} معامله`;
  if (!tradeCount) {
    content.innerHTML = '<div class="trades-empty">هنوز معامله‌ای برای محاسبه ثبت نشده است.</div>';
    return;
  }
  const mode = state.profitMode;
  const modeLabel = mode === "with_underlying" ? "با تغییرات دارایی پایه" : "فقط سود و زیان اختیار";
  const combined = summary.combined || {};
  const covered = summary.covered_call || {};
  const longCall = summary.long_call || {};
  const currentProfit = combined[`${mode}_profit`];
  const current = combined[`${mode}_scaled`] || {};
  const finalScale = summary.final_scaled || {};
  const liquidationScale = summary.all_offset_and_sell_scaled || {};
  const rate = (value) => value == null ? "—" : `${signed(value)}٪`;
  const rateClass = (value) => value == null ? "" : profitTone(value);
  const capitalSource = accountGrowth.initial_capital_source === "user" ? "سرمایه ثبت‌شده حساب" : "سرمایه برآوردی از بیشترین نقدینگی هم‌زمان";
  const quoteAmount = (value, previous = false) => value == null ? "—" : `${num(value,2)}${previous ? '<em class="previous-price-tag">قیمت روز قبل</em>' : ""}`;
  const quoteStack = (bid, ask, last, previous) => `<div class="recognition-quote-stack"><span>خرید <b>${quoteAmount(bid)}</b></span><span>فروش <b>${quoteAmount(ask)}</b></span><span>آخرین <b>${quoteAmount(last,previous)}</b></span></div>`;
  const detailRows = (summary.details || []).map((item) => {
    const closed = item.status === "closed";
    const isLong = item.strategy_type === "long_call";
    const selected = item[`${mode}_profit`];
    const selectedBasis = mode === "with_underlying" ? item.underlying_basis : item.option_basis;
    const gap = isLong && item.exercise_cost_gap != null ? `<small>اعمال + پرمیوم − پایه: ${signed(item.exercise_cost_gap,0)}</small>` : "";
    const selectedPercent = item.invested_capital > 0 && selected != null ? Number(selected) / Number(item.invested_capital) * 100 : null;
    return `<tr><td><strong>${esc(item.asset)}</strong><small>${marketLabel(item.market)}</small></td><td><span class="symbol">${esc(item.option_symbol)}</span><small>${isLong ? "خرید اختیار" : "کاوردکال"}</small></td><td><span class="profit-recognition-status ${closed ? "closed" : "open"}">${closed ? "بسته" : "باز"}</span></td><td>${quoteStack(item.base_best_bid,item.base_best_ask,item.base_last_trade,item.base_last_is_previous_day)}</td><td>${quoteStack(item.option_best_bid,item.option_best_ask,item.option_last_trade,item.option_last_is_previous_day)}</td><td><strong class="${profitTone(selected)}">${signed(selected, 0)}</strong><small class="${profitTone(selectedPercent)}">${rate(selectedPercent)}</small><small>${esc(selectedBasis)}</small>${gap}</td><td><strong class="${profitTone(item.all_offset_and_sell_profit)}">${isLong ? "—" : signed(item.all_offset_and_sell_profit,0)}</strong><small class="${profitTone(item.all_offset_and_sell_percent)}">${isLong ? "—" : rate(item.all_offset_and_sell_percent)}</small></td><td><strong class="${profitTone(item.final_profit)}">${signed(item.final_profit, 0)}</strong><small>${esc(item.final_basis)}</small></td><td>${closed ? "—" : `${num(item.remaining_days)} روز`}<small>${esc(item.expiry_display || solarDate(item.expiry))}</small></td></tr>`;
  }).join("");
  const positions = (summary.underlying_positions || []).map((item) => `<article class="underlying-position"><header><div><strong>${esc(item.asset)}</strong><small>${marketLabel(item.market)} · ${esc(item.source_label)}</small></div><span>${qty(item.quantity)} واحد</span></header><div><span>قیمت ورود/اعمال <b>${num(item.entry_price,2)}</b></span><span>قیمت جاری <b>${num(item.current_price,2)}</b></span></div><footer>سود تغییرات پس از مبنای ثبت <strong class="${profitTone(item.profit)}">${signed(item.profit,0)}</strong></footer></article>`).join("");
  const strategyCard = (title, data, optionLabel, baseLabel) => `<article class="profit-recognition-strategy"><header><h3>${title}</h3><span>${modeLabel}</span></header><strong class="${profitTone(data[`${mode}_profit`])}">${signed(data[`${mode}_profit`],0)}</strong><div><span>${optionLabel}<b class="${profitTone(data.option_only_profit)}">${signed(data.option_only_profit,0)}</b></span><span>${baseLabel}<b class="${profitTone(data.with_underlying_profit)}">${signed(data.with_underlying_profit,0)}</b></span></div></article>`;
  content.innerHTML = `<div class="profit-recognition-kpis"><article class="profit-recognition-card current"><header><div><small>${modeLabel}</small><h3>سود قابل‌شناسایی تا امروز</h3></div><span>${num(summary.elapsed_days)} روز از اولین ورود</span></header><strong class="profit-recognition-amount ${profitTone(currentProfit)}">${signed(currentProfit, 0)}</strong><div class="profit-recognition-rates"><div><span>بازده دوره</span><b class="${rateClass(current.return_percent)}">${rate(current.return_percent)}</b></div><div><span>معادل ماهانه</span><b class="${rateClass(current.monthly_return_percent)}">${rate(current.monthly_return_percent)}</b></div><div><span>معادل سالانه</span><b class="${rateClass(current.annual_return_percent)}">${rate(current.annual_return_percent)}</b></div></div><footer><span>کاوردکال: <b>${signed(covered[`${mode}_profit`], 0)}</b></span><span>خرید اختیار: <b>${signed(longCall[`${mode}_profit`], 0)}</b></span></footer></article><article class="profit-recognition-card final"><header><div><small>سود قطعی بسته‌ها + سود انتظاری کاوردکال‌های باز</small><h3>سود تا آخرین کاوردکال</h3></div><span class="last-days">${num(summary.remaining_days_to_last)} روز مانده</span></header><strong class="profit-recognition-amount ${profitTone(summary.final_profit)}">${signed(summary.final_profit, 0)}</strong><div class="profit-recognition-rates"><div><span>بازده تا آخرین سررسید</span><b class="${rateClass(finalScale.return_percent)}">${rate(finalScale.return_percent)}</b></div><div><span>معادل ماهانه</span><b class="${rateClass(finalScale.monthly_return_percent)}">${rate(finalScale.monthly_return_percent)}</b></div><div><span>معادل سالانه</span><b class="${rateClass(finalScale.annual_return_percent)}">${rate(finalScale.annual_return_percent)}</b></div></div><footer><span>آخرین سررسید: <b>${esc(solarDate(summary.final_date))}</b></span><span>سود انتظاری بازها: <b>${signed(summary.open_expected_profit, 0)}</b></span></footer></article></div><section class="profit-recognition-strategies">${strategyCard("کاوردکال",covered,"فقط اختیار","اختیار + تغییرات پایه")}${strategyCard("خرید اختیار خرید",longCall,"اختلاف پرمیوم","اعمال امروز + پایه‌های دریافتی")}</section><section class="profit-recognition-context"><div><span>سرمایه مبنای بازده</span><strong>${num(summary.capital, 0)}</strong><small>${esc(capitalSource)}</small></div><div><span>معاملات لحاظ‌شده</span><strong>${num(summary.open_count)} باز · ${num(summary.closed_count)} بسته</strong><small>${num(summary.covered_trade_count)} کاوردکال · ${num(summary.long_trade_count)} خرید اختیار</small></div><div><span>تعریف اعمال امروز</span><strong>پایه − (اعمال + پرمیوم)</strong><small>در جدول، «اعمال + پرمیوم − پایه» نیز برای کنترل عدد نمایش داده می‌شود.</small></div></section><section class="underlying-tracker"><header><div><small>رصد دارایی پایه</small><h3>سهام و دارایی‌های پایه تحت مالکیت</h3></div><span>${num((summary.underlying_positions || []).length)} موقعیت</span></header><div class="underlying-position-grid">${positions || '<div class="trades-empty">دارایی پایه‌ای از کاوردکال باز یا اعمال اختیار ثبت نشده است.</div>'}</div></section><section class="profit-recognition-details"><header><div><small>ردیابی اجزای محاسبه</small><h3>سهم هر معامله در سود شناسایی‌شده</h3></div><span>${modeLabel}</span></header><div class="profit-recognition-table-wrap"><table><thead><tr><th>دارایی پایه</th><th>اختیار و استراتژی</th><th>وضعیت</th><th>سود منتخب امروز</th><th>سود نهایی/اعمال</th><th>سررسید</th></tr></thead><tbody>${detailRows}</tbody></table></div></section><p class="profit-recognition-note">سود لحظه‌ای خرید اختیار برابر اختلاف پرمیوم جاری و پرمیوم ورود است. سود اعمال امروز برابر قیمت پایه منهای مجموع قیمت اعمال و پرمیوم پرداختی است. بازده ماهانه و سالانه به‌صورت خطی مقیاس شده‌اند.</p>`;
  const detailHead = content.querySelector(".profit-recognition-details thead");
  if (detailHead) detailHead.innerHTML = "<tr><th>دارایی پایه</th><th>اختیار و استراتژی</th><th>وضعیت</th><th>قیمت‌های دارایی پایه</th><th>قیمت‌های اختیار</th><th>سود منتخب امروز</th><th>آفست همه + فروش پایه</th><th>سود نهایی/اعمال</th><th>سررسید</th></tr>";
  const kpiGrid = content.querySelector(".profit-recognition-kpis");
  if (kpiGrid) kpiGrid.insertAdjacentHTML("beforeend", `<article class="profit-recognition-card liquidation"><header><div><small>خروج کامل با قیمت قابل اجرا</small><h3>آفست همه قراردادها + فروش همه پایه‌ها</h3></div><span>${num(summary.open_all_offset_and_sell_count)} موقعیت</span></header><strong class="profit-recognition-amount ${profitTone(summary.all_offset_and_sell_profit)}">${signed(summary.all_offset_and_sell_profit,0)}</strong><div class="profit-recognition-rates"><div><span>بازده دوره</span><b class="${rateClass(liquidationScale.return_percent)}">${rate(liquidationScale.return_percent)}</b></div><div><span>معادل ماهانه</span><b class="${rateClass(liquidationScale.monthly_return_percent)}">${rate(liquidationScale.monthly_return_percent)}</b></div><div><span>معادل سالانه</span><b class="${rateClass(liquidationScale.annual_return_percent)}">${rate(liquidationScale.annual_return_percent)}</b></div></div><footer><span>اختیار: بهترین پیشنهاد فروش</span><span>پایه: بهترین پیشنهاد خرید</span></footer></article>`);
}

function tradeTimelineMarkup(item) {
  const closed = item.status === "closed";
  const rawProgress = closed && Number(item.entry_days) > 0
    ? Number(item.invested_days || 0) / Number(item.entry_days) * 100
    : Number(item.strategy_progress_percent) || 0;
  const progress = Math.max(0,Math.min(100,rawProgress));
  const elapsed = closed ? item.invested_days : item.elapsed_days;
  const footer = closed
    ? `خروج ${esc(item.exit_date_display)} · ${num(item.invested_days)} روز نگهداری`
    : `${num(item.remaining_days)} روز باقی‌مانده · سررسید ${esc(item.expiry_display)}`;
  return `<div class="trade-timeline"><div><span>خط زمانی تا سررسید</span><b>${num(elapsed)} روز از ${num(item.entry_days)} روز</b></div><div class="trade-timeline-track" style="--timeline-progress:${progress}" role="progressbar" aria-label="پیشرفت زمانی استراتژی" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${num(progress,0)}"><i style="width:${progress}%"></i></div><small>${footer}</small></div>`;
}

function tradeItmTag(item) {
  const closed = item.status === "closed";
  const value = closed ? (item.exit_itm_percent ?? item.current_itm_percent) : item.current_itm_percent;
  const label = closed ? "ITM خروج" : "ITM فعلی";
  const tone = value == null ? "" : Number(value) >= 0 ? "profit-up" : "profit-down";
  return `<span class="compact-trade-itm ${tone}">${label} ${signed(value)}٪</span>`;
}

function coveredCallIndicators(item, {compact = false} = {}) {
  if ((item.strategy_type || "covered_call") !== "covered_call") return "";
  const statusLabels = {open:"باز",closed:"بسته",rolled:"رول‌شده",exercised:"اعمال‌شده"};
  const status = item.covered_position_status || (item.status === "closed" ? "closed" : "open");
  const probability = item.covered_assignment_probability;
  const probabilityText = probability == null ? "داده ناکافی" : `${num(probability,1)}٪`;
  const metrics = [
    ["پرمیوم خالص دریافتی", num(item.covered_net_premium_received,0), ""],
    ["بازده پرمیوم / سرمایه", `${signed(item.covered_premium_return_percent,2)}٪`, profitTone(item.covered_premium_return_percent)],
    ["بازده سالانه پرمیوم", `${signed(item.covered_premium_return_yoy,2)}٪`, profitTone(item.covered_premium_return_yoy)],
    ["فاصله سهم تا اعمال", strikeDistanceText(item.covered_strike_distance_percent), ""],
    ["نقطه سربه‌سر", num(item.covered_breakeven,2), ""],
    ["حداکثر سود معامله", num(item.covered_max_profit,0), profitTone(item.covered_max_profit)],
    ["پوشش نزول با پرمیوم", `${num(item.covered_downside_protection_percent,2)}٪`, ""],
    ["احتمال تقریبی اعمال", probabilityText, probability == null ? "" : Number(probability) >= 50 ? "profit-down" : ""],
    ["سود ازدست‌رفته از سقف رشد", num(item.covered_foregone_upside,0), Number(item.covered_foregone_upside) > 0 ? "profit-down" : ""],
  ];
  const visibleMetrics = compact ? metrics.slice(0,4) : metrics;
  const modelNote = item.covered_assignment_probability_estimated
    ? "نوسان ۳۵٪ برآوردی؛ قیمت بازار برای IV کافی نبوده است."
    : `نوسان ضمنی ${num(item.covered_assignment_probability_volatility,2)}٪.`;
  return `<section class="covered-position-indicators ${compact ? "compact" : ""}" aria-label="شاخص‌های موقعیت کاوردکال"><header><div><small>تحلیل همین موقعیت</small><h4>شاخص‌های اختصاصی کاوردکال</h4></div><span class="covered-position-state ${esc(status)}">${esc(statusLabels[status] || statusLabels.open)}</span></header><dl>${visibleMetrics.map(([label,value,tone])=>`<div><dt>${label}</dt><dd class="${tone}">${value}</dd></div>`).join("")}</dl>${compact ? `<button class="covered-indicators-hint" type="button" data-trade-detail="${esc(item.id)}">نمایش همه شاخص‌ها</button>` : `<p class="covered-assignment-model"><b>مدل احتمال اعمال:</b> ${esc(item.covered_assignment_probability_model || "Black–Scholes N(d2), q=0")}؛ احتمال ریسک‌خنثی اروپایی، نه پیش‌بینی قطعی. ${esc(modelNote)}</p>`}</section>`;
}

function baseClosedTag(item) {
  if (!item.base_is_closed) return "";
  const status = item.base_market_status && item.base_market_status !== "نامشخص"
    ? ` · ${item.base_market_status}` : "";
  return `<span class="trade-status base-closed">دارایی پایه بسته است${esc(status)}</span>`;
}

function renderOpenTradeSummaryCard(item) {
  const isLongCall = item.strategy_type === "long_call";
  const liquidationReview = !isLongCall
    && item.covered_liquidation_profit != null
    && item.covered_hold_profit != null
    && Number(item.covered_liquidation_profit) >= Number(item.covered_hold_profit);
  const primaryReturns = isLongCall
    ? `${compactDecisionReturnBox("فروش اختیار خرید",item.long_offset_profit,item.long_offset_profit_percent)}${compactDecisionReturnBox("اعمال اختیار خرید",item.long_exercise_profit,item.long_exercise_profit_percent)}`
    : `${compactDecisionReturnBox("نگهداری پوزیشن کاوردکال",item.covered_hold_profit,item.covered_hold_percent)}${compactDecisionReturnBox("آفست اختیار و فروش دارایی پایه",item.covered_liquidation_profit,item.covered_liquidation_percent,{review:liquidationReview})}`;
  return `<article class="trade-card compact-trade-card ${isLongCall ? "long" : "covered"}" data-trade-id="${esc(item.id)}"><header class="compact-trade-header"><strong class="symbol">${esc(item.option_symbol)}</strong><div class="compact-trade-tags">${baseClosedTag(item)}${tradeItmTag(item)}</div></header>${tradeTimelineMarkup(item)}<div class="trade-returns compact-primary-returns ${isLongCall ? "long-call" : ""}">${primaryReturns}</div><footer><div class="trade-actions"><button class="trade-action detail" type="button" data-trade-detail="${esc(item.id)}">بیشتر</button><button class="trade-action" type="button" data-trade-action="edit" data-trade-id="${esc(item.id)}">ویرایش</button><button class="trade-action" type="button" data-trade-action="close" data-trade-id="${esc(item.id)}">ثبت خروج</button></div></footer></article>`;
}

function renderClosedTradeSummaryCard(item) {
  const isLongCall = item.strategy_type === "long_call";
  const primaryReturn = compactDecisionReturnBox("سود یا زیان قطعی",item.realized_profit,item.realized_profit_percent);
  return `<article class="trade-card compact-trade-card closed-summary-card ${isLongCall ? "long" : "covered"}" data-trade-id="${esc(item.id)}"><header class="compact-trade-header"><strong class="symbol">${esc(item.option_symbol)}</strong>${tradeItmTag(item)}</header>${tradeTimelineMarkup(item)}<div class="trade-returns compact-primary-returns single">${primaryReturn}</div><footer><div class="trade-actions"><button class="trade-action detail" type="button" data-trade-detail="${esc(item.id)}">بیشتر</button><button class="trade-action" type="button" data-trade-action="close" data-trade-id="${esc(item.id)}">ویرایش خروج</button><button class="trade-action danger" type="button" data-trade-action="delete" data-trade-id="${esc(item.id)}">حذف</button></div></footer></article>`;
}

function coveredTradeAnalysisContent(item,{actions,realizedResult,additionalReturns,fulfillmentChart,capitalShare}) {
  const closed=item.status==="closed";
  const entryBase=Number(item.entry_base_price),currentBase=Number(closed?(item.exit_base_price??item.current_base_price):item.current_base_price),strike=Number(item.strike),entryPremium=Number(item.entry_premium);
  const units=Math.max(1,Number(item.underlying_units||item.quantity||1));
  const netPremiumTotal=Number(item.covered_net_premium_received),netPremiumPerUnit=Number.isFinite(netPremiumTotal)?netPremiumTotal/units:entryPremium;
  const breakeven=Number.isFinite(Number(item.covered_breakeven))?Number(item.covered_breakeven):entryBase-netPremiumPerUnit;
  const maxProfitTotal=Number(item.covered_max_profit),maxProfitPerUnit=Number.isFinite(maxProfitTotal)?maxProfitTotal/units:Math.max(0,strike-entryBase+netPremiumPerUnit);
  const metric={base:currentBase,costBase:entryBase,strike,netPremium:netPremiumPerUnit,breakeven,maxProfit:maxProfitPerUnit,downsideProtection:Number(item.covered_downside_protection_percent),strikeDistance:Number(item.covered_strike_distance_percent),assignmentProbability:item.covered_assignment_probability==null?null:Number(item.covered_assignment_probability),volatility:Number(item.covered_assignment_probability_volatility),estimated:Boolean(item.covered_assignment_probability_estimated),model:item.covered_assignment_probability_model||"Black–Scholes N(d2), q=0"};
  const fmt=(v,d=2,s="")=>analysisValue(v,d,s),tone=v=>Number(v)<0?"negative":Number(v)>0?"positive":"";
  const invested=Number(item.invested_capital),maxReturn=invested>0&&Number.isFinite(maxProfitTotal)?maxProfitTotal/invested*100:null;
  const statusLabels={open:"باز",closed:"بسته",rolled:"رول‌شده",exercised:"اعمال‌شده"};
  const status=item.covered_position_status||(closed?"closed":"open");
  const expiry=`${item.expiry_display||"—"} — ${num(closed?item.invested_days:item.remaining_days)} ${closed?"روز نگهداری":"روز مانده"}`;
  const currentOption=Number(item.current_option_exit_price),premiumChange=Number(item.premium_price_change_percent);
  const fairGap=Number.isFinite(currentOption)&&entryPremium>0?(currentOption-entryPremium)/entryPremium*100:null;
  const assignmentModel=item.covered_assignment_probability_estimated?"مدل با نوسان مرجع ۳۵٪":"مدل با نوسان ضمنی ثبت‌شده";
  const baseChange=Number(item.covered_base_change_profit??item.base_profit),optionChange=Number(item.covered_option_change_profit??item.option_profit),combinedChange=Number(item.covered_combined_change_profit??item.covered_liquidation_profit);
  const foregoneFromCombined=Number(item.covered_foregone_upside);
  const exitScenarios=`${decisionReturnBox("آفست اختیار و فروش دارایی پایه",`اختیار: ${item.option_valuation_basis||"—"} · پایه: ${item.base_valuation_basis||"—"}`,item.covered_liquidation_profit,item.covered_liquidation_percent,`بستن کامل موقعیت · کل کارمزد مسیر ${num(item.offset_and_sell_total_commission,0)}`)}${additionalReturns}${decisionReturnBox("سود انتظاری کاوردکال","نگهداری موقعیت تا سررسید",item.covered_hold_profit,item.covered_hold_percent,`اعمال − بهای پایه ورود + پریمیوم خالص · کل کارمزد مسیر ${num(item.exercise_total_commission,0)}`)}`;
  const detailsOpen=localStorage.getItem("nicoption-trade-covered-details")==="open";
  const info=(label,text)=>analysisTooltip(label,text);
  return `<div class="covered-analysis-workspace trade-covered-analysis">
    <section class="covered-analysis-head"><div><small>تحلیل همین موقعیت</small><h3><span class="symbol">${esc(item.asset)}</span> / <span class="symbol">${esc(item.option_symbol)}</span></h3><p>${marketLabel(item.market)} · ورود ${esc(item.entry_date_display||"—")} · ${closed?`خروج ${esc(item.exit_date_display||"—")}`:"قیمت‌های جاری بازار"}</p></div><span class="analysis-status ${status==="open"?"positive":status==="exercised"?"warning":""}">${esc(statusLabels[status]||statusLabels.open)}</span></section>
    <section class="covered-kpi-grid">
      <article><span>بازده سالانه‌شده پریمیوم ${info("بازده سالانه‌شده پریمیوم","بازده پریمیوم خالص بر سرمایه درگیر است که بر مبنای مدت موقعیت سالانه شده؛ تضمین تکرار نیست.")}</span><strong class="${tone(item.covered_premium_return_yoy)}" dir="ltr">${fmt(item.covered_premium_return_yoy,2,"٪")}</strong><small>بر مبنای مدت موقعیت</small></article>
      <article><span>حداکثر بازده تا سررسید</span><strong class="${tone(maxReturn)}" dir="ltr">${fmt(maxReturn,2,"٪")}</strong><small>حداکثر سود موقعیت <b dir="ltr">${fmt(maxProfitTotal,0)}</b></small></article>
      <article><span>پوشش نزول ${info("پوشش نزول","پریمیوم خالص دریافتی نسبت به بهای خرید دارایی پایه؛ میزان افت اولیه قابل پوشش را نشان می‌دهد.")}</span><strong dir="ltr">${fmt(metric.downsideProtection,2,"٪")}</strong><small>سربه‌سر <b dir="ltr">${fmt(breakeven,0)}</b></small></article>
      <article><span>پریمیوم خالص دریافتی</span><strong dir="ltr">${fmt(netPremiumTotal,0)}</strong><small>بازده پریمیوم <b dir="ltr">${fmt(item.covered_premium_return_percent,2,"٪")}</b></small></article>
    </section>
    <section class="trade-covered-outcomes primary-outcomes"><header><div><h4>سناریوهای خروج و تحقق سود</h4><small>مقایسه دو روش آفست با سود انتظاری نگهداری تا سررسید</small></div></header><div class="trade-returns">${exitScenarios}</div>${fulfillmentChart}</section>
    <section class="covered-decision-grid">
      <article class="covered-spec-panel"><header><h4>مشخصات معامله</h4><small>ورودی ثبت‌شده و قیمت جاری</small></header><dl><div><dt>قیمت سهم در ورود</dt><dd dir="ltr">${fmt(entryBase,0)}</dd></div><div><dt>قیمت فعلی سهم</dt><dd dir="ltr">${fmt(currentBase,0)}</dd></div><div><dt>قیمت اعمال</dt><dd dir="ltr">${fmt(strike,0)}</dd></div><div class="wide"><dt>سررسید و زمان</dt><dd dir="ltr">${esc(expiry)}</dd></div><div><dt>پرمیوم ورود</dt><dd dir="ltr">${fmt(entryPremium,0)}</dd></div><div><dt>قیمت بازخرید فعلی</dt><dd dir="ltr">${fmt(currentOption,0)}</dd></div><div><dt>فاصله سهم تا اعمال</dt><dd>${strikeDistanceText(metric.strikeDistance)}</dd></div><div><dt>احتمال اعمال ${info("احتمال اعمال","احتمال ریسک‌خنثی مدل Black–Scholes؛ پیش‌بینی قطعی بازار نیست.")}</dt><dd class="model-value" dir="ltr">${fmt(metric.assignmentProbability,2,"٪")}</dd></div></dl></article>
      <article class="covered-payoff-panel"><header><div><h4>نمودار سود و زیان موقعیت در سررسید</h4><small>بر پایه قیمت خرید و پریمیوم ثبت‌شده؛ نشانگر فعلی با قیمت جاری بازار</small></div></header>${coveredDecisionRange(metric)}${coveredPayoffChart(item,metric)}</article>
    </section>
    <section class="covered-analysis-panels">
      <article><header><h4>قیمت‌گذاری اختیار</h4><small>ورود در برابر هزینه خروج فعلی</small></header><dl><div><dt>پرمیوم ورود</dt><dd dir="ltr">${fmt(entryPremium,0)}</dd></div><div><dt>قیمت بازخرید فعلی</dt><dd dir="ltr">${fmt(currentOption,0)}</dd></div><div><dt>تغییر قیمت اختیار</dt><dd class="${tone(premiumChange)}" dir="ltr">${fmt(premiumChange,2,"٪")}</dd></div><div><dt>فاصله بازخرید تا ورود</dt><dd dir="ltr">${fmt(fairGap,2,"٪")}</dd></div><div><dt>مبنای قیمت اختیار</dt><dd>${esc(item.option_valuation_basis||"—")}</dd></div></dl></article>
      <article><header><h4>احتمال و ریسک</h4><small>بر مبنای همین موقعیت</small></header><dl><div><dt>احتمال اعمال</dt><dd class="model-value" dir="ltr">${fmt(metric.assignmentProbability,2,"٪")}</dd></div><div><dt>فاصله سهم تا اعمال</dt><dd>${strikeDistanceText(metric.strikeDistance)}</dd></div><div><dt>حداکثر زیان نظری ${info("حداکثر زیان نظری","تقریب زیان در صورت صفرشدن ارزش دارایی پایه پس از کسر پریمیوم خالص؛ هزینه‌های آتی را تضمین نمی‌کند.")}</dt><dd class="negative" dir="ltr">${fmt(-invested,0)}</dd></div><div><dt>سرمایه درگیر</dt><dd dir="ltr">${fmt(invested,0)}</dd></div><div><dt>سهم از سرمایه صفحه</dt><dd dir="ltr">${fmt(capitalShare,2,"٪")}</dd></div></dl></article>
      <article><header><h4>وضعیت و نتیجه</h4><small>خلاصه اجرای معامله</small></header><dl><div><dt>تعداد قرارداد</dt><dd dir="ltr">${qty(item.quantity)}</dd></div><div><dt>تعداد دارایی پایه وثیقه</dt><dd dir="ltr">${qty(item.underlying_units)}</dd></div><div><dt>کارمزد ورود</dt><dd dir="ltr">${fmt(item.commission,0)}</dd></div><div><dt>کارمزد آفست و نگهداری پایه</dt><dd dir="ltr">${fmt(item.option_offset_total_commission,0)}</dd></div><div><dt>کارمزد آفست و فروش پایه</dt><dd dir="ltr">${fmt(item.offset_and_sell_total_commission,0)}</dd></div><div><dt>کارمزد نگهداری تا تخصیص</dt><dd dir="ltr">${fmt(item.exercise_total_commission,0)}</dd></div><div><dt>سود انتظاری از کاوردکال</dt><dd class="${tone(item.covered_hold_profit)}" dir="ltr">${fmt(item.covered_hold_profit,0)}</dd></div><div><dt>کیفیت برآورد احتمال</dt><dd class="model-value">${assignmentModel}</dd></div></dl></article>
    </section>
    ${realizedResult}
    <details class="covered-advanced" aria-expanded="${detailsOpen?"true":"false"}" ${detailsOpen?"open":""}><summary><span><b>نمایش جزئیات محاسبات</b><small>یونانی‌ها، فروض مدل و داده‌های ورود/وضعیت فعلی</small></span><i aria-hidden="true">⌄</i></summary><div><dl><div><dt>احتمال ITM فعلی</dt><dd dir="ltr">${fmt(item.current_itm_percent,2,"٪")}</dd></div><div><dt>دلتا اختیار</dt><dd class="model-value" dir="ltr">${fmt(item.current_option_delta??item.option_delta,4)}</dd></div><div><dt>دلتا استراتژی</dt><dd class="model-value" dir="ltr">${fmt(item.current_strategy_delta??item.strategy_delta,4)}</dd></div><div><dt>نوسان ضمنی</dt><dd class="model-value" dir="ltr">${fmt(item.current_implied_volatility??metric.volatility,2,"٪")}</dd></div><div><dt>مدل احتمال اعمال</dt><dd class="model-value">${esc(metric.model)}</dd></div><div><dt>تغییر دارایی پایه</dt><dd class="calculation-value" dir="ltr">${fmt(baseChange,0)}</dd></div><div><dt>تغییر موقعیت اختیار</dt><dd class="calculation-value" dir="ltr">${fmt(optionChange,0)}</dd></div><div><dt>جمع تغییر پایه و اختیار</dt><dd class="calculation-value" dir="ltr">${fmt(combinedChange,0)}</dd></div><div><dt>سود ازدست‌رفته نسبت به نگهداری سهم</dt><dd class="calculation-value" dir="ltr">${fmt(foregoneFromCombined,0)}</dd></div><div><dt>بهای پایه وثیقه</dt><dd class="calculation-value" dir="ltr">${fmt(item.collateral_cost_basis??entryBase,0)}</dd></div><div><dt>مبنای قیمت پایه</dt><dd>${esc(item.base_valuation_basis||"—")}</dd></div></dl><p>سود ازدست‌رفته با مقایسه سود نگهداری ساده سهم و جمع تغییرات دارایی پایه و موقعیت اختیار محاسبه می‌شود. احتمال اعمال، دلتا و نوسان مقادیر مدل‌شده‌اند و پیش‌بینی قطعی نیستند. ${metric.estimated?"برای احتمال اعمال از نوسان مرجع ۳۵٪ استفاده شده است.":"نوسان ثبت‌شده موقعیت در محاسبه استفاده شده است."}</p></div></details>
    <div class="trade-detail-actions">${actions}<button class="trade-action danger" type="button" data-trade-action="delete" data-trade-id="${esc(item.id)}">حذف</button></div>
  </div>`;
}

function longTradeDecisionRange(item) {
  const points = [
    {label:"پایه ورود",value:Number(item.entry_base_price),className:"entry"},
    {label:"پایه فعلی",value:Number(item.current_base_price),className:"current"},
    {label:"اعمال",value:Number(item.strike),className:"strike"},
    {label:"سربه‌سر",value:Number(item.long_exercise_breakeven),className:"breakeven"},
  ].filter((point)=>Number.isFinite(point.value));
  if (!points.length) return '<div class="covered-analysis-empty">داده کافی برای نوار تصمیم وجود ندارد.</div>';
  const values=points.map((point)=>point.value);
  const minimum=Math.min(...values),maximum=Math.max(...values),padding=Math.max(1,(maximum-minimum)*.12);
  const domainMin=minimum-padding,domainMax=maximum+padding,span=domainMax-domainMin||1;
  const current=Number(item.current_base_price),breakeven=Number(item.long_exercise_breakeven);
  const distance=Number.isFinite(current)&&Number.isFinite(breakeven)&&breakeven!==0?(current-breakeven)/breakeven*100:null;
  const decisionText=distance==null?"فاصله قیمت فعلی تا سربه‌سر قابل محاسبه نیست.":distance>=0?`قیمت فعلی دارایی پایه ${num(distance,2)}٪ بالاتر از نقطه سربه‌سر است.`:`برای رسیدن به سربه‌سر، دارایی پایه باید ${num(Math.abs(distance),2)}٪ رشد کند.`;
  return `<section class="long-trade-decision-range" aria-label="مقایسه قیمت‌های کلیدی معامله"><header><div><small>وضعیت تصمیم معامله</small><h4>ورود، قیمت جاری، اعمال و سربه‌سر</h4><p>${esc(decisionText)}</p></div><span>مبالغ به ریال</span></header><div class="decision-track"><i></i>${points.map((point)=>`<b class="decision-point ${point.className}" style="--position:${(point.value-domainMin)/span*100}%"><span>${point.label}</span><em dir="ltr">${num(point.value,0)}</em></b>`).join("")}</div></section>`;
}

function longTradeRiskFreeCompact(item) {
  const strategy=Number(item.strategy_profit_for_risk_free);
  const benchmark=Number(item.risk_free_profit);
  const excess=Number.isFinite(strategy)&&Number.isFinite(benchmark)?strategy-benchmark:null;
  const multiple=item.strategy_to_risk_free_multiple;
  return `<section class="long-risk-free-compact"><header><div><small>معیار فرصت از‌دست‌رفته</small><h4>مقایسه فشرده با درآمد ثابت</h4></div><span>${num(item.risk_free_days,0)} روز · نرخ سالانه ${num(item.risk_free_annual_rate,0)}٪</span></header><div><article><span>سود بدون‌ریسک همین دوره</span><strong dir="ltr">${signed(item.risk_free_profit,0)}</strong><small>بازده ${signed(item.risk_free_return_percent,2)}٪</small></article><article><span>مازاد استراتژی نسبت به بدون‌ریسک</span><strong class="${profitTone(excess)}" dir="ltr">${signed(excess,0)}</strong><small>${multiple==null?"نسبت قابل محاسبه نیست":`${signed(multiple,2)} برابر سود بدون‌ریسک`}</small></article></div></section>`;
}

function longTradeAnalysisContent(item,{actions,realizedResult,capitalShare}) {
  const closed=item.status==="closed";
  const currentPrefix=closed?"exit":"current";
  const currentBase=item[`${currentPrefix}_base_price_snapshot`]??(closed?item.exit_base_price:item.current_base_price);
  const currentOption=item[`${currentPrefix}_option_price_snapshot`]??(closed?item.exit_option_price:item.current_option_exit_price);
  const currentItm=item[`${currentPrefix}_itm_percent`]??item.current_itm_percent;
  const currentMoneyness=item[`${currentPrefix}_moneyness`]??item.current_moneyness??"—";
  const optionProfit=closed?item.realized_profit:item.long_offset_profit;
  const optionReturn=closed?item.realized_profit_percent:item.long_offset_profit_percent;
  const optionChange=item.premium_price_change_percent;
  const statusLabel=closed?"بسته":"باز";
  const updateLabel=closed?`خروج ${item.exit_date_display||"—"}`:`ارزش‌گذاری ${item.option_valuation_basis||"قیمت جاری بازار"}`;
  const detailsOpen=localStorage.getItem("nicoption-trade-long-details")==="open";
  const comparisonRows=[
    ["قیمت دارایی پایه",item.entry_base_price,currentBase],
    ["قیمت اختیار",item.entry_premium,currentOption],
    ["درصد ITM",item.entry_itm_percent,currentItm,"٪"],
    ["دلتا اختیار",item.entry_option_delta,item[`${currentPrefix}_option_delta`]??item.option_delta],
    ["دلتا استراتژی",item.entry_strategy_delta,item[`${currentPrefix}_strategy_delta`]??item.strategy_delta],
    ["نوسان ضمنی",item.entry_implied_volatility,item[`${currentPrefix}_implied_volatility`]??item.current_implied_volatility,"٪"],
    ["روز تا سررسید",item.entry_days_to_expiry,item[`${currentPrefix}_days_to_expiry`]??(closed?0:item.remaining_days)],
  ];
  const row=(label,entry,current,suffix="")=>`<tr><th scope="row">${esc(label)}</th><td dir="ltr">${analysisValue(entry,2,suffix)}</td><td dir="ltr">${analysisValue(current,2,suffix)}</td></tr>`;
  const holdLabel=closed?"نتیجه ثبت‌شده":"وابسته به قیمت آینده";
  const exitPaths=`<article class="long-exit-path executable"><header><span>قابل اجرا با قیمت فعلی</span><h5>فروش اختیار در بازار</h5></header><strong class="${profitTone(item.long_offset_profit)}" dir="ltr">${signed(item.long_offset_profit,0)}</strong><p>بازده ${signed(item.long_offset_profit_percent,2)}٪ با ${esc(item.option_valuation_basis||"مبنای قیمت جاری")}</p><dl><div><dt>قیمت خروج اختیار</dt><dd>${num(item.current_option_exit_price,2)}</dd></div><div><dt>قیمت ورود</dt><dd>${num(item.entry_premium,2)}</dd></div><div><dt>کل کارمزد این مسیر</dt><dd>${num(item.option_offset_total_commission,0)}</dd></div></dl></article>
  <article class="long-exit-path calculated"><header><span>محاسبه با قیمت پایه فعلی</span><h5>اعمال اختیار و فروش دارایی پایه</h5></header><strong class="${profitTone(item.long_exercise_profit)}" dir="ltr">${signed(item.long_exercise_profit,0)}</strong><p>بازده ${signed(item.long_exercise_profit_percent,2)}٪؛ نیازمند تأمین وجه اعمال</p><dl><div><dt>وجه لازم برای اعمال</dt><dd>${num(item.long_exercise_required_cash,0)}</dd></div><div><dt>سربه‌سر با همه کارمزدها</dt><dd>${num(item.long_exercise_breakeven,2)}</dd></div><div><dt>کل کارمزد این مسیر</dt><dd>${num(item.exercise_and_sell_total_commission,0)}</dd></div></dl></article>
  <article class="long-exit-path dependent"><header><span>${holdLabel}</span><h5>نگهداری اختیار تا سررسید</h5></header><strong>${closed?signed(item.realized_profit,0):"—"}</strong><p>${closed?"نتیجه قطعی معامله بسته‌شده":"سود نهایی به قیمت دارایی پایه در سررسید وابسته است و امروز قطعی نیست."}</p><dl><div><dt>روز باقی‌مانده</dt><dd>${num(closed?0:item.remaining_days)}</dd></div><div><dt>وضعیت فعلی</dt><dd>${esc(currentMoneyness)}</dd></div></dl></article>`;
  return `<div class="covered-analysis-workspace trade-long-analysis">
    <section class="covered-analysis-head long-trade-head"><div><small>تحلیل همین موقعیت خرید اختیار خرید</small><h3><span class="symbol">${esc(item.option_symbol)}</span> <span aria-hidden="true">/</span> <span class="symbol">${esc(item.asset)}</span></h3><p>${marketLabel(item.market)} · ورود ${esc(item.entry_date_display||"—")} · ${esc(updateLabel)}</p></div><span class="analysis-status ${closed?"":"positive"}">${statusLabel}</span></section>
    <section class="covered-kpi-grid long-trade-kpis">
      <article><span>${closed?"سود یا زیان قطعی":"سود یا زیان قابل تحقق اکنون"}</span><strong class="${profitTone(optionProfit)}" dir="ltr">${signed(optionProfit,0)}</strong><small class="${profitTone(optionReturn)}">${signed(optionReturn,2)}٪</small></article>
      <article><span>قیمت اختیار؛ ورود ← اکنون</span><strong dir="ltr">${num(item.entry_premium,2)} ← ${num(currentOption,2)}</strong><small class="${profitTone(optionChange)}">تغییر ${signed(optionChange,2)}٪</small></article>
      <article><span>سرمایه درگیر با کارمزد</span><strong dir="ltr">${num(item.invested_capital,0)}</strong><small>${capitalShare==null?"مبنای کل سرمایه موجود نیست":`${num(capitalShare,2)}٪ از سرمایه معاملات ${closed?"بسته":"باز"}`}</small></article>
      <article><span>سررسید و وضعیت اختیار</span><strong>${num(closed?item.invested_days:item.remaining_days)} روز</strong><small>${esc(item.expiry_display||"—")} · ${esc(currentMoneyness)} · ITM ${signed(currentItm,2)}٪</small></article>
    </section>
    ${longTradeDecisionRange(item)}
    <section class="long-trade-decision-layout">
      <article class="long-exit-panel"><header><div><h4>مسیرهای خروج و نگهداری</h4><small>اعداد قطعی، قابل اجرا و وابسته به آینده از هم جدا شده‌اند.</small></div></header><div class="long-exit-grid">${exitPaths}</div></article>
      <article class="long-entry-current"><header><h4>ورود در برابر وضعیت فعلی</h4><small>داده‌های ثبت‌شده و آخرین وضعیت موجود</small></header><div class="table-scroll"><table><thead><tr><th>شاخص</th><th>ورود</th><th>${closed?"خروج":"اکنون"}</th></tr></thead><tbody>${comparisonRows.map((values)=>row(...values)).join("")}</tbody></table></div></article>
    </section>
    ${longTradeProfitComparison(item,{title:"مقایسه مسیرهای تحقق سود تا امروز"})}
    ${longTradeRiskFreeCompact(item)}
    ${realizedResult}
    <details class="covered-advanced long-trade-advanced" aria-expanded="${detailsOpen?"true":"false"}" ${detailsOpen?"open":""}><summary><span><b>جزئیات معامله و مبنای محاسبات</b><small>تخصیص قراردادها، کارمزد، مدل و داده‌های ثبت‌شده</small></span><i aria-hidden="true">⌄</i></summary><div><dl><div><dt>قیمت اعمال</dt><dd dir="ltr">${num(item.strike,2)}</dd></div><div><dt>تعداد قرارداد</dt><dd dir="ltr">${qty(item.quantity)}</dd></div><div><dt>تعداد با هدف اعمال</dt><dd dir="ltr">${qty(item.exercise_quantity)}</dd></div><div><dt>تعداد نوسان‌گیری</dt><dd dir="ltr">${qty(item.premium_trade_quantity)}</dd></div><div><dt>وجه اعمال بخش تخصیص‌یافته</dt><dd dir="ltr">${num(item.exercise_allocation_required_cash,0)}</dd></div><div><dt>کارمزد ورود</dt><dd dir="ltr">${num(item.commission,0)} · ${commissionSourceLabel(item.commission_source)}</dd></div><div><dt>کارمزد خروج ثبت‌شده</dt><dd dir="ltr">${item.status==="closed"?`${num(item.exit_commission,0)} · ${commissionSourceLabel(item.exit_commission_source)}`:"—"}</dd></div><div><dt>برآورد کارمزد آفست اختیار</dt><dd dir="ltr">${num(item.option_exit_commission_estimate,0)}</dd></div><div><dt>برآورد کارمزد اعمال</dt><dd dir="ltr">${num(item.exercise_commission_estimate,0)}</dd></div><div><dt>برآورد کارمزد فروش پایه</dt><dd dir="ltr">${num(item.underlying_exit_commission_estimate,0)}</dd></div><div><dt>نسخه و واحد محاسبه</dt><dd dir="ltr">v${num(item.calculation_version||7,0)} · ${item.currency_unit==="rial"?"ریال":esc(item.currency_unit||"legacy")}</dd></div><div><dt>روش بهره</dt><dd>${item.interest_convention==="simple"?`ساده ${esc(item.interest_day_count||"ACT/365")}`:item.interest_convention==="compound_legacy"?"مرکب نسخه قدیمی":"—"}</dd></div><div><dt>مبنای قیمت اختیار</dt><dd>${esc(item.option_valuation_basis||"—")}</dd></div><div><dt>مبنای قیمت دارایی پایه</dt><dd>${esc(item.base_valuation_basis||"—")}</dd></div></dl><p>هر سناریو فقط کارمزدهای مرتبط با همان مسیر را کسر می‌کند. کارمزد «ثبت کاربر» حتی اگر صفر باشد، دوباره برآورد نمی‌شود.</p></div></details>
    <div class="trade-detail-actions long-trade-sticky-actions">${actions}<button class="trade-action danger" type="button" data-trade-action="delete" data-trade-id="${esc(item.id)}">حذف</button></div>
  </div>`;
}

function tradeDetailContent(item) {
  const isLongCall = item.strategy_type === "long_call";
  const closed = item.status === "closed";
  const premiumChangeTone = item.premium_price_change_percent == null ? "" : profitTone(isLongCall ? item.premium_price_change_percent : -Number(item.premium_price_change_percent));
  const entryAnalytics = tradeAnalyticsSnapshot(item,"entry","وضعیت هنگام ورود");
  const currentAnalytics = tradeAnalyticsSnapshot(item,closed ? "exit" : "current",closed ? "وضعیت هنگام خروج" : "وضعیت فعلی بازار");
  const allocationMetrics = isLongCall
    ? `<div class="trade-allocation-group"><div><span>تعداد برای اعمال</span><b>${qty(item.exercise_quantity)}</b></div><div><span>تعداد برای نوسان‌گیری</span><b>${qty(item.premium_trade_quantity)}</b></div><div><span>نقدینگی اعمال بخش تخصیص‌یافته</span><b>${num(item.exercise_allocation_required_cash,0)}</b></div></div>`
    : `<div class="trade-allocation-group"><div><span>فاصله اعمال تا قیمت ورود هر سهم</span><b>${signed(item.covered_exercise_profit_per_unit,2)}</b><small>اعمال − قیمت پایه ورود</small></div><div><span>پرمیوم دریافتی هر سهم</span><b>${num(item.covered_hold_premium_per_unit,2)}</b></div><div><span>تعداد نهایی پایه</span><b>${qty(item.underlying_units)}</b><small>${qty(item.quantity)} قرارداد × ضریب ${qty(item.contract_size)}</small></div></div>`;
  const additionalReturns = isLongCall
    ? longCallReturnBoxes(item)
    : decisionReturnBox("آفست اختیار و نگهداری دارایی پایه",`خرید مجدد اختیار با ${item.option_valuation_basis || "—"}`,item.covered_option_only_profit,item.covered_option_only_percent,`دارایی پایه فروخته نمی‌شود · کل کارمزد مسیر ${num(item.option_offset_total_commission,0)}`);
  const fulfillmentChart = isLongCall
    ? longTradeProfitComparison(item,{title:"نمودار تحقق سود اختیار خرید"})
    : coveredFulfillmentChart(item,{centerZero:true});
  const realizedResult = closed ? `<div class="realized-result"><div><span>سود یا زیان قطعی</span><strong class="${profitTone(item.realized_profit)}">${signed(item.realized_profit,0)}</strong></div><div><span>درصد سود</span><strong class="${profitTone(item.realized_profit_percent)}">${signed(item.realized_profit_percent)}٪</strong></div><div><span>مدت معامله</span><strong>${num(item.invested_days)} روز</strong></div><div><span>بازده سالانه</span><strong class="${profitTone(item.realized_profit_yoy)}">${signed(item.realized_profit_yoy)}٪</strong></div></div>` : "";
  const actions = closed
    ? `<button class="trade-action" type="button" data-trade-action="close" data-trade-id="${esc(item.id)}">ویرایش خروج</button>`
    : `<button class="trade-action" type="button" data-trade-action="edit" data-trade-id="${esc(item.id)}">ویرایش معامله</button><button class="trade-action" type="button" data-trade-action="close" data-trade-id="${esc(item.id)}">ثبت خروج</button>`;
  const portfolioCapital = Number(closed
    ? state.lastTradesPayload?.closed_summary?.invested_capital
    : state.lastTradesPayload?.summary?.total?.invested_capital) || 0;
  const capitalShare = portfolioCapital > 0 ? Number(item.invested_capital || 0) / portfolioCapital * 100 : null;
  if (!isLongCall) return coveredTradeAnalysisContent(item,{actions,realizedResult,additionalReturns,fulfillmentChart,capitalShare});
  return longTradeAnalysisContent(item,{actions,realizedResult,capitalShare});
}

function bringTradeDetailToFront(windowElement) {
  tradeDetailZIndex += 1;
  windowElement.style.zIndex = String(tradeDetailZIndex);
}

function bindTradeCoveredDetails(windowElement) {
  const advanced=windowElement.querySelector(".covered-advanced");
  advanced?.addEventListener("toggle",()=>{advanced.setAttribute("aria-expanded",String(advanced.open));localStorage.setItem(advanced.classList.contains("long-trade-advanced")?"nicoption-trade-long-details":"nicoption-trade-covered-details",advanced.open?"open":"closed");});
  windowElement.querySelectorAll("[data-trade-detail-basis]").forEach((selectElement) => selectElement.addEventListener("change", () => updateTradeDetailPricing(windowElement)));
}

function detailPriceOptions(selected) {
  return [["last","آخرین معامله"],["bid","بهترین خرید"],["ask","بهترین فروش"]].map(([value,label])=>`<option value="${value}"${selected===value?" selected":""}>${label}</option>`).join("");
}
function tradeDetailPricingControls(item,selections={option:"last",base:"last"}) {
  const quote=(last,bid,ask)=>`آخرین ${num(last,2)} · خرید ${num(bid,2)} · فروش ${num(ask,2)}`;
  return `<section class="trade-detail-pricing" aria-label="مبنای محاسبات این پنجره"><header><div><small>تنظیم مستقل این موقعیت</small><h3>مبنای محاسبات</h3></div><span>جداول صفحه همیشه بر پایه آخرین معامله‌اند</span></header><div><label><span>قیمت اختیار</span><select data-trade-detail-basis="option">${detailPriceOptions(selections.option)}</select><small>${quote(item.option_last_trade,item.option_best_bid,item.option_best_ask)}</small></label><label><span>قیمت دارایی پایه</span><select data-trade-detail-basis="base">${detailPriceOptions(selections.base)}</select><small>${quote(item.base_last_trade,item.base_best_bid,item.base_best_ask)}</small></label></div><p>تغییر این دو گزینه فقط محاسبات همین پنجره را به‌روزرسانی می‌کند.</p></section>`;
}
function tradeDetailWindowBody(item,selections={option:"last",base:"last"}) { return `${tradeDetailPricingControls(item,selections)}${tradeDetailContent(item)}`; }
async function updateTradeDetailPricing(windowElement) {
  const tradeId=windowElement.dataset.tradeDetailWindow, option=windowElement.querySelector('[data-trade-detail-basis="option"]')?.value||"last", base=windowElement.querySelector('[data-trade-detail-basis="base"]')?.value||"last";
  windowElement.dataset.optionBasis=option; windowElement.dataset.baseBasis=base;
  const current=state.trades.find((trade)=>String(trade.id)===String(tradeId)); if(!current)return;
  const params=new URLSearchParams({covered_option_basis:"last",covered_base_basis:"last",long_option_basis:"last",long_base_basis:"last"});
  if(current.strategy_type==="long_call"){params.set("long_option_basis",option);params.set("long_base_basis",base);}else{params.set("covered_option_basis",option);params.set("covered_base_basis",base);}
  const body=windowElement.querySelector(".trade-detail-window-body"); windowElement.setAttribute("aria-busy","true");
  try { const response=await fetch(`/api/trades?${params}`,{headers:{Accept:"application/json"}}); if(!response.ok)throw new Error("دریافت محاسبات جدید ناموفق بود"); const payload=await response.json(); const item=(payload.trades||[]).find((trade)=>String(trade.id)===String(tradeId)); if(!item)throw new Error("معامله در پاسخ جدید پیدا نشد"); body.innerHTML=tradeDetailWindowBody(item,{option,base}); bindTradeCoveredDetails(windowElement); }
  catch(error){body.querySelector(".trade-detail-pricing")?.insertAdjacentHTML("beforeend",`<p class="trade-detail-pricing-error" role="alert">${esc(error.message||"به‌روزرسانی محاسبات ناموفق بود")}</p>`);} finally{windowElement.removeAttribute("aria-busy");}
}

function positionTradeDetailWindow(windowElement, anchorElement) {
  const gap = 12;
  const rect = anchorElement?.getBoundingClientRect?.();
  const width = windowElement.offsetWidth || Math.min(517, window.innerWidth - gap * 2);
  const height = Math.min(windowElement.offsetHeight || 420, window.innerHeight - gap * 2);
  let left = Math.max(gap, window.innerWidth - width - gap);
  let top = 72;
  if (rect) {
    const roomOnLeft = rect.left - gap;
    const roomOnRight = window.innerWidth - rect.right - gap;
    if (roomOnLeft >= width) left = rect.left - width - gap;
    else if (roomOnRight >= width) left = rect.right + gap;
    else left = Math.max(gap, Math.min(window.innerWidth - width - gap, rect.left));
    top = Math.max(gap, Math.min(window.innerHeight - height - gap, rect.top));
  }
  windowElement.style.left = `${left}px`;
  windowElement.style.top = `${top}px`;
}

function openTradeDetailWindow(tradeId, anchorElement=null) {
  const workspace = $("tradeDetailWorkspace");
  if (!workspace) return;
  const existing = workspace.querySelector(`[data-trade-detail-window="${CSS.escape(String(tradeId))}"]`);
  if (existing) { positionTradeDetailWindow(existing, anchorElement); bringTradeDetailToFront(existing); return; }
  const item = state.trades.find((trade) => String(trade.id) === String(tradeId));
  if (!item) return;
  const windowElement = document.createElement("article");
  const gap = 12;
  const cardWidth = Math.min(1180,window.innerWidth - gap * 2);
  windowElement.className = `trade-detail-window ${item.strategy_type === "long_call" ? "long" : "covered"}`;
  windowElement.dataset.tradeDetailWindow = tradeId;
  windowElement.dataset.optionBasis = "last";
  windowElement.dataset.baseBasis = "last";
  windowElement.style.width = `${cardWidth}px`;
  windowElement.innerHTML = `<header data-trade-detail-drag><div><small>${item.status === "closed" ? "جزئیات معامله بسته" : item.strategy_type === "long_call" ? "جزئیات خرید اختیار خرید" : "جزئیات کاوردکال"}</small><strong><span class="symbol">${esc(item.option_symbol)}</span> · ${esc(item.asset)}</strong></div><button type="button" data-trade-detail-close aria-label="بستن جزئیات">×</button></header><div class="trade-detail-window-body">${tradeDetailWindowBody(item)}</div>`;
  workspace.appendChild(windowElement);
  bindTradeCoveredDetails(windowElement);
  positionTradeDetailWindow(windowElement, anchorElement);
  bringTradeDetailToFront(windowElement);
}

function refreshOpenTradeDetailWindows() {
  document.querySelectorAll("[data-trade-detail-window]").forEach((windowElement) => {
    const item = state.trades.find((trade) => String(trade.id) === String(windowElement.dataset.tradeDetailWindow));
    if (!item) { windowElement.remove(); return; }
    const selections={option:windowElement.dataset.optionBasis||"last",base:windowElement.dataset.baseBasis||"last"};
    if(selections.option!=="last"||selections.base!=="last") updateTradeDetailPricing(windowElement);
    else { windowElement.querySelector(".trade-detail-window-body").innerHTML=tradeDetailWindowBody(item,selections); bindTradeCoveredDetails(windowElement); }
  });
}

function underlyingPriceForBasis(item,basis){return Number(basis==="bid"?item.best_bid:basis==="ask"?item.best_ask:item.current_price);}
function underlyingDetailContent(item,basis="last") {
  const price=underlyingPriceForBasis(item,basis),available=Number(item.available_quantity||0),quantity=Number(item.quantity||0),allocatedCommission=quantity>0?Number(item.commission||0)*available/quantity:0,invested=Number(item.entry_price||0)*available+allocatedCommission,profit=Number.isFinite(price)?(price-Number(item.entry_price||0))*available-allocatedCommission:null,percent=profit!=null&&invested>0?profit/invested*100:null,days=Math.max(1,Number(item.holding_days||1));
  return `<section class="trade-detail-pricing underlying-pricing" aria-label="مبنای محاسبات دارایی پایه"><header><div><small>تنظیم مستقل این خرید</small><h3>مبنای محاسبات</h3></div><span>جدول بر پایه آخرین معامله است</span></header><div><label><span>قیمت دارایی پایه</span><select data-underlying-detail-basis>${detailPriceOptions(basis)}</select><small>آخرین ${num(item.current_price,2)} · خرید ${num(item.best_bid,2)} · فروش ${num(item.best_ask,2)}</small></label></div></section><section class="underlying-detail-summary"><header><div><small>خرید دارایی پایه</small><h3>${esc(item.asset||"—")}</h3></div><span>${esc(item.entry_date_display||"—")}</span></header><dl><div><dt>تعداد آزاد</dt><dd>${qty(available)}</dd></div><div><dt>قیمت خرید</dt><dd>${num(item.entry_price,2)}</dd></div><div><dt>قیمت محاسبات</dt><dd>${Number.isFinite(price)?num(price,2):"ناموجود"}</dd></div><div><dt>سرمایه درگیر</dt><dd>${num(invested,0)}</dd></div><div><dt>کارمزد ورود</dt><dd>${num(item.commission,0)} · ${commissionSourceLabel(item.commission_source)}</dd></div><div><dt>کارمزد خروج</dt><dd>${item.status==="closed"?`${num(item.exit_commission,0)} · ${commissionSourceLabel(item.exit_commission_source)}`:"—"}</dd></div><div><dt>سود و زیان تحقق‌نیافته</dt><dd class="${profitTone(profit)}">${profit==null?"ناموجود":signed(profit,0)}</dd></div><div><dt>بازده</dt><dd class="${profitTone(percent)}">${percent==null?"—":`${signed(percent,2)}٪`}</dd></div><div><dt>بازده سالانه‌شده</dt><dd class="${profitTone(percent)}">${percent==null?"—":`${signed(percent*365/days,2)}٪`}</dd></div><div><dt>تخصیص به کاوردکال</dt><dd>${qty(item.allocated_quantity||0)}</dd></div></dl><footer><button class="trade-action" type="button" data-underlying-action="sell" data-position-id="${esc(item.id)}">ثبت فروش</button><button class="trade-action" type="button" data-underlying-action="edit" data-position-id="${esc(item.id)}">ویرایش</button></footer></section>`;
}
function bindUnderlyingDetailWindow(windowElement,item){windowElement.querySelector("[data-underlying-detail-basis]")?.addEventListener("change",(event)=>{windowElement.querySelector(".trade-detail-window-body").innerHTML=underlyingDetailContent(item,event.target.value);bindUnderlyingDetailWindow(windowElement,item);});}
function openUnderlyingDetailWindow(positionId,anchorElement=null){const workspace=$("tradeDetailWorkspace"),item=state.underlyingPositions.find((row)=>String(row.id)===String(positionId));if(!workspace||!item)return;const existing=workspace.querySelector(`[data-underlying-detail-window="${CSS.escape(String(positionId))}"]`);if(existing){positionTradeDetailWindow(existing,anchorElement);bringTradeDetailToFront(existing);return;}const windowElement=document.createElement("article");windowElement.className="trade-detail-window underlying";windowElement.dataset.underlyingDetailWindow=positionId;windowElement.style.width=`${Math.min(900,window.innerWidth-24)}px`;windowElement.innerHTML=`<header data-trade-detail-drag><div><small>جزئیات خرید دارایی پایه</small><strong>${esc(item.asset||"—")}</strong></div><button type="button" data-trade-detail-close aria-label="بستن جزئیات">×</button></header><div class="trade-detail-window-body">${underlyingDetailContent(item)}</div>`;workspace.appendChild(windowElement);bindUnderlyingDetailWindow(windowElement,item);positionTradeDetailWindow(windowElement,anchorElement);bringTradeDetailToFront(windowElement);}
window.openUnderlyingDetailWindow=openUnderlyingDetailWindow;

function applyOpenTradeView() {
  const list = $("tradesList");
  if (!list) return;
  list.classList.toggle("full-trade-view",state.tradeFullView);
  document.querySelectorAll('[data-trade-view-mode="open"]').forEach((button) => button.classList.toggle("active", button.dataset.value === (state.tradeFullView ? "full" : "summary")));
  document.querySelectorAll('[data-trade-view-mode="closed"]').forEach((button) => button.classList.toggle("active", button.dataset.value === (state.closedTradeFullView ? "full" : "summary")));
  document.querySelectorAll("[data-trade-strategy-filter]").forEach((button) => button.classList.toggle("active", button.dataset.value === state.tradeStrategyFilter[button.dataset.tradeStrategyFilter]));
}

function syncTradeSelectionUi() {
  const availableIds = new Set(state.trades.map((item) => String(item.id)));
  [...selectedTradeIds].forEach((id) => {
    if (!availableIds.has(id)) selectedTradeIds.delete(id);
  });
  document.querySelectorAll("#tradesList .trade-card, #closedTradesList .trade-card").forEach((card) => {
    const id = String(card.dataset.tradeId || "");
    const trade = state.trades.find((item) => String(item.id) === id);
    if (!trade) return;
    const actionRow = card.querySelector(".trade-actions");
    if (!actionRow) return;
    let control = actionRow.querySelector("[data-trade-select]")?.closest("label");
    if (!control) {
      control = document.createElement("label");
      control.className = "trade-select-control trade-select-action";
      control.title = `انتخاب ${trade.option_symbol || trade.asset}`;
      control.innerHTML = `<input type="checkbox" data-trade-select="${esc(id)}" aria-label="انتخاب معامله ${esc(trade.option_symbol || trade.asset)}" /><span>انتخاب</span>`;
      actionRow.append(control);
    }
    const checkbox = control.querySelector("input");
    checkbox.checked = selectedTradeIds.has(id);
    card.classList.toggle("is-selected", checkbox.checked);
  });
  for (const status of ["open", "closed"]) {
    const ids = state.trades
      .filter((item) => (item.status === "closed" ? "closed" : "open") === status)
      .map((item) => String(item.id));
    const selected = ids.filter((id) => selectedTradeIds.has(id)).length;
    const selectAll = document.querySelector(`[data-trade-select-all="${status}"]`);
    const deleteButton = document.querySelector(`[data-trade-bulk-delete="${status}"]`);
    const counter = document.querySelector(`[data-trade-selected-count="${status}"]`);
    if (selectAll) {
      selectAll.disabled = ids.length === 0;
      selectAll.checked = ids.length > 0 && selected === ids.length;
      selectAll.indeterminate = selected > 0 && selected < ids.length;
    }
    if (deleteButton) deleteButton.disabled = selected === 0;
    if (counter) counter.textContent = `${num(selected)} انتخاب`;
  }
}

function underlyingStatus(item) {
  return item.status === "closed" ? "closed" : "open";
}

function syncUnderlyingSelectionUi() {
  const availableIds = new Set(state.underlyingPositions.map((item) => String(item.id)));
  [...selectedUnderlyingIds].forEach((id) => {
    if (!availableIds.has(id)) selectedUnderlyingIds.delete(id);
  });
  document.querySelectorAll("[data-underlying-id]").forEach((card) => {
    const id = String(card.dataset.underlyingId || "");
    const checkbox = card.querySelector("[data-underlying-select]");
    if (!checkbox) return;
    checkbox.checked = selectedUnderlyingIds.has(id);
    card.classList.toggle("is-selected", checkbox.checked);
  });
  for (const status of ["open", "closed"]) {
    const ids = state.underlyingPositions
      .filter((item) => underlyingStatus(item) === status && (status === "closed" || Number(item.available_quantity || 0) > 0))
      .map((item) => String(item.id));
    const selected = ids.filter((id) => selectedUnderlyingIds.has(id)).length;
    const selectAll = document.querySelector(`[data-underlying-select-all="${status}"]`);
    const deleteButton = document.querySelector(`[data-underlying-bulk-delete="${status}"]`);
    const counter = document.querySelector(`[data-underlying-selected-count="${status}"]`);
    if (selectAll) {
      selectAll.disabled = ids.length === 0;
      selectAll.checked = ids.length > 0 && selected === ids.length;
      selectAll.indeterminate = selected > 0 && selected < ids.length;
    }
    if (deleteButton) deleteButton.disabled = selected === 0;
    if (counter) counter.textContent = `${num(selected)} انتخاب`;
  }
}

async function deleteSelectedUnderlyings(status) {
  const ids = state.underlyingPositions
    .filter((item) => underlyingStatus(item) === status && (status === "closed" || Number(item.available_quantity || 0) > 0))
    .map((item) => String(item.id))
    .filter((id) => selectedUnderlyingIds.has(id));
  if (!ids.length) return;
  const label = status === "closed" ? "بسته" : "باز";
  if (!await requestConfirmation({
    title: `حذف ${num(ids.length)} دارایی پایه ${label}`,
    description: "موقعیت‌های انتخاب‌شده و سابقه ثبت‌شده آن‌ها حذف می‌شوند و قابل بازیابی نیستند.",
    actionLabel: `حذف ${num(ids.length)} دارایی پایه`,
  })) return;
  const button = document.querySelector(`[data-underlying-bulk-delete="${status}"]`);
  button.disabled = true;
  try {
    const response = await apiFetch("/api/underlyings/bulk-delete", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ids, status}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "حذف گروهی دارایی‌های پایه ناموفق بود");
    ids.forEach((id) => selectedUnderlyingIds.delete(id));
    await loadTrades();
    tradeMessage("success", `${num(data.bulk_deleted)} دارایی پایه حذف شد.`);
  } catch (error) {
    tradeMessage("error", error.message || "حذف گروهی دارایی‌های پایه ناموفق بود");
    syncUnderlyingSelectionUi();
  }
}

async function deleteSelectedTrades(status) {
  const ids = state.trades
    .filter((item) => (item.status === "closed" ? "closed" : "open") === status)
    .map((item) => String(item.id))
    .filter((id) => selectedTradeIds.has(id));
  if (!ids.length) return;
  const label = status === "closed" ? "بسته" : "باز";
  if (!await requestConfirmation({
    title: `حذف ${num(ids.length)} معامله ${label}`,
    description: "معاملات انتخاب‌شده و اطلاعات محاسباتی آن‌ها حذف می‌شوند و قابل بازیابی نیستند.",
    actionLabel: `حذف ${num(ids.length)} معامله`,
  })) return;
  const button = document.querySelector(`[data-trade-bulk-delete="${status}"]`);
  button.disabled = true;
  try {
    const response = await apiFetch("/api/trades/bulk-delete", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ids, status}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "حذف گروهی ناموفق بود");
    ids.forEach((id) => selectedTradeIds.delete(id));
    await loadTrades();
    tradeMessage("success", `${num(data.bulk_deleted)} معامله حذف شد.`);
  } catch (error) {
    tradeMessage("error", error.message || "حذف گروهی ناموفق بود");
    syncTradeSelectionUi();
  }
}

let closedPerformanceLimit = 20;
let closedPerformanceAnimationFrame = 0;
let closedPerformanceResizeObserver = null;
let dashboardTrendAnimationFrame = 0;
let dashboardTrendResizeObserver = null;
const CLOSED_RISK_FREE_ANNUAL_RATE = 0.40;

function finiteNumber(value) {
  const number = Number(value);
  return value == null || value === "" || !Number.isFinite(number) ? null : number;
}

function median(values = []) {
  const sorted = values.filter(Number.isFinite).sort((a,b)=>a-b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function closedEpisodeRows(allTrades = []) {
  const rootOf = (item) => String(item.strategy_episode_id || item.roll_chain_id || item.parent_trade_id || item.source_trade_id || item.id);
  const openRoots = new Set(allTrades.filter((item)=>item.status !== "closed").map(rootOf));
  const groups = new Map();
  allTrades.filter((item)=>item.status === "closed").forEach((item) => {
    const root = rootOf(item);
    if (openRoots.has(root)) return;
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(item);
  });
  return [...groups.entries()].map(([episodeId, legs]) => {
    legs.sort((a,b)=>String(a.exit_date||"").localeCompare(String(b.exit_date||"")));
    const first = legs[0], last = legs[legs.length - 1];
    const total = (key) => legs.reduce((sum,item)=>sum+(finiteNumber(item[key])||0),0);
    const quantities = legs.reduce((sum,item)=>sum+(finiteNumber(item.quantity)||0),0);
    const weighted = (key) => quantities > 0 ? legs.reduce((sum,item)=>sum+(finiteNumber(item[key])||0)*(finiteNumber(item.quantity)||0),0)/quantities : null;
    const net = total("realized_profit"), fees = total("realized_commission");
    const capital = total("invested_capital"), days = Math.max(1, finiteNumber(last.invested_days) || finiteNumber(first.invested_days) || 1);
    let hasBenchmarkCapital = false;
    const benchmark = legs.reduce((sum,item)=>{
      const legCapital=finiteNumber(item.invested_capital),legDays=finiteNumber(item.invested_days);
      if(legCapital==null||legCapital<=0||legDays==null) return sum;
      hasBenchmarkCapital=true;
      return sum+legCapital*CLOSED_RISK_FREE_ANNUAL_RATE*Math.max(0,legDays)/365;
    },0);
    return {
      ...last, id:last.id, detail_id:last.id, episode_id:episodeId, leg_count:legs.length,
      entry_date:first.entry_date, entry_date_display:first.entry_date_display,
      exit_date:last.exit_date, exit_date_display:last.exit_date_display,
      quantity:quantities, exit_option_price:weighted("exit_option_price"), exit_base_price:weighted("exit_base_price"),
      realized_profit:net, gross_profit:net+fees, realized_commission:fees,
      invested_capital:capital, invested_days:days,
      realized_profit_percent:capital>0?net/capital*100:null,
      benchmark_profit:hasBenchmarkCapital?benchmark:null, excess_profit:hasBenchmarkCapital?net-benchmark:null,
      option_component_profit:total("option_profit"), base_component_profit:total("base_profit"),
      premium_cashflow:legs.reduce((sum,item)=>sum+(finiteNumber(item.entry_premium)||0)*(finiteNumber(item.quantity)||0),0),
      entry_dte:finiteNumber(first.entry_days), entry_moneyness:first.entry_moneyness || (finiteNumber(first.entry_itm_percent)>2?"ITM":finiteNumber(first.entry_itm_percent)<-2?"OTM":"ATM"),
      final_status:last.exit_method === "exercise" ? "exercise" : last.exit_method === "roll" ? "roll" : Number(last.exit_option_price||0)===0 ? "expired" : "offset",
    };
  });
}

function closedPerformanceStats(rows = []) {
  const profits=rows.map((r)=>finiteNumber(r.realized_profit)).filter((v)=>v!=null);
  const returns=rows.map((r)=>finiteNumber(r.realized_profit_percent)).filter((v)=>v!=null);
  const wins=profits.filter((v)=>v>0),losses=profits.filter((v)=>v<0);
  const total=(values)=>values.reduce((sum,value)=>sum+value,0);
  const capital=total(rows.map((r)=>finiteNumber(r.invested_capital)||0));
  const net=total(profits),fees=total(rows.map((r)=>finiteNumber(r.realized_commission)||0));
  const ordered=[...rows].sort((a,b)=>String(a.exit_date||"").localeCompare(String(b.exit_date||"")));
  let cumulative=0,cumulativeGrossFees=0,cumulativeCapital=0,cumulativeBenchmark=0,hasBenchmark=false,peak=0,maxDrawdown=0,drawdownStart=null,troughIndex=null,recoveryDays=null,lossStreak=0,maxLossStreak=0,winStreak=0,maxWinStreak=0;
  const curve=ordered.map((row,index)=>{
    cumulative+=finiteNumber(row.realized_profit)||0;
    cumulativeGrossFees+=finiteNumber(row.realized_commission)||0;
    cumulativeCapital+=Math.max(0,finiteNumber(row.invested_capital)||0);
    if(finiteNumber(row.benchmark_profit)!=null){cumulativeBenchmark+=Number(row.benchmark_profit);hasBenchmark=true;}
    peak=Math.max(peak,cumulative);
    const drawdown=peak-cumulative;
    if(drawdown>0&&drawdownStart==null) drawdownStart=index;
    if(drawdown>maxDrawdown){maxDrawdown=drawdown;troughIndex=index;}
    if(drawdown===0&&drawdownStart!=null){if(troughIndex!=null){const start=new Date(ordered[troughIndex].exit_date),end=new Date(row.exit_date);recoveryDays=Math.max(0,Math.round((end-start)/86400000));}drawdownStart=null;troughIndex=null;}
    const value=finiteNumber(row.realized_profit)||0;
    if(value<0){lossStreak+=1;winStreak=0;maxLossStreak=Math.max(maxLossStreak,lossStreak);}else if(value>0){winStreak+=1;lossStreak=0;maxWinStreak=Math.max(maxWinStreak,winStreak);}
    return {...row,cumulative_net:cumulative,cumulative_gross:cumulative+cumulativeGrossFees,cumulative_capital:cumulativeCapital,cumulative_benchmark:hasBenchmark?cumulativeBenchmark:null,drawdown};
  });
  const avg=(values)=>values.length?total(values)/values.length:null;
  const winRate=profits.length?wins.length/profits.length:null,avgWin=avg(wins),avgLoss=avg(losses);
  const holdingDays=rows.map((r)=>finiteNumber(r.invested_days)).filter((v)=>v!=null);
  return {count:rows.length,net,gross:net+fees,fees,capital,returnPercent:capital>0?net/capital*100:null,wins:wins.length,losses:losses.length,winRate,avgWin,avgLoss,medianWin:median(wins),medianLoss:median(losses),expectancy:profits.length?net/profits.length:null,expectancyPercent:returns.length?avg(returns):null,profitFactor:losses.length?total(wins)/Math.abs(total(losses)):null,payoffRatio:losses.length&&wins.length?avgWin/Math.abs(avgLoss):null,averageDays:avg(holdingDays),medianDays:median(holdingDays),maxDrawdown,recoveryDays,maxLossStreak,maxWinStreak,biggestWin:wins.length?Math.max(...wins):null,biggestLoss:losses.length?Math.min(...losses):null,meanReturn:avg(returns),medianReturn:median(returns),curve,drawdownMethod:"closed_exit_points",drawdownScopeLabel:"افت سود تجمعی در خروج‌های ثبت‌شده",drawdownIsDaily:false};
}

function closedMetric(label,value,note="",tone="") { return `<article><span>${esc(label)}</span><strong class="${tone}" dir="ltr">${value}</strong>${note?`<small>${esc(note)}</small>`:""}</article>`; }
function metricOrDash(value,digits=0,suffix="") { return value==null?"—":`${num(value,digits)}${suffix}`; }

function closedChartMoney(value) {
  const absolute=Math.abs(value);
  if(absolute>=1e9) return `${num(value/1e9,1)} میلیارد`;
  if(absolute>=1e6) return `${num(value/1e6,1)} میلیون`;
  if(absolute>=1e3) return `${num(value/1e3,0)} هزار`;
  return num(value,0);
}

function closedChartTickIndexes(length,maximum=6) {
  if(length<=1) return [0];
  const count=Math.min(maximum,length);
  return [...new Set(Array.from({length:count},(_,index)=>Math.round(index*(length-1)/(count-1))))];
}

function closedPerformanceLineChart(stats, mode="amount") {
  const points=stats.curve||[];
  if(!points.length) return '<div class="closed-empty-state"><strong>داده‌ای برای نمودار وجود ندارد</strong><p>فیلترها را تغییر دهید یا یک معامله را کامل ببندید.</p></div>';
  const percent=mode==="percent";
  const chartValue=(point,key)=>{
    const value=finiteNumber(point[key]);
    if(value==null) return null;
    if(!percent) return value;
    const basis=finiteNumber(point.cumulative_capital);
    return basis!=null&&basis>0?value/basis*100:null;
  };
  const plot={x:96,y:12,width:350,height:184},width=490,height=226;
  const plotWidth=plot.width,plotHeight=plot.height;
  const values=points.flatMap((p)=>[chartValue(p,"cumulative_net"),chartValue(p,"cumulative_gross"),chartValue(p,"cumulative_benchmark")]).filter((v)=>v!=null);
  let min=Math.min(0,...values),max=Math.max(0,...values);
  const rawSpan=max-min||1;
  min-=rawSpan*.08;max+=rawSpan*.08;
  const span=max-min||1;
  const xy=(value,index)=>[plot.x+(points.length===1?.5:index/(points.length-1))*plotWidth,plot.y+(max-value)/span*plotHeight];
  const path=(key)=>points.map((p,i)=>`${i?"L":"M"}${xy(chartValue(p,key)??0,i).map((value)=>value.toFixed(2)).join(" ")}`).join(" ");
  const zeroY=xy(0,0)[1];
  const nodes=points.map((p,i)=>{const net=chartValue(p,"cumulative_net")??0,[x,y]=xy(net,i),gross=chartValue(p,"cumulative_gross"),benchmark=chartValue(p,"cumulative_benchmark"),date=p.exit_date_display||p.exit_date||"—";return `<circle class="closed-chart-point" data-closed-chart-point="${i}" data-date="${esc(date)}" data-net="${net}" data-gross="${gross??""}" data-benchmark="${benchmark??""}" cx="${x}" cy="${y}" r="4" tabindex="0" aria-label="${esc(date)}، ${percent?`${signed(net,2)} درصد`:signed(net,0)}"><title>${esc(date)} · ${esc(p.option_symbol)} · ${percent?`${signed(net,2)}٪`:signed(p.realized_profit,0)}</title></circle>`;}).join("");
  const hasBenchmark=points.some((p)=>p.cumulative_benchmark!=null),benchmarkPath=hasBenchmark?`<path d="${path("cumulative_benchmark")}" class="benchmark" data-closed-animated-path/>`:"";
  const yGrid=Array.from({length:5},(_,index)=>max-span*index/4).map((value)=>{const y=plot.y+(max-value)/span*plotHeight;return `<g><line x1="${plot.x}" y1="${y}" x2="${plot.x+plot.width}" y2="${y}"/><text class="closed-performance-axis-label" x="${plot.x-12}" y="${y+4}" text-anchor="end" direction="rtl">${percent?`${num(value,1)}٪`:esc(closedChartMoney(value))}</text></g>`;}).join("");
  const xIndexes=[0,Math.floor((points.length-1)/2),points.length-1].filter((value,index,array)=>array.indexOf(value)===index),xGrid=xIndexes.map((index,labelIndex)=>{const [x]=xy(0,index),label=points[index].exit_date_display||points[index].exit_date||"—";return `<g><text x="${x}" y="217" text-anchor="${labelIndex===0?"start":labelIndex===xIndexes.length-1?"end":"middle"}" direction="ltr">${esc(label)}</text></g>`;}).join("");
  const areaPath=`${path("cumulative_net")} L${xy(0,points.length-1).map((value)=>value.toFixed(2)).join(" ")} L${xy(0,0).map((value)=>value.toFixed(2)).join(" ")} Z`;
  const finalPercent=stats.capital>0?stats.net/stats.capital*100:null;
  return `<div class="closed-chart-legend"><span class="net">خالص پس از کارمزد</span><span class="gross">قبل از کارمزد</span><span class="benchmark">معیار بدون‌ریسک ۴۰٪ سالانه</span></div><div class="closed-chart-scroll"><svg class="closed-performance-line themed-chart" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="closedTrendChartTitle closedTrendChartDescription"><title id="closedTrendChartTitle">روند تجمعی ${percent?"درصد سود":"سود خالص"}</title><desc id="closedTrendChartDescription">${num(stats.count)} معامله با نتیجه ${percent?`${signed(finalPercent,2)} درصد`:signed(stats.net,0)}. برای دیدن جزئیات، نشانگر را روی نمودار حرکت دهید یا نقاط را با کلید Tab انتخاب کنید.</desc><defs><linearGradient id="closedTrendArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--chart-series-1)" stop-opacity=".16"/><stop offset="100%" stop-color="var(--chart-series-1)" stop-opacity="0"/></linearGradient></defs><rect class="closed-chart-plot" x="${plot.x}" y="${plot.y}" width="${plot.width}" height="${plot.height}" fill="transparent"/><g class="closed-chart-grid closed-chart-y-grid">${yGrid}</g><g class="closed-chart-grid closed-chart-x-grid">${xGrid}</g><line x1="${plot.x}" y1="${zeroY}" x2="${plot.x+plot.width}" y2="${zeroY}" class="zero"/><path d="${areaPath}" class="net-area"/><path d="${path("cumulative_gross")}" class="gross" data-closed-animated-path/>${benchmarkPath}<path d="${path("cumulative_net")}" class="net" data-closed-animated-path data-closed-net-path/>${nodes}<line class="closed-chart-cursor hidden" x1="${plot.x}" y1="${plot.y}" x2="${plot.x}" y2="${plot.y+plot.height}"/><circle class="closed-chart-active-point hidden" r="5"/><circle class="closed-chart-animation-head hidden" r="4" aria-hidden="true"/><g class="closed-chart-tooltip hidden" aria-hidden="true"><rect width="176" height="82" rx="3"/><text class="closed-chart-tooltip-date" x="166" y="18" text-anchor="start"></text><text data-closed-tooltip-net x="166" y="38" text-anchor="start"></text><text data-closed-tooltip-gross x="166" y="57" text-anchor="start"></text><text data-closed-tooltip-benchmark x="166" y="76" text-anchor="start"></text></g><rect class="closed-chart-hitbox" x="${plot.x}" y="${plot.y}" width="${plot.width}" height="${plot.height}" fill="transparent" data-closed-chart-cursor aria-hidden="true"/></svg></div><span class="closed-chart-live sr-only" aria-live="polite"></span><p class="chart-text-summary">${percent?`رشد خالص تجمعی نسبت به مجموع سرمایه درگیر ${finalPercent==null?"—":`${signed(finalPercent,2)}٪`} است.`:`سود خالص تجمعی ${signed(stats.net,0)} است و بیشترین افت از قله قبلی ${num(stats.maxDrawdown,0)} بوده است.`} معیار مقایسه با نرخ ساده سالانه ۴۰٪ و متناسب با سرمایه و روزهای هر معامله محاسبه می‌شود.</p>`;
}

function bindClosedPerformanceLineChart(container,mode="amount") {
  cancelAnimationFrame(closedPerformanceAnimationFrame);
  closedPerformanceResizeObserver?.disconnect();
  closedPerformanceResizeObserver=null;
  const svg=container?.querySelector(".closed-performance-line"),hitbox=svg?.querySelector("[data-closed-chart-cursor]"),nodes=svg?[...svg.querySelectorAll("[data-closed-chart-point]")]:[];
  if(!svg||!hitbox||!nodes.length)return;
  let tooltipScale=1;
  const sizeChartText=()=>{const viewBoxWidth=svg.viewBox.baseVal.width||490,renderedWidth=svg.getBoundingClientRect().width;if(!renderedWidth)return;const scale=renderedWidth/viewBoxWidth,targetSize=Math.min(15,Math.max(13.5,renderedWidth/73.333));tooltipScale=1/scale;svg.style.setProperty("--closed-performance-axis-font-size",`${targetSize/scale}px`);};
  sizeChartText();
  if("ResizeObserver" in window){closedPerformanceResizeObserver=new ResizeObserver(sizeChartText);closedPerformanceResizeObserver.observe(svg);}
  const plot={x:96,y:12,width:350,height:184},cursor=svg.querySelector(".closed-chart-cursor"),active=svg.querySelector(".closed-chart-active-point"),tooltip=svg.querySelector(".closed-chart-tooltip"),dateText=tooltip.querySelector(".closed-chart-tooltip-date"),netText=tooltip.querySelector("[data-closed-tooltip-net]"),grossText=tooltip.querySelector("[data-closed-tooltip-gross]"),benchmarkText=tooltip.querySelector("[data-closed-tooltip-benchmark]"),live=container.querySelector(".closed-chart-live"),percent=mode==="percent";
  const formatted=(value)=>value===""?"—":percent?`${signed(Number(value),2)}٪`:closedChartMoney(Number(value));
  const hide=()=>{cursor.classList.add("hidden");active.classList.add("hidden");tooltip.classList.add("hidden");};
  const show=(index,announce=false)=>{const node=nodes[index];if(!node)return;const x=Number(node.getAttribute("cx")),y=Number(node.getAttribute("cy")),tooltipX=x>plot.x+plot.width/2?x-186*tooltipScale:x+10,tooltipY=Math.max(plot.y+4,Math.min(y-90*tooltipScale,plot.y+plot.height-86*tooltipScale));cursor.setAttribute("x1",x);cursor.setAttribute("x2",x);active.setAttribute("cx",x);active.setAttribute("cy",y);tooltip.setAttribute("transform",`translate(${tooltipX} ${tooltipY}) scale(${tooltipScale})`);dateText.textContent=node.dataset.date;netText.textContent=`خالص: ${formatted(node.dataset.net)}`;grossText.textContent=`ناخالص: ${formatted(node.dataset.gross)}`;benchmarkText.textContent=`بدون‌ریسک: ${formatted(node.dataset.benchmark)}`;cursor.classList.remove("hidden");active.classList.remove("hidden");tooltip.classList.remove("hidden");if(announce)live.textContent=`${node.dataset.date}، خالص ${formatted(node.dataset.net)}، ناخالص ${formatted(node.dataset.gross)}`;};
  const nearestIndex=(event)=>{const matrix=svg.getScreenCTM();if(!matrix)return 0;const position=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()),ratio=Math.max(0,Math.min(1,(position.x-plot.x)/plot.width));return Math.round(ratio*(nodes.length-1));};
  hitbox.addEventListener("pointermove",(event)=>show(nearestIndex(event)));
  hitbox.addEventListener("pointerdown",(event)=>show(nearestIndex(event)));
  hitbox.addEventListener("pointerleave",()=>{if(!svg.contains(document.activeElement))hide();});
  nodes.forEach((node,index)=>{node.addEventListener("focus",()=>show(index,true));node.addEventListener("blur",hide);});
  if(matchMedia("(prefers-reduced-motion: reduce)").matches)return;
  const paths=[...svg.querySelectorAll("[data-closed-animated-path]")],netPath=svg.querySelector("[data-closed-net-path]"),head=svg.querySelector(".closed-chart-animation-head"),lengths=paths.map((path)=>path.getTotalLength());
  paths.forEach((path,index)=>{path.style.strokeDasharray=`${lengths[index]} ${lengths[index]}`;path.style.strokeDashoffset=String(lengths[index]);});
  head.classList.remove("hidden");
  const duration=1150,start=performance.now(),animate=(now)=>{const progress=Math.min(1,(now-start)/duration),eased=1-Math.pow(1-progress,3);paths.forEach((path,index)=>{path.style.strokeDashoffset=String(lengths[index]*(1-eased));});const point=netPath.getPointAtLength(netPath.getTotalLength()*eased);head.setAttribute("cx",point.x);head.setAttribute("cy",point.y);if(progress<1){closedPerformanceAnimationFrame=requestAnimationFrame(animate);}else{paths.forEach((path)=>{path.style.removeProperty("stroke-dasharray");path.style.removeProperty("stroke-dashoffset");});head.classList.add("hidden");}};
  closedPerformanceAnimationFrame=requestAnimationFrame(animate);
}

function exportClosedPerformanceCsv(rows=[]) {
  const money=(row,key)=>window.NicOptionFinancialCsv.money(row,key);
  const columns=[["استراتژی",r=>r.strategy_type==="long_call"?"خرید Call":"کاوردکال"],["دارایی پایه",r=>r.asset],["نماد اختیار",r=>r.option_symbol],["تاریخ ورود",r=>r.entry_date],["تاریخ خروج",r=>r.exit_date],["تعداد قرارداد",r=>r.quantity],["اندازه قرارداد",r=>r.contract_size],["واحد پایه",r=>r.underlying_units],["نوع مقدار",r=>r.quantity_kind],["واحد پول",r=>r.currency_unit],["نسخه محاسبه",r=>r.calculation_version],["مدت نگهداری",r=>r.invested_days],["سرمایه درگیر",r=>money(r,"invested_capital")],["سود خالص",r=>money(r,"realized_profit")],["بازده خالص",r=>r.realized_profit_percent],["کل کارمزد",r=>money(r,"realized_commission")],["سود معیار",r=>money(r,"benchmark_profit")],["مازاد سود",r=>money(r,"excess_profit")]];
  const csv="\uFEFF"+window.NicOptionFinancialCsv.render(columns,rows);
  const link=document.createElement("a");link.href=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));link.download=`nicoption-closed-performance-${new Date().toISOString().slice(0,10)}.csv`;link.click();URL.revokeObjectURL(link.href);
}

function closedDistributionChart(rows,mode="return") {
  const key=mode==="profit"?"realized_profit":mode==="days"?"invested_days":"realized_profit_percent";
  const values=rows.map((r)=>finiteNumber(r[key])).filter((v)=>v!=null);
  if(!values.length) return '<div class="closed-empty-state">داده کافی برای توزیع وجود ندارد.</div>';
  const min=Math.min(...values),max=Math.max(...values),bins=Math.min(9,Math.max(3,Math.ceil(Math.sqrt(values.length)))),step=(max-min||1)/bins;
  const data=Array.from({length:bins},(_,i)=>({from:min+i*step,to:i===bins-1?max:min+(i+1)*step,covered:0,long:0}));
  rows.forEach((r)=>{const value=finiteNumber(r[key]);if(value==null)return;const index=Math.min(bins-1,Math.floor((value-min)/(step||1)));data[index][r.strategy_type==="long_call"?"long":"covered"]+=1;});
  const tallest=Math.max(1,...data.map((b)=>b.covered+b.long));
  const average=values.reduce((a,b)=>a+b,0)/values.length,middle=median(values);
  const width=940,height=330,margin={top:22,right:20,bottom:68,left:62};
  const plotWidth=width-margin.left-margin.right,plotHeight=height-margin.top-margin.bottom,groupWidth=plotWidth/bins,barWidth=Math.min(26,groupWidth*.28);
  const yTicks=[...new Set(Array.from({length:5},(_,index)=>Math.round(tallest*index/4)))].sort((a,b)=>a-b);
  const yGrid=yTicks.map((value)=>{const y=margin.top+plotHeight-value/tallest*plotHeight;return `<g><line x1="${margin.left}" y1="${y}" x2="${width-margin.right}" y2="${y}"/><text x="${margin.left-12}" y="${y+4}" text-anchor="end">${num(value)}</text></g>`;}).join("");
  const valueLabel=(value)=>mode==="return"?`${num(value,1)}٪`:mode==="days"?`${num(value,0)} روز`:closedChartMoney(value);
  const bars=data.map((bin,index)=>{
    const center=margin.left+groupWidth*(index+.5),coveredHeight=bin.covered/tallest*plotHeight,longHeight=bin.long/tallest*plotHeight;
    const label=`${valueLabel(bin.from)} تا ${valueLabel(bin.to)}`;
    return `<g class="closed-distribution-bin"><line class="bin-guide" x1="${center}" y1="${margin.top}" x2="${center}" y2="${margin.top+plotHeight}"/><rect class="covered" x="${center-barWidth-2}" y="${margin.top+plotHeight-coveredHeight}" width="${barWidth}" height="${Math.max(0,coveredHeight)}" rx="4"><title>${esc(label)} · کاوردکال ${num(bin.covered)}</title></rect><rect class="long" x="${center+2}" y="${margin.top+plotHeight-longHeight}" width="${barWidth}" height="${Math.max(0,longHeight)}" rx="4"><title>${esc(label)} · خرید Call ${num(bin.long)}</title></rect><text x="${center}" y="${height-margin.bottom+25}" text-anchor="middle" direction="rtl">${esc(label)}</text></g>`;
  }).join("");
  return `<div class="closed-distribution-summary"><span><small>میانگین</small><strong>${esc(valueLabel(average))}</strong></span><span><small>میانه</small><strong>${esc(valueLabel(middle))}</strong></span><span><small>تعداد نمونه</small><strong>${num(values.length)}</strong></span></div><div class="closed-chart-scroll"><svg class="closed-distribution-chart themed-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="توزیع ${values.length} معامله؛ میانگین ${valueLabel(average)} و میانه ${valueLabel(middle)}"><g class="closed-chart-grid closed-chart-y-grid">${yGrid}</g>${bars}<text class="closed-chart-axis-title" x="${margin.left}" y="14">تعداد معاملات</text></svg></div><div class="closed-chart-legend"><span class="covered">کاوردکال</span><span class="long">خرید Call</span></div>`;
}

function closedMonthlyHeatmap(rows) {
  const months=new Map();rows.forEach((r)=>{if(!r.exit_date)return;const key=String(r.exit_date).slice(0,7);if(!months.has(key))months.set(key,{profit:0,count:0,best:null,worst:null});const cell=months.get(key),v=finiteNumber(r.realized_profit)||0;cell.profit+=v;cell.count+=1;cell.best=cell.best==null?v:Math.max(cell.best,v);cell.worst=cell.worst==null?v:Math.min(cell.worst,v);});
  if(!months.size)return '<div class="closed-empty-state">ماه قابل محاسبه‌ای وجود ندارد.</div>';
  const max=Math.max(1,...[...months.values()].map((v)=>Math.abs(v.profit)));
  return `<div class="closed-month-grid">${[...months.entries()].sort().map(([key,cell])=>`<button type="button" style="--heat:${Math.abs(cell.profit)/max}" class="${cell.profit>=0?"positive":"negative"}" aria-label="ماه ${key}، ${cell.count} معامله، سود خالص ${cell.profit}"><span>${esc(key)}</span><strong dir="ltr">${signed(cell.profit,0)}</strong><small>${num(cell.count)} معامله</small><span class="heat-tooltip">بهترین ${signed(cell.best,0)} · بدترین ${signed(cell.worst,0)}</span></button>`).join("")}</div>`;
}

function renderClosedPerformanceDashboard(allTrades = []) {
  const isPerformanceReport=currentPage==="profit-recognition";
  const host=$(isPerformanceReport?"performanceDashboard":"closedPerformanceDashboard"); if(!host)return;
  const params=new URLSearchParams(location.search);
  const allRows=closedEpisodeRows(allTrades);
  const strategy=params.get("closed_strategy")||"all",asset=params.get("closed_asset")||"all",exit=params.get("closed_exit")||"all",result=params.get("closed_result")||"all",range=params.get("closed_range")||"all",moneyness=params.get("closed_money")||"all",dte=params.get("closed_dte")||"all",sort=params.get("closed_sort")||"date_desc",distribution=params.get("closed_distribution")||"return",trendMode=params.get("closed_trend")==="percent"?"percent":"amount";
  const latest=allRows.map((r)=>new Date(r.exit_date)).filter((d)=>!Number.isNaN(d.valueOf())).sort((a,b)=>b-a)[0]||new Date();
  const rangeDays={"30d":30,"3m":90,"6m":180,"1y":365}[range];
  const cutoff=rangeDays?new Date(latest.getTime()-rangeDays*86400000):null;
  const dteMatches=(row)=>dte==="all"||(dte==="short"&&Number(row.entry_dte)<=30)||(dte==="medium"&&Number(row.entry_dte)>30&&Number(row.entry_dte)<=60)||(dte==="long"&&Number(row.entry_dte)>60);
  const rangeMatches=(row)=>range==="year"?new Date(row.exit_date).getFullYear()===latest.getFullYear():!cutoff||new Date(row.exit_date)>=cutoff;
  let rows=allRows.filter((r)=>(strategy==="all"||r.strategy_type===strategy)&&(asset==="all"||r.asset===asset)&&(exit==="all"||r.final_status===exit)&&(result==="all"||(result==="win"?Number(r.realized_profit)>0:Number(r.realized_profit)<0))&&(moneyness==="all"||r.entry_moneyness===moneyness)&&dteMatches(r)&&rangeMatches(r));
  rows.sort((a,b)=>sort==="profit_desc"?Number(b.realized_profit)-Number(a.realized_profit):sort==="return_desc"?Number(b.realized_profit_percent)-Number(a.realized_profit_percent):sort==="days_desc"?Number(b.invested_days)-Number(a.invested_days):String(b.exit_date||"").localeCompare(String(a.exit_date||"")));
  const stats=closedPerformanceStats(rows),covered=rows.filter((r)=>(r.strategy_type||"covered_call")==="covered_call"),long=rows.filter((r)=>r.strategy_type==="long_call"),coveredStats=closedPerformanceStats(covered),longStats=closedPerformanceStats(long);
  const assets=[...new Set(allRows.map((r)=>r.asset).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"fa"));
  const options=(values,current)=>values.map(([value,label])=>`<option value="${value}" ${current===value?"selected":""}>${label}</option>`).join("");
  const kpi=`<div class="closed-primary-kpis">${closedMetric("سود خالص تحقق‌یافته",signed(stats.net,0),`ناخالص ${num(stats.gross,0)} · کارمزد ${num(stats.fees,0)}`,profitTone(stats.net))}${closedMetric("بازده خالص سرمایه",stats.returnPercent==null?"—":`${signed(stats.returnPercent,2)}٪`,`سرمایه مبنا ${num(stats.capital,0)}`,profitTone(stats.returnPercent))}${closedMetric("امید ریاضی هر معامله",signed(stats.expectancy,0),`درصدی ${metricOrDash(stats.expectancyPercent,2,"٪")} · برد ${metricOrDash(stats.avgWin,0)} · باخت ${metricOrDash(stats.avgLoss,0)}`,profitTone(stats.expectancy))}${closedMetric(stats.drawdownScopeLabel,stats.count?num(stats.maxDrawdown,0):"—",`بر اساس ترتیب خروج‌ها · بازیابی ${stats.recoveryDays==null?"—":`${num(stats.recoveryDays)} روز`} · زنجیره زیان ${num(stats.maxLossStreak)}`,stats.maxDrawdown>0?"profit-down":"")}</div>`;
  const strip=[["معامله",stats.count],["سودده",stats.wins],["زیان‌ده",stats.losses],["نرخ برد",stats.winRate==null?"—":`${num(stats.winRate*100,1)}٪`],["Profit Factor",metricOrDash(stats.profitFactor,2)],["نسبت برد/باخت",metricOrDash(stats.payoffRatio,2)],["میانه مدت نگهداری",stats.medianDays==null?"—":`${num(stats.medianDays,1)} روز`],["کل کارمزد",num(stats.fees,0)]].map(([l,v])=>`<div><span>${l}</span><b dir="ltr">${v}</b></div>`).join("");
  const strategyTable=(s)=>`<td>${num(s.count)}</td><td class="${profitTone(s.net)}">${signed(s.net,0)}</td><td>${metricOrDash(s.returnPercent,2,"٪")}</td><td>${metricOrDash(s.winRate==null?null:s.winRate*100,1,"٪")}</td><td>${metricOrDash(s.profitFactor,2)}</td><td>${metricOrDash(s.expectancy,0)}</td><td>${metricOrDash(s.averageDays,1," روز")}</td><td>${metricOrDash(s.maxDrawdown,0)}</td>`;
  const coveredPremium=covered.reduce((s,r)=>s+(finiteNumber(r.premium_cashflow)||0),0),coveredOption=covered.reduce((s,r)=>s+(finiteNumber(r.option_component_profit)||0),0),coveredFees=covered.reduce((s,r)=>s+(finiteNumber(r.realized_commission)||0),0),coveredBase=covered.reduce((s,r)=>s+(finiteNumber(r.base_component_profit)||0),0);
  const longPremium=long.reduce((s,r)=>s+(finiteNumber(r.premium_cashflow)||0),0);
  const feeShare=stats.gross?Math.abs(stats.fees/stats.gross*100):null;
  const insightItems=[];
  if(feeShare!=null) insightItems.push({tone:feeShare>15?"warning":"info",title:"اثر هزینه‌ها",text:`کارمزدها ${num(feeShare,1)}٪ از سود ناخالص را جذب کرده‌اند.`,n:stats.count});
  if(coveredStats.count&&longStats.count) insightItems.push({tone:coveredStats.net>=longStats.net?"positive":"info",title:"مقایسه استراتژی",text:`سود خالص ${coveredStats.net>=longStats.net?"کاوردکال":"خرید Call"} در این فیلتر بیشتر بوده است.`,n:coveredStats.count+longStats.count});
  if(stats.avgLoss!=null&&stats.avgWin!=null&&Math.abs(stats.avgLoss)>stats.avgWin) insightItems.push({tone:"warning",title:"کیفیت باخت‌ها",text:"میانگین زیان از میانگین سود معاملات موفق بزرگ‌تر است.",n:stats.losses});
  const shortDteLosses=long.filter((r)=>Number(r.entry_dte)<=30&&Number(r.realized_profit)<0).length;
  if(shortDteLosses) insightItems.push({tone:"warning",title:"ریسک سررسید کوتاه",text:`${num(shortDteLosses)} خرید Call با DTE ورود حداکثر ۳۰ روز زیان‌ده بوده است.`,n:long.length});
  const insights=insightItems.slice(0,4).map((item)=>`<article class="performance-insight ${item.tone}"><span>${esc(item.title)}</span><p>${esc(item.text)}</p><small>نمونه: ${num(item.n)} دوره بسته</small></article>`).join("")||'<div class="closed-empty-state compact">برای تولید بینش، نمونه بیشتری لازم است.</div>';
  const cashflow=`<div class="performance-waterfall" role="img" aria-label="سود ناخالص ${stats.gross}، هزینه‌ها ${stats.fees} و سود خالص ${stats.net}"><div class="gross"><span>سود ناخالص</span><b dir="ltr">${signed(stats.gross,0)}</b></div><i aria-hidden="true">−</i><div class="fees"><span>کارمزد و هزینه ثبت‌شده</span><b dir="ltr">${num(stats.fees,0)}</b></div><i aria-hidden="true">=</i><div class="net"><span>سود خالص واقعی</span><b class="${profitTone(stats.net)}" dir="ltr">${signed(stats.net,0)}</b></div></div><p class="performance-data-note">مالیات، واریز و برداشت در داده‌های فعلی ثبت نشده‌اند؛ بنابراین با «—» گزارش می‌شوند و مقدار صفر فرض نشده است.</p>`;
  const tableRows=rows.slice(0,closedPerformanceLimit).map((r)=>`<tr><td data-label="استراتژی"><span class="strategy-dot ${r.strategy_type==="long_call"?"long":"covered"}"></span>${r.strategy_type==="long_call"?"خرید Call":"کاوردکال"}</td><td data-label="نماد"><strong>${esc(r.asset)}</strong><small>${esc(r.option_symbol)}</small></td><td data-label="ورود">${esc(r.entry_date_display||r.entry_date||"—")}</td><td data-label="خروج">${esc(r.exit_date_display||r.exit_date||"—")}</td><td data-label="مدت">${num(r.invested_days)} روز</td><td data-label="سرمایه" dir="ltr">${num(r.invested_capital,0)}</td><td data-label="نوع خروج">${esc(r.exit_method_label||r.final_status)}</td><td data-label="سود خالص" class="${profitTone(r.realized_profit)}" dir="ltr">${signed(r.realized_profit,0)}</td><td data-label="بازده" class="${profitTone(r.realized_profit_percent)}" dir="ltr">${signed(r.realized_profit_percent,2)}٪</td><td data-label="کارمزد" dir="ltr">${num(r.realized_commission,0)}</td><td data-label="معیار" dir="ltr">${metricOrDash(r.benchmark_profit,0)}</td><td data-label="مازاد" class="${profitTone(r.excess_profit)}" dir="ltr">${r.excess_profit==null?"—":signed(r.excess_profit,0)}</td><td data-label="جزئیات"><button type="button" class="secondary-button closed-detail-button" data-closed-detail="${esc(r.detail_id)}">جزئیات</button></td></tr>`).join("");
  host.innerHTML=`<header class="closed-performance-title"><div><small>کارنامه واقعی پس از همه هزینه‌های ثبت‌شده</small><h2>${isPerformanceReport?"گزارش عملکرد":"عملکرد معاملات بسته‌شده"}</h2><p>فقط موقعیت‌های کاملاً بسته؛ سود و زیان تحقق‌نیافتهٔ معاملات باز در این گزارش محاسبه نمی‌شود.</p></div><div class="performance-title-actions"><span>${num(rows.length)} از ${num(allRows.length)} دوره</span><a class="secondary-button" href="/methodology">روش محاسبات</a><button type="button" class="secondary-button" data-performance-export>خروجی CSV</button></div></header>
  <form class="closed-filter-bar" aria-label="فیلتر عملکرد معاملات بسته"><label><span>بازه زمانی</span><select name="closed_range">${options([["all","کل دوره"],["30d","۳۰ روز"],["3m","۳ ماه"],["6m","۶ ماه"],["year","امسال"],["1y","یک سال"]],range)}</select></label><label><span>استراتژی</span><select name="closed_strategy">${options([["all","همه"],["covered_call","کاوردکال"],["long_call","خرید Call"]],strategy)}</select></label><label><span>دارایی پایه</span><select name="closed_asset"><option value="all">همه نمادها</option>${assets.map((v)=>`<option ${asset===v?"selected":""}>${esc(v)}</option>`).join("")}</select></label><label><span>نوع خروج</span><select name="closed_exit">${options([["all","همه خروج‌ها"],["offset","فروش/آفست"],["exercise","اعمال"],["expired","انقضا"],["roll","رول"]],exit)}</select></label><label><span>نتیجه</span><select name="closed_result">${options([["all","سود و زیان"],["win","سودده"],["loss","زیان‌ده"]],result)}</select></label><label><span>وضعیت ورود</span><select name="closed_money">${options([["all","همه"],["ITM","ITM"],["ATM","ATM"],["OTM","OTM"]],moneyness)}</select></label><label><span>DTE ورود</span><select name="closed_dte">${options([["all","همه"],["short","تا ۳۰ روز"],["medium","۳۱ تا ۶۰"],["long","بیش از ۶۰"]],dte)}</select></label><label><span>مرتب‌سازی</span><select name="closed_sort">${options([["date_desc","جدیدترین"],["profit_desc","بیشترین سود"],["return_desc","بیشترین بازده"],["days_desc","بیشترین نگهداری"]],sort)}</select></label><button type="button" class="secondary-button" data-reset-closed-filters>پاک‌کردن</button></form>
  ${rows.length?kpi:`<div class="closed-empty-state"><strong>${allRows.length?"برای این فیلتر معامله‌ای وجود ندارد":"هنوز معامله کاملاً بسته‌شده‌ای ثبت نشده است"}</strong><p>${allRows.length?"فیلترها را تغییر دهید.":"پس از ثبت خروج کامل، آمار واقعی اینجا نمایش داده می‌شود."}</p></div>`}
  ${rows.length?`<div class="closed-secondary-strip">${strip}</div><div class="closed-dashboard-grid"><section class="closed-panel performance-trend"><header><div><small>روند زمانی</small><h3>روند سود و زیان تحقق‌یافته</h3></div><div class="closed-trend-mode" role="group" aria-label="مبنای محور عمودی نمودار"><button type="button" data-closed-trend="amount" aria-pressed="${trendMode==="amount"}">رشد عددی حساب</button><button type="button" data-closed-trend="percent" aria-pressed="${trendMode==="percent"}">رشد درصدی</button></div></header>${closedPerformanceLineChart(stats,trendMode)}</section><aside class="closed-panel performance-insights"><header><div><small>تحلیل خودکار توصیفی</small><h3>بینش‌های این دوره</h3></div></header><div>${insights}</div></aside><section class="closed-panel strategy-comparison"><header><div><small>سرمایه و بازده هم‌زمان</small><h3>عملکرد به تفکیک استراتژی</h3></div></header><div class="table-scroll"><table><thead><tr><th>استراتژی</th><th>تعداد</th><th>سود خالص</th><th>بازده</th><th>نرخ برد</th><th>PF</th><th>امید ریاضی</th><th>روز</th><th>افت</th></tr></thead><tbody><tr><th>کاوردکال</th>${strategyTable(coveredStats)}</tr><tr><th>خرید Call</th>${strategyTable(longStats)}</tr></tbody></table></div></section>
  <section class="closed-panel strategy-deep covered"><header><div><small>درآمد اختیار + تغییر سهم</small><h3>عملکرد کاوردکال</h3></div><span>${num(covered.length)} دوره</span></header><div class="closed-detail-metrics">${closedMetric("پریمیوم دریافتی",num(coveredPremium,0),`خالص اختیار ${signed(coveredOption,0)}`)}${closedMetric("درصد پریمیوم حفظ‌شده",coveredPremium>0?`${signed(coveredOption/coveredPremium*100,2)}٪`:"—","پس از بازخرید و کارمزد",profitTone(coveredOption))}${closedMetric("سود خالص کل",signed(coveredStats.net,0),`سهم ${signed(coveredBase,0)} · اختیار ${signed(coveredOption,0)}`,profitTone(coveredStats.net))}${closedMetric("نرخ اعمال",covered.length?`${num(covered.filter((r)=>r.final_status==="exercise").length/covered.length*100,1)}٪`:"—",`کارمزد ${num(coveredFees,0)}`)}${closedMetric("بازده در برابر نگهداری",metricOrDash(coveredStats.returnPercent,2,"٪"),"هزینه فرصت رشد جدا از زیان واقعی")}${closedMetric("میانگین DTE ورود",metricOrDash(covered.length?covered.reduce((s,r)=>s+(r.entry_dte||0),0)/covered.length:null,1," روز"),"توصیفی؛ تضمین آینده نیست")}</div></section>
  <section class="closed-panel strategy-deep long"><header><div><small>ریسک محدود به پریمیوم</small><h3>عملکرد خرید Call</h3></div><span>${num(long.length)} دوره</span></header><div class="closed-detail-metrics">${closedMetric("پریمیوم پرداختی",num(longPremium,0),`سرمایه مبنا ${num(longStats.capital,0)}`)}${closedMetric("سود خالص",signed(longStats.net,0),`بازده ${metricOrDash(longStats.returnPercent,2,"٪")}`,profitTone(longStats.net))}${closedMetric("میانگین برد",metricOrDash(longStats.avgWin,0),`میانگین باخت ${metricOrDash(longStats.avgLoss,0)}`)}${closedMetric("بهترین / بدترین",`${metricOrDash(longStats.biggestWin,0)} / ${metricOrDash(longStats.biggestLoss,0)}`,"دو سوی توزیع")}${closedMetric("نرخ اعمال",long.length?`${num(long.filter((r)=>r.final_status==="exercise").length/long.length*100,1)}٪`:"—","بر اساس خروج ثبت‌شده")}${closedMetric("انقضای بی‌ارزش",long.length?`${num(long.filter((r)=>r.final_status==="expired").length/long.length*100,1)}٪`:"—","بدون Attribution ساختگی")}</div></section>
  <section class="closed-panel distribution"><header><div><small>میانگین در کنار میانه</small><h3>توزیع معاملات بسته‌شده</h3></div><select data-closed-distribution aria-label="نوع نمودار توزیع">${options([["return","بازده درصدی"],["profit","سود ریالی"],["days","مدت نگهداری"]],distribution)}</select></header>${closedDistributionChart(rows,distribution)}</section>
  <section class="closed-panel win-loss"><header><div><small>برد بدون پنهان‌کردن باخت</small><h3>کیفیت بردها و باخت‌ها</h3></div></header><div class="closed-detail-metrics">${closedMetric("نرخ برد",metricOrDash(stats.winRate==null?null:stats.winRate*100,1,"٪"),`میانگین برد ${metricOrDash(stats.avgWin,0)}`)}${closedMetric("میانگین باخت",metricOrDash(stats.avgLoss,0),`میانه ${metricOrDash(stats.medianLoss,0)}`,profitTone(stats.avgLoss))}${closedMetric("بزرگ‌ترین برد",metricOrDash(stats.biggestWin,0),`بزرگ‌ترین باخت ${metricOrDash(stats.biggestLoss,0)}`)}${closedMetric("زنجیره‌ها",`${num(stats.maxWinStreak)} برد / ${num(stats.maxLossStreak)} باخت`,"به ترتیب زمانی")}${closedMetric("Profit Factor",metricOrDash(stats.profitFactor,2),stats.losses?"سودها ÷ قدرمطلق زیان‌ها":"معامله زیان‌ده کافی نیست")}${closedMetric("امید ریاضی",metricOrDash(stats.expectancy,0),"به‌ازای هر دوره",profitTone(stats.expectancy))}</div>${stats.winRate!=null&&stats.winRate>.5&&stats.avgLoss!=null&&stats.avgWin!=null&&Math.abs(stats.avgLoss)>stats.avgWin?'<p class="closed-risk-warning">نرخ برد بالا است، اما میانگین زیان از میانگین سود معاملات موفق بیشتر است.</p>':""}</section>
  <section class="closed-panel monthly"><header><div><small>مقدار و تعداد در هر سلول</small><h3>ماتریس عملکرد ماهانه</h3></div></header>${closedMonthlyHeatmap(rows)}</section><section class="closed-panel performance-cashflow"><header><div><small>از ناخالص تا خالص</small><h3>جریان سود و هزینه‌ها</h3></div></header>${cashflow}</section><section class="closed-panel performance-risk"><header><div><small>ریسک تحقق‌یافته در نقاط خروج؛ نه MDD روزانه</small><h3>افت ثبت‌شده و بازیابی</h3></div></header><div class="closed-detail-metrics">${closedMetric(stats.drawdownScopeLabel,stats.count?num(stats.maxDrawdown,0):"—","از قله سود تجمعی در خروج‌ها")}${closedMetric("زمان بازیابی",stats.recoveryDays==null?"—":`${num(stats.recoveryDays)} روز`,"بر اساس تاریخ خروج")}${closedMetric("بدترین معامله",metricOrDash(stats.biggestLoss,0),`زنجیره زیان ${num(stats.maxLossStreak)}`,profitTone(stats.biggestLoss))}</div></section></div>
  <details class="closed-advanced"><summary><span><b>آمار پیشرفته</b><small>فقط شاخص‌هایی که داده معتبر دارند</small></span><i>⌄</i></summary><div class="closed-advanced-grid">${closedMetric("انحراف معیار بازده",returnsStd(rows),"بازده معاملات بسته")}${closedMetric("MAE / MFE","—","تاریخچه قیمت طی دوره ثبت نشده است")}${closedMetric("Attribution بر اساس Greeks","—","داده تاریخی Greeks موجود نیست")}${closedMetric("Sharpe / Sortino","—","سری بازده دوره‌ای کافی نیست")}</div></details>
  <section class="closed-panel closed-trades-table"><header><div><small>جمع‌ها پس از اعمال فیلتر</small><h3>جدول معاملات بسته‌شده</h3></div><button id="closedDashboardCsv" class="secondary-button" type="button">خروجی CSV</button></header><div class="table-scroll"><table><thead><tr><th>استراتژی</th><th>نماد</th><th>ورود</th><th>خروج</th><th>مدت</th><th>سرمایه</th><th>نوع خروج</th><th>سود خالص</th><th>بازده</th><th>کارمزد</th><th>معیار</th><th>مازاد</th><th>جزئیات</th></tr></thead><tbody>${tableRows}</tbody><tfoot><tr><th colspan="5">جمع ${num(rows.length)} دوره</th><td>${num(stats.capital,0)}</td><td>—</td><td>${signed(stats.net,0)}</td><td>${metricOrDash(stats.returnPercent,2,"٪")}</td><td>${num(stats.fees,0)}</td><td colspan="3">—</td></tr></tfoot></table></div>${rows.length>closedPerformanceLimit?'<button type="button" class="secondary-button closed-load-more" data-closed-load-more>نمایش معاملات بیشتر</button>':""}</section>`:""}`;
  host.setAttribute("aria-busy","false");
  host.querySelector(".closed-performance-title > div:first-child")?.remove();
  host.querySelector('.performance-title-actions a[href="/methodology"]')?.remove();
  bindClosedPerformanceLineChart(host.querySelector(".performance-trend"),trendMode);
  host.querySelectorAll("select[name^='closed_'],[data-closed-distribution]").forEach((control)=>control.addEventListener("change",()=>{const query=new URLSearchParams(location.search);query.set(control.name||"closed_distribution",control.value);history.replaceState(null,"",`${location.pathname}?${query}`);closedPerformanceLimit=20;renderClosedPerformanceDashboard(state.trades);}));
  host.querySelectorAll("[data-closed-trend]").forEach((button)=>button.addEventListener("click",()=>{const query=new URLSearchParams(location.search);query.set("closed_trend",button.dataset.closedTrend);history.replaceState(null,"",`${location.pathname}?${query}`);renderClosedPerformanceDashboard(state.trades);}));
  host.querySelector("[data-reset-closed-filters]")?.addEventListener("click",()=>{const query=new URLSearchParams(location.search);[...query.keys()].filter((key)=>key.startsWith("closed_")).forEach((key)=>query.delete(key));history.replaceState(null,"",`${location.pathname}${query.toString()?`?${query}`:""}`);closedPerformanceLimit=20;renderClosedPerformanceDashboard(state.trades);});
  host.querySelector("[data-closed-load-more]")?.addEventListener("click",()=>{closedPerformanceLimit+=20;renderClosedPerformanceDashboard(state.trades);});
  host.querySelectorAll("[data-closed-detail]").forEach((button)=>button.addEventListener("click",()=>openTradeDetailWindow(button.dataset.closedDetail,button)));
  host.querySelector("#closedDashboardCsv")?.addEventListener("click",()=>exportClosedPerformanceCsv(rows));
  host.querySelector("[data-performance-export]")?.addEventListener("click",()=>exportClosedPerformanceCsv(rows));
}

function returnsStd(rows=[]) { const values=rows.map((r)=>finiteNumber(r.realized_profit_percent)).filter((v)=>v!=null);if(values.length<2)return "—";const mean=values.reduce((a,b)=>a+b,0)/values.length;return `${num(Math.sqrt(values.reduce((s,v)=>s+(v-mean)**2,0)/(values.length-1)),2)}٪`; }

function dashboardTradeProfit(item) {
  if (item.status === "closed") return finiteNumber(item.realized_profit);
  if (item.strategy_type === "long_call") return finiteNumber(item.long_offset_profit);
  return dashboardCoveredProfitChoice(item).profit;
}

function dashboardCoveredProfitChoice(item) {
  const moneyness=String(item.current_moneyness||item.moneyness||"—").toUpperCase();
  const liquidation=finiteNumber(item.covered_liquidation_profit),hold=finiteNumber(item.covered_hold_profit);
  const liquidationPercent=finiteNumber(item.covered_liquidation_percent),holdPercent=finiteNumber(item.covered_hold_percent);
  const forceHold=moneyness==="OTM";
  const useLiquidation=!forceHold&&liquidation!=null&&(hold==null||liquidation>hold);
  return useLiquidation
    ? {profit:liquidation,percent:liquidationPercent,label:"آفست اختیار و فروش دارایی پایه",moneyness}
    : {profit:hold,percent:holdPercent,label:"نگهداری پوزیشن کاوردکال",moneyness};
}

function dashboardStrategyMatches(item) {
  if (state.dashboardStrategy === "all") return true;
  return (item.strategy_type || "covered_call") === state.dashboardStrategy;
}

function dashboardRangeRows(rows) {
  if (state.dashboardRange === "all" || !rows.length) return rows;
  const latest = rows.map((row) => new Date(row.exit_date)).filter((date) => !Number.isNaN(date.valueOf())).sort((a,b)=>b-a)[0] || new Date();
  if (state.dashboardRange === "year") return rows.filter((row) => new Date(row.exit_date).getFullYear() === latest.getFullYear());
  const days = {"30d":30,"3m":90,"6m":180}[state.dashboardRange];
  if (!days) return rows;
  const cutoff = latest.getTime() - days * 86400000;
  return rows.filter((row) => new Date(row.exit_date).getTime() >= cutoff);
}

function dashboardOpportunityRows() {
  const source = state.data?.top_opportunities || {};
  const flatten = (value) => Object.values(value || {}).flatMap((entry) => Array.isArray(entry) ? entry : []);
  const rank = (a,b) => Number(b.covered_score ?? b.annual_return ?? b.monthly_return ?? 0) - Number(a.covered_score ?? a.annual_return ?? a.monthly_return ?? 0);
  const covered = flatten(source.covered_call).map((item) => ({...item,strategy_type:"covered_call"})).sort(rank);
  const long = flatten(source.long_underlying).map((item) => ({...item,strategy_type:"long_call"})).sort(rank);
  if(state.dashboardStrategy==="covered_call") return covered;
  if(state.dashboardStrategy==="long_call") return long;
  const balanced=[...covered.slice(0,4),...long.slice(0,4)];
  const selected=new Set(balanced);
  return [...balanced,...[...covered,...long].filter((item)=>!selected.has(item)).sort(rank)];
}

function dashboardTrendChart(stats) {
  const points = stats.curve || [];
  if (!points.length) return '<div class="dashboard-empty compact"><strong>هنوز معامله بسته‌شده‌ای ندارید</strong><p>پس از ثبت خروج، روند سود خالص اینجا نمایش داده می‌شود.</p><a href="/trades/open">مشاهده معاملات باز</a></div>';
  const plot={x:72,y:12,width:374,height:184},width=490,height=226,values=points.map((point)=>Number(point.cumulative_net)||0);
  let min=Math.min(0,...values),max=Math.max(0,...values);
  const rawSpan=max-min||1;min-=rawSpan*.08;max+=rawSpan*.08;
  const span=max-min||1,xy=(value,index)=>[plot.x+(points.length===1?.5:index/(points.length-1))*plot.width,plot.y+(max-value)/span*plot.height];
  const path=points.map((point,index)=>`${index?"L":"M"}${xy(Number(point.cumulative_net)||0,index).map((value)=>value.toFixed(2)).join(" ")}`).join(" ");
  const area=`${path} L${xy(0,points.length-1).map((value)=>value.toFixed(2)).join(" ")} L${xy(0,0).map((value)=>value.toFixed(2)).join(" ")} Z`,zeroY=xy(0,0)[1];
  const yGrid=Array.from({length:5},(_,index)=>max-span*index/4).map((value)=>{const y=plot.y+(max-value)/span*plot.height;return `<g><line x1="${plot.x}" y1="${y}" x2="${plot.x+plot.width}" y2="${y}"/><text class="dashboard-trend-axis-label" x="${plot.x-12}" y="${y+4}" text-anchor="end" direction="rtl">${esc(closedChartMoney(value))}</text></g>`;}).join("");
  const xIndexes=[0,Math.floor((points.length-1)/2),points.length-1].filter((value,index,array)=>array.indexOf(value)===index),xGrid=xIndexes.map((index,labelIndex)=>{const [x]=xy(0,index),label=points[index].exit_date_display||points[index].exit_date||"—";return `<g><text x="${x}" y="217" text-anchor="${labelIndex===0?"start":labelIndex===xIndexes.length-1?"end":"middle"}" direction="ltr">${esc(label)}</text></g>`;}).join("");
  const nodes=points.map((point,index)=>{const cumulative=Number(point.cumulative_net)||0,[x,y]=xy(cumulative,index),date=point.exit_date_display||point.exit_date||"—",profit=Number(point.realized_profit)||0,fee=Number(point.realized_commission)||0;return `<circle class="closed-chart-point dashboard-trend-point" data-dashboard-trend-point="${index}" data-date="${esc(date)}" data-cumulative="${cumulative}" data-profit="${profit}" data-fee="${fee}" cx="${x}" cy="${y}" r="4" tabindex="0" aria-label="${esc(date)}، سود تجمعی ${signed(cumulative,0)}"><title>${esc(date)} · سود تجمعی ${signed(cumulative,0)} · تغییر دوره ${signed(profit,0)}</title></circle>`;}).join("");
  return `<div class="dashboard-chart-scroll"><svg class="dashboard-trend-chart closed-performance-line themed-chart" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="dashboardTrendChartTitle dashboardTrendChartDescription"><title id="dashboardTrendChartTitle">روند سود خالص تحقق‌یافته</title><desc id="dashboardTrendChartDescription">${num(stats.count)} معامله با نتیجه ${signed(stats.net,0)}. برای دیدن جزئیات، نشانگر را روی نمودار حرکت دهید یا نقاط را با کلید Tab انتخاب کنید.</desc><defs><linearGradient id="dashboardTrendArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--chart-series-1)" stop-opacity=".16"/><stop offset="100%" stop-color="var(--chart-series-1)" stop-opacity="0"/></linearGradient></defs><rect class="closed-chart-plot" x="${plot.x}" y="${plot.y}" width="${plot.width}" height="${plot.height}" fill="transparent"/><g class="closed-chart-grid closed-chart-y-grid">${yGrid}</g><g class="closed-chart-grid closed-chart-x-grid">${xGrid}</g><line x1="${plot.x}" y1="${zeroY}" x2="${plot.x+plot.width}" y2="${zeroY}" class="zero"/><path d="${area}" class="net-area"/><path d="${path}" class="net" data-dashboard-animated-path data-dashboard-net-path/>${nodes}<line class="closed-chart-cursor hidden" x1="${plot.x}" y1="${plot.y}" x2="${plot.x}" y2="${plot.y+plot.height}"/><circle class="closed-chart-active-point hidden" r="5"/><circle class="closed-chart-animation-head hidden" r="4" aria-hidden="true"/><g class="closed-chart-tooltip dashboard-trend-tooltip hidden" aria-hidden="true"><rect width="184" height="82" rx="3"/><text class="closed-chart-tooltip-date" x="174" y="18" text-anchor="start"></text><text data-dashboard-tooltip-cumulative x="174" y="38" text-anchor="start"></text><text data-dashboard-tooltip-profit x="174" y="57" text-anchor="start"></text><text data-dashboard-tooltip-fee x="174" y="76" text-anchor="start"></text></g><rect class="closed-chart-hitbox" x="${plot.x}" y="${plot.y}" width="${plot.width}" height="${plot.height}" fill="transparent" data-dashboard-chart-cursor aria-hidden="true"/></svg></div><span class="dashboard-chart-live sr-only" aria-live="polite"></span><p class="dashboard-chart-summary">نتیجه خالص دوره ${signed(stats.net,0)} و بیشترین افت از قله قبلی ${num(stats.maxDrawdown,0)} است.</p>`;
}

function bindDashboardTrendChart(container) {
  cancelAnimationFrame(dashboardTrendAnimationFrame);
  dashboardTrendResizeObserver?.disconnect();
  dashboardTrendResizeObserver=null;
  const svg=container?.querySelector(".dashboard-trend-chart"),hitbox=svg?.querySelector("[data-dashboard-chart-cursor]"),nodes=svg?[...svg.querySelectorAll("[data-dashboard-trend-point]")]:[];
  if(!svg||!hitbox||!nodes.length)return;
  let tooltipScale=1;
  const sizeChartText=()=>{
    const viewBoxWidth=svg.viewBox.baseVal.width||490,renderedWidth=svg.getBoundingClientRect().width;
    if(!renderedWidth)return;
    const scale=renderedWidth/viewBoxWidth,targetSize=Math.min(10,Math.max(9,renderedWidth/110));
    tooltipScale=1/scale;
    svg.style.setProperty("--dashboard-axis-font-size",`${targetSize/scale}px`);
  };
  sizeChartText();
  if("ResizeObserver" in window){dashboardTrendResizeObserver=new ResizeObserver(sizeChartText);dashboardTrendResizeObserver.observe(svg);}
  const plot={x:72,y:12,width:374,height:184},cursor=svg.querySelector(".closed-chart-cursor"),active=svg.querySelector(".closed-chart-active-point"),tooltip=svg.querySelector(".dashboard-trend-tooltip"),dateText=tooltip.querySelector(".closed-chart-tooltip-date"),cumulativeText=tooltip.querySelector("[data-dashboard-tooltip-cumulative]"),profitText=tooltip.querySelector("[data-dashboard-tooltip-profit]"),feeText=tooltip.querySelector("[data-dashboard-tooltip-fee]"),live=container.querySelector(".dashboard-chart-live");
  const hide=()=>{cursor.classList.add("hidden");active.classList.add("hidden");tooltip.classList.add("hidden");};
  const show=(index,announce=false)=>{const node=nodes[index];if(!node)return;const x=Number(node.getAttribute("cx")),y=Number(node.getAttribute("cy")),tooltipX=x>plot.x+plot.width/2?x-194*tooltipScale:x+10,tooltipY=Math.max(plot.y+4,Math.min(y-86*tooltipScale,plot.y+plot.height-82*tooltipScale));cursor.setAttribute("x1",x);cursor.setAttribute("x2",x);active.setAttribute("cx",x);active.setAttribute("cy",y);tooltip.setAttribute("transform",`translate(${tooltipX} ${tooltipY}) scale(${tooltipScale})`);dateText.textContent=node.dataset.date;cumulativeText.textContent=`تجمعی: ${closedChartMoney(Number(node.dataset.cumulative))}`;profitText.textContent=`تغییر دوره: ${closedChartMoney(Number(node.dataset.profit))}`;feeText.textContent=`کارمزد: ${closedChartMoney(Number(node.dataset.fee))}`;cursor.classList.remove("hidden");active.classList.remove("hidden");tooltip.classList.remove("hidden");if(announce)live.textContent=`${node.dataset.date}، سود تجمعی ${closedChartMoney(Number(node.dataset.cumulative))}، تغییر دوره ${closedChartMoney(Number(node.dataset.profit))}`;};
  const nearestIndex=(event)=>{const matrix=svg.getScreenCTM();if(!matrix)return 0;const position=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()),ratio=Math.max(0,Math.min(1,(position.x-plot.x)/plot.width));return Math.round(ratio*(nodes.length-1));};
  hitbox.addEventListener("pointermove",(event)=>show(nearestIndex(event)));
  hitbox.addEventListener("pointerdown",(event)=>show(nearestIndex(event)));
  hitbox.addEventListener("pointerleave",()=>{if(!svg.contains(document.activeElement))hide();});
  nodes.forEach((node,index)=>{node.addEventListener("focus",()=>show(index,true));node.addEventListener("blur",hide);});
  if(matchMedia("(prefers-reduced-motion: reduce)").matches)return;
  const path=svg.querySelector("[data-dashboard-animated-path]"),head=svg.querySelector(".closed-chart-animation-head"),length=path.getTotalLength();
  path.style.strokeDasharray=`${length} ${length}`;path.style.strokeDashoffset=String(length);head.classList.remove("hidden");
  const duration=1150,start=performance.now(),animate=(now)=>{const progress=Math.min(1,(now-start)/duration),eased=1-Math.pow(1-progress,3);path.style.strokeDashoffset=String(length*(1-eased));const point=path.getPointAtLength(length*eased);head.setAttribute("cx",point.x);head.setAttribute("cy",point.y);if(progress<1){dashboardTrendAnimationFrame=requestAnimationFrame(animate);}else{path.style.removeProperty("stroke-dasharray");path.style.removeProperty("stroke-dashoffset");head.classList.add("hidden");}};
  dashboardTrendAnimationFrame=requestAnimationFrame(animate);
}

function renderDashboardOverview() {
  const host=$("dashboardOverview");
  if(!host || currentPage!=="overview" || !state.data || !state.lastTradesPayload) return;
  const hasAnyTrade=state.trades.length>0||(state.lastTradesPayload.underlying_positions||[]).length>0;
  const hasOpenTrade=state.trades.some((item)=>item.status!=="closed")||(state.lastTradesPayload.underlying_positions||[]).some((item)=>item.status!=="closed"&&Number(item.available_quantity||0)>0);
  host.classList.toggle("has-no-trades",!hasAnyTrade);
  host.classList.toggle("has-no-open-trades",!hasOpenTrade);
  const nowHour=new Date().getHours(), greeting=nowHour<12?"صبح بخیر":nowHour<18?"وقت بخیر":"شب بخیر";
  const open=state.trades.filter((item)=>item.status!=="closed"&&dashboardStrategyMatches(item));
  const closed=dashboardRangeRows(closedEpisodeRows(state.trades).filter(dashboardStrategyMatches));
  const performance=closedPerformanceStats(closed);
  const valued=open.map((item)=>dashboardTradeProfit(item)).filter((value)=>value!=null);
  const openProfit=valued.length?valued.reduce((sum,value)=>sum+value,0):null;
  const invested=open.reduce((sum,item)=>sum+(finiteNumber(item.invested_capital)||0),0);
  const coveredCapital=open.filter((item)=>(item.strategy_type||"covered_call")==="covered_call").reduce((sum,item)=>sum+(finiteNumber(item.invested_capital)||0),0);
  const longCapital=open.filter((item)=>item.strategy_type==="long_call").reduce((sum,item)=>sum+(finiteNumber(item.invested_capital)||0),0);
  const nearest=[...open].filter((item)=>finiteNumber(item.remaining_days)!=null).sort((a,b)=>Number(a.remaining_days)-Number(b.remaining_days))[0];
  const dueSoon=open.filter((item)=>finiteNumber(item.remaining_days)!=null&&Number(item.remaining_days)<=7);
  const opportunities=dashboardOpportunityRows();
  const urgent=[...open].filter((item)=>finiteNumber(item.remaining_days)!=null&&Number(item.remaining_days)<=5).sort((a,b)=>Number(a.remaining_days)-Number(b.remaining_days)).slice(0,2).map((item)=>({tone:"urgent",label:"فوری",title:`${num(item.remaining_days)} روز تا سررسید ${item.option_symbol||item.asset}`,text:"سناریوی خروج، اعمال یا نگهداری این موقعیت را بررسی کنید.",href:`/trades/${item.id}`,action:"مشاهده معامله"}));
  const generated=state.lastTradesPayload.generated_at||state.data.generated_at;
  const generatedDate=generated?new Date(generated):null;
  if(generatedDate&&!Number.isNaN(generatedDate.valueOf())&&Date.now()-generatedDate.getTime()>30*60*1000) urgent.push({tone:"review",label:"نیازمند بررسی",title:"داده بازار نیاز به تازه‌سازی دارد",text:"برای تصمیم‌گیری، زمان آخرین دریافت قیمت‌ها را بررسی کنید.",href:"/market",action:"مشاهده داده بازار"});
  opportunities.slice(0,Math.max(0,4-urgent.length)).forEach((opportunity)=>urgent.push({tone:"info",label:"اطلاع‌رسانی",title:`فرصت تازه برای ${opportunity.asset||opportunity.symbol||"بازار"}`,text:"این مورد بر اساس معیارهای سامانه شناسایی شده و نیازمند تحلیل شماست.",href:"/opportunities",action:"مشاهده تحلیل"}));
  const rangeLabel={"30d":"۳۰ روز","3m":"۳ ماه","6m":"۶ ماه",year:"امسال",all:"کل دوره"}[state.dashboardRange]||"۳ ماه";
  const strategyLabel=(item)=>item.strategy_type==="long_call"?"خرید Call":"کاوردکال";
  const attentionRank=(item)=>Number(item.remaining_days)<=5?0:["base_closed","quote_unavailable"].includes(item.data_status)?1:2;
  const sortedOpen=[...open].sort((a,b)=>attentionRank(a)-attentionRank(b)||Number(a.remaining_days??9999)-Number(b.remaining_days??9999)||Number(b.invested_capital||0)-Number(a.invested_capital||0));
  const updatedLabel=generatedDate&&!Number.isNaN(generatedDate.valueOf())?generatedDate.toLocaleTimeString("fa-IR",{hour:"2-digit",minute:"2-digit"}):"نامشخص";
  const username=$("currentUsername")?.textContent||"کاربر";
  const alertMarkup=urgent.slice(0,4).map((item)=>`<article class="dashboard-alert ${item.tone}"><span class="dashboard-alert-icon" aria-hidden="true">${item.tone==="urgent"?"!":item.tone==="review"?"◷":"i"}</span><div><small>${esc(item.label)}</small><strong>${esc(item.title)}</strong><p>${esc(item.text)}</p></div><a href="${item.href}">${esc(item.action)}</a></article>`).join("")||'<div class="dashboard-clear"><span aria-hidden="true">✓</span><div><strong>در حال حاضر مورد فوری برای بررسی ندارید</strong><p>موقعیت‌های شما هشدار با اولویت بالا ندارند.</p></div></div>';
  const openStatus=(item)=>{const days=finiteNumber(item.remaining_days);if(days!=null&&days<=5)return {label:"نزدیک سررسید",tone:"warning"};if(item.data_status==="base_closed")return {label:"نماد پایه بسته است",tone:"warning"};if(item.data_status==="quote_unavailable")return {label:"آخرین قیمت موجود نیست",tone:"warning"};return {label:"قیمت آخرین معامله",tone:"normal"};};
  const openRow=(item)=>{const covered=(item.strategy_type||"covered_call")==="covered_call",choice=covered?dashboardCoveredProfitChoice(item):null,profit=covered?choice.profit:finiteNumber(item.long_offset_profit),percent=covered?choice.percent:finiteNumber(item.long_offset_percent),days=finiteNumber(item.remaining_days),status=openStatus(item),money=String(item.current_moneyness||item.moneyness||"—").toUpperCase();return `<article class="dashboard-open-row ${covered?"covered":"long"}"><div><strong>${esc(item.asset||"—")}</strong><small dir="ltr">${esc(item.option_symbol||"—")}</small></div><div class="${profitTone(profit)}" dir="ltr"><b>${profit==null?"—":signed(profit,0)}</b><small>${percent==null?"بدون ارزش‌گذاری":`${signed(percent,1)}٪`}</small>${covered?`<em>${esc(choice.label)}</em>`:"<em>آفست اختیار بر اساس آخرین معامله</em>"}</div><span class="dashboard-moneyness ${money.toLowerCase()}">${esc(money)}</span><span><b>${days==null?"—":num(days)}</b><small>روز</small></span><span class="dashboard-status ${status.tone}">${esc(status.label)}</span><a href="/trades/${esc(item.id)}" aria-label="مشاهده معامله ${esc(item.option_symbol||item.asset)}">مشاهده</a></article>`;};
  const coveredRows=sortedOpen.filter((item)=>(item.strategy_type||"covered_call")==="covered_call").slice(0,5).map(openRow).join("")||'<div class="dashboard-empty compact"><strong>کاوردکال باز ندارید</strong></div>';
  const longRows=sortedOpen.filter((item)=>item.strategy_type==="long_call").slice(0,5).map(openRow).join("")||'<div class="dashboard-empty compact"><strong>اختیار خرید باز ندارید</strong></div>';
  const opportunityMarkup=opportunities.slice(0,4).map((item)=>{const asset=item.asset||item.symbol||"—",annual=finiteNumber(item.annual_return),monthly=finiteNumber(item.monthly_return),days=finiteNumber(item.days??item.remaining_days),strategy=item.strategy_type==="long_call"?"long_underlying":"covered_call",key=`${strategy}|${item.market}|${item.symbol}`;state.details.set(key,{...item,asset,strategy});return `<article class="dashboard-opportunity"><header><span class="strategy-chip ${item.strategy_type==="long_call"?"long":"covered"}">${strategyLabel(item)}</span><small>شناسایی سامانه</small></header><h4>${esc(asset)}</h4><ul><li>${annual==null?"بازده نیازمند بررسی":`بازده سالانه محاسبه‌شده ${num(annual,1)}٪`}</li><li>${days==null?(monthly==null?"اطلاعات قرارداد آماده تحلیل است":`بازده ماهانه ${num(monthly,1)}٪`):`${num(days)} روز تا سررسید`}</li></ul><button type="button" class="dashboard-opportunity-link" data-dashboard-opportunity-detail="${esc(key)}">مشاهده تحلیل</button></article>`;}).join("")||'<div class="dashboard-empty compact"><strong>فرصتی مطابق معیارها پیدا نشد</strong><p>برای بررسی دستی قراردادها به داده‌های بازار بروید.</p><a href="/market">مشاهده داده‌های بازار</a></div>';
  const expiryMarkup=[...open].filter((item)=>finiteNumber(item.remaining_days)!=null).sort((a,b)=>Number(a.remaining_days)-Number(b.remaining_days)).slice(0,4).map((item)=>{const days=Number(item.remaining_days),group=days<=7?"تا هفت روز":days<=30?"هشت تا سی روز":"بیشتر از سی روز";return `<li><span class="timeline-dot ${days<=7?"urgent":""}" aria-hidden="true"></span><div><small>${group}</small><strong>${num(days)} روز دیگر · ${esc(item.option_symbol||item.asset)}</strong><span>${strategyLabel(item)} · ${num(item.quantity||1)} موقعیت</span></div><a href="/trades/${esc(item.id)}">جزئیات</a></li>`;}).join("")||'<div class="dashboard-empty compact"><strong>سررسید فعالی ندارید</strong></div>';
  const recent=[...state.trades].filter(dashboardStrategyMatches).sort((a,b)=>String(b.exit_date||b.entry_date||"").localeCompare(String(a.exit_date||a.entry_date||""))).slice(0,5).map((item)=>`<li><span class="activity-icon" aria-hidden="true">${item.status==="closed"?"✓":"+"}</span><div><strong>${item.status==="closed"?"معامله بسته شد":"معامله ثبت شد"} · ${esc(item.option_symbol||item.asset)}</strong><small>${strategyLabel(item)} · ${esc(item.exit_date_display||item.entry_date_display||"—")}</small></div><span class="${profitTone(item.status==="closed"?item.realized_profit:dashboardTradeProfit(item))}" dir="ltr">${item.status==="closed"?signed(item.realized_profit,0):"باز"}</span><a href="/trades/${esc(item.id)}">مشاهده</a></li>`).join("")||'<div class="dashboard-empty compact"><strong>هنوز فعالیتی ثبت نشده است</strong></div>';
  host.innerHTML=`<header class="dashboard-header"><div><small>${greeting}، ${esc(username)}</small><h2>مرور تصمیم‌های امروز</h2><p>موقعیت‌ها، فرصت‌ها و عملکرد شما در یک نمای عملیاتی</p><div class="dashboard-market-meta"><span>وضعیت بازار از منبع داده دریافت نشده</span><span>آخرین به‌روزرسانی ${updatedLabel}</span></div></div><div class="dashboard-header-actions"><label class="dashboard-search"><span class="sr-only">جست‌وجوی نماد یا قرارداد</span><input type="search" id="dashboardSearch" placeholder="جست‌وجوی نماد یا قرارداد" autocomplete="off"/><button type="button" aria-label="پاک‌کردن جست‌وجو" hidden>×</button></label><a class="primary-button" href="/trades/new">ثبت معامله</a></div></header><div class="dashboard-filterbar"><div role="group" aria-label="فیلتر استراتژی">${[["all","همه"],["covered_call","کاوردکال"],["long_call","خرید Call"]].map(([value,label])=>`<button type="button" data-dashboard-strategy="${value}" aria-pressed="${state.dashboardStrategy===value}">${label}</button>`).join("")}</div><div role="group" aria-label="بازه زمانی">${[["30d","۳۰ روز"],["3m","۳ ماه"],["6m","۶ ماه"],["year","امسال"],["all","کل دوره"]].map(([value,label])=>`<button type="button" data-dashboard-range="${value}" aria-pressed="${state.dashboardRange===value}">${label}</button>`).join("")}</div></div><section class="dashboard-action-center"><header><div><small>مرکز اقدام امروز</small><h3>چه چیزی به توجه شما نیاز دارد؟</h3></div><span>${num(Math.min(urgent.length,3))} مورد</span></header><div class="dashboard-alerts">${alertMarkup}</div></section><section class="dashboard-kpis" aria-label="شاخص‌های اصلی"><a href="/trades/open"><span>سود و زیان تحقق‌نیافته</span><strong class="${profitTone(openProfit)}" dir="ltr">${openProfit==null?"—":signed(openProfit,0)}</strong><small>${num(open.length)} موقعیت باز · آخرین قیمت معتبر</small></a><a href="/trades/closed"><span>سود خالص تحقق‌یافته</span><strong class="${profitTone(performance.net)}" dir="ltr">${metricOrDash(performance.net,0)}</strong><small>${rangeLabel} · کارمزد کسرشده ${num(performance.fees,0)}</small></a><a href="/trades/open"><span>سرمایه درگیر</span><strong dir="ltr">${num(invested,0)}</strong><small>کاوردکال ${num(coveredCapital,0)} · Call ${num(longCapital,0)}</small></a><a href="/trades/open"><span>نزدیک‌ترین سررسید</span><strong>${nearest?`${num(nearest.remaining_days)} روز`:"—"}</strong><small>${nearest?`${esc(nearest.option_symbol||nearest.asset)} · ${num(dueSoon.length)} مورد تا ۷ روز آینده`:"سررسید فعالی ندارید"}</small></a></section><div class="dashboard-grid"><section class="dashboard-panel open-trades"><header><div><h3>معاملات باز</h3><small>${num(open.length)} موقعیت · محاسبه فقط با آخرین معامله</small></div><a href="/trades/open">مشاهده همه</a></header><div class="dashboard-trade-tables"><section class="dashboard-strategy-table covered"><header><div><span class="strategy-chip covered">کاوردکال</span><strong>${num(sortedOpen.filter((item)=>(item.strategy_type||"covered_call")==="covered_call").length)} موقعیت</strong></div><small>انتخاب سود طبق وضعیت ITM/OTM و سناریوی بهتر</small></header><div class="dashboard-open-head" aria-hidden="true"><span>نماد</span><span>سود و زیان</span><span>وضعیت</span><span>سررسید</span><span>مبنای قیمت</span><span>اقدام</span></div><div class="dashboard-open-list">${coveredRows}</div></section><section class="dashboard-strategy-table long"><header><div><span class="strategy-chip long">خرید اختیار خرید</span><strong>${num(sortedOpen.filter((item)=>item.strategy_type==="long_call").length)} موقعیت</strong></div><small>سود آفست اختیار بر اساس آخرین معامله</small></header><div class="dashboard-open-head" aria-hidden="true"><span>نماد</span><span>سود و زیان</span><span>وضعیت</span><span>سررسید</span><span>مبنای قیمت</span><span>اقدام</span></div><div class="dashboard-open-list">${longRows}</div></section></div></section><section class="dashboard-panel opportunities"><header><div><h3>فرصت‌های جدید</h3><small>پیشنهاد تحلیلی، نه تضمین بازده</small></div><a href="/opportunities">همه فرصت‌ها</a></header><div class="dashboard-opportunity-list">${opportunityMarkup}</div></section><section class="dashboard-panel performance"><header><div><h3>روند سود تحقق‌یافته</h3><small>${rangeLabel}</small></div><a href="/performance">گزارش کامل</a></header><div class="dashboard-performance-summary"><span>سود خالص <b class="${profitTone(performance.net)}" dir="ltr">${metricOrDash(performance.net,0)}</b></span><span>معاملات بسته <b>${num(performance.count)}</b></span><span>افت در خروج‌های ثبت‌شده <b dir="ltr">${num(performance.maxDrawdown,0)}</b></span></div>${dashboardTrendChart(performance)}</section><section class="dashboard-panel expiries"><header><div><h3>سررسیدهای پیش رو</h3><small>مرتب‌شده بر اساس فوریت</small></div><a href="/trades/open">مشاهده همه</a></header><ol class="dashboard-timeline">${expiryMarkup}</ol></section><section class="dashboard-panel activity"><header><div><h3>فعالیت‌های اخیر</h3><small>ثبت و خروج معاملات</small></div><a href="/trades">سوابق معاملات</a></header><ol class="dashboard-activity-list">${recent}</ol></section></div>`;
  const dashboardHero=host.querySelector(".dashboard-header");
  dashboardHero?.classList.add("economic-hero","shared-page-hero","shared-page-hero--dashboard");
  dashboardHero?.firstElementChild?.classList.add("economic-hero-copy");
  if(state.articles.length){
    host.querySelector(".dashboard-grid")?.insertAdjacentHTML("beforeend",`<section class="dashboard-panel latest-articles"><header><div><h3>آخرین مقالات</h3><small>یادداشت‌های تحلیلی و آموزشی</small></div><a href="/articles">همه مقالات</a></header><div class="dashboard-article-list">${state.articles.slice(0,3).map((article)=>`<article><small>${esc(article.published_at_display)}</small><h4><a href="/articles/${encodeURIComponent(article.slug)}">${esc(article.title)}</a></h4><p>${esc(article.summary)}</p><a href="/articles/${encodeURIComponent(article.slug)}">مطالعه مقاله</a></article>`).join("")}</div></section>`);
  }
  const actionCount=host.querySelector(".dashboard-action-center>header>span");
  if(actionCount)actionCount.textContent=`${num(Math.min(urgent.length,4))} مورد`;
  if(!hasAnyTrade) host.querySelector(".dashboard-trade-tables").innerHTML='<div class="dashboard-empty"><strong>هیچ معامله‌ای وارد نشده</strong></div>';
  host.setAttribute("aria-busy","false");
  bindDashboardTrendChart(host.querySelector(".dashboard-panel.performance"));
  host.querySelectorAll("[data-dashboard-opportunity-detail]").forEach((button)=>button.addEventListener("click",()=>openAnalysisByKey(button.dataset.dashboardOpportunityDetail)));
  host.querySelectorAll("[data-dashboard-strategy]").forEach((button)=>button.addEventListener("click",()=>{state.dashboardStrategy=button.dataset.dashboardStrategy;const params=new URLSearchParams(location.search);state.dashboardStrategy==="all"?params.delete("dashboard_strategy"):params.set("dashboard_strategy",state.dashboardStrategy);history.replaceState({},"",`${location.pathname}${params.size?`?${params}`:""}`);renderDashboardOverview();}));
  host.querySelectorAll("[data-dashboard-range]").forEach((button)=>button.addEventListener("click",()=>{state.dashboardRange=button.dataset.dashboardRange;const params=new URLSearchParams(location.search);state.dashboardRange==="3m"?params.delete("dashboard_range"):params.set("dashboard_range",state.dashboardRange);history.replaceState({},"",`${location.pathname}${params.size?`?${params}`:""}`);renderDashboardOverview();}));
  const search=host.querySelector("#dashboardSearch"),clear=host.querySelector(".dashboard-search button");
  search?.addEventListener("input",()=>{clear.hidden=!search.value.trim();const query=faNorm(search.value);host.querySelectorAll(".dashboard-open-row,.dashboard-opportunity").forEach((row)=>row.hidden=!!query&&!faNorm(row.textContent).includes(query));});
  clear?.addEventListener("click",()=>{search.value="";search.dispatchEvent(new Event("input"));search.focus();});
}

function renderTrades(payload) {
  state.lastTradesPayload = payload;
  const currentAsset = $("tradeForm").elements.asset.value;
  const currentSymbol = $("tradeForm").elements.option_symbol.value;
  state.tradeContracts = payload.contracts || [];
  state.trades = payload.trades || [];
  state.account = payload.account || {};
  state.profitRecognition = payload.profit_recognition || {};
  state.accountGrowth = payload.account_growth || {};
  const hasAnyTrade=state.trades.length>0||(payload.underlying_positions||[]).length>0;
  document.body.classList.toggle("has-no-trades",!hasAnyTrade);
  renderDashboardOverview();
  renderUnderlyingPositions(payload);
  populateTradeAssets(currentAsset);
  populateTradeContracts(currentSymbol);
  const openTrades = state.trades.filter((item) => item.status !== "closed").sort((a, b) =>
    Number(a.remaining_days ?? Number.MAX_SAFE_INTEGER) - Number(b.remaining_days ?? Number.MAX_SAFE_INTEGER)
    || String(a.expiry || "").localeCompare(String(b.expiry || ""))
    || String(a.option_symbol || "").localeCompare(String(b.option_symbol || ""), "fa")
  );
  if (typeof window.renderOpenTradesDashboard === "function") {
    window.renderOpenTradesDashboard(payload, openTrades);
  } else {
    const host = $("openTradesDashboard");
    if (host) {
      host.setAttribute("aria-busy", "false");
      host.innerHTML = '<div class="open-empty-state"><strong>نمای معاملات باز بارگذاری نشد</strong><p>صفحه را یک‌بار با حذف کش مرورگر تازه‌سازی کنید.</p></div>';
    }
    console.error("open-trades.js did not load; renderOpenTradesDashboard is unavailable.");
  }
  const closedTrades = state.trades.filter((item) => item.status === "closed").sort((a, b) =>
    String(b.exit_date || "").localeCompare(String(a.exit_date || ""))
    || String(a.option_symbol || "").localeCompare(String(b.option_symbol || ""), "fa")
  );
  renderClosedPerformanceDashboard(state.trades);
  const displayedOpenTrades = openTrades.filter((item) => state.tradeStrategyFilter.open === "all" || (item.strategy_type || "covered_call") === state.tradeStrategyFilter.open);
  const displayedClosedTrades = closedTrades.filter((item) => state.tradeStrategyFilter.closed === "all" || (item.strategy_type || "covered_call") === state.tradeStrategyFilter.closed);
  $("tradesCount").textContent = `${num(openTrades.length)} معامله باز`;
  if ($("openTradeSidebarCount")) $("openTradeSidebarCount").textContent = `${num(displayedOpenTrades.length)} از ${num(openTrades.length)} معامله`;
  $("exportOpenTrades").disabled = openTrades.length === 0;
  renderOpenTradesSummary(payload.summary);
  renderPortfolioAssetLedger(payload.asset_ledger);
  renderAccountGrowth(payload.account_growth, payload.generated_at);
  renderProfitRecognition(payload.profit_recognition, payload.account_growth);
  const renderTradeCard = (item) => {
    const open = item.status !== "closed";
    const isLongCall = item.strategy_type === "long_call";
    const quoteWarning = !open ? `خروج ثبت‌شده ${esc(item.exit_date_display || item.valuation_date_display)}` : item.data_status === "base_closed" ? `<span class="warning">دارایی پایه بسته است؛ سود محاسبه نشده</span>` : item.data_status === "quote_unavailable" ? `<span class="warning">آخرین معامله اختیار یا دارایی پایه در دسترس نیست</span>` : `ارزش‌گذاری با آخرین معامله · ${esc(item.valuation_date_display)}`;
    const comparableProfits = [item.covered_hold_profit, item.covered_option_only_profit, item.covered_liquidation_profit]
      .filter((value) => value != null && Number.isFinite(Number(value)))
      .map(Number);
    const highestProfit = comparableProfits.length ? Math.max(...comparableProfits) : null;
    const isHighest = (value) => highestProfit != null && value != null && Number(value) === highestProfit;
    const liquidationReview = !isLongCall
      && item.covered_liquidation_profit != null
      && item.covered_hold_profit != null
      && Number(item.covered_liquidation_profit) >= Number(item.covered_hold_profit);
    const partialMarker = item.partial_close
      ? '<span class="trade-status partial">بخش بسته‌شده</span>'
      : Number(item.partial_close_count || 0) > 0
      ? `<span class="trade-status partial">مانده پس از ${num(item.partial_close_count)} خروج</span>` : "";
    const strategyBadge = `<span class="trade-strategy ${isLongCall ? "long" : "covered"}">${isLongCall ? "خرید اختیار" : "کاوردکال"}</span>${partialMarker}`;
    const optionPriceLabel = open ? `${isLongCall ? "پرمیوم پرداختی" : "پرمیوم دریافتی"} ← ${esc(item.option_valuation_basis || "مبنای انتخابی")}` : "پرمیوم ورود ← قیمت خروج";
    const basePriceLabel = open ? `پایه ورود ← ${esc(item.base_valuation_basis || "مبنای انتخابی")}` : "پایه ورود ← قیمت خروج";
    const coveredReturns = `${decisionReturnBox("آفست اختیار و فروش دارایی پایه", `اختیار: ${item.option_valuation_basis || "—"} | پایه: ${item.base_valuation_basis || "—"}`, item.covered_liquidation_profit, item.covered_liquidation_percent, "بستن کامل پوزیشن", isHighest(item.covered_liquidation_profit), liquidationReview)}${decisionReturnBox("نگهداری پوزیشن کاوردکال", "اعمال − قیمت پایه ورود + پرمیوم دریافتی", item.covered_hold_profit, item.covered_hold_percent, "سود کاوردکال", isHighest(item.covered_hold_profit))}${decisionReturnBox("آفست اختیار و نگهداری دارایی پایه", `خرید مجدد اختیار با ${item.option_valuation_basis || "—"}`, item.covered_option_only_profit, item.covered_option_only_percent, "دارایی پایه فروخته نمی‌شود", isHighest(item.covered_option_only_profit))}`;
    const returns = isLongCall ? longCallReturnBoxes(item) : coveredReturns;
    const sixthMetric = isLongCall ? `<span>نرخ بهره دوره (a)</span><b>${num(Number(item.period_interest_rate || 0) * 100, 2)}٪</b>` : `<span>تغییر دارایی پایه</span><b class="${profitTone(item.base_profit)}">${signed(item.base_profit, 0)}</b>`;
    const allocationMetrics = isLongCall ? `<div class="trade-allocation-group"><div><span>تعداد برای اعمال</span><b>${qty(item.exercise_quantity)}</b></div><div><span>تعداد برای نوسان‌گیری</span><b>${qty(item.premium_trade_quantity)}</b></div><div><span>نقدینگی اعمال بخش تخصیص‌یافته</span><b>${num(item.exercise_allocation_required_cash,0)}</b></div></div>` : "";
    const exitNote = !open && item.exit_note ? `<p class="trade-exit-note"><b>یادداشت خروج:</b> ${esc(item.exit_note)}</p>` : "";
    const exitMethodLabel = item.exit_method === "exercise" ? (isLongCall ? "اعمال قرارداد" : "تخصیص و فروش دارایی پایه") : item.exit_method === "mixed" ? "خروج ترکیبی: اعمال + آفست" : "آفست قرارداد";
    const realizedResult = !open ? `<div class="realized-result"><div><span>سود یا زیان قطعی</span><strong class="${profitTone(item.realized_profit)}">${signed(item.realized_profit, 0)}</strong></div><div><span>درصد سود</span><strong class="${profitTone(item.realized_profit_percent)}">${signed(item.realized_profit_percent)}٪</strong></div><div><span>مدت معامله</span><strong>${num(item.invested_days)} روز</strong></div><div><span>درصد سود سالانه (YOY)</span><strong class="${profitTone(item.realized_profit_yoy)}">${signed(item.realized_profit_yoy)}٪</strong></div><div><span>روش خروج</span><strong>${esc(exitMethodLabel)}</strong></div></div>` : "";
    const entryAnalytics = tradeAnalyticsSnapshot(item, "entry", "وضعیت هنگام ورود");
    const latestAnalytics = open
      ? tradeAnalyticsSnapshot(item, "current", "وضعیت فعلی بازار")
      : tradeAnalyticsSnapshot(item, "exit", "وضعیت هنگام خروج");
    const analyticsHistory = entryAnalytics || latestAnalytics
      ? `<details class="trade-analytics-details"><summary><span>${open ? "وضعیت هنگام ورود و وضعیت فعلی" : "وضعیت هنگام ورود و خروج"}</span><b><i>بیشتر</i><i>کمتر</i></b></summary><div class="trade-analytics-history">${entryAnalytics}${latestAnalytics}</div></details>`
      : "";
    const commissionLabel = open ? `کارمزد ورود ${num(item.commission, 0)}` : `کارمزد ورود ${num(item.commission, 0)} · خروج ${num(item.exit_commission, 0)}`;
    const timelineFooter = open ? `${num(item.strategy_progress_percent, 1)}٪ از دوره · ${num(item.remaining_days)} روز باقی‌مانده` : `مدت نگهداری ${num(item.invested_days)} روز · خروج ${esc(item.exit_date_display)}`;
    const remainingLabel = open ? "روز باقی‌مانده" : "روز مانده تا سررسید هنگام خروج";
    const premiumChangeTone = item.premium_price_change_percent == null
      ? ""
      : profitTone(isLongCall ? item.premium_price_change_percent : -Number(item.premium_price_change_percent));
    const timelineProgress=Math.max(0,Math.min(100,Number(item.strategy_progress_percent)||0));
    const quantityMeta = Number(item.calculation_version || 7) >= 8
      ? `${qty(item.quantity)} قرارداد × ضریب ${qty(item.contract_size)}`
      : `${qty(item.quantity)} واحد · نسخه محاسبه قدیمی`;
    return `<article class="trade-card" data-trade-id="${esc(item.id)}"><header><div><div class="trade-card-title"><strong>${esc(item.asset)}</strong><span class="symbol">${esc(item.option_symbol)}</span>${strategyBadge}<span class="trade-status ${open ? "open" : "closed"}">${open ? "باز" : "بسته"}</span>${baseClosedTag(item)}${tradeItmTag(item)}</div><small>${marketLabel(item.market)} · ورود ${esc(item.entry_date_display)} · سررسید ${esc(item.expiry_display)}</small></div><small>${quoteWarning}</small></header><div class="trade-timeline"><div><span>خط زمانی استراتژی</span><b>${num(item.elapsed_days)} روز از ${num(item.entry_days)} روز گذشته</b></div><div class="trade-timeline-track" style="--timeline-progress:${timelineProgress}" role="progressbar" aria-label="پیشرفت زمانی استراتژی" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${num(timelineProgress, 0)}"><i style="width:${timelineProgress}%"></i></div><small>${timelineFooter}</small></div><div class="trade-prices"><div><span>${basePriceLabel}</span><b>${num(item.entry_base_price, 2)} ← ${num(item.current_base_price, 2)}</b><small class="trade-price-change ${profitTone(item.base_price_change_percent)}">تغییر ${signed(item.base_price_change_percent, 2)}٪</small></div><div><span>${optionPriceLabel}</span><b>${num(item.entry_premium, 2)} ← ${num(item.current_option_exit_price, 2)}</b><small class="trade-price-change ${premiumChangeTone}">تغییر ${signed(item.premium_price_change_percent, 2)}٪</small></div><div><span>قیمت اعمال</span><b>${num(item.strike, 2)}</b></div><div><span>${isLongCall ? "سرمایه خرید اختیار با کارمزد" : "سرمایه خالص ورود با کارمزد"}</span><b>${num(item.invested_capital, 0)}</b></div><div><span>${remainingLabel}</span><b>${num(item.remaining_days)}</b></div><div>${sixthMetric}</div>${allocationMetrics}</div>${realizedResult}${analyticsHistory}${exitNote}<div class="trade-returns ${isLongCall ? "long-call" : ""}">${returns}</div><footer><span>${quantityMeta} · ${commissionLabel}</span><div class="trade-actions">${open ? `<button class="trade-action detail" type="button" data-trade-detail="${esc(item.id)}">بیشتر</button><button class="trade-action" type="button" data-trade-action="edit" data-trade-id="${esc(item.id)}">ویرایش</button>` : `<button class="trade-action detail" type="button" data-trade-detail="${esc(item.id)}">بیشتر</button>`}<button class="trade-action" type="button" data-trade-action="close" data-trade-id="${esc(item.id)}">${open ? "ثبت خروج" : "ویرایش خروج"}</button><button class="trade-action danger" type="button" data-trade-action="delete" data-trade-id="${esc(item.id)}">حذف</button></div></footer></article>`;
  };
  const tradeGroups = [
    {type: "covered_call", title: "معاملات کاوردکال", subtitle: "فروش اختیار خرید در کنار نگهداری دارایی پایه"},
    {type: "long_call", title: "معاملات خرید اختیار خرید", subtitle: "رشد پرمیوم و مقایسه با دارایی پایه با لحاظ نرخ بهره"},
  ];
  $("tradesList").innerHTML = tradeGroups.map((group) => {
    const items = displayedOpenTrades.filter((item) => (item.strategy_type || "covered_call") === group.type);
    if (!items.length && state.tradeStrategyFilter.open !== "all") return "";
    const sectionId = group.type === "long_call" ? "open-trades-long" : "open-trades-covered";
    const cardRenderer = state.tradeFullView ? renderTradeCard : renderOpenTradeSummaryCard;
    return `<section id="${sectionId}" data-open-trade-strategy="${group.type}" class="trade-strategy-group ${group.type === "long_call" ? "long" : "covered"}"><header><div><h3>${esc(group.title)}</h3><small>${esc(group.subtitle)}</small></div><span>${num(items.length)} معامله</span></header><div class="trade-strategy-grid">${items.length ? items.map(cardRenderer).join("") : `<div class="trades-empty">هنوز معامله‌ای در این استراتژی ثبت نشده است.</div>`}</div></section>`;
  }).join("");
  applyOpenTradeView();
  const closedSummary = payload.closed_summary || {};
  const wins = Number(closedSummary.wins ?? closedTrades.filter((item) => Number(item.realized_profit) > 0).length);
  const losses = Number(closedSummary.losses ?? closedTrades.filter((item) => Number(item.realized_profit) < 0).length);
  const netProfit = Number(closedSummary.net_profit ?? closedTrades.reduce((sum, item) => sum + Number(item.realized_profit || 0), 0));
  $("closedTradesCount").textContent = num(closedSummary.count ?? closedTrades.length);
  $("closedWinsCount").textContent = num(wins);
  $("closedLossesCount").textContent = num(losses);
  $("closedWinRate").textContent = `نرخ موفقیت ${num(closedTrades.length ? wins / closedTrades.length * 100 : 0, 1)}٪`;
  $("closedNetProfit").textContent = signed(netProfit, 0);
  $("closedNetProfit").className = profitTone(netProfit);
  $("closedProfitPercent").textContent = `${signed(closedSummary.profit_percent)}٪`;
  $("closedProfitPercent").className = profitTone(closedSummary.profit_percent);
  $("closedAverageDays").textContent = `${num(closedSummary.average_holding_days, 1)} روز`;
  $("closedAnnualizedReturn").textContent = `${signed(closedSummary.annualized_return_percent)}٪`;
  $("closedAnnualizedReturn").className = profitTone(closedSummary.annualized_return_percent);
  renderClosedCoveredEvaluation(closedSummary);
  renderAssetPortfolioBreakdown("closedPortfolioByAsset", closedSummary.by_asset || [], {closed: true});
  $("closedTradesBadge").textContent = `${num(closedTrades.length)} معامله`;
  if ($("closedTradeSidebarCount")) $("closedTradeSidebarCount").textContent = `${num(displayedClosedTrades.length)} از ${num(closedTrades.length)} معامله`;
  $("exportClosedTrades").disabled = closedTrades.length === 0;
  $("closedTradesList").innerHTML = displayedClosedTrades.length ? tradeGroups.map((group) => {
    const items = displayedClosedTrades.filter((item) => (item.strategy_type || "covered_call") === group.type);
    if (!items.length) return "";
    const sectionId = group.type === "long_call" ? "closed-trades-long" : "closed-trades-covered";
    const cardRenderer = state.closedTradeFullView ? renderTradeCard : renderClosedTradeSummaryCard;
    return `<section id="${sectionId}" class="trade-strategy-group ${group.type === "long_call" ? "long" : "covered"}"><header><div><h3>${esc(group.title.replace("معاملات", "خروج‌های"))}</h3><small>${esc(group.subtitle)}</small></div><span>${num(items.length)} معامله</span></header><div class="trade-strategy-grid">${items.map(cardRenderer).join("")}</div></section>`;
  }).join("") : '<div class="trades-empty">هنوز معامله بسته‌شده‌ای ثبت نشده است.</div>';
  syncTradeSelectionUi();
  setupTradeJumpNav({
    covered: openTrades.filter((item) => (item.strategy_type || "covered_call") === "covered_call").length,
    long: openTrades.filter((item) => item.strategy_type === "long_call").length,
    closedCovered: closedTrades.filter((item) => (item.strategy_type || "covered_call") === "covered_call").length,
    closedLong: closedTrades.filter((item) => item.strategy_type === "long_call").length,
  });
  refreshOpenTradeDetailWindows();
}

function setupTradeJumpNav(counts) {
  if ($("tradeJumpCoveredCount")) $("tradeJumpCoveredCount").textContent = num(counts.covered);
  if ($("tradeJumpLongCount")) $("tradeJumpLongCount").textContent = num(counts.long);
  if ($("closedJumpCoveredCount")) $("closedJumpCoveredCount").textContent = num(counts.closedCovered);
  if ($("closedJumpLongCount")) $("closedJumpLongCount").textContent = num(counts.closedLong);
  if (tradeJumpObserver) tradeJumpObserver.disconnect();
  if (currentPage === "trades") { applyOpenTradeView(); return; }
  if (currentPage !== "closed-trades" || typeof IntersectionObserver === "undefined") return;
  const rail = document.querySelector(`.trade-jump-rail[data-page-view="${currentPage}"]`);
  const buttons = rail ? [...rail.querySelectorAll("[data-trade-scroll-target]")] : [];
  const setActive = (targetId) => buttons.forEach((button) => {
    const active = button.dataset.tradeScrollTarget === targetId;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "true" : "false");
  });
  tradeJumpObserver = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting)
      .sort((a, b) => Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top));
    if (visible[0]) setActive(visible[0].target.id);
  }, {rootMargin: "-6% 0px -72% 0px", threshold: [0, 0.05, 0.2]});
  buttons.forEach((button) => {
    const target = $(button.dataset.tradeScrollTarget);
    if (target) tradeJumpObserver.observe(target);
  });
}

function populateTradeAssets(selectedAsset = "") {
  const form = $("tradeForm");
  const market = form.elements.market.value;
  const assets = [...new Set(state.tradeContracts.filter((item) => item.market === market).map((item) => item.asset))].sort((a, b) => a.localeCompare(b, "fa"));
  $("tradeAssetOptions").innerHTML = assets.map((asset) => `<option value="${esc(asset)}"></option>`).join("");
  form.elements.asset.value = selectedAsset;
}

function populateUnderlyingPositionChoices(selectedId = "") {
  const form=$("tradeForm");
  const select=form.elements.underlying_position_id;
  if (!select) return;
  const market=form.elements.market.value;
  const asset=faNorm(form.elements.asset.value);
  const choices=state.underlyingPositions.filter((item)=>item.status!=="closed" && item.market===market && faNorm(item.asset)===asset && (Number(item.available_quantity||0)>0 || item.id===selectedId));
  select.innerHTML='<option value="">انتخاب دارایی پایه ثبت‌شده</option>'+choices.map((item)=>`<option value="${esc(item.id)}">${esc(item.asset)} — آزاد ${qty(item.available_quantity)} از ${qty(item.quantity)} واحد — خرید ${num(item.entry_price,2)}</option>`).join("");
  if (choices.some((item)=>item.id===selectedId)) select.value=selectedId;
  select.disabled=choices.length===0;
  const required=tradeUnderlyingUnits(form);
  $("tradeUnderlyingPositionMeta").textContent=choices.length ? `نیاز این کاوردکال: ${qty(required)} واحد پایه. قیمت روز پایه را جداگانه در فیلد قیمت استراتژی وارد کنید.` : "برای ثبت کاوردکال جدید ابتدا دارایی پایه را در بخش خرید دارایی پایه ثبت کنید.";
}

function tradeEntryQuantity(form) {
  return form.elements.strategy_type.value === "long_call"
    ? Number(form.elements.exercise_quantity.value || 0) + Number(form.elements.premium_trade_quantity.value || 0)
    : Number(form.elements.quantity.value || 0);
}

function tradeContractSize(form) {
  if (manualExpiredContractMode(form)) {
    return Number(form.elements.manual_contract_size.value || 0);
  }
  const contract = state.tradeContracts.find((item) =>
    item.market === form.elements.market.value
    && item.symbol === form.elements.option_symbol.value
  );
  return Number(contract?.contract_size || 1);
}

function tradeUnderlyingUnits(form) {
  return tradeEntryQuantity(form) * tradeContractSize(form);
}

function itemUnderlyingUnits(item, contracts) {
  const quantity = Number(contracts || 0);
  return Number(item?.calculation_version || 7) >= 8
    ? quantity * Number(item?.contract_size || 1)
    : quantity;
}

function updateTradeEntryCommissions({force=false}={}) {
  const form = $("tradeForm");
  const isLongCall = form.elements.strategy_type.value === "long_call";
  const market = form.elements.market.value;
  const quantity = tradeUnderlyingUnits(form);
  const optionRateKey = isLongCall ? "optionBuy" : "optionSell";
  setAutomaticCommission(
    form.elements.commission,
    calculatedCommission(form.elements.entry_premium.value, quantity, commissionRate(market, optionRateKey)),
    {force},
  );
  const buyingNew = !isLongCall && form.elements.underlying_source_mode.value === "new";
  if (buyingNew) {
    setAutomaticCommission(
      form.elements.underlying_purchase_commission,
      calculatedCommission(form.elements.entry_base_price.value, quantity, commissionRate(market, "underlyingBuy")),
      {force},
    );
  }
}

function updateUnderlyingEntryCommission({force=false}={}) {
  const form = $("underlyingForm");
  const fromTrade = form.elements.acquisition_method.value === "exercise" && form.elements.exercise_entry_mode.value === "trade";
  const sourceTrade = fromTrade ? state.trades.find((item)=>String(item.id)===String(form.elements.source_trade_id.value)) : null;
  const transactionPrice = sourceTrade ? sourceTrade.strike : form.elements.entry_price.value;
  setAutomaticCommission(
    form.elements.commission,
    calculatedCommission(transactionPrice, form.elements.quantity.value, commissionRate(form.elements.market.value, "underlyingBuy")),
    {force},
  );
}

function updateUnderlyingCloseCommission({force=false}={}) {
  const form = $("underlyingCloseForm");
  const item = state.underlyingPositions.find((row)=>String(row.id)===String(form.elements.position_id.value));
  setAutomaticCommission(
    form.elements.exit_commission,
    calculatedCommission(form.elements.exit_price.value, form.elements.quantity.value, commissionRate(item?.market || "tehran", "underlyingSell")),
    {force},
  );
}

function syncCoveredUnderlyingSource() {
  const form = $("tradeForm");
  const isLongCall = form.elements.strategy_type.value === "long_call";
  const buyingNew = !isLongCall && form.elements.underlying_source_mode.value === "new";
  $("tradeUnderlyingSourceModeField").classList.toggle("hidden", isLongCall);
  $("tradeUnderlyingPositionField").classList.toggle("hidden", isLongCall || buyingNew);
  $("tradeNewUnderlyingCommissionField").classList.toggle("hidden", !buyingNew);
  form.elements.underlying_source_mode.disabled = isLongCall;
  form.elements.underlying_position_id.disabled = isLongCall || buyingNew;
  form.elements.underlying_position_id.required = !isLongCall && !buyingNew;
  form.elements.underlying_purchase_commission.disabled = !buyingNew;
  $("tradeBaseEntryLabel").textContent = isLongCall
    ? "قیمت پایه در ورود"
    : buyingNew ? "قیمت خرید جدید دارایی پایه" : "قیمت روز پایه هنگام اجرای کاوردکال";
  $("tradeBaseEntryHint").textContent = buyingNew
    ? "این قیمت برای خرید مستقل جدید و وثیقه همین کاوردکال ثبت می‌شود."
    : "برای محاسبه دقیق کاوردکال، قیمت روز را وارد کنید؛ نه بهای خرید تاریخی دارایی.";
  updateTradeEntryCommissions();
}

function manualExpiredContractMode(form = $("tradeForm")) {
  return form.elements.contract_entry_mode.value === "manual_expired";
}

function syncTradeContractEntryMode() {
  const form = $("tradeForm");
  const manual = manualExpiredContractMode(form);
  const liveField = $("tradeLiveContractField");
  const manualFields = $("tradeManualContractFields");
  const liveSelect = form.elements.option_symbol;
  liveField.classList.toggle("hidden", manual);
  manualFields.classList.toggle("hidden", !manual);
  liveSelect.disabled = manual || ![...liveSelect.options].some((option) => option.value);
  liveSelect.required = !manual;
  for (const name of ["manual_option_symbol", "manual_strike", "manual_expiry", "manual_contract_size"]) {
    const field = form.elements[name];
    field.disabled = !manual;
    field.required = manual;
  }
  if (manual) {
    const symbol = form.elements.manual_option_symbol.value.trim();
    const strike = form.elements.manual_strike.value;
    const expiry = form.elements.manual_expiry.value.trim();
    $("tradeContractMeta").innerHTML = symbol || strike || expiry
      ? `قرارداد منقضی‌شده <b class="symbol">${esc(symbol || "—")}</b> · اعمال <b>${strike ? num(strike) : "—"}</b> · سررسید <b>${esc(expiry || "—")}</b> · <span class="warning">بدون قیمت زنده</span>`
      : "مشخصات قرارداد منقضی‌شده را مطابق سابقه کارگزاری تکمیل کنید.";
  } else {
    syncTradeContract();
  }
  populateUnderlyingPositionChoices(form.elements.underlying_position_id?.value || "");
  updateTradeEntryCommissions();
}

function populateTradeContracts(selectedSymbol = "") {
  const form = $("tradeForm");
  const market = form.elements.market.value;
  const isLongCall = form.elements.strategy_type.value === "long_call";
  const select = form.elements.option_symbol;
  const assetQuery = faNorm(form.elements.asset.value);
  const contracts = assetQuery ? state.tradeContracts.filter((item) => item.market === market && faNorm(item.asset).includes(assetQuery)) : [];
  select.innerHTML = `<option value="">${assetQuery ? (contracts.length ? `${num(contracts.length)} قرارداد مرتبط` : "قراردادی برای این نماد پیدا نشد") : "ابتدا نام نماد پایه را بنویسید"}</option>` + contracts.map((item) => `<option value="${esc(item.symbol)}">${esc(item.symbol)} — اعمال ${num(item.strike)} — سررسید ${esc(item.expiry_display)} — ${isLongCall ? "آخرین معامله" : "بهترین فروش"} ${num(isLongCall ? (item.option_last ?? item.option_exit_bid) : item.option_exit_ask)}</option>`).join("");
  if (contracts.some((item) => item.symbol === selectedSymbol)) select.value = selectedSymbol;
  select.disabled = manualExpiredContractMode(form) || contracts.length === 0;
  if (manualExpiredContractMode(form)) {
    syncTradeContractEntryMode();
    return;
  }
  syncTradeContract();
  populateUnderlyingPositionChoices($("tradeForm").elements.underlying_position_id?.value || "");
}

function syncTradeContract() {
  const form = $("tradeForm");
  if (manualExpiredContractMode(form)) {
    syncTradeContractEntryMode();
    return;
  }
  const isLongCall = form.elements.strategy_type.value === "long_call";
  const contract = state.tradeContracts.find((item) => item.market === form.elements.market.value && item.symbol === form.elements.option_symbol.value);
  if (contract) {
    form.elements.asset.value = contract.asset;
    if (!form.elements.trade_id.value) {
      if (contract.base_last != null) form.elements.entry_base_price.value = contract.base_last;
      if (contract.option_last != null) form.elements.entry_premium.value = contract.option_last;
      form.elements.price_confirmed.checked = false;
    }
  }
  const meta = $("tradeContractMeta");
  const exitAvailable = contract ? (isLongCall ? (contract.long_last_available || contract.long_exit_quote_available) : contract.exit_quote_available) : false;
  if (meta) meta.innerHTML = contract ? `اعمال <b>${num(contract.strike)}</b> · سررسید <b>${esc(contract.expiry_display)}</b> · آخرین پایه <b>${num(contract.base_last)}</b> · آخرین پرمیوم <b>${num(contract.option_last)}</b>${exitAvailable ? "" : ` · <span class="warning">بدون قیمت معتبر</span>`}` : "با انتخاب قرارداد، مشخصات بازار اینجا نمایش داده می‌شود.";
  populateUnderlyingPositionChoices(form.elements.underlying_position_id?.value || "");
  updateTradeEntryCommissions();
}

function syncTradeType() {
  const form = $("tradeForm");
  if (form.elements.strategy_type.value === "underlying") {
    openUnderlyingForm();
    return;
  }
  const isLongCall = form.elements.strategy_type.value === "long_call";
  const edited = state.trades.find((item) => String(item.id) === String(form.elements.trade_id.value));
  const legacy = edited && Number(edited.calculation_version || 7) < 8;
  $("tradeQuantityLabel").textContent = legacy ? "تعداد نهایی سهم/واحد (نسخه قدیمی)" : "تعداد قرارداد";
  $("tradeExerciseQuantityLabel").textContent = legacy ? "تعداد واحد با هدف اعمال (نسخه قدیمی)" : "تعداد قرارداد با هدف اعمال";
  $("tradePremiumQuantityLabel").textContent = legacy ? "تعداد واحد با هدف نوسان‌گیری (نسخه قدیمی)" : "تعداد قرارداد با هدف نوسان‌گیری پرمیوم";
  for (const name of ["quantity", "exercise_quantity", "premium_trade_quantity"]) {
    form.elements[name].step = legacy ? "any" : "1";
  }
  $("tradePremiumLabel").textContent = isLongCall ? "پرمیوم پرداختی" : "پرمیوم دریافتی";
  $("tradeCommissionLabel").textContent = isLongCall ? "کارمزد خرید اختیار خرید" : "کارمزد فروش اختیار";
  $("tradeInterestRateField").classList.toggle("hidden", !isLongCall);
  $("tradeQuantityField").classList.toggle("hidden", isLongCall);
  $("tradeExerciseQuantityField").classList.toggle("hidden", !isLongCall);
  $("tradePremiumQuantityField").classList.toggle("hidden", !isLongCall);
  $("tradeBaseEntryHint").classList.toggle("hidden", isLongCall);
  form.elements.quantity.disabled = isLongCall;
  form.elements.exercise_quantity.disabled = !isLongCall;
  form.elements.premium_trade_quantity.disabled = !isLongCall;
  updateTradeEntryCommissions();
  syncCoveredUnderlyingSource();
  populateTradeContracts(form.elements.option_symbol.value);
}

function tradeMessage(kind, message) {
  const box = $("tradeMessage");
  box.className = `trade-message ${kind}`;
  box.textContent = message;
  box.classList.remove("hidden");
}

function tradeModalMessage(kind="",message="") {
  const box=$("tradeEditModalMessage");
  if(!box) return;
  if(!message){box.className="trade-message hidden";box.textContent="";return;}
  box.className=`trade-message ${kind}`; box.textContent=message; box.classList.remove("hidden");
}

function tradeFieldContainer(field) {
  return field?.closest("label,.trade-date-field") || field?.parentElement;
}

function clearTradeFieldError(field) {
  if (!field) return;
  const errorId = field.dataset.tradeErrorId;
  if (errorId) {
    document.getElementById(errorId)?.remove();
    const describedBy = (field.getAttribute("aria-describedby") || "")
      .split(/\s+/).filter((id) => id && id !== errorId);
    if (describedBy.length) field.setAttribute("aria-describedby", describedBy.join(" "));
    else field.removeAttribute("aria-describedby");
    delete field.dataset.tradeErrorId;
  }
  field.removeAttribute("aria-invalid");
}

function clearTradeValidation(form, {clearMessage=true}={}) {
  form.querySelectorAll("[data-trade-error-id]").forEach(clearTradeFieldError);
  form.querySelectorAll(".trade-field-error").forEach((error) => error.remove());
  if (clearMessage) tradeModalMessage();
}

function setTradeFieldError(field, message) {
  if (!field || !message) return;
  clearTradeFieldError(field);
  const error = document.createElement("small");
  const safeName = String(field.name || "field").replace(/[^a-z0-9_-]/gi, "-");
  error.id = `trade-${safeName}-error`;
  error.className = "trade-field-error";
  error.textContent = message;
  tradeFieldContainer(field)?.appendChild(error);
  field.dataset.tradeErrorId = error.id;
  field.setAttribute("aria-invalid", "true");
  const describedBy = new Set((field.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean));
  describedBy.add(error.id);
  field.setAttribute("aria-describedby", [...describedBy].join(" "));
}

function validateTradeForm(form) {
  clearTradeValidation(form);
  const errors = [];
  const add = (name, message) => {
    const field = form.elements[name];
    if (!field || errors.some((item) => item.field === field)) return;
    errors.push({field, message});
  };
  const value = (name) => String(form.elements[name]?.value || "").trim();
  const number = (name) => Number(value(name));
  const strategy = value("strategy_type");
  const edited = state.trades.find((item) => String(item.id) === value("trade_id"));
  const canonicalContracts = !edited || Number(edited.calculation_version || 7) >= 8;

  if (!value("asset")) add("asset", "نام نماد پایه را وارد کنید.");
  if (manualExpiredContractMode(form)) {
    if (!value("manual_option_symbol")) add("manual_option_symbol", "نماد قرارداد منقضی‌شده را وارد کنید.");
    if (!value("manual_strike") || !Number.isFinite(number("manual_strike")) || number("manual_strike") <= 0) add("manual_strike", "قیمت اعمال باید بیشتر از صفر باشد.");
    if (!value("manual_expiry")) add("manual_expiry", "تاریخ سررسید قرارداد را وارد کنید.");
    if (!value("manual_contract_size") || !Number.isFinite(number("manual_contract_size")) || number("manual_contract_size") <= 0) add("manual_contract_size", "اندازه قرارداد باید بیشتر از صفر باشد.");
  } else if (!value("option_symbol")) add("option_symbol", "پس از انتخاب نماد پایه، قرارداد مرتبط را انتخاب کنید.");
  if (!value("entry_date")) add("entry_date", "تاریخ ورود را از تقویم انتخاب کنید.");
  if (!value("entry_base_price") || !Number.isFinite(number("entry_base_price")) || number("entry_base_price") <= 0) {
    add("entry_base_price", "قیمت روز دارایی پایه باید بیشتر از صفر باشد.");
  }
  if (!value("entry_premium") || !Number.isFinite(number("entry_premium")) || number("entry_premium") < 0 || (strategy === "long_call" && number("entry_premium") <= 0)) {
    add("entry_premium", strategy === "long_call" ? "پرمیوم پرداختی باید بیشتر از صفر باشد." : "پرمیوم دریافتی را وارد کنید.");
  }
  if (strategy === "long_call") {
    const exercise = number("exercise_quantity") || 0;
    const premium = number("premium_trade_quantity") || 0;
    if (exercise + premium <= 0) add("premium_trade_quantity", "حداقل یکی از تعدادهای اعمال یا نوسان‌گیری باید بیشتر از صفر باشد.");
    if (canonicalContracts && (!Number.isInteger(exercise) || exercise < 0)) add("exercise_quantity", "تعداد قرارداد اعمال باید عدد صحیح نامنفی باشد.");
    if (canonicalContracts && (!Number.isInteger(premium) || premium < 0)) add("premium_trade_quantity", "تعداد قرارداد نوسان‌گیری باید عدد صحیح نامنفی باشد.");
  } else if (!value("quantity") || !Number.isFinite(number("quantity")) || number("quantity") <= 0) {
    add("quantity", "تعداد قرارداد باید بیشتر از صفر باشد.");
  } else if (canonicalContracts && !Number.isInteger(number("quantity"))) {
    add("quantity", "تعداد قرارداد باید عدد صحیح باشد.");
  }
  if (strategy === "covered_call" && value("underlying_source_mode") === "existing" && !value("underlying_position_id")) {
    add("underlying_position_id", "دارایی پایه تأمین‌کننده کاوردکال را انتخاب کنید.");
  }
  if (!form.elements.price_confirmed.checked) add("price_confirmed", "برای ثبت، صحت قیمت‌ها و اطلاعات معامله را تأیید کنید.");

  errors.forEach(({field,message}) => setTradeFieldError(field, message));
  if (!errors.length) return true;
  tradeModalMessage("error", `لطفاً ${num(errors.length)} مورد مشخص‌شده را اصلاح کنید.`);
  const firstFocusable = errors.map(({field}) => field).find((field) => !field.disabled && !field.closest(".hidden"));
  firstFocusable?.focus();
  firstFocusable?.scrollIntoView({block:"nearest"});
  return false;
}

function tradeErrorFields(message, form) {
  const rules = [
    [/تأیید/, "price_confirmed"],
    [/تاریخ ورود|قبل از سررسید|امروز تهران/, "entry_date"],
    [/قیمت پایه/, "entry_base_price"],
    [/پرمیوم/, "entry_premium"],
    [/سررسید آن گذشته|تاریخ سررسید/, "manual_expiry"],
    [/قیمت اعمال/, "manual_strike"],
    [/اندازه قرارداد/, "manual_contract_size"],
    [/نماد قرارداد منقضی‌شده/, "manual_option_symbol"],
    [/نماد اختیار|قرارداد/, manualExpiredContractMode(form) ? "manual_option_symbol" : "option_symbol"],
    [/تخصیص|وثیقه|موجودی آزاد/, "underlying_position_id"],
    [/تعدادهای اعمال/, "exercise_quantity"],
    [/تعداد/, "quantity"],
    [/دارایی پایه/, "asset"],
    [/بازار/, "market"],
  ];
  const match = rules.find(([pattern,name]) => pattern.test(message) && form.elements[name]);
  return match ? [form.elements[match[1]]] : [];
}

function showTradeSubmissionError(form, message) {
  clearTradeValidation(form, {clearMessage:false});
  tradeModalMessage("error", message);
  const fields = tradeErrorFields(message, form);
  fields.forEach((field) => setTradeFieldError(field, message));
  const focusTarget = fields.find((field) => !field.disabled && !field.closest(".hidden"));
  if (focusTarget) focusTarget.focus();
  else $("tradeEditModalMessage")?.focus();
}

async function loadTrades() {
  try {
    const params = new URLSearchParams(state.tradePricing);
    const response = await apiFetch(`/api/trades?${params}`, {cache: "no-store"});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "دریافت معاملات ناموفق بود");
    if (Number(payload.calculation_schema_version || 0) < 5) {
      throw new Error("موتور محاسبات هنوز نسخه قدیمی است؛ برنامه را یک‌بار ببندید و دوباره اجرا کنید.");
    }
    renderTrades(payload);
    syncTradePricingControls();
  } catch (error) {
    tradeMessage("error", error.message || "دریافت معاملات ناموفق بود");
  }
}

function syncTradePricingControls() {
  const mappings = [
    ["tradeCoveredOption", "covered_option_basis"],
    ["tradeCoveredBase", "covered_base_basis"],
    ["tradeLongOption", "long_option_basis"],
    ["tradeLongBase", "long_base_basis"],
  ];
  mappings.forEach(([datasetKey,stateKey])=>document.querySelectorAll(`[data-${datasetKey.replace(/[A-Z]/g,(c)=>`-${c.toLowerCase()}`)}]`).forEach((button)=>{
    const selected = button.dataset[datasetKey] === state.tradePricing[stateKey];
    button.classList.toggle("active",selected);
    button.setAttribute("aria-pressed",String(selected));
  }));
}

async function setTradePricing(key, value) {
  state.tradePricing[key] = value;
  try { localStorage.setItem("nicoption.trade-pricing.v1",JSON.stringify(state.tradePricing)); } catch { /* Current session still works. */ }
  syncTradePricingControls();
  await loadTrades();
}

async function saveAccountCapital(value, cashValue, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "در حال ذخیره…";
  try {
    const response = await apiFetch("/api/account", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        initial_capital:value === "" ? null : value,
        cash_balance:cashValue === "" ? null : cashValue,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "ذخیره سرمایه اولیه ناموفق بود");
    await loadTrades();
    setStatus("success", value === "" ? "محاسبه خودکار سرمایه اولیه فعال و وجه نقد ذخیره شد." : "اطلاعات حساب ذخیره شد.");
  } catch (error) {
    setStatus("error", error.message || "ذخیره سرمایه اولیه ناموفق بود");
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

async function submitAccountCapital(event) {
  event.preventDefault();
  const form = event.currentTarget;
  await saveAccountCapital(
    form.elements.initial_capital.value,
    form.elements.cash_balance.value,
    form.querySelector('button[type="submit"]'),
  );
}

function restoreTradeForm() {
  const form = $("tradeForm");
  const slot = $("tradeFormSlot");
  closeEntryDatePicker();
  if (form.parentElement !== slot) slot.appendChild(form);
  modalManager.close($("tradeEditModal"));
}

function resetTradeForm() {
  const form = $("tradeForm");
  clearTradeValidation(form);
  restoreTradeForm();
  form.reset();
  form.dataset.idempotencyKey = crypto.randomUUID();
  form.elements.trade_id.value = "";
  form.elements.contract_entry_mode.value = "live";
  form.elements.manual_option_symbol.value = "";
  form.elements.manual_strike.value = "";
  form.elements.manual_expiry.value = "";
  form.elements.manual_contract_size.value = "1000";
  form.elements.quantity.value = "1";
  form.elements.exercise_quantity.value = "0";
  form.elements.premium_trade_quantity.value = "1";
  form.elements.commission.value = "0";
  form.elements.option_exit_commission_estimate.value = "0";
  form.elements.exercise_commission_estimate.value = "0";
  form.elements.underlying_exit_commission_estimate.value = "0";
  form.elements.annual_interest_rate.value = "40";
  form.elements.underlying_source_mode.value = "existing";
  form.elements.underlying_purchase_commission.value = "0";
  form.elements.commission.dataset.commissionManual = "false";
  form.elements.underlying_purchase_commission.dataset.commissionManual = "false";
  form.querySelector('button[type="submit"]').textContent = "ثبت معامله";
  $("tradeCancelEdit").classList.add("hidden");
  document.querySelector(".trades-panel")?.classList.remove("editing");
  populateTradeAssets();
  syncTradeContractEntryMode();
  syncTradeType();
}

function closeTradeEdit() {
  if ($("tradeEditModal").classList.contains("hidden")) return;
  resetUnderlyingCloseForm();
  resetUnderlyingForm();
  resetTradeForm();
  tradeModalMessage();
}

function openNewTradeForm() {
  const trigger = document.activeElement;
  resetUnderlyingCloseForm();
  resetUnderlyingForm();
  resetTradeForm();
  const form = $("tradeForm");
  tradeModalMessage();
  $("tradeEntryConfirmation").checked = false;
  $("tradeEditEyebrow").textContent = "ثبت معامله جدید";
  $("tradeEditTitle").textContent = "اطلاعات ورود به معامله";
  $("tradeEditModalBody").appendChild(form);
  modalManager.open($("tradeEditModal"), {trigger, initialFocus:form.elements.strategy_type, close:closeTradeEdit});
}

function resetUnderlyingForm() {
  const form=$("underlyingForm");
  if (form.parentElement!==$("underlyingFormSlot")) $("underlyingFormSlot").appendChild(form);
  form.reset(); form.elements.position_id.value=""; form.elements.commission.value="0";
  form.elements.commission.dataset.commissionManual="false";
  form.elements.entry_kind.value="underlying";
  form.elements.exercise_entry_mode.value="trade";
  form.elements.entry_date.value=solarDate(formatJalaliInput(currentJalaliDate()));
  form.elements.price_confirmed.checked=false;
  $("underlyingPriceSuggestion").textContent="با انتخاب نماد، آخرین معامله به‌صورت پیشنهادی درج می‌شود.";
  $("underlyingExerciseModeField").classList.add("hidden");
  $("underlyingExerciseSourceField").classList.add("hidden");
  $("underlyingExerciseCalculation").classList.add("hidden");
  $("underlyingExerciseCalculation").innerHTML="";
  closeUnderlyingDatePicker();
  for(const name of ["asset","entry_price","quantity"]) form.elements[name].readOnly=false;
  form.elements.market.disabled=false;
  form.querySelector('button[type="submit"]').textContent="ثبت دارایی پایه";
}

function resetUnderlyingCloseForm() {
  const form = $("underlyingCloseForm");
  if (form.parentElement !== $("underlyingCloseFormSlot")) $("underlyingCloseFormSlot").appendChild(form);
  form.reset(); form.elements.position_id.value = ""; form.elements.exit_commission.value = "0";
  form.elements.exit_commission.dataset.commissionManual = "false";
}

function populateUnderlyingExerciseSources(selected="") {
  const form=$("underlyingForm");
  const select=form.elements.source_trade_id;
  const rows=state.trades.filter((item)=>item.strategy_type==="long_call" && item.status==="closed" && ["exercise","mixed"].includes(item.exit_method) && Number(item.exercise_quantity||0)>0).sort((a,b)=>{
    const dateA=String(a.exit_date||a.entry_date||"");
    const dateB=String(b.exit_date||b.entry_date||"");
    return dateB.localeCompare(dateA)||String(a.option_symbol||"").localeCompare(String(b.option_symbol||""),"fa");
  });
  const optionHtml=(item)=>{
    const registered=state.underlyingPositions.some((position)=>position.source_trade_id===item.id && position.id!==$("underlyingForm").elements.position_id.value);
    const date=item.status==="closed"?(item.exit_date_display||item.entry_date_display):(item.entry_date_display||"");
    return `<option value="${esc(item.id)}" ${registered?"disabled":""}>${esc(item.option_symbol)} — ${esc(item.asset)}${date?` — ${esc(date)}`:""}${registered?" · قبلاً ثبت شده":""}</option>`;
  };
  select.innerHTML='<option value="">انتخاب معامله اعمال‌شده</option>'
    +(rows.length?`<optgroup label="معاملات اعمال‌شده (${rows.length})">${rows.map(optionHtml).join("")}</optgroup>`:"");
  if(rows.some((item)=>item.id===selected)) select.value=selected;
}

function switchFromUnderlyingForm() {
  const form=$("underlyingForm");
  const strategy=form.elements.entry_kind.value;
  if(strategy==="underlying") return;
  resetUnderlyingForm();
  resetTradeForm();
  const tradeForm=$("tradeForm");
  tradeForm.elements.strategy_type.value=strategy;
  syncTradeType();
  $("tradeEditEyebrow").textContent="ثبت معامله جدید";
  $("tradeEditTitle").textContent=strategy==="covered_call"?"ثبت کاوردکال":"ثبت خرید اختیار خرید";
  $("tradeEditModalBody").appendChild(tradeForm);
  tradeForm.elements.strategy_type.focus();
}

function syncUnderlyingAcquisition() {
  const form=$("underlyingForm");
  const exercise=form.elements.acquisition_method.value==="exercise";
  const fromTrade=exercise && form.elements.exercise_entry_mode.value==="trade";
  $("underlyingExerciseModeField").classList.toggle("hidden",!exercise);
  $("underlyingExerciseSourceField").classList.toggle("hidden",!fromTrade);
  form.elements.exercise_entry_mode.disabled=!exercise;
  form.elements.source_trade_id.disabled=!fromTrade;
  form.elements.source_trade_id.required=fromTrade;
  // Keep computed controls successful form fields. `disabled` controls are
  // omitted from FormData and caused exercise registrations to be rejected in
  // some browsers; readonly preserves both validation and submission.
  form.elements.market.disabled=false;
  for(const name of ["asset","entry_price","quantity"]) {
    form.elements[name].disabled=false;
    form.elements[name].readOnly=fromTrade;
  }
  if(fromTrade){populateUnderlyingExerciseSources(form.elements.source_trade_id.value); syncUnderlyingExerciseSource();}
  else {$("underlyingExerciseCalculation").classList.add("hidden"); $("underlyingExerciseCalculation").innerHTML="";}
  updateUnderlyingEntryCommission();
}

function syncUnderlyingAssetMarket() {
  const form=$("underlyingForm");
  const asset=faNorm(form.elements.asset.value);
  if(!asset) return;
  const matches=state.underlyingQuotes.filter((item)=>faNorm(item.asset)===asset);
  const markets=[...new Set(matches.map((item)=>item.market).filter(Boolean))];
  if(markets.length===1) form.elements.market.value=markets[0];
  const quote=matches.find((item)=>item.market===form.elements.market.value)||matches[0];
  const fromTrade=form.elements.acquisition_method.value==="exercise" && form.elements.exercise_entry_mode.value==="trade";
  if(quote && !form.elements.position_id.value && !fromTrade){
    form.elements.entry_price.value=quote.last??"";
    form.elements.price_confirmed.checked=false;
    $("underlyingPriceSuggestion").innerHTML=quote.last!=null
      ? `آخرین معامله پیشنهادی: <b>${num(quote.last,2)}</b> — در صورت نیاز ویرایش کنید.`
      : "قیمت بازار در دسترس نیست؛ قیمت را دستی وارد و سپس تأیید کنید.";
  }
  updateUnderlyingEntryCommission();
}

function syncUnderlyingExerciseSource() {
  const form=$("underlyingForm");
  const trade=state.trades.find((item)=>item.id===form.elements.source_trade_id.value);
  const calculation=$("underlyingExerciseCalculation");
  if(!trade){calculation.classList.add("hidden");calculation.innerHTML="";return;}
  const contracts=Number(trade.exercise_quantity||0), units=itemUnderlyingUnits(trade, contracts);
  const rate=Number(trade.annual_interest_rate??40);
  const entryTime=Date.parse(`${trade.entry_date}T00:00:00Z`), exerciseTime=Date.parse(`${trade.exit_date}T00:00:00Z`);
  const days=Math.max(0,Math.round((exerciseTime-entryTime)/86400000));
  const strike=Number(trade.strike||0), premium=Number(trade.entry_premium||0);
  const canonical=Number(trade.calculation_version||7)>=8;
  const periodRate=canonical?(rate/100)*(days/365):Math.pow(1+rate/100,days/365)-1;
  const discountFactor=1+periodRate;
  const adjustedStrike=canonical?strike-strike*periodRate:strike/discountFactor, interest=strike-adjustedStrike, adjusted=adjustedStrike+premium;
  const base=Number(trade.entry_base_price||0), advantage=base>0?(base-adjusted)/base*100:null;
  form.elements.market.value=trade.market; form.elements.asset.value=trade.asset;
  form.elements.entry_date.value=trade.exit_date_display||solarDate(formatJalaliInput(currentJalaliDate()));
  form.elements.quantity.value=units;
  form.elements.entry_price.value=adjusted>0?adjusted.toFixed(4).replace(/\.?0+$/,""):"";
  form.elements.price_confirmed.checked=false;
  calculation.innerHTML=`<strong>سربه‌سر خرید از طریق اعمال</strong><span>اعمال تنزیل‌شده ${num(adjustedStrike,2)} + پرمیوم ${num(premium,2)} = <b>${num(adjusted,2)}</b></span><span>${canonical?"بهره ساده ACT/365":"تنزیل مرکب نسخه قدیمی"} با نرخ بدون ریسک ${pct(rate,2)} برای ${num(days)} روز · تعدیل ${num(interest,2)} · مزیت نسبی <b class="${advantage!=null&&advantage>=0?"positive":"negative"}">${advantage==null?"—":pct(advantage,2)}</b></span>`;
  calculation.classList.remove("hidden");
  updateUnderlyingEntryCommission();
}

function openUnderlyingForm(positionId="") {
  const trigger=document.activeElement;
  resetTradeForm();
  resetUnderlyingCloseForm();
  resetUnderlyingForm();
  const form=$("underlyingForm");
  tradeModalMessage();
  let selectedSource="";
  if(positionId){
    const item=state.underlyingPositions.find((row)=>row.id===positionId); if(!item) return;
    form.elements.position_id.value=item.id; form.elements.acquisition_method.value=item.acquisition_method||"direct";
    form.elements.exercise_entry_mode.value=item.exercise_entry_mode||"manual";
    selectedSource=item.source_trade_id||"";
    form.elements.market.value=item.market; form.elements.asset.value=item.asset; form.elements.entry_date.value=item.entry_date_display;
    form.elements.entry_price.value=item.entry_price; form.elements.quantity.value=item.quantity; form.elements.commission.value=item.commission||0;
    form.elements.commission.dataset.commissionManual=item.commission_source === "estimated" ? "false" : "true";
    form.querySelector('button[type="submit"]').textContent="ذخیره تغییرات";
  }
  populateUnderlyingExerciseSources(selectedSource); syncUnderlyingAcquisition();
  $("tradeEditEyebrow").textContent=positionId ? "ویرایش دارایی پایه" : "ثبت خرید دارایی پایه";
  $("tradeEditTitle").textContent=positionId ? `ویرایش ${form.elements.asset.value}` : "اطلاعات خرید دارایی پایه";
  $("tradeEditModalBody").appendChild(form); modalManager.open($("tradeEditModal"),{trigger,initialFocus:form.elements.acquisition_method,close:closeTradeEdit});
}

function openUnderlyingCloseForm(positionId) {
  const trigger=document.activeElement;
  resetTradeForm(); resetUnderlyingForm(); resetUnderlyingCloseForm();
  const item = state.underlyingPositions.find((row)=>row.id===positionId && row.status!=="closed");
  if (!item) return;
  const form = $("underlyingCloseForm");
  form.elements.position_id.value = item.id;
  form.elements.quantity.value = item.available_quantity;
  form.elements.exit_price.value = item.current_price ?? item.best_bid ?? "";
  form.elements.exit_date.value = solarDate(state.lastTradesPayload?.generated_at || new Date().toISOString());
  updateUnderlyingCloseCommission({force:true});
  $("underlyingCloseMeta").textContent = `${item.asset} · موجودی آزاد ${qty(item.available_quantity)} واحد · قیمت خرید ${num(item.entry_price,2)}`;
  $("tradeEditEyebrow").textContent = "ثبت فروش دارایی پایه";
  $("tradeEditTitle").textContent = `فروش ${item.asset}`;
  $("tradeEditModalBody").appendChild(form); modalManager.open($("tradeEditModal"),{trigger,initialFocus:form.elements.quantity,close:closeTradeEdit});
}

async function saveUnderlyingClose(event) {
  event.preventDefault(); const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.exit_commission_source = form.elements.exit_commission.dataset.commissionManual === "true" ? "actual" : "estimated";
  const id = payload.position_id; delete payload.position_id;
  const button = form.querySelector('button[type="submit"]'); button.disabled = true;
  try {
    const response = await apiFetch(`/api/underlyings/${id}/close`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const data = await response.json(); if (!response.ok) throw new Error(data.error||"ثبت فروش ناموفق بود");
    renderTrades(data); resetUnderlyingCloseForm(); modalManager.close($("tradeEditModal")); tradeMessage("success","فروش دارایی پایه ثبت شد.");
  } catch(error) { tradeMessage("error",error.message||"ثبت فروش ناموفق بود"); }
  finally { button.disabled = false; }
}

async function saveUnderlying(event){
  event.preventDefault(); const form=event.currentTarget; const payload=Object.fromEntries(new FormData(form).entries());
  payload.commission_source = form.elements.commission.dataset.commissionManual === "true" ? "actual" : "estimated";
  const id=payload.position_id; delete payload.position_id;
  const button=form.querySelector('button[type="submit"]'); button.disabled=true; tradeModalMessage();
  try{
    const response=await apiFetch(id?`/api/underlyings/${id}`:"/api/underlyings",{method:id?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const data=await response.json(); if(!response.ok) throw new Error(data.error||"ثبت دارایی پایه ناموفق بود");
    renderTrades(data); resetUnderlyingForm(); modalManager.close($("tradeEditModal")); tradeMessage("success",id?"دارایی پایه ویرایش شد.":"دارایی پایه ثبت شد.");
  }catch(error){const message=error.message||"ثبت دارایی پایه ناموفق بود";tradeModalMessage("error",message);tradeMessage("error",message);}finally{button.disabled=false;}
}

async function mutateUnderlying(positionId,action){
  if(action==="edit"){openUnderlyingForm(positionId);return;}
  if(action==="sell"){openUnderlyingCloseForm(positionId);return;}
  if(action==="delete" && !await requestConfirmation({
    title:"حذف موقعیت دارایی پایه",
    description:"این موقعیت و سابقه ثبت‌شده آن برای حساب شما حذف می‌شود و قابل بازیابی نیست.",
    actionLabel:"حذف موقعیت",
  })) return;
  try{const response=await apiFetch(`/api/underlyings/${positionId}`,{method:"DELETE"}); const data=await response.json(); if(!response.ok) throw new Error(data.error||"حذف ناموفق بود"); renderTrades(data); tradeMessage("success","دارایی پایه حذف شد.");}
  catch(error){tradeMessage("error",error.message||"عملیات ناموفق بود");}
}

async function saveTrade(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (form.dataset.submitting === "true") return;
  if (!validateTradeForm(form)) return;
  const button = form.querySelector('button[type="submit"]');
  const payload = Object.fromEntries(new FormData(form).entries());
  const manualExpired = manualExpiredContractMode(form);
  if (manualExpired) payload.option_symbol = payload.manual_option_symbol;
  const tradeId = payload.trade_id; delete payload.trade_id;
  if (!tradeId) payload.client_request_id = form.dataset.idempotencyKey;
  payload.commission_source = form.elements.commission.dataset.commissionManual === "true" ? "actual" : "estimated";
  payload.underlying_purchase_commission_source = form.elements.underlying_purchase_commission.dataset.commissionManual === "true" ? "actual" : "estimated";
  if (tradeId) {
    const current = state.trades.find((item) => String(item.id) === String(tradeId));
    if (current?.mutation_version != null) payload.mutation_version = current.mutation_version;
  }
  form.dataset.submitting = "true";
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    const headers = {"Content-Type": "application/json"};
    if (!tradeId) headers["Idempotency-Key"] = form.dataset.idempotencyKey;
    const response = await apiFetch(tradeId ? `/api/trades/${tradeId}` : "/api/trades", {method: tradeId ? "PUT" : "POST", headers, body: JSON.stringify(payload)});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "ثبت معامله ناموفق بود");
    await loadTrades(); resetTradeForm();
    tradeMessage("success", tradeId
      ? "معامله ویرایش شد."
      : manualExpired
        ? "قرارداد منقضی‌شده با مشخصات دستی ثبت شد."
        : "معامله ثبت شد و از این پس با بازار به‌روزرسانی می‌شود.");
  } catch (error) {
    const message = error instanceof TypeError
      ? "ارتباط با سرور برقرار نشد؛ اطلاعات فرم حفظ شده است و می‌توانید دوباره تلاش کنید."
      : error.message || "ثبت معامله ناموفق بود؛ اطلاعات فرم حفظ شده است و می‌توانید دوباره تلاش کنید.";
    showTradeSubmissionError(form, message);
  }
  finally {
    form.dataset.submitting = "false";
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

function editTrade(tradeId) {
  const trigger = document.activeElement;
  const item = state.trades.find((trade) => String(trade.id) === String(tradeId));
  if (!item) return;
  const form = $("tradeForm");
  $("tradeEntryConfirmation").checked = false;
  form.elements.strategy_type.value = item.strategy_type || "covered_call";
  form.elements.annual_interest_rate.value = item.annual_interest_rate ?? "40";
  form.elements.market.value = item.market;
  const liveContract = state.tradeContracts.find((quote) => quote.market === item.market && quote.symbol === item.option_symbol);
  const manualContract = item.contract_entry_mode === "manual_expired" || !liveContract;
  form.elements.contract_entry_mode.value = manualContract ? "manual_expired" : "live";
  form.elements.manual_option_symbol.value = manualContract ? (item.option_symbol || "") : "";
  form.elements.manual_strike.value = manualContract ? (item.strike ?? "") : "";
  form.elements.manual_expiry.value = manualContract ? (item.expiry || item.expiry_display || "") : "";
  form.elements.manual_contract_size.value = manualContract ? (item.contract_size ?? 1000) : "1000";
  populateTradeAssets(item.asset);
  syncTradeContractEntryMode();
  populateTradeContracts(item.option_symbol);
  for (const key of ["entry_base_price", "entry_premium", "quantity", "commission", "option_exit_commission_estimate", "exercise_commission_estimate", "underlying_exit_commission_estimate"]) form.elements[key].value = item[key] ?? 0;
  form.elements.commission.dataset.commissionManual = item.commission_source === "estimated" ? "false" : "true";
  form.elements.exercise_quantity.value = item.exercise_quantity ?? 0;
  form.elements.premium_trade_quantity.value = item.premium_trade_quantity ?? (item.strategy_type === "long_call" ? item.quantity : 0);
  form.elements.asset.value = item.asset;
  populateUnderlyingPositionChoices(item.underlying_position_id || "");
  form.elements.underlying_position_id.value = item.underlying_position_id || "";
  form.elements.underlying_source_mode.value = "existing";
  form.elements.entry_date.value = item.entry_date_display;
  form.elements.trade_id.value = item.id;
  syncTradeType();
  form.querySelector('button[type="submit"]').textContent = "ذخیره تغییرات";
  $("tradeCancelEdit").classList.remove("hidden");
  document.querySelector(".trades-panel")?.classList.add("editing");
  $("tradeEditEyebrow").textContent = "ویرایش معامله باز";
  $("tradeEditTitle").textContent = `ویرایش ${item.option_symbol}`;
  $("tradeEditModalBody").appendChild(form);
  modalManager.open($("tradeEditModal"), {trigger, initialFocus:form.querySelector("input:not([type='hidden']), select"), close:closeTradeEdit});
}

async function mutateTrade(tradeId, action) {
  if (action === "delete" && !await requestConfirmation({
    title:"حذف معامله",
    description:"این معامله و اطلاعات محاسباتی آن برای حساب شما حذف می‌شود و قابل بازیابی نیست.",
    actionLabel:"حذف معامله",
  })) return;
  try {
    const response = await apiFetch(`/api/trades/${tradeId}`, {method: "DELETE"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "عملیات ناموفق بود");
    await loadTrades();
    tradeMessage("success", "معامله حذف شد.");
  } catch (error) { tradeMessage("error", error.message || "عملیات ناموفق بود"); }
}

function updateTradeCloseCommissions({force=false}={}) {
  const form = $("tradeCloseForm");
  const item = state.trades.find((trade)=>String(trade.id)===String(form.elements.trade_id.value));
  if (!item) return;
  const isLongCall = item.strategy_type === "long_call";
  const method = form.elements.exit_method.value;
  const exercising = method === "exercise";
  const mixed = method === "mixed";
  const optionInput = $("tradeCloseOptionCommission");
  const underlyingInput = $("tradeCloseUnderlyingCommission");
  const optionQuantity = isLongCall
    ? (mixed ? Number(form.elements.close_premium_trade_quantity.value || 0) : exercising ? Number(form.elements.close_exercise_quantity.value || 0) : Number(form.elements.close_premium_trade_quantity.value || item.quantity || 0))
    : Number(form.elements.close_quantity.value || 0);
  const exerciseQuantity = isLongCall
    ? (mixed || exercising ? Number(form.elements.close_exercise_quantity.value || 0) : 0)
    : (exercising ? Number(form.elements.close_quantity.value || 0) : 0);
  const optionRateKey = exercising && !mixed ? "optionExercise" : isLongCall ? "optionSell" : "optionBuy";
  const optionPrice = exercising && !mixed ? Number(item.strike || 0) : Number(form.elements.exit_option_price.value || 0);
  const offsetCommission = calculatedCommission(optionPrice, itemUnderlyingUnits(item, exercising && !mixed ? exerciseQuantity : optionQuantity), commissionRate(item.market, optionRateKey));
  const exerciseCommission = mixed
    ? calculatedCommission(item.strike, itemUnderlyingUnits(item, exerciseQuantity), commissionRate(item.market, "optionExercise"))
    : 0;
  const calculatedOption = offsetCommission + exerciseCommission;
  setAutomaticCommission(optionInput, calculatedOption, {force});

  const coveredSell = !isLongCall && (exercising || form.elements.underlying_disposition.value === "sell");
  const longExercise = isLongCall && exerciseQuantity > 0;
  const showUnderlying = coveredSell || longExercise;
  $("tradeCloseUnderlyingCommissionField").classList.toggle("hidden", !showUnderlying);
  $("tradeCloseUnderlyingCommissionLabel").textContent = longExercise ? "کارمزد خرید دارایی پایه در اعمال" : "کارمزد فروش دارایی پایه";
  $("tradeCloseOptionCommissionLabel").textContent = exercising && !mixed ? "کارمزد اعمال/تخصیص اختیار" : isLongCall ? "کارمزد فروش اختیار" : "کارمزد بازخرید اختیار";
  const underlyingQuantity = itemUnderlyingUnits(item, longExercise ? exerciseQuantity : Number(form.elements.close_quantity.value || 0));
  const underlyingPrice = longExercise ? Number(item.strike || 0) : Number(form.elements.exit_base_price.value || 0);
  const underlyingRateKey = longExercise ? "underlyingBuy" : "underlyingSell";
  setAutomaticCommission(underlyingInput, showUnderlying ? calculatedCommission(underlyingPrice, underlyingQuantity, commissionRate(item.market, underlyingRateKey)) : 0, {force});
  form.elements.exit_commission.value = String(Number(optionInput.value || 0) + (showUnderlying ? Number(underlyingInput.value || 0) : 0));
}

function fillTradeCloseMarket() {
  const form = $("tradeCloseForm");
  const item = state.trades.find((trade) => String(trade.id) === String(form.elements.trade_id.value));
  if (!item) return;
  const contract = state.tradeContracts.find((quote) => quote.market === item.market && quote.symbol === item.option_symbol);
  const isLongCall = item.strategy_type === "long_call";
  const basePrice = contract?.base_last;
  const exercising = form.elements.exit_method.value === "exercise";
  const optionPrice = exercising
    ? (isLongCall ? contract?.option_last : 0)
    : contract?.option_last;
  if (basePrice != null) form.elements.exit_base_price.value = basePrice;
  else if (item.status !== "closed") form.elements.exit_base_price.value = "";
  if (optionPrice != null) form.elements.exit_option_price.value = optionPrice;
  else if (item.status !== "closed") form.elements.exit_option_price.value = "";
  updateTradeCloseCommissions();
}

function syncTradeExitMethod({refreshMarket = true} = {}) {
  const form = $("tradeCloseForm");
  const item = state.trades.find((trade) => String(trade.id) === String(form.elements.trade_id.value));
  if (!item) return;
  const isLongCall = item.strategy_type === "long_call";
  const isClosed = item.status === "closed";
  const select = form.elements.exit_method;
  select.disabled = isLongCall && !isClosed;
  const coveredQuantityField = $("tradeCloseQuantityField");
  const exerciseQuantityField = $("tradeCloseExerciseQuantityField");
  const premiumQuantityField = $("tradeClosePremiumQuantityField");
  coveredQuantityField.classList.toggle("hidden", isLongCall || isClosed);
  exerciseQuantityField.classList.toggle("hidden", !isLongCall || isClosed);
  premiumQuantityField.classList.toggle("hidden", !isLongCall || isClosed);
  form.elements.close_quantity.disabled = isLongCall || isClosed;
  form.elements.close_exercise_quantity.disabled = !isLongCall || isClosed;
  form.elements.close_premium_trade_quantity.disabled = !isLongCall || isClosed;
  if (isLongCall && !isClosed) {
    const closeExercise = Number(form.elements.close_exercise_quantity.value || 0);
    const closePremium = Number(form.elements.close_premium_trade_quantity.value || 0);
    select.value = closeExercise > 0 && closePremium > 0 ? "mixed" : closeExercise > 0 ? "exercise" : "offset";
  }
  select.options[0].textContent = isLongCall ? "آفست کردن (فروش اختیار)" : "آفست اختیار و تعیین وضعیت دارایی پایه";
  select.options[1].textContent = isLongCall ? "اعمال قرارداد (پرداخت اعمال و خرید دارایی)" : "فروش دارایی با قیمت اعمال در سررسید";
  select.options[2].hidden = !isLongCall;
  select.options[2].disabled = !isLongCall;
  select.options[2].textContent = "خروج ترکیبی: بخشی اعمال و بخشی آفست";
  if (!isLongCall && select.value === "mixed") select.value = "offset";
  const exercising = select.value === "exercise";
  const mixed = select.value === "mixed";
  const keepUnderlying = !isLongCall && !exercising && form.elements.underlying_disposition.value === "keep";
  const baseLabel = $("tradeExitBasePriceLabel");
  const baseNote = $("tradeExitBasePriceNote");
  const baseInput = form.elements.exit_base_price;
  baseLabel.textContent = exercising && !isLongCall ? "قیمت فروش دارایی پایه (قیمت اعمال)" : keepUnderlying ? "قیمت فعلی دارایی پایه" : "قیمت فروش دارایی پایه";
  baseNote.classList.toggle("hidden", !keepUnderlying);
  baseNote.textContent = keepUnderlying
    ? `قیمت پایه هنگام شروع کاوردکال ${num(item.entry_base_price, 0)} بوده است. اگر قیمت جدیدی وارد کنید، سایت سود یا زیان تغییر قیمت دارایی را محاسبه می‌کند و در بخش دارایی‌ها نیز محاسبات با همین قیمت جدید انجام می‌شود.`
    : "";
  baseInput.readOnly = exercising && !isLongCall;
  if (exercising && !isLongCall) baseInput.value = String(item.strike || 0);
  const showDisposition = !isLongCall && !exercising;
  $("tradeUnderlyingDispositionField").classList.toggle("hidden", !showDisposition);
  form.elements.underlying_disposition.disabled = !showDisposition;
  const keepBasisField = $("tradeUnderlyingKeepBasisField");
  const showKeepBasis = showDisposition && form.elements.underlying_disposition.value === "keep";
  keepBasisField.classList.toggle("hidden", !showKeepBasis);
  form.elements.underlying_keep_basis.disabled = !showKeepBasis;
  const optionInput = form.elements.exit_option_price;
  optionInput.readOnly = exercising && !isLongCall;
  optionInput.required = !exercising || isLongCall;
  $("tradeExitOptionPriceField").classList.toggle("settlement-only", exercising);
  $("tradeExitOptionPriceLabel").textContent = exercising
    ? (isLongCall ? "قیمت پرمیوم در زمان اعمال" : "قیمت اختیار در تسویه (صفر)")
    : (isLongCall ? (mixed ? "قیمت فروش بخش نوسان‌گیری در آفست" : "قیمت فروش اختیار در آفست") : "قیمت بازخرید اختیار در آفست");
  if (exercising && !isLongCall) optionInput.value = "0";
  if (refreshMarket) fillTradeCloseMarket();
  updateTradeCloseCommissions();
  const closeTotal = isLongCall
    ? Number(form.elements.close_exercise_quantity.value || 0) + Number(form.elements.close_premium_trade_quantity.value || 0)
    : Number(form.elements.close_quantity.value || 0);
  const remaining = Math.max(0, Number(item.quantity || 0) - closeTotal);
  const explanation = exercising
    ? (isLongCall ? "در اعمال، قیمت اعمال پرداخت و دارایی پایه دریافت می‌شود؛ قیمت پرمیوم زمان اعمال نیز برای سابقه و تحلیل ذخیره می‌شود." : "در تخصیص، قیمت اعمال دریافت و دارایی پایه فروخته می‌شود؛ اختیار بازخرید نمی‌شود.")
    : mixed ? `تعداد ${qty(form.elements.close_exercise_quantity.value || 0)} قرارداد اعمال و تعداد ${qty(form.elements.close_premium_trade_quantity.value || 0)} قرارداد با قیمت پرمیوم خروج آفست می‌شود.`
    : (isLongCall ? "در آفست، اختیار با قیمت آخرین معامله بسته می‌شود." : keepUnderlying ? `اختیار بازخرید و دارایی پایه نگهداری می‌شود. بهای تمام‌شده آن در بخش دارایی‌ها بر اساس ${form.elements.underlying_keep_basis.value === "entry" ? "قیمت پایه هنگام ثبت کاوردکال" : "قیمت پایه روز آفست"} ثبت خواهد شد.` : "اختیار بازخرید و دارایی پایه با قیمت فروش واردشده فروخته می‌شود.");
  $("tradeCloseMeta").innerHTML = `${esc(item.asset)} · ${marketLabel(item.market)} · مانده فعلی ${qty(item.quantity)} قرارداد<br>${esc(explanation)}${isClosed ? "" : `<br><b>پس از ثبت: ${qty(closeTotal)} بسته · ${qty(remaining)} باز می‌ماند</b>`}<br><b>پیش از ثبت، هر دو قیمت را با تابلو بازار تطبیق دهید.</b>`;
}

function openTradeClose(tradeId) {
  const trigger = document.activeElement;
  const item = state.trades.find((trade) => String(trade.id) === String(tradeId));
  if (!item) return;
  const form = $("tradeCloseForm");
  const legacy = Number(item.calculation_version || 7) < 8;
  $("tradeCloseQuantityLabel").textContent = "تعداد قرارداد/واحد برای بستن";
  $("tradeCloseExerciseQuantityLabel").textContent = "تعداد قرارداد/واحد برای اعمال در این خروج";
  $("tradeClosePremiumQuantityLabel").textContent = "تعداد قرارداد/واحد برای فروش (آفست) در این خروج";
  for (const name of ["close_quantity", "close_exercise_quantity", "close_premium_trade_quantity"]) {
    form.elements[name].step = legacy ? "any" : "1";
  }
  form.reset();
  form.elements.trade_id.value = item.id;
  form.elements.exit_method.value = item.exit_method || (
    item.strategy_type === "long_call" && Number(item.exercise_quantity) > 0 && Number(item.premium_trade_quantity) > 0
      ? "mixed"
      : item.strategy_type === "long_call" && Number(item.exercise_quantity) > 0
      ? "exercise" : "offset"
  );
  form.elements.close_quantity.value = item.quantity ?? "";
  form.elements.close_exercise_quantity.value = item.exercise_quantity ?? 0;
  form.elements.close_premium_trade_quantity.value = item.premium_trade_quantity ?? (item.strategy_type === "long_call" ? item.quantity : 0);
  form.elements.close_exercise_quantity.max = item.quantity ?? "";
  form.elements.close_premium_trade_quantity.max = item.quantity ?? "";
  form.elements.exit_date.value = item.exit_date_display || item.valuation_date_display || "";
  form.elements.exit_base_price.value = item.exit_base_price ?? item.current_base_price ?? "";
  form.elements.exit_option_price.value = item.exit_option_price ?? item.current_option_exit_price ?? "";
  form.elements.exit_commission.value = item.exit_commission ?? 0;
  const exitWasEstimated = item.exit_commission_source === "estimated";
  $("tradeCloseOptionCommission").dataset.commissionManual = exitWasEstimated ? "false" : "true";
  $("tradeCloseUnderlyingCommission").dataset.commissionManual = exitWasEstimated ? "false" : "true";
  form.elements.exit_note.value = item.exit_note || "";
  form.elements.underlying_disposition.value = item.underlying_disposition || "sell";
  form.elements.underlying_keep_basis.value = item.underlying_keep_basis || "entry";
  form.elements.price_confirmed.checked = false;
  $("tradeCloseTitle").textContent = `${item.status === "closed" ? "ویرایش خروج" : "ثبت خروج"} · ${item.option_symbol}`;
  syncTradeExitMethod({refreshMarket: item.status !== "closed"});
  if (item.status === "closed") {
    $("tradeCloseOptionCommission").value = String(item.exit_commission ?? 0);
    $("tradeCloseUnderlyingCommission").value = "0";
    $("tradeCloseOptionCommission").dataset.commissionManual = "true";
    form.elements.exit_commission.value = String(item.exit_commission ?? 0);
  } else updateTradeCloseCommissions({force:true});
  $("tradeCloseForm").querySelector('button[type="submit"]').textContent = item.status === "closed" ? "ذخیره تغییرات خروج" : "ثبت خروج";
  modalManager.open($("tradeCloseModal"), {trigger, initialFocus:form.elements.exit_date, close:closeTradeClose});
}

function closeTradeClose() {
  modalManager.close($("tradeCloseModal"));
}

async function saveTradeClose(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  const tradeId = payload.trade_id;
  const currentTrade = state.trades.find((item) => String(item.id) === String(tradeId));
  if (currentTrade?.mutation_version != null) payload.mutation_version = currentTrade.mutation_version;
  payload.exit_commission_source = [$("tradeCloseOptionCommission"), $("tradeCloseUnderlyingCommission")]
    .some((input) => input.dataset.commissionManual === "true") ? "actual" : "estimated";
  delete payload.trade_id;
  const item = state.trades.find((trade) => String(trade.id) === String(tradeId));
  const requested = item?.strategy_type === "long_call"
    ? [payload.close_exercise_quantity, payload.close_premium_trade_quantity]
    : [payload.close_quantity];
  payload.underlying_keep_basis = form.elements.underlying_keep_basis.value;
  if (Number(item?.calculation_version || 7) >= 8 && requested.some((value) => !Number.isInteger(Number(value || 0)))) {
    tradeMessage("error", "تعداد قرارداد برای خروج باید عدد صحیح باشد.");
    return;
  }
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const response = await apiFetch(`/api/trades/${tradeId}/close`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "ثبت خروج ناموفق بود");
    await loadTrades();
    closeTradeClose();
    tradeMessage("success", "اطلاعات خروج ثبت شد و نتیجه بخش بسته‌شده با قیمت‌های واردشده محاسبه شد.");
  } catch (error) { tradeMessage("error", error.message || "ثبت خروج ناموفق بود"); }
  finally { button.disabled = false; }
}

function forecastChart(chart, {percent=false, signals=false}={}) {
  const width=820, height=250, margin={top:18,right:18,bottom:34,left:66};
  const values=(chart.series || []).flatMap((series)=>series.values || []).filter((value)=>Number.isFinite(Number(value))).map(Number);
  const thresholds=(chart.thresholds || []).map((item)=>Number(item.value)).filter(Number.isFinite);
  const allValues=[...values,...thresholds];
  if (!allValues.length) return '<div class="forecast-chart-empty">داده کافی برای نمودار موجود نیست.</div>';
  let min=Math.min(...allValues), max=Math.max(...allValues);
  if (min === max) { min-=1; max+=1; }
  const padding=(max-min)*0.08;
  min-=padding; max+=padding;
  const plotWidth=width-margin.left-margin.right, plotHeight=height-margin.top-margin.bottom;
  const count=Math.max(1,(chart.dates || []).length-1);
  const x=(index)=>margin.left+index/count*plotWidth;
  const y=(value)=>margin.top+(max-Number(value))/(max-min)*plotHeight;
  const formatAxis=(value)=>percent ? `${num(value,1)}٪` : num(value,Math.abs(value)<100 ? 2 : 0);
  const grid=[0,.25,.5,.75,1].map((ratio)=>{
    const value=max-(max-min)*ratio, yy=margin.top+plotHeight*ratio;
    return `<line class="forecast-grid-line" x1="${margin.left}" y1="${yy}" x2="${width-margin.right}" y2="${yy}"/><text class="forecast-axis-label" x="${margin.left-8}" y="${yy+4}" text-anchor="end">${esc(formatAxis(value))}</text>`;
  }).join("");
  const lines=(chart.series || []).map((series,index)=>{
    let path="", drawing=false;
    (series.values || []).forEach((value,i)=>{
      if (!Number.isFinite(Number(value))) { drawing=false; return; }
      path+=`${drawing ? "L" : "M"}${x(i).toFixed(2)},${y(value).toFixed(2)} `; drawing=true;
    });
    return `<path class="forecast-series forecast-series-${index%4}" d="${path.trim()}"/>`;
  }).join("");
  const thresholdLines=(chart.thresholds || []).map((item,index)=>`<line class="forecast-threshold forecast-threshold-${index%4}" x1="${margin.left}" y1="${y(item.value)}" x2="${width-margin.right}" y2="${y(item.value)}"><title>${esc(item.label)}: ${esc(item.value)}</title></line>`).join("");
  const dateIndex=new Map((chart.dates || []).map((date,index)=>[date,index]));
  const markers=signals ? [
    ...(chart.buy_points || []).map((item)=>({...item,type:"buy"})),
    ...(chart.sell_points || []).map((item)=>({...item,type:"sell"})),
  ].map((item)=>{
    const index=dateIndex.get(item.date);
    if (index == null || !Number.isFinite(Number(item.value))) return "";
    return `<circle class="forecast-signal-marker ${item.type}" cx="${x(index)}" cy="${y(item.value)}" r="5"><title>${item.type === "buy" ? "خرید" : "فروش"} · ${solarDate(item.date)} · ${num(item.value,2)}</title></circle>`;
  }).join("") : "";
  const firstDate=chart.dates?.[0], lastDate=chart.dates?.at(-1);
  return `<svg class="forecast-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="نمودار سری زمانی">
    ${grid}${thresholdLines}${lines}${markers}
    <text class="forecast-axis-label" x="${margin.left}" y="${height-8}" text-anchor="start">${esc(solarDate(firstDate))}</text>
    <text class="forecast-axis-label" x="${width-margin.right}" y="${height-8}" text-anchor="end">${esc(solarDate(lastDate))}</text>
  </svg>`;
}

function forecastLegend(chart, {signals=false}={}) {
  const series=(chart.series || []).map((item,index)=>`<span><i class="forecast-legend-line line-${index%4}"></i>${esc(item.name)}</span>`);
  const thresholds=(chart.thresholds || []).map((item,index)=>`<span><i class="forecast-legend-line threshold threshold-${index%4}"></i>${esc(item.label)} ${num(item.value,2)}</span>`);
  if (signals) series.push('<span><i class="forecast-legend-dot buy"></i>خرید</span>','<span><i class="forecast-legend-dot sell"></i>فروش</span>');
  return `<div class="forecast-chart-legend">${[...series,...thresholds].join("")}</div>`;
}

function renderForecastAsset(asset) {
  const metric=asset.metrics || {};
  const signalClass=asset.latest_signal === "buy" ? "buy" : asset.latest_signal === "sell" ? "sell" : "hold";
  const metricCard=(label,value,tone="")=>`<div class="forecast-metric ${tone}"><span>${esc(label)}</span><strong>${value}</strong></div>`;
  const chartCard=(title,chart,options={})=>`<article class="forecast-chart-card"><header><h4>${esc(title)}</h4>${forecastLegend(chart,options)}</header>${forecastChart(chart,options)}</article>`;
  return `<article class="forecast-asset-card">
    <header class="forecast-asset-header">
      <div><small>مدل روزانه</small><h3>${esc(asset.label)}</h3><p>${esc(asset.rule)}</p></div>
      <div class="forecast-signal ${signalClass}"><span>آخرین سیگنال</span><strong>${esc(asset.latest_signal_label)}</strong><small>${esc(solarDate(asset.signal_date_display))} · ${num(asset.signal_price,2)}</small></div>
    </header>
    <div class="forecast-current-strip"><span>وضعیت مدل: <strong>${asset.current_position ? "داخل معامله" : "خارج از معامله"}</strong></span><span>آخرین قیمت: <strong>${num(asset.current_price,2)}</strong></span><span>آخرین کندل: <strong>${esc(solarDate(asset.current_date_display))}</strong></span></div>
    <div class="forecast-metrics">
      ${metricCard("بازده استراتژی",`${num(metric.strategy_return_percent,2)}٪`,valueTone(metric.strategy_return_percent))}
      ${metricCard("خرید و نگهداری",`${num(metric.buy_hold_return_percent,2)}٪`,valueTone(metric.buy_hold_return_percent))}
      ${metricCard("بیشترین افت",`${num(metric.strategy_mdd_percent,2)}٪`,"negative-value")}
      ${metricCard("شارپ",num(metric.sharpe,2))}
      ${metricCard("تعداد معاملات",num(metric.trades))}
      ${metricCard("درگیری سرمایه",`${num(metric.exposure_percent,2)}٪`)}
    </div>
    <div class="forecast-chart-grid">
      ${chartCard("قیمت و نقاط ورود/خروج",asset.charts.price,{signals:true})}
      ${chartCard("شاخص تصمیم مدل",asset.charts.indicator)}
      ${chartCard("ارزش سرمایه: استراتژی و خرید و نگهداری",asset.charts.equity)}
      ${chartCard("افت سرمایه",asset.charts.drawdown,{percent:true})}
    </div>
  </article>`;
}

function renderForecast(data) {
  const container=$("forecastResults");
  if (!container) return;
  container.innerHTML=`<div class="forecast-meta">
    <div><span>منبع</span><strong>${esc(data.source?.name)} · ${esc(data.source?.grain)}</strong></div>
    <div><span>شروع دوره مدل</span><strong>${esc(solarDate(data.source?.model_start_date_display))}</strong></div>
    <div><span>زمان محاسبه</span><strong>${esc(String(data.generated_at_display || "—").replace(/\d/g,(digit)=>"۰۱۲۳۴۵۶۷۸۹"[digit]))}</strong></div>
  </div>${(data.assets || []).map(renderForecastAsset).join("")}
  <aside class="forecast-disclaimer"><strong>نکته روش‌شناسی:</strong> ${esc(data.methodology?.execution)} ${esc(data.methodology?.warning)}</aside>`;
}

function commodityFxTone(value) {
  return Number(value) > 0 ? "fx-expensive" : "fx-cheap";
}

function renderCommodityFx(data) {
  const container = $("commodityFxResults");
  if (!container) return;
  const free = Number(data.free_market?.price_toman);
  $("updatedAt").textContent = formatDate(data.generated_at);
  setStatus("success", `محاسبه دلار ضمنی ${num(data.assets?.length || 0)} گواهی انجام شد · دلار آزاد ${num(free)} تومان`);
  const benchmark = data.benchmarks || {};
  const cards = (data.assets || []).map((asset) => {
    const rows = (asset.quotes || []).map((quote) => {
      const tone = commodityFxTone(quote.difference_percent);
      const width = Math.min(100, Math.abs(Number(quote.difference_percent) || 0) * 4);
      return `<div class="commodity-fx-quote ${quote.id === "last" ? "is-last" : ""}">
        <strong>${esc(quote.label)}</strong>
        <span><small>قیمت گواهی</small><b>${num(quote.certificate_price_rial)} ریال</b></span>
        <span><small>دلار ضمنی</small><b>${num(quote.implied_usd_toman)} تومان</b></span>
        <span class="${tone}"><small>اختلاف با دلار آزاد</small><b>${quote.difference_toman > 0 ? "+" : ""}${num(quote.difference_toman)} تومان · ${quote.difference_percent > 0 ? "+" : ""}${num(quote.difference_percent, 2)}٪</b></span>
        <i class="commodity-fx-gap ${tone}" style="--fx-gap:${width}%" aria-hidden="true"></i>
      </div>`;
    }).join("");
    const benchmarkLabel = asset.benchmark_key === "hg" ? "مس جهانی" : asset.benchmark_key === "si" ? "نقره جهانی" : "طلای جهانی";
    const benchmarkUnit = asset.benchmark_key === "hg" ? "دلار/پوند" : "دلار/اونس";
    return `<article class="commodity-fx-card">
      <header><div><small>${esc(asset.contract_code)}</small><h3>${esc(asset.label)}</h3></div><span class="commodity-fx-live">بورس کالا</span></header>
      <div class="commodity-fx-spec"><span>${esc(asset.unit_label)}</span><span>${benchmarkLabel}: <b>${num(asset.benchmark_price, asset.benchmark_key === "hg" ? 4 : 2)} ${benchmarkUnit}</b></span></div>
      <div class="commodity-fx-conversion">
        <strong>${esc(asset.conversion?.formula || "")}</strong>
        <span dir="ltr">${esc(asset.conversion?.calculation || "")}</span>
        <small>${esc(asset.conversion?.result_unit || "")}${asset.conversion?.note ? ` · ${esc(asset.conversion.note)}` : ""}</small>
      </div>
      <div class="commodity-fx-quotes">${rows}</div>
      <footer>آخرین قیمت جهانی: ${solarDate(asset.benchmark_date)} · ارزش دلاری هر گواهی: ${num(asset.usd_value_per_certificate, 4)} دلار</footer>
    </article>`;
  }).join("");
  container.innerHTML = `<section class="commodity-fx-summary">
      <div><small>دلار بازار آزاد</small><strong>${num(free)} <em>تومان</em></strong><span>نماد TDT · ${solarDate(data.free_market?.date)}</span></div>
      <div class="commodity-benchmarks">
        <span>طلا <b>${num(benchmark.gold?.price, 2)}</b> دلار/اونس</span>
        <span>نقره <b>${num(benchmark.silver?.price, 3)}</b> دلار/اونس</span>
        <span>مس <b>${num(benchmark.copper?.price, 4)}</b> دلار/پوند</span>
      </div>
    </section>
    <div class="commodity-fx-grid">${cards}</div>
    <aside class="commodity-fx-note"><strong>روش محاسبه:</strong> ${esc(data.methodology)} نرخ گواهی سکه، حباب خود سکه را نیز در نرخ ضمنی منعکس می‌کند.</aside>
    <div class="commodity-fx-sources">منابع: <a href="https://cdn.ime.co.ir/" target="_blank" rel="noreferrer">بورس کالای ایران</a><span>·</span><a href="https://max.chartix.ir/" target="_blank" rel="noreferrer">قیمت جهانی و دلار آزاد</a></div>`;
}

async function loadCommodityFx(force = false) {
  const localButton = $("commodityFxRefreshButton"), globalButton = $("refreshButton");
  [localButton, globalButton].filter(Boolean).forEach((button) => { button.disabled = true; });
  if ($("commodityFxStatus")) {
    $("commodityFxStatus").className = "forecast-status loading";
    $("commodityFxStatus").innerHTML = '<span class="spinner"></span><span>در حال دریافت قیمت‌های بورس کالا و بازار جهانی…</span>';
  }
  try {
    const response = await apiFetch(`/api/commodity-fx${force ? "?refresh=1" : ""}`, {cache:"no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "دریافت دلار ضمنی ناموفق بود");
    state.commodityFx = data;
    renderCommodityFx(data);
    if ($("commodityFxStatus")) {
      $("commodityFxStatus").className = "forecast-status success";
      $("commodityFxStatus").textContent = `به‌روزرسانی کامل شد · ${num(data.assets?.length || 0)} گواهی · دلار آزاد ${num(data.free_market?.price_toman)} تومان`;
    }
  } catch (error) {
    setStatus("error", error.message || "دریافت دلار ضمنی بورس کالا ناموفق بود");
    if ($("commodityFxStatus")) {
      $("commodityFxStatus").className = "forecast-status error";
      $("commodityFxStatus").textContent = error.message || "دریافت دلار ضمنی بورس کالا ناموفق بود";
    }
  } finally {
    [localButton, globalButton].filter(Boolean).forEach((button) => { button.disabled = false; });
  }
}

function orderFlowHistoryChart(history = []) {
  const width=820,height=190,left=42,right=18,top=18,bottom=30;
  const x=(index)=>left+(history.length <= 1 ? (width-left-right)/2 : index*(width-left-right)/(history.length-1));
  const y=(value)=>top+(100-Math.max(-100,Math.min(100,Number(value)||0)))*(height-top-bottom)/200;
  const path=history.map((item,index)=>`${index ? "L" : "M"}${x(index).toFixed(1)},${y(item.imbalance_percent).toFixed(1)}`).join(" ");
  const first=history[0]?.timestamp,last=history.at(-1)?.timestamp;
  return `<svg class="order-flow-history-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="تغییر توازن سفارش‌ها">
    <line class="order-flow-history-guide upper" x1="${left}" y1="${y(50)}" x2="${width-right}" y2="${y(50)}"/>
    <line class="order-flow-history-zero" x1="${left}" y1="${y(0)}" x2="${width-right}" y2="${y(0)}"/>
    <line class="order-flow-history-guide lower" x1="${left}" y1="${y(-50)}" x2="${width-right}" y2="${y(-50)}"/>
    <text x="${left-6}" y="${y(50)+4}" text-anchor="end">+۵۰٪</text><text x="${left-6}" y="${y(0)+4}" text-anchor="end">۰</text><text x="${left-6}" y="${y(-50)+4}" text-anchor="end">−۵۰٪</text>
    ${path ? `<path class="order-flow-history-line" d="${path}"/>` : ""}
    ${history.map((item,index)=>`<circle cx="${x(index)}" cy="${y(item.imbalance_percent)}" r="3"><title>${formatDate(item.timestamp)} · ${num(item.imbalance_percent,2)}٪</title></circle>`).join("")}
    <text class="order-flow-time" x="${left}" y="${height-7}" text-anchor="start">${first ? esc(formatDate(first)) : "شروع ثبت"}</text>
    <text class="order-flow-time" x="${width-right}" y="${height-7}" text-anchor="end">${last ? esc(formatDate(last)) : "—"}</text>
  </svg>`;
}

function orderFlowDepthCurve(levels = []) {
  const bids=levels.filter((row)=>row.bid_price && Number(row.bid_volume)>0).map((row)=>({price:Number(row.bid_price),volume:Number(row.bid_volume)})).sort((a,b)=>a.price-b.price);
  const asks=levels.filter((row)=>row.ask_price && Number(row.ask_volume)>0).map((row)=>({price:Number(row.ask_price),volume:Number(row.ask_volume)})).sort((a,b)=>a.price-b.price);
  const points=[...bids,...asks];
  if (!points.length) return '<div class="forecast-chart-empty">داده کافی برای نمودار عمق موجود نیست.</div>';
  const width=820,height=255,left=58,right=24,top=25,bottom=42;
  let minPrice=Math.min(...points.map((row)=>row.price)),maxPrice=Math.max(...points.map((row)=>row.price));
  if (minPrice===maxPrice) { minPrice*=.99; maxPrice*=1.01; }
  const bidPoints=bids.map((row,index)=>({...row,cumulative:bids.slice(index).reduce((sum,item)=>sum+item.volume,0)}));
  let askTotal=0;
  const askPoints=asks.map((row)=>({...row,cumulative:(askTotal+=row.volume)}));
  const maxVolume=Math.max(1,...bidPoints.map((row)=>row.cumulative),...askPoints.map((row)=>row.cumulative));
  const x=(value)=>left+(value-minPrice)/(maxPrice-minPrice)*(width-left-right);
  const y=(value)=>height-bottom-value/maxVolume*(height-top-bottom);
  const stepPath=(rows)=>rows.map((row,index)=>`${index ? "L" : "M"}${x(row.price).toFixed(1)},${y(row.cumulative).toFixed(1)}`).join(" ");
  const areaPath=(rows)=>rows.length ? `${stepPath(rows)} L${x(rows.at(-1).price).toFixed(1)},${height-bottom} L${x(rows[0].price).toFixed(1)},${height-bottom} Z` : "";
  const bestBid=Number(bids.at(-1)?.price)||null,bestAsk=Number(asks[0]?.price)||null;
  const midpoint=bestBid && bestAsk ? (bestBid+bestAsk)/2 : (minPrice+maxPrice)/2;
  return `<svg class="order-flow-depth-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="نمودار تجمعی عمق خرید و فروش برحسب قیمت">
    <line class="depth-axis" x1="${left}" y1="${height-bottom}" x2="${width-right}" y2="${height-bottom}"/>
    <line class="depth-axis" x1="${left}" y1="${top}" x2="${left}" y2="${height-bottom}"/>
    <line class="depth-midline" x1="${x(midpoint)}" y1="${top}" x2="${x(midpoint)}" y2="${height-bottom}"/>
    ${bidPoints.length ? `<path class="depth-area bid-area" d="${areaPath(bidPoints)}"/><path class="depth-line bid-line" d="${stepPath(bidPoints)}"/>` : ""}
    ${askPoints.length ? `<path class="depth-area ask-area" d="${areaPath(askPoints)}"/><path class="depth-line ask-line" d="${stepPath(askPoints)}"/>` : ""}
    ${bidPoints.map((row)=>`<circle class="bid-dot" cx="${x(row.price)}" cy="${y(row.cumulative)}" r="4"><title>خرید ${num(row.price)} · حجم تجمعی ${num(row.cumulative)}</title></circle>`).join("")}
    ${askPoints.map((row)=>`<circle class="ask-dot" cx="${x(row.price)}" cy="${y(row.cumulative)}" r="4"><title>فروش ${num(row.price)} · حجم تجمعی ${num(row.cumulative)}</title></circle>`).join("")}
    <text x="${left}" y="${height-12}" text-anchor="start">${num(minPrice)}</text><text x="${width-right}" y="${height-12}" text-anchor="end">${num(maxPrice)}</text>
    <text class="depth-y-label" x="${left-8}" y="${top+5}" text-anchor="end">${num(maxVolume)}</text>
    <text class="depth-bid-label" x="${left+8}" y="${top+16}" text-anchor="start">خرید تجمعی</text><text class="depth-ask-label" x="${width-right-8}" y="${top+16}" text-anchor="end">فروش تجمعی</text>
  </svg>`;
}

function orderFlowCandleDepthChart(candles = [], levels = []) {
  const recent=candles.slice(-18);
  if (!recent.length) return '<div class="order-flow-candle-empty">هنوز معامله‌ای برای ساخت کندل ۱۵ دقیقه‌ای این نماد ثبت نشده است.</div>';
  const orderLines=levels.flatMap((row)=>[
    row.bid_price && Number(row.bid_volume)>0 ? {side:"bid",price:Number(row.bid_price),volume:Number(row.bid_volume),level:row.level} : null,
    row.ask_price && Number(row.ask_volume)>0 ? {side:"ask",price:Number(row.ask_price),volume:Number(row.ask_volume),level:row.level} : null,
  ]).filter(Boolean);
  const allPrices=[...recent.flatMap((row)=>[Number(row.low),Number(row.high)]),...orderLines.map((row)=>row.price)].filter((value)=>Number.isFinite(value)&&value>0);
  if (!allPrices.length) return '<div class="order-flow-candle-empty">داده قیمتی کافی موجود نیست.</div>';
  const width=980,height=230,left=76,right=76,top=20,bottom=38;
  let minPrice=Math.min(...allPrices),maxPrice=Math.max(...allPrices);
  const padding=Math.max((maxPrice-minPrice)*.06,maxPrice*.001);
  minPrice=Math.max(0,minPrice-padding);maxPrice+=padding;
  const candleLeft=190,candleRight=width-190;
  const x=(index)=>recent.length===1 ? (candleLeft+candleRight)/2 : candleLeft+index*(candleRight-candleLeft)/(recent.length-1);
  const y=(price)=>top+(maxPrice-price)/(maxPrice-minPrice)*(height-top-bottom);
  const candleWidth=Math.max(8,Math.min(18,(candleRight-candleLeft)/Math.max(2,recent.length)*.48));
  const maxOrderVolume=Math.max(1,...orderLines.map((row)=>row.volume));
  const maxLine=150,latestX=x(recent.length-1);
  const priceTicks=[maxPrice,(maxPrice+minPrice)/2,minPrice];
  const marks=recent.map((row,index)=>{
    const open=Number(row.open),close=Number(row.close),high=Number(row.high),low=Number(row.low),up=close>=open;
    const bodyTop=y(Math.max(open,close)),bodyHeight=Math.max(3,Math.abs(y(open)-y(close)));
    return `<g class="candle ${up ? "up" : "down"}"><line x1="${x(index)}" y1="${y(high)}" x2="${x(index)}" y2="${y(low)}"/><rect x="${x(index)-candleWidth/2}" y="${bodyTop}" width="${candleWidth}" height="${bodyHeight}" rx="2"><title>${esc(formatDate(row.timestamp))} · باز ${num(open)} · بیشینه ${num(high)} · کمینه ${num(low)} · بسته ${num(close)}</title></rect></g>`;
  }).join("");
  const depth=orderLines.map((row)=>{
    const length=Math.max(8,row.volume/maxOrderVolume*maxLine);
    const x2=row.side==="bid" ? latestX-length : latestX+length;
    const anchor=row.side==="bid" ? "end" : "start";
    const labelX=x2+(row.side==="bid" ? -5 : 5);
    return `<g class="candle-depth-level ${row.side}"><line x1="${latestX}" y1="${y(row.price)}" x2="${x2}" y2="${y(row.price)}"><title>${row.side==="bid" ? "خرید" : "فروش"} سطح ${num(row.level)} · قیمت ${num(row.price)} · حجم ${num(row.volume)}</title></line><circle cx="${x2}" cy="${y(row.price)}" r="3"/><text x="${labelX}" y="${y(row.price)-5}" text-anchor="${anchor}">${num(row.volume)}</text></g>`;
  }).join("");
  const timeLabel=(value)=>{ try{return new Date(value).toLocaleTimeString("fa-IR",{hour:"2-digit",minute:"2-digit"});}catch{return "—";} };
  return `<svg class="order-flow-candle-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="کندل‌های پانزده دقیقه و سطوح حجم سفارش">
    ${priceTicks.map((value)=>`<line class="candle-grid" x1="${left}" y1="${y(value)}" x2="${width-right}" y2="${y(value)}"/><text x="${left-8}" y="${y(value)+4}" text-anchor="end">${num(value)}</text>`).join("")}
    <line class="candle-latest-guide" x1="${latestX}" y1="${top}" x2="${latestX}" y2="${height-bottom}"/>
    ${marks}${depth}
    <text class="candle-bid-caption" x="${latestX-158}" y="${top+13}" text-anchor="start">سطوح خرید ←</text><text class="candle-ask-caption" x="${latestX+158}" y="${top+13}" text-anchor="end">→ سطوح فروش</text>
    <text x="${x(0)}" y="${height-14}" text-anchor="middle">${esc(timeLabel(recent[0].timestamp))}</text><text x="${latestX}" y="${height-14}" text-anchor="middle">${esc(timeLabel(recent.at(-1).timestamp))}</text>
  </svg>`;
}

function renderOrderFlow(data) {
  const container=$("orderFlowResults");
  if (!container) return;
  const levels=data.levels || [];
  const maxVolume=Math.max(1,...levels.flatMap((row)=>[Number(row.bid_volume)||0,Number(row.ask_volume)||0]));
  const ladder=levels.map((row)=>{
    const bidWidth=(Number(row.bid_volume)||0)/maxVolume*100;
    const askWidth=(Number(row.ask_volume)||0)/maxVolume*100;
    return `<div class="order-flow-level">
      <div class="order-flow-side bid"><i style="width:${bidWidth}%"></i><span><b>${num(row.bid_volume)}</b><small>${row.bid_orders == null ? "" : `${num(row.bid_orders)} سفارش`}</small></span><strong>${row.bid_price ? num(row.bid_price) : "—"}</strong></div>
      <em>${num(row.level)}</em>
      <div class="order-flow-side ask"><strong>${row.ask_price ? num(row.ask_price) : "—"}</strong><span><b>${num(row.ask_volume)}</b><small>${row.ask_orders == null ? "" : `${num(row.ask_orders)} سفارش`}</small></span><i style="width:${askWidth}%"></i></div>
    </div>`;
  }).join("");
  const rows=levels.map((row)=>`<tr><td>${num(row.level)}</td><td>${row.bid_orders == null ? "—" : num(row.bid_orders)}</td><td>${num(row.bid_volume)}</td><td class="bid-price">${row.bid_price ? num(row.bid_price) : "—"}</td><td class="ask-price">${row.ask_price ? num(row.ask_price) : "—"}</td><td>${num(row.ask_volume)}</td><td>${row.ask_orders == null ? "—" : num(row.ask_orders)}</td></tr>`).join("");
  const imbalance=Number(data.imbalance_percent)||0;
  container.innerHTML=`<section class="order-flow-kpis">
    <article><span>بهترین خرید</span><strong class="bid-price">${data.best_bid ? num(data.best_bid) : "—"}</strong></article>
    <article><span>بهترین فروش</span><strong class="ask-price">${data.best_ask ? num(data.best_ask) : "—"}</strong></article>
    <article><span>شکاف قیمت</span><strong>${data.spread_percent == null ? "—" : `${num(data.spread_percent,3)}٪`}</strong></article>
    <article><span>توازن حجم</span><strong class="${imbalance >= 0 ? "bid-price" : "ask-price"}">${imbalance > 0 ? "+" : ""}${num(imbalance,2)}٪</strong></article>
  </section>
  <article class="order-flow-card candle-depth-card"><header><div><small>قیمت و نقدینگی در یک مقیاس</small><h3>کندل ۱۵ دقیقه و سطوح سفارش</h3></div><span>طول خط = حجم سفارش</span></header>${orderFlowCandleDepthChart(data.candles || [],levels)}<footer>${esc(data.candle_source || "")} · خطوط سبز خرید و خطوط قرمز فروش هستند.</footer></article>
  <section class="order-flow-grid">
    <article class="order-flow-card depth-card"><header><div><small>${data.market === "tehran" ? "بورس تهران" : "بورس کالا"} · ${data.instrument_type === "option" ? "اختیار خرید" : "دارایی پایه"}</small><h3>${esc(data.symbol)}</h3><p>${esc(data.asset)}</p></div><span>${num(data.depth_limit)} ردیف رسمی</span></header><div class="order-flow-axis"><b>خرید</b><span>قیمت و سطح</span><b>فروش</b></div><div class="order-flow-ladder">${ladder}</div><footer>حجم کل خرید ${num(data.total_bid_volume)} · حجم کل فروش ${num(data.total_ask_volume)}</footer></article>
    <article class="order-flow-card curve-card"><header><div><small>حجم تجمعی در هر قیمت</small><h3>منحنی عمق بازار</h3></div><span>قیمت ← حجم تجمعی</span></header>${orderFlowDepthCurve(levels)}<p>سمت خرید از بهترین قیمت به بیرون و سمت فروش از بهترین عرضه به بیرون تجمیع شده است.</p></article>
    <article class="order-flow-card history-card"><header><div><small>از زمان بازبودن این صفحه</small><h3>روند توازن سفارش‌ها</h3></div><span>صفر = تعادل</span></header>${orderFlowHistoryChart(data.history || [])}<p>عدد مثبت یعنی غلبه حجم خرید و عدد منفی یعنی غلبه حجم فروش در ردیف‌های قابل مشاهده.</p></article>
  </section>
  <section class="order-flow-table-card"><header><h3>جدول دقیق عمق بازار</h3><span>${esc(data.source)} · ${num(levels.length)} سطح</span></header><div class="order-flow-table-wrap"><table><thead><tr><th>سطح</th><th>تعداد خرید</th><th>حجم خرید</th><th>قیمت خرید</th><th>قیمت فروش</th><th>حجم فروش</th><th>تعداد فروش</th></tr></thead><tbody>${rows}</tbody></table></div></section>
  <aside class="order-flow-note"><strong>محدوده داده:</strong> ${esc(data.note)} ${data.depth_limit < 5 ? `این نماد در منبع رسمی ${num(data.depth_limit)} ردیف منتشر می‌کند.` : ""} تاریخچه نمودار از زمان مشاهده نماد در همین اجرای برنامه ساخته می‌شود.</aside>`;
  $("updatedAt").textContent=formatDate(data.generated_at);
}

function populateOrderFlowSymbols({load=true}={}) {
  const select=$("orderFlowSymbol");
  if (!select) return;
  const current=select.value;
  const items=state.orderFlowCatalog.filter((item)=>item.market===state.orderFlowMarket && item.instrument_type===state.orderFlowType);
  select.innerHTML=items.map((item)=>`<option value="${esc(item.symbol)}">${esc(item.symbol)}${item.instrument_type === "option" ? ` · ${esc(item.asset)}` : ""}</option>`).join("");
  if (items.some((item)=>item.symbol===current)) select.value=current;
  if (load && select.value) loadOrderFlow(false);
}

function scheduleOrderFlowRefresh() {
  if (state.orderFlowTimer) clearInterval(state.orderFlowTimer);
  if (currentPage !== "order-flow") return;
  const seconds=Number($("orderFlowRefreshRate")?.value)||30;
  state.orderFlowTimer=setInterval(()=>loadOrderFlow(true),seconds*1000);
}

async function loadOrderFlow(force=false) {
  const symbol=$("orderFlowSymbol")?.value;
  if (!symbol) return;
  const button=$("orderFlowRefreshButton");
  if (button) button.disabled=true;
  if ($("orderFlowStatus")) { $("orderFlowStatus").className="forecast-status loading"; $("orderFlowStatus").innerHTML='<span class="spinner"></span><span>در حال دریافت دفتر سفارش از منبع رسمی…</span>'; }
  try {
    const query=new URLSearchParams({market:state.orderFlowMarket,instrument_type:state.orderFlowType,symbol});
    if(force) query.set("refresh","1");
    const response=await apiFetch(`/api/order-book?${query}`,{cache:"no-store"});
    const data=await response.json();
    if(!response.ok) throw new Error(data.detail || data.error || "دریافت دفتر سفارش ناموفق بود");
    renderOrderFlow(data);
    setStatus("success",`عمق سفارش ${symbol} به‌روز شد · ${num(data.levels?.length || 0)} ردیف رسمی`);
    if ($("orderFlowStatus")) { $("orderFlowStatus").className="forecast-status success"; $("orderFlowStatus").textContent=`${num(data.levels?.length || 0)} ردیف تجمیعی دریافت شد · ${data.source}`; }
  } catch(error) {
    setStatus("error",error.message || "دریافت جریان سفارش‌ها ناموفق بود");
    if ($("orderFlowStatus")) { $("orderFlowStatus").className="forecast-status error"; $("orderFlowStatus").textContent=error.message || "دریافت جریان سفارش‌ها ناموفق بود"; }
  } finally { if(button) button.disabled=false; }
}

async function loadOrderFlowPage() {
  try {
    const response=await apiFetch("/api/order-book/catalog",{cache:"no-store"});
    const data=await response.json();
    if(!response.ok) throw new Error(data.detail || data.error || "دریافت فهرست نمادها ناموفق بود");
    state.orderFlowCatalog=data.instruments || [];
    populateOrderFlowSymbols({load:false});
    await loadOrderFlow(false);
    scheduleOrderFlowRefresh();
  } catch(error) {
    setStatus("error",error.message || "دریافت فهرست نمادها ناموفق بود");
    if ($("orderFlowStatus")) { $("orderFlowStatus").className="forecast-status error"; $("orderFlowStatus").textContent=error.message; }
  }
}

async function loadForecast(force=false) {
  const localButton=$("forecastRefreshButton"), globalButton=$("refreshButton");
  [localButton,globalButton].filter(Boolean).forEach((button)=>{button.disabled=true;button.classList.add("loading");});
  if ($("forecastStatus")) $("forecastStatus").innerHTML='<span class="spinner"></span><span>در حال دریافت هشت سری زمانی و اجرای سه مدل…</span>';
  setStatus("loading",force ? "در حال محاسبه دوباره پیش‌بینی با تازه‌ترین کندل‌ها…" : "در حال دریافت نتایج مدل پیش‌بینی…");
  try {
    const response=await apiFetch(`/api/forecast${force ? "?refresh=1" : ""}`,{cache:"no-store"});
    const data=await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || "دریافت پیش‌بینی ناموفق بود");
    state.forecast=data; renderForecast(data);
    $("updatedAt").textContent=formatDate(data.generated_at);
    if ($("forecastStatus")) { $("forecastStatus").className="forecast-status success"; $("forecastStatus").innerHTML=`<span>محاسبه کامل شد · ${num(data.assets?.length || 0)} بازار · آخرین کندل‌ها تا ${esc(solarDate(data.assets?.[0]?.current_date_display))}</span>`; }
    setStatus("success",`پیش‌بینی‌ها به‌روز شدند · تازه‌سازی بعدی تا ${num(state.userSettings.refreshMinutes)} دقیقه دیگر`);
  } catch(error) {
    if ($("forecastStatus")) { $("forecastStatus").className="forecast-status error"; $("forecastStatus").textContent=error.message || "دریافت پیش‌بینی ناموفق بود"; }
    setStatus("error",error.message || "دریافت پیش‌بینی ناموفق بود");
  } finally { [localButton,globalButton].filter(Boolean).forEach((button)=>{button.disabled=false;button.classList.remove("loading");}); }
}

async function loadData(force = false) {
  const button = $("refreshButton");
  button.disabled = true; button.classList.add("loading");
  setStatus("loading", force ? "در حال تازه‌سازی مستقیم از منابع بازار…" : "در حال دریافت داده‌ها…");
  try {
    const response = await apiFetch(`/api/data${force ? "?refresh=1" : ""}`, {cache: "no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || "خطای دریافت اطلاعات");
    state.data = data;
    if (state.longInterestRate == null) state.longInterestRate = Number(data.rules.long_interest_rate ?? 40);
    applyLongInterestRate();
    applyPricingBasis();
    syncLongInterestRateControls();
    fillSummary(data); renderRules(data); render(); await loadTrades();
    setDataLoadedStatus();
  } catch (error) { setStatus("error", error.message || "دریافت اطلاعات ناموفق بود"); }
  finally { button.disabled = false; button.classList.remove("loading"); }
}

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => { document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active")); tab.classList.add("active"); state.strategy = tab.dataset.strategy; render(); }));
$("assetFilter").addEventListener("change", (event) => { state.asset = event.target.value; render(); });
if ($("marketFilter")) $("marketFilter").addEventListener("change", (event) => setMarket(event.target.value));
document.querySelectorAll("[data-overview-market]").forEach((card) => card.addEventListener("click", () => setMarket(card.dataset.overviewMarket)));
document.querySelectorAll("[data-market-card]").forEach((card) => card.addEventListener("click", () => setMarket(card.dataset.marketCard)));
document.querySelectorAll("[data-state-filter]").forEach((button)=>button.addEventListener("click",()=>{ state.status=button.dataset.stateFilter; syncMarketControls(); render(); }));
document.querySelectorAll("[data-covered-basis]").forEach((button)=>button.addEventListener("click",()=>{ state.coveredBasis=button.dataset.coveredBasis; saveMarketPricing(); applyPricingBasis(); fillSummary(state.data); syncMarketControls(); render(); }));
document.querySelectorAll("[data-covered-base-basis]").forEach((button)=>button.addEventListener("click",()=>{ state.coveredBaseBasis=button.dataset.coveredBaseBasis; saveMarketPricing(); applyPricingBasis(); fillSummary(state.data); syncMarketControls(); render(); }));
document.querySelectorAll("[data-covered-ranking]").forEach((button)=>button.addEventListener("click",()=>{ state.coveredRanking=button.dataset.coveredRanking; syncMarketControls(); renderTopOpportunities(); }));
document.querySelectorAll("[data-long-basis]").forEach((button)=>button.addEventListener("click",()=>{ state.longBasis=button.dataset.longBasis; saveMarketPricing(); applyPricingBasis(); fillSummary(state.data); syncMarketControls(); render(); }));
document.querySelectorAll("[data-long-base-basis]").forEach((button)=>button.addEventListener("click",()=>{ state.longBaseBasis=button.dataset.longBaseBasis; saveMarketPricing(); applyPricingBasis(); fillSummary(state.data); syncMarketControls(); render(); }));
$("longInterestRateFilter").addEventListener("input", (event) => updateLongInterestRate(event.target.value));
$("chainLongInterestRate").addEventListener("input", (event) => updateLongInterestRate(event.target.value));
$("symbolSearch").addEventListener("input", (event) => { state.search = event.target.value.trim(); render(); });
$("chainStrategy").addEventListener("change", (event) => { state.chainStrategy = event.target.value; state.chainSortKey = state.chainStrategy === "covered_call" ? "annual_return" : "advantage_percent"; state.chainSortDirection = "desc"; syncLongInterestRateControls(); renderTehranChain(); });
$("chainMarket").addEventListener("change", (event) => { state.chainMarket = event.target.value; renderTehranChain(); });
document.querySelectorAll("[data-market-data-view]").forEach((button)=>button.addEventListener("click",()=>{
  state.marketDataView=button.dataset.marketDataView;
  state.chainStrategy=state.marketDataView==="long_underlying"?"long_underlying":"covered_call";
  $("chainStrategy").value=state.chainStrategy;
  state.chainSortKey=state.marketDataView==="all"?"symbol":state.marketDataView==="covered_call"?"annual_return":"advantage_percent";
  state.chainSortDirection="desc";
  syncLongInterestRateControls(); renderTehranChain();
}));
$("marketDataRefresh")?.addEventListener("click",()=>loadData(true));
$("marketDataSavedFilters")?.addEventListener("click",()=>{ $("toggleColumnManager")?.click(); $("chainColumnManager")?.scrollIntoView({behavior:"smooth",block:"start"}); });
$("chainMarket").value=state.chainMarket;
$("tehranChainSearch").value=state.chainSearch;
$("tehranChainState").value=state.chainState;
[["marketStrikeMin","marketStrikeMin"],["marketStrikeMax","marketStrikeMax"],["marketVolumeMin","marketVolumeMin"],["marketOpenInterestMin","marketOpenInterestMin"]].forEach(([id,key])=>{if(state[key]!=null)$(id).value=state[key];$(id).addEventListener("input",(event)=>{state[key]=numericFilterValue(event.target.value);renderTehranChain();});});
$("marketValidQuotesOnly").checked=state.marketValidQuotesOnly;
$("marketValidQuotesOnly").addEventListener("change",(event)=>{state.marketValidQuotesOnly=event.target.checked;renderTehranChain();});
document.querySelectorAll("[data-chain-filter-target]").forEach((button) => button.addEventListener("click", () => {
  const control = $(button.dataset.chainFilterTarget);
  if (!control || control.value === button.dataset.chainFilterValue) return;
  control.value = button.dataset.chainFilterValue;
  control.dispatchEvent(new Event("change", {bubbles:true}));
}));
$("tehranChainSearch").addEventListener("input", (event) => { state.chainSearch = event.target.value.trim(); renderTehranChain(); });

document.querySelectorAll("[data-clear-target]").forEach((button) => {
  const input = $(button.dataset.clearTarget);
  if (!input) return;
  const syncVisibility = () => button.classList.toggle("hidden", !input.value);
  input.addEventListener("input", syncVisibility);
  button.addEventListener("click", () => {
    input.value = "";
    input.dispatchEvent(new Event("input", {bubbles: true}));
    input.focus();
  });
  syncVisibility();
});
$("tehranChainState").addEventListener("change", (event) => { state.chainState = event.target.value; renderTehranChain(); });
$("tehranChainItmOperator").addEventListener("change", (event) => { state.chainItmOperator = event.target.value; renderTehranChain(); });
$("tehranChainItmValue").addEventListener("input", (event) => { state.chainItmValue = numericFilterValue(event.target.value); renderTehranChain(); });
$("tehranChainQueue").addEventListener("change", (event) => { state.chainQueue = event.target.value; renderTehranChain(); });
$("tehranChainTransactionOperator").addEventListener("change", (event) => { state.chainTransactionOperator = event.target.value; renderTehranChain(); });
$("tehranChainTransactionValue").addEventListener("input", (event) => { state.chainTransactionValue = numericFilterValue(event.target.value); renderTehranChain(); });
$("tehranChainDaysOperator").addEventListener("change", (event) => { state.chainDaysOperator = event.target.value; renderTehranChain(); });
$("tehranChainDaysMin").addEventListener("input", (event) => { state.chainDaysMin = numericFilterValue(event.target.value); renderTehranChain(); });
$("tehranChainAnnualMin").addEventListener("input", (event) => { state.chainAnnualMin = numericFilterValue(event.target.value); renderTehranChain(); });
$("toggleColumnManager").addEventListener("click", () => {
  const panel = $("chainColumnManager");
  const expanded = panel.classList.toggle("hidden") === false;
  $("toggleColumnManager").setAttribute("aria-expanded", String(expanded));
});
$("resetChainColumns").addEventListener("click", () => {
  delete state.chainColumnOrders[activeChainLayoutKey()];
  delete state.chainHiddenColumns[activeChainLayoutKey()];
  saveChainColumnOrders();
  saveChainHiddenColumns();
  renderTehranChain();
  setChainViewMessage("ترتیب و ستون‌های پیش‌فرض بازگردانده شد.");
});
$("showAllChainColumns").addEventListener("click", () => {
  state.chainHiddenColumns[activeChainLayoutKey()] = [];
  saveChainHiddenColumns();
  renderTehranChain();
  setChainViewMessage("همه ستون‌ها نمایش داده شدند.");
});
$("saveChainView").addEventListener("click", saveCurrentChainView);
$("loadChainView").addEventListener("click", loadSelectedChainView);
$("deleteChainView").addEventListener("click", deleteSelectedChainView);
$("savedChainViews").addEventListener("change", (event) => {
  $("loadChainView").disabled = !event.target.value;
  $("deleteChainView").disabled = !event.target.value;
});
$("chainViewName").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); saveCurrentChainView(); } });
$("textScaleSetting").addEventListener("input", (event) => updateUserSettings({textScale:Number(event.target.value)}));
$("refreshIntervalSetting").addEventListener("input", (event) => updateUserSettings({refreshMinutes:Number(event.target.value)}));
const systemThemeMedia = window.matchMedia?.("(prefers-color-scheme: dark)");
systemThemeMedia?.addEventListener?.("change", () => {
  if (state.userSettings.theme === "system") applyUserSettings();
});
$("themeToggle").addEventListener("click", () => {
  const resolvedTheme = document.documentElement.dataset.theme;
  updateUserSettings({theme:resolvedTheme === "dark" ? "light" : "dark"});
});
const navigationToggle = $("navigationToggle");
const mainNavigation = $("mainNavigation");
const navigationBackdrop = $("navigationBackdrop");
const appHeader = document.querySelector(".app-header");
const navigationHome = {parent:mainNavigation.parentElement, next:mainNavigation.nextElementSibling};
const backdropHome = {parent:navigationBackdrop.parentElement, next:navigationBackdrop.nextElementSibling};
let navigationReturnFocus = null;
const navigationDropdownSections = [...mainNavigation.querySelectorAll(".nav-section")];

function setNavigationDropdown(section, open, {restoreFocus=false}={}) {
  navigationDropdownSections.forEach((candidate) => {
    const candidateOpen = candidate === section && open;
    candidate.classList.toggle("dropdown-open", candidateOpen);
    candidate.querySelectorAll(":scope > .nav-section-main [aria-controls]").forEach((control) => {
      control.setAttribute("aria-expanded", String(candidateOpen));
    });
    if (!candidateOpen) candidate.querySelector(":scope > .nav-children")?.setAttribute("aria-hidden", "true");
    else candidate.querySelector(":scope > .nav-children")?.setAttribute("aria-hidden", "false");
  });
  if (!open && restoreFocus) section?.querySelector(":scope > .nav-section-main [aria-controls]")?.focus();
}

function setNavigationOpen(open, {restoreFocus=true}={}) {
  const mobile = window.matchMedia("(max-width: 959px)").matches;
  const nextOpen = Boolean(open && mobile);
  if (nextOpen) navigationReturnFocus = navigationToggle;
  document.body.classList.toggle("nav-open", nextOpen);
  navigationToggle.setAttribute("aria-expanded", String(nextOpen));
  navigationToggle.setAttribute("aria-label", nextOpen ? "بستن منوی اصلی" : "بازکردن منوی اصلی");
  mainNavigation.setAttribute("aria-hidden", String(mobile && !nextOpen));
  mainNavigation.inert = mobile && !nextOpen;
  navigationBackdrop.hidden = !nextOpen;
  if (nextOpen) setTimeout(() => {
    if (document.body.classList.contains("nav-open")) {
      mainNavigation.querySelector("a:not([hidden]),button:not([hidden])")?.focus();
    }
  }, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 210);
  else {
    setNavigationDropdown(null, false);
    if (restoreFocus && navigationReturnFocus instanceof HTMLElement) navigationReturnFocus.focus();
    navigationReturnFocus = null;
  }
}

navigationToggle.addEventListener("click", () => setNavigationOpen(!document.body.classList.contains("nav-open")));
navigationBackdrop.addEventListener("click", () => setNavigationOpen(false));
mainNavigation.querySelectorAll(".nav-section-main [aria-controls]").forEach((control) => {
  control.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const section = control.closest(".nav-section");
    setNavigationDropdown(section, !section.classList.contains("dropdown-open"));
  });
});
document.addEventListener("click", (event) => {
  if (!mainNavigation.contains(event.target)) setNavigationDropdown(null, false);
});
document.addEventListener("keydown", (event) => {
  const openDropdown = mainNavigation.querySelector(".nav-section.dropdown-open");
  if (event.key === "Escape" && document.body.classList.contains("nav-open")) {
    event.preventDefault();
    setNavigationOpen(false);
    return;
  }
  if (event.key === "Escape" && openDropdown) {
    event.preventDefault();
    setNavigationDropdown(openDropdown, false, {restoreFocus:true});
    return;
  }
  if (event.key === "Tab" && document.body.classList.contains("nav-open")) {
    const controls = [...mainNavigation.querySelectorAll('a:not([hidden]),button:not([hidden])')].filter((item) => !item.closest('[aria-hidden="true"]'));
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
});
mainNavigation.addEventListener("keydown", (event) => {
  const trigger = event.target.closest(".nav-dropdown-trigger");
  if (trigger && event.key === "ArrowDown") {
    event.preventDefault();
    const section = trigger.closest(".nav-section");
    setNavigationDropdown(section, true);
    section.querySelector(".nav-children a:not([hidden])")?.focus();
    return;
  }
  const link = event.target.closest(".nav-children a");
  if (!link || !["ArrowDown", "ArrowUp"].includes(event.key)) return;
  event.preventDefault();
  const links = [...link.closest(".nav-children").querySelectorAll("a:not([hidden])")];
  const offset = event.key === "ArrowDown" ? 1 : -1;
  links[(links.indexOf(link) + offset + links.length) % links.length]?.focus();
});
mainNavigation.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
  setNavigationDropdown(null, false);
  setNavigationOpen(false, {restoreFocus:false});
}));
const navigationMedia = window.matchMedia("(max-width: 959px)");
function syncNavigationMode() {
  const mobile = navigationMedia.matches;
  if (mobile) document.body.append(navigationBackdrop, mainNavigation);
  else {
    navigationHome.parent.insertBefore(mainNavigation, navigationHome.next);
    backdropHome.parent.insertBefore(navigationBackdrop, backdropHome.next);
  }
  navigationToggle.hidden = !mobile;
  if (!mobile) setNavigationOpen(false, {restoreFocus:false});
  else if (!document.body.classList.contains("nav-open")) {
    mainNavigation.setAttribute("aria-hidden", "true");
    mainNavigation.inert = true;
  }
}
navigationMedia.addEventListener?.("change", syncNavigationMode);
syncNavigationMode();
function syncHeaderScrollState() { appHeader?.classList.toggle("is-scrolled", window.scrollY > 12); }
window.addEventListener("scroll", syncHeaderScrollState, {passive:true});
syncHeaderScrollState();
$("resetUserSettings").addEventListener("click", () => {
  state.userSettings={...DEFAULT_USER_SETTINGS};
  saveUserSettings();
  applyUserSettings({announce:true});
  scheduleAutoRefresh();
  if(state.data) {
    renderRules(state.data);
    setDataLoadedStatus();
  }
});
$("refreshButton").addEventListener("click", () => currentPage === "articles" ? loadArticles() : ["economic-indicators","economic-comparison"].includes(currentPage) ? loadEconomicIndicators(true) : currentPage === "statistical-center" ? loadStatisticalCenter(statisticalCenterFilters()) : currentPage === "central-bank" ? loadMonetaryIndicators("all", true) : currentPage === "forecast" ? loadForecast(true) : currentPage === "commodity-exchange" ? loadCommodityFx(true) : currentPage === "order-flow" ? loadOrderFlow(true) : loadData(true));
if ($("forecastRefreshButton")) $("forecastRefreshButton").addEventListener("click", () => loadForecast(true));
if ($("commodityFxRefreshButton")) $("commodityFxRefreshButton").addEventListener("click", () => loadCommodityFx(true));
if ($("orderFlowRefreshButton")) $("orderFlowRefreshButton").addEventListener("click", () => loadOrderFlow(true));
document.querySelectorAll("[data-order-market]").forEach((button)=>button.addEventListener("click",()=>{
  state.orderFlowMarket=button.dataset.orderMarket;
  document.querySelectorAll("[data-order-market]").forEach((item)=>item.classList.toggle("active",item===button));
  populateOrderFlowSymbols();
}));
document.querySelectorAll("[data-order-type]").forEach((button)=>button.addEventListener("click",()=>{
  state.orderFlowType=button.dataset.orderType;
  document.querySelectorAll("[data-order-type]").forEach((item)=>item.classList.toggle("active",item===button));
  populateOrderFlowSymbols();
}));
if ($("orderFlowSymbol")) $("orderFlowSymbol").addEventListener("change",()=>loadOrderFlow(false));
if ($("orderFlowRefreshRate")) $("orderFlowRefreshRate").addEventListener("change",scheduleOrderFlowRefresh);
$("coveredCalculatorForm").addEventListener("submit", calculateCoveredCall);
$("calculatorReset").addEventListener("click", () => { $("calculatorResult").classList.add("hidden"); $("calculatorResult").innerHTML = ""; });
$("longCalculatorForm").addEventListener("submit", calculateLongCallManual);
$("longCalculatorReset").addEventListener("click", () => { $("longCalculatorResult").classList.add("hidden"); $("longCalculatorResult").innerHTML = ""; });
$("tradeForm").addEventListener("submit", saveTrade);
for (const eventName of ["input","change"]) {
  $("tradeForm").addEventListener(eventName, (event) => {
    const field = event.target.closest("input,select,textarea");
    if (!field?.name) return;
    clearTradeFieldError(field);
    if (field.name === "asset") clearTradeFieldError(event.currentTarget.elements.option_symbol);
    if (!event.currentTarget.querySelector('[aria-invalid="true"]')) tradeModalMessage();
  });
}
$("underlyingForm").addEventListener("submit", saveUnderlying);
$("underlyingForm").addEventListener("invalid", (event) => {
  const label=event.target.closest("label,.trade-date-field")?.querySelector("span")?.textContent?.trim()||"اطلاعات فرم";
  tradeModalMessage("error",`فیلد «${label}» را تکمیل یا بررسی کنید.`);
}, true);
$("underlyingCloseForm").addEventListener("submit", saveUnderlyingClose);
$("accountCapitalForm").addEventListener("submit", submitAccountCapital);
$("accountCapitalAuto").addEventListener("click", (event) => saveAccountCapital("", $("accountCapitalForm").elements.cash_balance.value, event.currentTarget));
document.querySelectorAll("[data-open-trade-form]").forEach((button) => button.addEventListener("click", openNewTradeForm));
document.querySelectorAll("[data-open-underlying-form]").forEach((button) => button.addEventListener("click", () => openUnderlyingForm()));
$("underlyingCancelEdit").addEventListener("click", closeTradeEdit);
$("underlyingCloseCancel").addEventListener("click", closeTradeEdit);
$("underlyingForm").elements.acquisition_method.addEventListener("change", syncUnderlyingAcquisition);
$("underlyingForm").elements.entry_kind.addEventListener("change", switchFromUnderlyingForm);
$("underlyingForm").elements.exercise_entry_mode.addEventListener("change", syncUnderlyingAcquisition);
$("underlyingForm").elements.source_trade_id.addEventListener("change", syncUnderlyingExerciseSource);
$("underlyingForm").elements.asset.addEventListener("change", syncUnderlyingAssetMarket);
$("underlyingForm").elements.asset.addEventListener("input", syncUnderlyingAssetMarket);
$("underlyingForm").elements.entry_price.addEventListener("input", () => {
  $("underlyingForm").elements.price_confirmed.checked = false;
  updateUnderlyingEntryCommission();
});
$("underlyingForm").elements.quantity.addEventListener("input", () => updateUnderlyingEntryCommission());
$("underlyingForm").elements.market.addEventListener("change", () => updateUnderlyingEntryCommission());
$("underlyingForm").elements.commission.addEventListener("input", markCommissionManual);
$("underlyingCloseForm").elements.exit_price.addEventListener("input", () => updateUnderlyingCloseCommission());
$("underlyingCloseForm").elements.quantity.addEventListener("input", () => updateUnderlyingCloseCommission());
$("underlyingCloseForm").elements.exit_commission.addEventListener("input", markCommissionManual);
$("underlyingDatePickerButton").addEventListener("click", (event) => {
  event.stopPropagation();
  if ($("underlyingDatePicker").classList.contains("hidden")) openUnderlyingDatePicker();
  else closeUnderlyingDatePicker();
});
$("underlyingForm").elements.entry_date.addEventListener("click", (event) => { event.stopPropagation(); openUnderlyingDatePicker(); });
$("underlyingDatePicker").addEventListener("click", (event) => {
  event.stopPropagation();
  const nav=event.target.closest("[data-underlying-jalali-nav]");
  if(nav){shiftUnderlyingCalendar(Number(nav.dataset.underlyingJalaliNav));return;}
  if(event.target.closest("[data-underlying-jalali-today]")){
    $("underlyingForm").elements.entry_date.value=solarDate(formatJalaliInput(currentJalaliDate()));
    closeUnderlyingDatePicker();return;
  }
  const dayButton=event.target.closest("[data-underlying-jalali-day]");
  if(!dayButton||!underlyingCalendarView)return;
  $("underlyingForm").elements.entry_date.value=solarDate(formatJalaliInput({...underlyingCalendarView,day:Number(dayButton.dataset.underlyingJalaliDay)}));
  closeUnderlyingDatePicker();
});
$("tradeCancelEdit").addEventListener("click", resetTradeForm);
$("tradeEditDismiss").addEventListener("click", closeTradeEdit);
$("tradeEditModal").addEventListener("click", (event) => { if (event.target === $("tradeEditModal")) closeTradeEdit(); });
$("entryDatePickerButton").addEventListener("click", (event) => {
  event.stopPropagation();
  if ($("entryDatePicker").classList.contains("hidden")) openEntryDatePicker();
  else closeEntryDatePicker();
});
$("tradeForm").elements.entry_date.addEventListener("click", (event) => { event.stopPropagation(); openEntryDatePicker(); });
$("entryDatePicker").addEventListener("click", (event) => {
  event.stopPropagation();
  const nav = event.target.closest("[data-jalali-nav]");
  if (nav) { shiftEntryCalendar(Number(nav.dataset.jalaliNav)); return; }
  if (event.target.closest("[data-jalali-today]")) {
    const today = currentJalaliDate();
    $("tradeForm").elements.entry_date.value = solarDate(formatJalaliInput(today));
    closeEntryDatePicker();
    return;
  }
  const dayButton = event.target.closest("[data-jalali-day]");
  if (!dayButton || !entryCalendarView) return;
  $("tradeForm").elements.entry_date.value = solarDate(formatJalaliInput({...entryCalendarView,day:Number(dayButton.dataset.jalaliDay)}));
  closeEntryDatePicker();
});
$("tradeForm").elements.strategy_type.addEventListener("change", syncTradeType);
$("tradeForm").elements.contract_entry_mode.addEventListener("change", () => {
  clearTradeValidation($("tradeForm"));
  if (manualExpiredContractMode()) syncTradeContractEntryMode();
  else populateTradeContracts();
});
$("tradeForm").elements.underlying_source_mode.addEventListener("change", syncCoveredUnderlyingSource);
$("tradeForm").elements.market.addEventListener("change", () => { populateTradeAssets(); populateTradeContracts(); updateTradeEntryCommissions(); });
$("tradeForm").elements.asset.addEventListener("input", () => populateTradeContracts());
$("tradeForm").elements.asset.addEventListener("change", () => populateTradeContracts());
$("tradeForm").elements.option_symbol.addEventListener("change", syncTradeContract);
for (const name of ["manual_option_symbol", "manual_strike", "manual_expiry", "manual_contract_size"]) {
  $("tradeForm").elements[name].addEventListener("input", syncTradeContractEntryMode);
}
for (const name of ["entry_base_price", "entry_premium"]) {
  $("tradeForm").elements[name].addEventListener("input", () => {
    $("tradeForm").elements.price_confirmed.checked = false;
    updateTradeEntryCommissions();
  });
}
for (const name of ["quantity", "exercise_quantity", "premium_trade_quantity"]) {
  $("tradeForm").elements[name].addEventListener("input", () => {
    populateUnderlyingPositionChoices($("tradeForm").elements.underlying_position_id.value);
    updateTradeEntryCommissions();
  });
}
$("tradeForm").elements.commission.addEventListener("input", markCommissionManual);
$("tradeForm").elements.underlying_purchase_commission.addEventListener("input", markCommissionManual);
$("tradeCloseForm").addEventListener("submit", saveTradeClose);
$("tradeCloseForm").elements.close_quantity.addEventListener("input", () => syncTradeExitMethod({refreshMarket:false}));
$("tradeCloseForm").elements.close_exercise_quantity.addEventListener("input", () => syncTradeExitMethod({refreshMarket:false}));
$("tradeCloseForm").elements.close_premium_trade_quantity.addEventListener("input", () => syncTradeExitMethod({refreshMarket:false}));
$("tradeCloseMarket").addEventListener("click", fillTradeCloseMarket);
$("tradeExitMethod").addEventListener("change", () => syncTradeExitMethod());
$("tradeCloseForm").elements.underlying_disposition.addEventListener("change", () => syncTradeExitMethod({refreshMarket:false}));
for (const name of ["exit_base_price", "exit_option_price"]) {
  $("tradeCloseForm").elements[name].addEventListener("input", () => updateTradeCloseCommissions());
}
for (const id of ["tradeCloseOptionCommission", "tradeCloseUnderlyingCommission"]) {
  $(id).addEventListener("input", (event) => { markCommissionManual(event); updateTradeCloseCommissions(); });
}
document.querySelectorAll("[data-trade-covered-option]").forEach((button)=>button.addEventListener("click",()=>setTradePricing("covered_option_basis",button.dataset.tradeCoveredOption)));
document.querySelectorAll("[data-trade-covered-base]").forEach((button)=>button.addEventListener("click",()=>setTradePricing("covered_base_basis",button.dataset.tradeCoveredBase)));
document.querySelectorAll("[data-trade-long-option]").forEach((button)=>button.addEventListener("click",()=>setTradePricing("long_option_basis",button.dataset.tradeLongOption)));
document.querySelectorAll("[data-trade-long-base]").forEach((button)=>button.addEventListener("click",()=>setTradePricing("long_base_basis",button.dataset.tradeLongBase)));
document.querySelectorAll("[data-trade-strategy-filter]").forEach((button) => button.addEventListener("click", () => {
  state.tradeStrategyFilter[button.dataset.tradeStrategyFilter] = button.dataset.value;
  if (state.lastTradesPayload) renderTrades(state.lastTradesPayload);
}));
document.querySelectorAll("[data-trade-view-mode]").forEach((button) => button.addEventListener("click", () => {
  const full = button.dataset.value === "full";
  if (button.dataset.tradeViewMode === "open") state.tradeFullView = full;
  else state.closedTradeFullView = full;
  if (state.lastTradesPayload) renderTrades(state.lastTradesPayload);
}));
document.querySelectorAll("[data-profit-mode]").forEach((button) => button.addEventListener("click", () => {
  state.profitMode = button.dataset.profitMode;
  document.querySelectorAll("[data-profit-mode]").forEach((item) => {
    const active = item.dataset.profitMode === state.profitMode;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", String(active));
  });
  renderProfitRecognition(state.profitRecognition || {}, state.accountGrowth || {});
}));
$("exportClosedTrades").addEventListener("click", exportClosedTradesCsv);
$("exportOpenTrades").addEventListener("click", exportOpenTradesCsv);
document.querySelectorAll("[data-trade-bulk-delete]").forEach((button) => {
  button.addEventListener("click", () => deleteSelectedTrades(button.dataset.tradeBulkDelete));
});
document.querySelectorAll("[data-underlying-bulk-delete]").forEach((button) => {
  button.addEventListener("click", () => deleteSelectedUnderlyings(button.dataset.underlyingBulkDelete));
});
$("tradeCloseCancel").addEventListener("click", closeTradeClose);
$("tradeCloseDismiss").addEventListener("click", closeTradeClose);
$("tradeCloseModal").addEventListener("click", (event) => { if (event.target === $("tradeCloseModal")) closeTradeClose(); });
document.addEventListener("click", (event) => {
  if (!event.target.closest(".jalali-input-wrap")) { closeEntryDatePicker(); closeUnderlyingDatePicker(); }
  const cashButton = event.target.closest("[data-focus-account-cash]");
  if (cashButton) {
    event.preventDefault();
    focusAccountCash();
    return;
  }
  const scenarioButton = event.target.closest("[data-long-scenario-factor]");
  if (scenarioButton) {
    event.preventDefault();
    setLongCallScenario(scenarioButton, Number(scenarioButton.dataset.longScenarioFactor));
    return;
  }
  const retryButton = event.target.closest("[data-analysis-retry]");
  if (retryButton) {
    event.preventDefault();
    retryAnalysis();
    return;
  }
  const fullViewButton = event.target.closest("[data-trade-full-toggle]");
  if (fullViewButton) {
    state.tradeFullView = !state.tradeFullView;
    if (state.lastTradesPayload) renderTrades(state.lastTradesPayload);
    else applyOpenTradeView();
    return;
  }
  const detailButton = event.target.closest("[data-trade-detail]");
  if (detailButton) {
    event.preventDefault();
    try { openTradeDetailWindow(detailButton.dataset.tradeDetail, detailButton); }
    catch (error) { tradeMessage("error", error.message || "بازکردن جزئیات معامله ناموفق بود"); }
    return;
  }
  const detailClose = event.target.closest("[data-trade-detail-close]");
  if (detailClose) {
    detailClose.closest("[data-trade-detail-window], [data-underlying-detail-window]")?.remove();
    return;
  }
  const underlyingDetailButton=event.target.closest("[data-underlying-detail]");
  if(underlyingDetailButton){event.preventDefault();openUnderlyingDetailWindow(underlyingDetailButton.dataset.underlyingDetail,underlyingDetailButton);return;}
  const underlyingButton=event.target.closest("[data-underlying-action]");
  if(underlyingButton){mutateUnderlying(underlyingButton.dataset.positionId,underlyingButton.dataset.underlyingAction);return;}
  const hideButton = event.target.closest("[data-column-hide]");
  if (hideButton) {
    setChainColumnVisibility(hideButton.dataset.columnHide, false);
    return;
  }
  const sortButton = event.target.closest("[data-chain-sort]");
  if (sortButton) {
    const key = sortButton.dataset.chainSort;
    if (state.chainSortKey === key) state.chainSortDirection = state.chainSortDirection === "asc" ? "desc" : "asc";
    else { state.chainSortKey = key; state.chainSortDirection = ["asset","symbol","base_queue_status","recommendation","days"].includes(key) ? "asc" : "desc"; }
    renderTehranChain();
    return;
  }
  const button = event.target.closest("[data-trade-action]");
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  if (button.dataset.tradeAction === "edit") {
    try { editTrade(button.dataset.tradeId); }
    catch (error) { tradeMessage("error", error.message || "بازکردن پنجره ویرایش ناموفق بود"); }
  }
  else if (button.dataset.tradeAction === "close") openTradeClose(button.dataset.tradeId);
  else mutateTrade(button.dataset.tradeId, button.dataset.tradeAction);
});
document.addEventListener("input", (event) => {
  if (event.target.matches("[data-long-scenario-price]")) updateLongCallScenario(event.target);
});
document.addEventListener("pointerdown", (event) => {
  const handle = event.target.closest("[data-trade-detail-drag]");
  if (!handle || event.target.closest("[data-trade-detail-close]")) return;
  const windowElement = handle.closest("[data-trade-detail-window], [data-underlying-detail-window]");
  if (!windowElement) return;
  const rect = windowElement.getBoundingClientRect();
  tradeDetailDrag = {windowElement,pointerId:event.pointerId,offsetX:event.clientX-rect.left,offsetY:event.clientY-rect.top};
  bringTradeDetailToFront(windowElement);
  handle.setPointerCapture?.(event.pointerId);
  windowElement.classList.add("dragging");
  event.preventDefault();
});
document.addEventListener("pointermove", (event) => {
  if (!tradeDetailDrag || tradeDetailDrag.pointerId !== event.pointerId) return;
  const {windowElement,offsetX,offsetY} = tradeDetailDrag;
  const maxLeft = Math.max(8,window.innerWidth-windowElement.offsetWidth-8);
  const maxTop = Math.max(8,window.innerHeight-70);
  windowElement.style.left = `${Math.max(8,Math.min(maxLeft,event.clientX-offsetX))}px`;
  windowElement.style.top = `${Math.max(8,Math.min(maxTop,event.clientY-offsetY))}px`;
});
document.addEventListener("pointerup", (event) => {
  if (!tradeDetailDrag || tradeDetailDrag.pointerId !== event.pointerId) return;
  tradeDetailDrag.windowElement.classList.remove("dragging");
  tradeDetailDrag = null;
});
document.addEventListener("change", (event) => {
  const underlyingCheckbox = event.target.closest("[data-underlying-select]");
  if (underlyingCheckbox) {
    const id = underlyingCheckbox.dataset.underlyingSelect;
    if (underlyingCheckbox.checked) selectedUnderlyingIds.add(id);
    else selectedUnderlyingIds.delete(id);
    syncUnderlyingSelectionUi();
    return;
  }
  const underlyingSelectAll = event.target.closest("[data-underlying-select-all]");
  if (underlyingSelectAll) {
    const status = underlyingSelectAll.dataset.underlyingSelectAll;
    state.underlyingPositions
      .filter((item) => underlyingStatus(item) === status && (status === "closed" || Number(item.available_quantity || 0) > 0))
      .forEach((item) => {
        if (underlyingSelectAll.checked) selectedUnderlyingIds.add(String(item.id));
        else selectedUnderlyingIds.delete(String(item.id));
      });
    syncUnderlyingSelectionUi();
    return;
  }
  const tradeCheckbox = event.target.closest("[data-trade-select]");
  if (tradeCheckbox) {
    const id = tradeCheckbox.dataset.tradeSelect;
    if (tradeCheckbox.checked) selectedTradeIds.add(id);
    else selectedTradeIds.delete(id);
    syncTradeSelectionUi();
    return;
  }
  const selectAll = event.target.closest("[data-trade-select-all]");
  if (selectAll) {
    const status = selectAll.dataset.tradeSelectAll;
    state.trades
      .filter((item) => (item.status === "closed" ? "closed" : "open") === status)
      .forEach((item) => {
        if (selectAll.checked) selectedTradeIds.add(String(item.id));
        else selectedTradeIds.delete(String(item.id));
      });
    syncTradeSelectionUi();
    return;
  }
  const checkbox = event.target.closest("[data-column-visibility]");
  if (checkbox) setChainColumnVisibility(checkbox.dataset.columnVisibility, checkbox.checked);
});
document.addEventListener("dragstart", (event) => {
  const header = event.target.closest("th[data-column-key]");
  if (!header) return;
  state.chainDraggedColumn = header.dataset.columnKey;
  header.classList.add("dragging");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", state.chainDraggedColumn);
});
document.addEventListener("dragover", (event) => {
  const header = event.target.closest("th[data-column-key]");
  if (!header || !state.chainDraggedColumn) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
  document.querySelectorAll("th.column-drop-target").forEach((item)=>item.classList.remove("column-drop-target"));
  header.classList.add("column-drop-target");
});
document.addEventListener("drop", (event) => {
  const header = event.target.closest("th[data-column-key]");
  if (!header || !state.chainDraggedColumn) return;
  event.preventDefault();
  const targetIndex = state.chainVisibleColumnKeys.indexOf(header.dataset.columnKey);
  moveChainColumn(state.chainDraggedColumn,targetIndex);
  state.chainDraggedColumn = null;
});
document.addEventListener("dragend", () => {
  state.chainDraggedColumn = null;
  document.querySelectorAll("th.dragging, th.column-drop-target").forEach((item)=>item.classList.remove("dragging","column-drop-target"));
});
document.addEventListener("click", (event) => {
  const clearMarketFilters=event.target.closest("[data-clear-market-filters]");
  if(clearMarketFilters){state.chainSearch="";state.chainState="all";state.chainItmValue=null;state.chainQueue="all";state.chainTransactionValue=0;state.chainDaysMin=null;state.chainAnnualMin=null;state.marketStrikeMin=null;state.marketStrikeMax=null;state.marketVolumeMin=null;state.marketOpenInterestMin=null;state.marketValidQuotesOnly=false;["tehranChainSearch","tehranChainItmValue","tehranChainDaysMin","tehranChainAnnualMin","marketStrikeMin","marketStrikeMax","marketVolumeMin","marketOpenInterestMin"].forEach((id)=>$(id).value="");$("tehranChainState").value="all";$("tehranChainQueue").value="all";$("tehranChainTransactionValue").value="0";$("marketValidQuotesOnly").checked=false;renderTehranChain();return;}
  const button = event.target.closest("[data-detail]");
  if (!button) return;
  event.preventDefault();
  openAnalysisByKey(button.dataset.detail);
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-chain-detail]");
  if (!button || !state.data) return;
  const rows = state.data.strategy_tables?.[button.dataset.chainStrategy]?.[button.dataset.chainMarket] || [];
  const item = rows.find((row) => String(row.symbol) === button.dataset.chainSymbol);
  if (item) openAnalysis(item);
});
document.addEventListener("click", (event) => {
  const closeAssetButton=event.target.closest("[data-close-asset-trades]");if(closeAssetButton){event.preventDefault();event.stopPropagation();closeAssetTrades();return;}
  const assetButton=event.target.closest("[data-asset-trades]");if(assetButton){event.preventDefault();openAssetTrades(assetButton.dataset.assetTrades,assetButton);return;}
  const button = event.target.closest("[data-trade-scroll-target]");
  if (!button) return;
  const target = $(button.dataset.tradeScrollTarget);
  if (!target) return;
  button.closest(".trade-jump-rail")?.querySelectorAll("[data-trade-scroll-target]").forEach((item) => {
    const active = item === button;
    item.classList.toggle("active", active);
    item.setAttribute("aria-current", active ? "true" : "false");
  });
  target.scrollIntoView({behavior: "smooth", block: "start"});
  target.classList.remove("asset-highlight");
  requestAnimationFrame(() => target.classList.add("asset-highlight"));
  setTimeout(() => target.classList.remove("asset-highlight"), 1400);
});
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-scroll-target]");
  if (!button) return;
  const target = document.getElementById(button.dataset.scrollTarget);
  if (!target) return;
  document.querySelectorAll(".asset-nav button").forEach((item) => item.classList.toggle("active", item === button));
  target.scrollIntoView({behavior: "smooth", block: "start"});
  target.classList.remove("asset-highlight");
  requestAnimationFrame(() => target.classList.add("asset-highlight"));
  setTimeout(() => target.classList.remove("asset-highlight"), 1400);
});
$("analysisClose").addEventListener("click", closeAnalysis);
$("analysisModal").addEventListener("click", (event) => { if (event.target === $("analysisModal")) closeAnalysis(); });
$("confirmationCancel").addEventListener("click", () => closeConfirmation(false));
$("confirmationAccept").addEventListener("click", () => closeConfirmation(true));
$("confirmationModal").addEventListener("click", (event) => { if (event.target === $("confirmationModal")) closeConfirmation(false); });
$("assetTradesDismiss").addEventListener("click",closeAssetTrades);
$("assetTradesModal").addEventListener("click",(event)=>{if(event.target===$("assetTradesModal"))closeAssetTrades();});
$("logoutButton").addEventListener("click", logoutCurrentUser);
document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = $(button.dataset.passwordToggle);
    const willShow = input.type === "password";
    input.type = willShow ? "text" : "password";
    button.textContent = willShow ? "پنهان" : "نمایش";
    button.setAttribute("aria-pressed", String(willShow));
    const fieldName = button.getAttribute("aria-label").replace(/^(نمایش|پنهان) /, "");
    button.setAttribute("aria-label", `${willShow ? "پنهان" : "نمایش"} ${fieldName}`);
  });
});
$("passwordChangeForm").addEventListener("submit", (event) => {
  event.preventDefault();
  submitPasswordChange(event.currentTarget);
});
document.querySelectorAll(".trade-import-form").forEach((form) => {
  const input = form.elements.file;
  const fileLabel = form.querySelector(".trade-import-file");
  const confirmButton = form.querySelector(".trade-import-confirm");
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    fileLabel.textContent = file ? `${file.name} · ${num(Math.ceil(file.size / 1024))} کیلوبایت` : "هنوز فایلی انتخاب نشده است.";
    confirmButton.classList.add("hidden");
    form.querySelector(".trade-import-result").replaceChildren();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitTradeImport(form, false);
  });
  confirmButton.addEventListener("click", () => submitTradeImport(form, true));
});

function enhancePricingBasisControls() {
  const pricingKeys = [
    "coveredBasis", "coveredBaseBasis", "longBasis", "longBaseBasis",
    "tradeCoveredOption", "tradeCoveredBase", "tradeLongOption", "tradeLongBase",
  ];
  document.querySelectorAll(".click-option-group").forEach((group) => {
    const buttons = [...group.querySelectorAll("button")];
    const key = pricingKeys.find((candidate) => buttons.some((button) => button.dataset[candidate] !== undefined));
    if (!key || !buttons.length || group.dataset.pricingEnhanced === "true") return;
    const label = group.closest(".click-option-field")?.querySelector(":scope > span")?.textContent?.trim()
      || group.parentElement?.querySelector(":scope > span")?.textContent?.trim()
      || "انتخاب مبنای قیمت";
    const select = document.createElement("select");
    select.className = "pricing-basis-select";
    select.dataset.pricingKey = key;
    select.setAttribute("aria-label", label);
    select.innerHTML = buttons.map((button) => `<option value="${esc(button.dataset[key])}">${esc(button.textContent.trim())}</option>`).join("");
    const syncFromButtons = () => {
      const active = buttons.find((button) => button.classList.contains("active")) || buttons[0];
      select.value = active.dataset[key];
    };
    select.addEventListener("change", () => {
      buttons.find((button) => button.dataset[key] === select.value)?.click();
      document.querySelectorAll(`.pricing-basis-select[data-pricing-key="${key}"]`).forEach((peer) => { peer.value = select.value; });
    });
    new MutationObserver(syncFromButtons).observe(group, {subtree:true, attributes:true, attributeFilter:["class"]});
    group.dataset.pricingEnhanced = "true";
    group.classList.add("pricing-button-options");
    group.insertAdjacentElement("afterend", select);
    syncFromButtons();
  });
}

function mountViewportOverlays() {
  ["analysisModal", "tradeEditModal", "tradeCloseModal", "confirmationModal", "assetTradesModal", "tradeDetailWorkspace"]
    .map((id) => $(id))
    .filter(Boolean)
    .forEach((element) => {
      if (element.parentElement !== document.body) document.body.appendChild(element);
    });
}

function mountTradeDashboardSections() {
  const valuation = $("tradeValuationControls");
  const tradeSidebar = document.querySelector('.trade-page-layout[data-page-view="trades"] > .trade-control-sidebar');
  const firstSidebarAction = tradeSidebar?.querySelector(".trade-sidebar-action");
  if (valuation && tradeSidebar && valuation.parentElement !== tradeSidebar) {
    tradeSidebar.insertBefore(valuation, firstSidebarAction || null);
  }

  const profitPanel = $("profitRecognitionPanel");
  if (!profitPanel) return;
  [$("openTradesSummary"), document.querySelector(".account-growth-panel")]
    .filter(Boolean)
    .forEach((section) => profitPanel.parentElement.insertBefore(section, profitPanel));
}

mountViewportOverlays();
mountTradeDashboardSections();
enhancePricingBasisControls();

async function bootstrapApplication() {
  await Promise.all([loadIdentity(),loadServerPreferences()]);
  if(currentPage==="articles" || (currentPage==="overview" && state.serverPreferences.show_articles)) await loadArticles();
  if (currentPage === "articles") return;
  if (["economic-indicators","economic-comparison"].includes(currentPage)) await loadEconomicIndicators(false);
  else if (currentPage === "central-bank") await loadMonetaryIndicators("all", false);
  else if (currentPage === "statistical-center") setDataLoadedStatus();
  else if (currentPage === "forecast") await loadForecast(false).then(scheduleAutoRefresh);
  else if (currentPage === "commodity-exchange") await loadCommodityFx(false).then(scheduleAutoRefresh);
  else if (currentPage === "order-flow") await loadOrderFlowPage();
  else await loadData(false).then(scheduleAutoRefresh);
  if (window.location.pathname === "/trades/new") openNewTradeForm();
  const tradeDetailMatch = window.location.pathname.match(/^\/trades\/([^/]+)$/);
  if (tradeDetailMatch && !["open","closed","new"].includes(tradeDetailMatch[1])) {
    const tradeId = decodeURIComponent(tradeDetailMatch[1]);
    const trade = state.trades.find((item) => String(item.id) === tradeId);
    if (trade) openTradeDetailWindow(tradeId);
    else setStatus("error", "معامله موردنظر پیدا نشد یا دیگر در دسترس نیست.");
  }
}
bootstrapApplication().catch((error) => setStatus("error", error.message));
if (currentPage === "profit-recognition" && window.location.hash === "#account-settings") focusAccountCash();
