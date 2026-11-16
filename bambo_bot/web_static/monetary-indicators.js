const monetaryState = {
  all: {payload: null, metric: "value", range: "5y", selected: "base_money", q: new URLSearchParams(location.search).get("m_q") || "", group: new URLSearchParams(location.search).get("m_group") || "all", composing: false, controller: null, request: 0},
  main: {payload: null, metric: "value", range: "5y", selected: "base_money", controller: null, request: 0},
  detailed: {payload: null, metric: "value", range: "5y", selected: "qard_al_hasana_savings", controller: null, request: 0},
};
const cbiSeriesState = {section: "monetary", seriesIndex: 0};

const MONETARY_METRICS = Object.freeze({
  value: {label: "مقدار شاخص", field: "value"},
  monthly: {label: "رشد ماهانه", field: "monthly_growth_percent"},
  yearly: {label: "رشد سالانه", field: "yearly_growth_percent"},
});

function monetaryEsc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[character]));
}

function monetaryNumeric(value) {
  if (value == null || value === "") return Number.NaN;
  return Number(value);
}

function monetaryNumber(value, maximumFractionDigits = 2) {
  const numeric = monetaryNumeric(value);
  if (!Number.isFinite(numeric)) return "—";
  return new Intl.NumberFormat("fa-IR", {maximumFractionDigits, minimumFractionDigits: 0}).format(numeric);
}

function monetaryGrowth(value) {
  const numeric = monetaryNumeric(value);
  if (!Number.isFinite(numeric)) return {text: "—", className: "unavailable", label: "داده کافی نیست"};
  const sign = numeric > 0 ? "+" : numeric < 0 ? "−" : "";
  return {
    text: `${sign}${monetaryNumber(Math.abs(numeric), 2)}٪`,
    className: numeric > 0 ? "up" : numeric < 0 ? "down" : "flat",
    label: numeric > 0 ? "افزایش" : numeric < 0 ? "کاهش" : "بدون تغییر",
  };
}

function monetaryReviewLabel(value) {
  const text = String(value || "");
  if (text.includes("تأیید")) return "تأییدشده";
  if (text.includes("مشکوک") || text.includes("بررسی")) return "نیازمند بررسی";
  return "ثبت رسمی";
}

function monetaryDate(value) {
  if (!value) return "—";
  const [year, month, day] = String(value).split("-");
  const digits = (part) => new Intl.NumberFormat("fa-IR", {useGrouping: false, maximumFractionDigits: 0}).format(Number(part));
  return `${digits(year)}/${digits(month)}/${digits(day)}`;
}

function monetaryPointLabel(point) {
  return point?.period || point?.period_date_jalali || monetaryDate(point?.jalali_date);
}

function monetaryMonthIndex(point, frequency = "monthly") {
  if ((frequency === "daily" || frequency === "weekly") && point?.period_date) {
    const days = Date.parse(point.period_date) / 86400000;
    if (Number.isFinite(days)) return days;
  }
  const raw = point.year_month || point.jalali_date || point.period_date_jalali || point.date;
  const match = String(raw || "").match(/(\d{4})\D+(\d{1,2})/);
  if (!match) return Number.NaN;
  const [year, month] = match.slice(1).map(Number);
  return year * 12 + month - 1;
}

function monetaryVisibleSeries(indicator, range) {
  const points = Array.isArray(indicator?.series) ? indicator.series : [];
  if (range === "all" || !points.length) return points;
  const frequency=indicator?.frequency||"monthly";
  const latest = monetaryMonthIndex(points.at(-1),frequency);
  const months = frequency === "daily" ? (range === "1y" ? 365 : 1825) : frequency === "weekly" ? (range === "1y" ? 364 : 1820) : (range === "1y" ? 12 : 60);
  return points.filter((point) => monetaryMonthIndex(point,frequency) >= latest - months + 1);
}

function monetaryTableAnalytics(indicator) {
  const points = (indicator.series || []).filter((point) => Number.isFinite(monetaryNumeric(point.value)));
  const trend = points.slice(-24);
  const latest = trend.at(-1);
  const frequency=indicator?.frequency||"monthly",interval=frequency==="daily"?90:frequency==="weekly"?91:3;
  const prior = points.findLast((point) => monetaryMonthIndex(point,frequency) <= monetaryMonthIndex(latest || {},frequency) - interval);
  const latestValue = monetaryNumeric(latest?.value), priorValue = monetaryNumeric(prior?.value);
  const change = Number.isFinite(latestValue) && Number.isFinite(priorValue) && priorValue !== 0 ? (latestValue / priorValue - 1) * 100 : Number.NaN;
  const percentile = trend.length ? Math.round(trend.filter((point) => monetaryNumeric(point.value) <= latestValue).length / trend.length * 100) : null;
  const signal = Number.isFinite(change) ? (change > 0 ? 1 : change < 0 ? -1 : 0) : 0;
  return {trend, change, percentile, signal};
}

function monetaryTableSparkline(indicator, analytics) {
  if (analytics.trend.length < 2) return `<span class="institutional-trend-empty">داده ناکافی</span>`;
  const values = analytics.trend.map((point) => monetaryNumeric(point.value));
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const coords = values.map((value, index) => `${3 + index * (114 / Math.max(1, values.length - 1))},${29 - (value - min) / span * 24}`);
  const tone = analytics.signal > 0 ? "up" : analytics.signal < 0 ? "down" : "flat";
  return `<svg class="institutional-sparkline ${tone}" viewBox="0 0 120 34" role="img" aria-label="روند دوساله ${monetaryEsc(indicator.title_fa)} از ${monetaryNumber(values[0])} تا ${monetaryNumber(values.at(-1))}"><title>روند دوساله ${monetaryEsc(indicator.title_fa)}</title><path d="M${coords.join(" L")}" vector-effect="non-scaling-stroke"/><circle cx="117" cy="${29 - (values.at(-1) - min) / span * 24}" r="2.6"/></svg>`;
}

function monetarySignal(analytics) {
  const label = analytics.signal > 0 ? "صعودی" : analytics.signal < 0 ? "نزولی" : "خنثی";
  const tone = analytics.signal > 0 ? "up" : analytics.signal < 0 ? "down" : "flat";
  const score = analytics.signal > 0 ? "+1" : String(analytics.signal);
  return `<span class="institutional-signal ${tone}"><b dir="ltr">${score}</b><small>${label}</small></span>`;
}

function monetaryModeControl(scope, state) {
  return `<div class="monetary-mode-control" role="group" aria-label="مبنای نمایش">
    ${Object.entries(MONETARY_METRICS).map(([key, metric]) => `<button type="button" data-monetary-metric="${key}" aria-pressed="${state.metric === key}">${metric.label}</button>`).join("")}
  </div>`;
}

function monetaryRangeControl(state) {
  return `<label class="monetary-range-control"><span>بازه نمودار</span><select data-monetary-range>
    <option value="1y"${state.range === "1y" ? " selected" : ""}>یک سال اخیر</option>
    <option value="5y"${state.range === "5y" ? " selected" : ""}>پنج سال اخیر</option>
    <option value="all"${state.range === "all" ? " selected" : ""}>کل تاریخچه</option>
  </select></label>`;
}

function monetaryIndicatorControl(indicators, state) {
  return `<label class="monetary-indicator-control"><span>شاخص نمودار</span><select data-monetary-indicator>${indicators.map((indicator) => `<option value="${monetaryEsc(indicator.technical_id)}"${state.selected === indicator.technical_id ? " selected" : ""}>${monetaryEsc(indicator.title_fa)}</option>`).join("")}</select></label>`;
}

function monetaryQuality(payload) {
  const quality = payload.quality || {};
  const missing = Array.isArray(quality.missing_months) ? quality.missing_months : [];
  const conflicts = Array.isArray(quality.metadata_conflicts) ? quality.metadata_conflicts : [];
  const nonNumeric = Array.isArray(quality.non_numeric_values) ? quality.non_numeric_values : [];
  return `<section class="monetary-quality" aria-labelledby="monetaryQualityTitle">
    <div><small>کنترل کیفیت فایل</small><h2 id="monetaryQualityTitle">${monetaryNumber(quality.row_count, 0)} دوره ماهانه</h2></div>
    <dl>
      <div><dt>ماه‌های مفقود</dt><dd>${monetaryNumber(missing.length, 0)}</dd></div>
      <div><dt>تاریخ تکراری</dt><dd>${monetaryNumber((quality.duplicate_jalali_months || []).length, 0)}</dd></div>
      <div><dt>مقدار غیرعددی</dt><dd>${monetaryNumber(nonNumeric.length, 0)}</dd></div>
      <div><dt>تعارض فراداده</dt><dd>${monetaryNumber(conflicts.length, 0)}</dd></div>
    </dl>
    <p class="monetary-warning"><strong>هشدار داده:</strong> مقادیر ۱۴۰۰/۱۲/۲۹ و ۱۴۰۱/۱۲/۲۹ مطابق review_status مشکوک‌اند و بدون اصلاح نمایش داده می‌شوند.</p>
    ${missing.length ? `<details><summary>مشاهده ماه‌های مفقود</summary><p>${missing.map((month) => monetaryEsc(month.replace("-", "/"))).join("، ")}</p></details>` : ""}
  </section>`;
}

function monetaryCard(indicator) {
  const point = indicator.current;
  const monthly = monetaryGrowth(point?.monthly_growth_percent);
  const yearly = monetaryGrowth(point?.yearly_growth_percent);
  return `<article class="monetary-card" data-technical-id="${monetaryEsc(indicator.technical_id)}">
    <header><div><small>${monetaryEsc(indicator.economic_group)}</small><h3>${monetaryEsc(indicator.title_fa)}</h3></div><code>${monetaryEsc(indicator.technical_id)}</code></header>
    <div class="monetary-card-value"><strong>${monetaryNumber(point?.value, indicator.unit === "بدون واحد" ? 3 : 2)}</strong><span>${monetaryEsc(indicator.unit)}</span></div>
    <dl>
      <div><dt>رشد ماهانه</dt><dd class="${monthly.className}"><b>${monthly.text}</b><small>${monthly.label}</small></dd></div>
      <div><dt>رشد سالانه</dt><dd class="${yearly.className}"><b>${yearly.text}</b><small>${yearly.label}</small></dd></div>
    </dl>
    <footer><span>دوره ${monetaryDate(point?.jalali_date)}</span><button type="button" data-monetary-select="${monetaryEsc(indicator.technical_id)}">نمایش روند</button></footer>
  </article>`;
}

function monetaryTable(indicators) {
  const groups = [...new Set(indicators.map((indicator) => indicator.economic_group))];
  return `<div class="monetary-table-wrap institutional-table-wrap" tabindex="0" role="region" aria-label="جدول شاخص‌های پولی؛ برای مشاهده ستون‌های بیشتر به‌صورت افقی پیمایش کنید">
    <table class="monetary-table institutional-table">
      <caption class="sr-only">شاخص‌های بانک مرکزی با آخرین مقدار، روند دوساله و دسترسی به تحلیل کامل</caption>
      <thead><tr><th scope="col">شاخص</th><th scope="col">آخرین مقدار</th><th scope="col">روند ۲ساله</th><th scope="col">تحلیل</th></tr></thead>
      ${groups.map((group) => `<tbody><tr class="institutional-group-row"><th colspan="4" scope="rowgroup">${monetaryEsc(group)} <span>${monetaryNumber(indicators.filter((indicator) => indicator.economic_group === group).length, 0)} شاخص</span></th></tr>${indicators.filter((indicator) => indicator.economic_group === group).map((indicator) => {
        const point = indicator.current;
        const analytics = monetaryTableAnalytics(indicator);
        const periodLabel=indicator.comparison_source==="cbi_mcp"?(point?.period||monetaryDate(point?.jalali_date)):monetaryDate(point?.jalali_date);
        return `<tr><th scope="row"><button type="button" data-monetary-preview="${monetaryEsc(indicator.technical_id)}" aria-pressed="false"><strong>${monetaryEsc(indicator.title_fa)}</strong></button></th><td><b>${monetaryNumber(point?.value, 2)}</b><small>${monetaryEsc(indicator.unit)} · ${monetaryEsc(periodLabel)}</small></td><td>${monetaryTableSparkline(indicator, analytics)}</td><td class="institutional-analysis-cell"><button type="button" data-monetary-analysis="${monetaryEsc(indicator.technical_id)}">تحلیل کامل</button></td></tr>`;
      }).join("")}</tbody>`).join("")}
    </table>
  </div>`;
}

function monetaryInstitutionalItem(indicator,compactCaption=false) {
  return {
    name_fa: indicator.title_fa,
    code: indicator.technical_id,
    unit: indicator.unit,
    frequency: indicator.frequency,
    group: indicator.economic_group,
    source: indicator.source || {name: "بانک مرکزی جمهوری اسلامی ایران"},
    compactCaption,
    series: (indicator.series || []).filter((point) => point.value !== null && point.value !== "").map((point) => ({
      period_date: point.period_date || point.date,
      period_date_jalali: point.period_date_jalali || point.jalali_date,
      period_label_fa: indicator.comparison_source === "cbi_mcp" ? (point.period || point.period_date_jalali || monetaryDate(point.jalali_date)) : monetaryDate(point.jalali_date),
      value: point.value,
      period: point.period,
      period_change_percent: point.period_change_percent ?? point.monthly_growth_percent,
      yearly_change_percent: point.yearly_change_percent ?? point.yearly_growth_percent,
      period_change_percentage_points: point.period_change_percentage_points,
      yearly_change_percentage_points: point.yearly_change_percentage_points,
      period_change_coefficient: point.period_change_coefficient,
      yearly_change_coefficient: point.yearly_change_coefficient,
    })),
  };
}

function monetarySideStats(indicator) {
  if (indicator.comparison_source === "cbi_mcp") {
    const latest=indicator.current||{};
    const delta=(value,unit)=>Number.isFinite(monetaryNumeric(value))?`${monetaryNumeric(value)>0?"+":monetaryNumeric(value)<0?"−":""}${monetaryNumber(Math.abs(value),2)} ${unit}`:"داده کافی نیست";
    const unit=indicator.unit==="درصد"?"واحد درصد":indicator.unit==="ضریب"?"ضریب":indicator.unit||"واحد شاخص";
    return `<dl class="institutional-detail-stats monetary-side-stats"><div><dt>آخرین مقدار</dt><dd dir="ltr">${monetaryNumber(latest.value,2)}</dd><small>${monetaryEsc(latest.period||monetaryDate(latest.jalali_date))} · ${monetaryEsc(indicator.unit||"—")}</small></div><div><dt>تغییر نسبت به دوره قبل</dt><dd dir="ltr">${delta(latest.period_change_value,unit)}</dd><small>فقط دوره پیوسته</small></div><div><dt>تغییر نسبت به دوره مشابه سال قبل</dt><dd dir="ltr">${delta(latest.yearly_change_value,unit)}</dd><small>مقایسه از مقدارهای ثبت‌شده</small></div></dl>`;
  }
  const latest=indicator.current,period=monetaryGrowth(latest?.monthly_growth_percent),yearly=monetaryGrowth(latest?.yearly_growth_percent);
  return `<dl class="institutional-detail-stats monetary-side-stats"><div><dt>آخرین مقدار</dt><dd dir="ltr">${latest?monetaryNumber(latest.value,2):"—"}</dd><small>${latest?monetaryDate(latest.jalali_date):"بدون داده"} · ${monetaryEsc(indicator.unit||"—")}</small></div><div><dt>تغییر نسبت به دوره قبل</dt><dd class="${period.className}" dir="ltr">${period.text}</dd><small>${period.label}</small></div><div><dt>تغییر نقطه‌به‌نقطه</dt><dd class="${yearly.className}" dir="ltr">${yearly.text}</dd><small>نسبت به دوره مشابه سال قبل</small></div></dl>`;
}

function openMonetaryDetail(indicator, trigger) {
  const dialog = document.getElementById("economicDetailDialog"), body = document.getElementById("economicDetailBody"), title = document.getElementById("economicDetailTitle");
  if (!dialog || !body || !title || !indicator) return;
  const item = monetaryInstitutionalItem(indicator);
  title.textContent = indicator.title_fa;
  const after = `<section class="economic-detail-definition institutional-detail-definition"><h3>مشخصات شاخص</h3><dl><div><dt>شناسه فنی</dt><dd dir="ltr">${monetaryEsc(indicator.technical_id)}</dd></div><div><dt>گروه اقتصادی</dt><dd>${monetaryEsc(indicator.economic_group)}</dd></div><div><dt>تناوب انتشار</dt><dd>${monetaryEsc(indicator.frequency)}</dd></div><div><dt>منبع</dt><dd>${monetaryEsc(indicator.comparison_source === "cbi_mcp" ? "بانک مرکزی · cbi-mcp" : "بانک مرکزی")}</dd></div><div><dt>وضعیت داده</dt><dd>${monetaryReviewLabel(indicator.review_status)}</dd></div></dl></section>`;
  body.innerHTML = economicInstitutionalDetailMarkup(item, {kicker: "نرخ‌ها · داده‌های پولی و بانکی", after});
  modalManager.open(dialog, {trigger, initialFocus: document.getElementById("economicDetailClose"), close: closeEconomicDetail});
  bindEconomicInstitutionalDetail(body, item);
}

function renderMonetarySideDetail(indicator,root=document,reveal=false) {
  const aside=root.querySelector("[data-monetary-side]");if(!aside||!indicator)return;
  const item=monetaryInstitutionalItem(indicator,true);aside.innerHTML=economicInstitutionalSideMarkup(item,{kicker:"داده‌های پولی و بانکی",stats:monetarySideStats(indicator),note:indicator.description_fa,compactSignal:true,latinRanges:true});
  aside.setAttribute("aria-busy","false");bindEconomicInstitutionalDetail(aside,item);
  root.querySelectorAll("[data-monetary-preview]").forEach((button)=>button.setAttribute("aria-pressed",String(button.dataset.monetaryPreview===indicator.technical_id)));
  if(reveal&&matchMedia("(max-width: 980px)").matches)aside.scrollIntoView({block:"start"});
}

function monetaryFiltered(indicators, state) {
  const query = state.q.trim().toLocaleLowerCase("fa-IR");
  return indicators.filter((indicator) => (state.group === "all" || indicator.economic_group === state.group) && (!query || [indicator.title_fa, indicator.technical_id, indicator.economic_group, indicator.metric_type].some((value) => String(value || "").toLocaleLowerCase("fa-IR").includes(query))));
}

function monetarySetCatalogUrl(state) {
  const params = new URLSearchParams(location.search);
  if (state.q) params.set("m_q", state.q); else params.delete("m_q");
  if (state.group !== "all") params.set("m_group", state.group); else params.delete("m_group");
  history.replaceState(history.state, "", `${location.pathname}${params.size ? `?${params}` : ""}${location.hash}`);
}

function monetaryCatalogForm(indicators, state) {
  const groups = [...new Set(indicators.map((indicator) => indicator.economic_group).filter(Boolean))].sort((a, b) => a.localeCompare(b, "fa"));
  if (state.group !== "all" && !groups.includes(state.group)) state.group = "all";
  return `<form id="monetaryCatalogFilters" class="monetary-catalog-filters" novalidate><label class="monetary-catalog-search"><span>جست‌وجو در همه داده‌های بانک مرکزی</span><span><input id="monetaryCatalogSearch" name="q" type="search" value="${monetaryEsc(state.q)}" placeholder="نام شاخص یا شناسه فنی" autocomplete="off"><button type="button" data-monetary-clear aria-label="پاک‌کردن جست‌وجوی بانک مرکزی"${state.q ? "" : " hidden"}>×</button></span></label><label><span>گروه اقتصادی</span><select name="group"><option value="all">همه گروه‌ها</option>${groups.map((group) => `<option value="${monetaryEsc(group)}"${state.group === group ? " selected" : ""}>${monetaryEsc(group)}</option>`).join("")}</select></label><button type="button" data-monetary-reset>پاک‌کردن فیلترها</button></form>`;
}

function monetaryCatalogResults(indicators, state) {
  const filtered = monetaryFiltered(indicators, state);
  if (!filtered.length) return `<section class="economic-empty monetary-catalog-empty"><h2>شاخصی مطابق این فیلترها پیدا نشد</h2><p>عبارت جست‌وجو یا گروه اقتصادی را تغییر دهید.</p><button type="button" data-monetary-reset>پاک‌کردن فیلترها</button></section>`;
  if(!filtered.some((indicator)=>indicator.technical_id===state.selected))state.selected=filtered[0].technical_id;
  const selected=filtered.find((indicator)=>indicator.technical_id===state.selected)||filtered[0];
  return `<div class="monetary-results-heading"><p><strong>${monetaryNumber(filtered.length, 0)}</strong> شاخص از ${monetaryNumber(indicators.length, 0)} داده بانک مرکزی</p></div><div class="institutional-master-detail"><div class="institutional-master">${monetaryTable(filtered)}</div><aside class="institutional-side" data-monetary-side aria-label="جزئیات شاخص انتخاب‌شده" aria-live="polite">${economicInstitutionalSideMarkup(monetaryInstitutionalItem(selected,true),{kicker:"داده‌های پولی و بانکی",stats:monetarySideStats(selected),note:selected.description_fa,compactSignal:true,latinRanges:true})}</aside></div>`;
}

function monetaryChart(indicator, state) {
  const metric = MONETARY_METRICS[state.metric];
  const source = monetaryVisibleSeries(indicator, state.range);
  const points = source.filter((point) => Number.isFinite(monetaryNumeric(point[metric.field])));
  if (points.length < 2) {
    return `<section class="monetary-chart-panel"><header><div><small>${metric.label}</small><h2>${monetaryEsc(indicator.title_fa)}</h2></div></header><div class="economic-detail-empty">برای این بازه داده کافی نیست.</div></section>`;
  }
  const width = 760, height = 280, plot = {x: 54, y: 18, width: 680, height: 214};
  const indexes = points.map((point)=>monetaryMonthIndex(point,indicator.frequency)), values = points.map((point) => monetaryNumeric(point[metric.field]));
  const minIndex = Math.min(...indexes), maxIndex = Math.max(...indexes), indexSpan = Math.max(1, maxIndex - minIndex);
  let minValue = Math.min(...values), maxValue = Math.max(...values);
  const padding = Math.max(Math.abs(maxValue - minValue) * .08, Math.abs(maxValue) * .02, 1e-9);
  minValue -= padding; maxValue += padding;
  const valueSpan = Math.max(1e-9, maxValue - minValue);
  const position = (point) => ({
    x: plot.x + (monetaryMonthIndex(point,indicator.frequency) - minIndex) / indexSpan * plot.width,
    y: plot.y + plot.height - (monetaryNumeric(point[metric.field]) - minValue) / valueSpan * plot.height,
  });
  const coords = points.map((point) => position(point));
  const grid = Array.from({length: 5}, (_, index) => {
    const ratio = index / 4, y = plot.y + ratio * plot.height, value = maxValue - ratio * valueSpan;
    return `<g class="economic-chart-grid"><line x1="${plot.x}" y1="${y}" x2="${plot.x + plot.width}" y2="${y}"/><text x="${plot.x - 8}" y="${y + 4}" text-anchor="end">${monetaryNumber(value, state.metric === "value" ? 1 : 2)}${state.metric === "value" ? "" : "٪"}</text></g>`;
  }).join("");
  const labels = [0, Math.floor((points.length - 1) / 2), points.length - 1].map((pointIndex, index) => `<text class="economic-chart-date" x="${coords[pointIndex].x}" y="258" text-anchor="${index === 0 ? "start" : index === 2 ? "end" : "middle"}">${monetaryEsc(monetaryPointLabel(points[pointIndex]))}</text>`).join("");
  const nodes = points.map((point, index) => {
    const {x, y} = coords[index], value = monetaryNumber(point[metric.field], 2), unit = state.metric === "value" ? indicator.unit : "درصد";
    if (point.is_suspicious) return `<rect class="monetary-anomaly" x="${x - 5}" y="${y - 5}" width="10" height="10" transform="rotate(45 ${x} ${y})" tabindex="0"><title>${monetaryEsc(monetaryPointLabel(point))} · ${value} ${monetaryEsc(unit)} · داده مشکوک</title></rect>`;
    return `<circle class="monetary-chart-point" cx="${x}" cy="${y}" r="3" tabindex="0"><title>${monetaryEsc(monetaryPointLabel(point))} · ${value} ${monetaryEsc(unit)}</title></circle>`;
  }).join("");
  const path = coords.map(({x, y}, index) => `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const latest = points.at(-1);
  const latestDisplay = state.metric === "value" ? `${monetaryNumber(latest[metric.field], 2)} ${indicator.unit}` : `${monetaryGrowth(latest[metric.field]).text}`;
  return `<section class="monetary-chart-panel" aria-labelledby="monetaryChartTitle">
    <header><div><small>${metric.label}</small><h2 id="monetaryChartTitle">${monetaryEsc(indicator.title_fa)}</h2></div><strong>${latestDisplay}</strong></header>
    <figure><svg viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="monetaryChartSvgTitle monetaryChartSvgDescription"><title id="monetaryChartSvgTitle">${metric.label} ${monetaryEsc(indicator.title_fa)}</title><desc id="monetaryChartSvgDescription">آخرین مقدار ${monetaryEsc(latestDisplay)} است. نقاط لوزی داده‌های مشکوک را نشان می‌دهند.</desc>${grid}<path class="monetary-chart-line" d="${path}" vector-effect="non-scaling-stroke"/>${nodes}${labels}</svg><figcaption><span>خط پیوسته: داده ثبت‌شده</span><span><i class="monetary-anomaly-key" aria-hidden="true"></i> لوزی: دوره مشکوک</span><span>واحد: ${monetaryEsc(state.metric === "value" ? indicator.unit : "درصد")}</span></figcaption></figure>
  </section>`;
}

function renderMonetary(scope) {
  const state = monetaryState[scope], payload = state.payload;
  const root = document.getElementById(scope === "main" ? "economicIndicatorsApp" : "monetaryDetailsApp");
  if (!root || !payload) return;
  const indicators = payload.indicators || [];
  if (!indicators.some((indicator) => indicator.technical_id === state.selected)) state.selected = indicators[0]?.technical_id || "";
  const selected = indicators.find((indicator) => indicator.technical_id === state.selected);
  root.setAttribute("aria-busy", "false");
  root.innerHTML = `<section class="monetary-toolbar" aria-label="کنترل نمایش شاخص‌های پولی">${monetaryModeControl(scope, state)}${monetaryIndicatorControl(indicators, state)}${monetaryRangeControl(state)}</section>
    ${scope === "all" ? "" : monetaryQuality(payload)}
    ${scope === "main" ? `<section class="monetary-card-grid" aria-label="شاخص‌های اصلی پولی">${indicators.map(monetaryCard).join("")}</section>` : scope === "all" ? `<section class="monetary-catalog" aria-labelledby="centralBankCatalogTitle">${monetaryCatalogForm(indicators, state)}<div class="monetary-catalog-results">${monetaryCatalogResults(indicators, state)}</div></section>` : monetaryTable(indicators)}
    ${selected && scope !== "all" ? monetaryChart(selected, state) : ""}`;
  bindMonetary(scope);
}

function bindMonetary(scope) {
  const state = monetaryState[scope];
  const root = document.getElementById(scope === "main" ? "economicIndicatorsApp" : "monetaryDetailsApp");
  root?.querySelectorAll("[data-monetary-metric]").forEach((button) => button.addEventListener("click", () => {state.metric = button.dataset.monetaryMetric; renderMonetary(scope); root.querySelector(`[data-monetary-metric="${state.metric}"]`)?.focus();}));
  root?.querySelector("[data-monetary-range]")?.addEventListener("change", (event) => {state.range = event.target.value; renderMonetary(scope); root.querySelector("[data-monetary-range]")?.focus();});
  root?.querySelector("[data-monetary-indicator]")?.addEventListener("change", (event) => {state.selected = event.target.value; renderMonetary(scope); root.querySelector("[data-monetary-indicator]")?.focus();});
  const bindSelection = (container = root) => {
    container?.querySelectorAll("[data-monetary-select]").forEach((button) => button.addEventListener("click", () => {const indicator=state.payload.indicators.find((candidate)=>candidate.technical_id===button.dataset.monetarySelect);state.selected=button.dataset.monetarySelect;openMonetaryDetail(indicator,button);}));
    container?.querySelectorAll("[data-monetary-preview]").forEach((button) => button.addEventListener("click",()=>{const indicator=state.payload.indicators.find((candidate)=>candidate.technical_id===button.dataset.monetaryPreview);state.selected=button.dataset.monetaryPreview;renderMonetarySideDetail(indicator,root,true);}));
    container?.querySelectorAll("[data-monetary-analysis]").forEach((button) => button.addEventListener("click",()=>{const indicator=state.payload.indicators.find((candidate)=>candidate.technical_id===button.dataset.monetaryAnalysis);openMonetaryDetail(indicator,button);}));
    const selected=state.payload.indicators.find((candidate)=>candidate.technical_id===state.selected);if(selected&&root.querySelector("[data-monetary-side]")){renderMonetarySideDetail(selected,root);}
  };
  bindSelection();
  if (scope === "all") {
    const form = root.querySelector("#monetaryCatalogFilters"), search = root.querySelector("#monetaryCatalogSearch");
    const updateResults = () => {monetarySetCatalogUrl(state);const results=root.querySelector(".monetary-catalog-results");results.innerHTML=monetaryCatalogResults(state.payload.indicators,state);bindSelection(results);results.querySelector("[data-monetary-reset]")?.addEventListener("click",reset);};
    const reset = () => {state.q="";state.group="all";search.value="";form.elements.group.value="all";form.querySelector("[data-monetary-clear]").hidden=true;updateResults();search.focus();};
    let timer;
    search.addEventListener("compositionstart",()=>{state.composing=true;});
    search.addEventListener("compositionend",()=>{state.composing=false;clearTimeout(timer);state.q=search.value;updateResults();});
    search.addEventListener("input",()=>{form.querySelector("[data-monetary-clear]").hidden=!search.value;if(state.composing)return;clearTimeout(timer);timer=setTimeout(()=>{state.q=search.value;updateResults();},300);});
    form.elements.group.addEventListener("change",()=>{state.group=form.elements.group.value;updateResults();});
    form.querySelector("[data-monetary-clear]").addEventListener("click",()=>{clearTimeout(timer);state.q="";search.value="";form.querySelector("[data-monetary-clear]").hidden=true;updateResults();search.focus();});
    form.querySelector("[data-monetary-reset]").addEventListener("click",reset);
  }
}

function cbiMcpLink(value, label) {
  if (!value || !/^https:\/\//i.test(String(value))) return "";
  return `<a href="${monetaryEsc(value)}" target="_blank" rel="noreferrer">${monetaryEsc(label)}</a>`;
}

function cbiMcpMetric(label, value, suffix = "") {
  return `<div><dt>${monetaryEsc(label)}</dt><dd>${value == null || value === "" ? "—" : monetaryEsc(value)}${suffix}</dd></div>`;
}

function cbiMcpHeadline(data) {
  const inflation = data.inflation?.latest || {};
  const policy = (data.policy_rates?.rows || [])[0] || {};
  const liquidity = data.liquidity?.monetary_aggregates || {};
  const auction = (data.bond_auctions?.auctions || [])[0] || {};
  const repo = data.open_market?.latest?.repo || {};
  return `<section class="cbi-mcp-headline" aria-label="آخرین نماگرهای کلیدی بانک مرکزی">
    <article><span>تورم ۱۲ماهه</span><strong>${inflation.rate_pct == null ? "—" : `${monetaryNumber(inflation.rate_pct, 1)}٪`}</strong><small>${monetaryEsc(inflation.month || data.inflation?.year || "آخرین دوره")}</small></article>
    <article><span>نرخ بازار بین‌بانکی</span><strong>${policy.interbank_pct == null ? "—" : `${monetaryNumber(policy.interbank_pct, 2)}٪`}</strong><small>${monetaryEsc(policy.date || "آخرین هفته")}</small></article>
    <article><span>رشد سالانه نقدینگی</span><strong>${liquidity.liquidity?.growth_pct == null ? "—" : `${monetaryNumber(liquidity.liquidity.growth_pct, 1)}٪`}</strong><small>${monetaryEsc(liquidity.period || "آخرین گزارش ماهانه")}</small></article>
    <article><span>فروش آخرین حراج اوراق</span><strong>${auction.total_sold_this_auction == null ? "—" : monetaryNumber(auction.total_sold_this_auction, 1)}</strong><small>هزار میلیارد ریال · ${monetaryEsc(auction.date || "—")}</small></article>
    <article><span>پذیرش ریپو</span><strong>${repo.orders_accepted == null ? "—" : monetaryNumber(repo.orders_accepted, 1)}</strong><small>هزار میلیارد ریال · نرخ ${repo.min_repo_rate_pct == null ? "—" : `${monetaryNumber(repo.min_repo_rate_pct, 2)}٪`}</small></article>
  </section>`;
}

function cbiMcpMarkets(data) {
  const policy = (data.policy_rates?.rows || [])[0] || {};
  const repo = data.open_market?.latest?.repo || {};
  return `<div class="cbi-mcp-grid">
    <section class="cbi-mcp-block"><header><div><small>بازار پول</small><h3>نرخ‌های سیاستی و بین‌بانکی</h3></div><span>${monetaryEsc(policy.date || "—")}</span></header><dl>${cbiMcpMetric("بین‌بانکی", policy.interbank_pct, "٪")}${cbiMcpMetric("حداقل ریپو", policy.repo_min_pct, "٪")}${cbiMcpMetric("اعتبارگیری قاعده‌مند", policy.standing_lending_pct, "٪")}${cbiMcpMetric("سپرده‌گذاری قاعده‌مند", policy.standing_deposit_pct, "٪")}</dl></section>
    <section class="cbi-mcp-block"><header><div><small>عملیات بازار باز</small><h3>آخرین حراج بازخرید</h3></div><span>حراج ${monetaryEsc(data.open_market?.latest?.auction_no || "—")}</span></header><dl>${cbiMcpMetric("بانک‌های مشارکت‌کننده", repo.banks_participating)}${cbiMcpMetric("سفارش پذیرفته‌شده", repo.orders_accepted, " هزار میلیارد ریال")}${cbiMcpMetric("سررسید", repo.repo_days, " روز")}${cbiMcpMetric("مانده ریپو", repo.outstanding, " هزار میلیارد ریال")}</dl></section>
  </div>`;
}

function cbiMcpStatistics(data) {
  const sections = (data.statistics_time_series?.sections || []).filter((item)=>item.key!=="balance_of_payments");
  if (!sections.length) return `<section class="cbi-mcp-statistics"><header><div><small>اعداد ماهانه بانک مرکزی</small><h3>سری‌های زمانی آماری</h3></div></header><div class="cbi-mcp-series-empty">هنوز سری زمانی همگام‌سازی نشده است.</div></section>`;
  if (!sections.some((item)=>item.key===cbiSeriesState.section)) cbiSeriesState.section=sections[0].key;
  const section=sections.find((item)=>item.key===cbiSeriesState.section)||sections[0], series=section.series||[];
  if(cbiSeriesState.seriesIndex>=series.length)cbiSeriesState.seriesIndex=0;
  const selected=series[cbiSeriesState.seriesIndex],points=selected?.points||[];
  let chart='<div class="cbi-mcp-series-empty">برای این انتخاب هنوز حداقل دو نقطه عددی موجود نیست.</div>';
  if(points.length>=2){
    const width=820,height=250,plot={x:70,y:22,w:720,h:176},values=points.map((point)=>Number(point.value)),min=Math.min(...values),max=Math.max(...values),span=max-min||1;
    const xy=points.map((point,index)=>({x:plot.x+index*plot.w/Math.max(1,points.length-1),y:plot.y+plot.h-(Number(point.value)-min)/span*plot.h}));
    const path=xy.map((point,index)=>`${index?'L':'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
    const guides=Array.from({length:4},(_,index)=>{const ratio=index/3,y=plot.y+ratio*plot.h,value=max-ratio*span;return `<g><line x1="${plot.x}" y1="${y}" x2="${plot.x+plot.w}" y2="${y}"/><text x="${plot.x-9}" y="${y+4}" text-anchor="end">${monetaryNumber(value,2)}</text></g>`;}).join('');
    const labels=[0,Math.floor((points.length-1)/2),points.length-1].map((index,position)=>`<text x="${xy[index].x}" y="232" text-anchor="${position===0?'start':position===2?'end':'middle'}">${monetaryEsc(points[index].period)}</text>`).join('');
    chart=`<figure class="cbi-mcp-series-chart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="روند ${monetaryEsc(selected.name)}">${guides}<path d="${path}"/>${xy.map((point,index)=>`<circle cx="${point.x}" cy="${point.y}" r="3"><title>${monetaryEsc(points[index].period)} · ${monetaryNumber(points[index].value,2)} ${monetaryEsc(selected.unit)}</title></circle>`).join('')}${labels}</svg><figcaption>واحد: ${monetaryEsc(selected.unit)} · ${monetaryNumber(points.length,0)} دوره دریافت‌شده از جدول عددی بانک مرکزی</figcaption></figure>`;
  }
  const latest=points.at(-1),previous=points.at(-2),change=latest&&previous&&Number(previous.value)!==0?(Number(latest.value)/Number(previous.value)-1)*100:null;
  return `<section class="cbi-mcp-statistics"><header><div><small>اعداد ماهانه بانک مرکزی</small><h3>سری‌های زمانی آماری</h3></div><span>داده خوانده‌شده از ردیف‌های Excel، نه فقط لینک گزارش</span></header>
    <div class="cbi-mcp-series-tabs" role="tablist" aria-label="حوزه آماری">${sections.map((item)=>`<button type="button" role="tab" data-cbi-series-section="${monetaryEsc(item.key)}" aria-selected="${item.key===section.key}">${monetaryEsc(item.label)} <small>${monetaryNumber(item.series?.length||0,0)} سری</small></button>`).join('')}</div>
    <div class="cbi-mcp-series-toolbar"><label><span>شاخص عددی</span><select data-cbi-series-select>${series.map((item,index)=>`<option value="${index}"${index===cbiSeriesState.seriesIndex?' selected':''}>${monetaryEsc(item.name)}</option>`).join('')}</select></label><dl>${cbiMcpMetric('آخرین مقدار',latest?monetaryNumber(latest.value,2):'—')}${cbiMcpMetric('آخرین دوره',latest?.period||'—')}${cbiMcpMetric('تغییر دوره‌ای',change==null?'—':`${change>0?'+':''}${monetaryNumber(change,2)}٪`)}</dl></div>
    <div class="cbi-mcp-series-layout">${chart}<div class="cbi-mcp-series-table-wrap"><table><caption>تاریخچه عددی ${monetaryEsc(selected?.name||'شاخص')}</caption><thead><tr><th>دوره</th><th>مقدار</th></tr></thead><tbody>${points.slice().reverse().map((point)=>`<tr><th>${monetaryEsc(point.period)}</th><td>${monetaryNumber(point.value,2)}</td></tr>`).join('')}</tbody></table></div></div>
  </section>`;
}

function bindCbiMcpStatistics(payload){
  const root=document.getElementById("centralBankMcpApp");
  root?.querySelectorAll("[data-cbi-series-section]").forEach((button)=>button.addEventListener("click",()=>{cbiSeriesState.section=button.dataset.cbiSeriesSection;cbiSeriesState.seriesIndex=0;renderCentralBankMcp(payload);}));
  root?.querySelector("[data-cbi-series-select]")?.addEventListener("change",(event)=>{cbiSeriesState.seriesIndex=Number(event.target.value)||0;renderCentralBankMcp(payload);});
}

function cbiMcpPublications(data) {
  const groups = [
    ["publications_economic_trends", "نماگرهای اقتصادی"],
    ["publications_monetary_reports", "آمار پولی و بانکی"],
    ["publications_annual_review", "مرور سالانه"],
    ["publications_interbank_reports", "بازار بین‌بانکی"],
  ];
  return `<section class="cbi-mcp-publications"><header><div><small>انتشارات رسمی</small><h3>تازه‌ترین گزارش‌ها</h3></div></header><div>${groups.map(([key,label])=>{const items=data[key]?.items||[];return `<article><h4>${label}</h4>${items.length?`<ul>${items.slice(0,4).map((item)=>`<li>${cbiMcpLink(item.url,item.title||item.published||"گزارش بانک مرکزی")}</li>`).join("")}</ul>`:"<p>گزارشی دریافت نشد.</p>"}</article>`;}).join("")}</div></section>`;
}

function renderCentralBankMcp(payload) {
  const root = document.getElementById("centralBankMcpApp");
  if (!root) return;
  root.setAttribute("aria-busy", "false");
  if (!payload.available) {
    root.innerHTML = `<section class="cbi-mcp-empty"><h3>هنوز تصویر MCP ثبت نشده است</h3><p>مدیر سامانه باید فرمان <code dir="ltr">python manage.py sync_cbi_mcp</code> را اجرا کند. فهرست تاریخی شاخص‌های پولی پایین صفحه همچنان در دسترس است.</p></section>`;
    return;
  }
  const data = payload.data || {}, errorCount = Object.keys(payload.errors || {}).length;
  root.innerHTML = `${payload.is_stale ? '<p class="cbi-mcp-stale" role="status">این تصویر بیش از ۳۶ ساعت قدمت دارد؛ تا همگام‌سازی بعدی با احتیاط استفاده کنید.</p>' : ""}${cbiMcpHeadline(data)}${cbiMcpMarkets(data)}${cbiMcpStatistics(data)}${cbiMcpPublications(data)}<footer class="cbi-mcp-credit"><span>داده رسمی: بانک مرکزی جمهوری اسلامی ایران · اتصال غیررسمی و فقط‌خواندنی</span><a href="${monetaryEsc(payload.source?.repository || "https://github.com/sepehr071/cbi-mcp")}" target="_blank" rel="noreferrer">cbi-mcp؛ ساخته سپهر رادمرد</a>${errorCount ? `<small>${monetaryNumber(errorCount,0)} بخش در این همگام‌سازی در دسترس نبود.</small>` : ""}</footer>`;
  bindCbiMcpStatistics(payload);
}

async function loadCentralBankMcp() {
  const root = document.getElementById("centralBankMcpApp");
  root?.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("/api/central-bank-snapshot", {cache:"no-store", credentials:"same-origin"});
    if (response.status === 401 || response.status === 403) return;
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "دریافت تصویر بانک مرکزی ناموفق بود");
    renderCentralBankMcp(payload);
    const synced = document.getElementById("centralBankMcpSyncedAt");
    if (synced) synced.textContent = payload.generated_at ? `همگام‌سازی ${new Intl.DateTimeFormat("fa-IR", {dateStyle:"short",timeStyle:"short",timeZone:"Asia/Tehran"}).format(new Date(payload.generated_at))}` : "در انتظار نخستین همگام‌سازی";
    return payload;
  } catch (error) {
    if (root) {
      root.setAttribute("aria-busy", "false");
      root.innerHTML = `<section class="economic-error" role="alert"><h3>تصویر تازه بانک مرکزی دریافت نشد</h3><p>${monetaryEsc(error.message || "خطای ناشناخته")}</p></section>`;
    }
  }
}

async function loadMonetaryIndicators(scope = "main", force = false) {
  const state = monetaryState[scope];
  const root = document.getElementById(scope === "main" ? "economicIndicatorsApp" : "monetaryDetailsApp");
  if (!root) return;
  state.controller?.abort();
  state.controller = new AbortController();
  const request = ++state.request;
  const refresh = document.getElementById(scope === "main" ? "monetaryRefreshButton" : "monetaryDetailsRefreshButton");
  refresh?.setAttribute("aria-busy", "true"); if (refresh) refresh.disabled = true;
  root.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/api/monetary-indicators?scope=${scope}${force ? "&refresh=1" : ""}`, {cache: "no-store", credentials: "same-origin", signal: state.controller.signal});
    if (response.status === 401 || response.status === 403) {location.assign(`/login?next=${encodeURIComponent(location.pathname + location.search)}`); return;}
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "دریافت داده‌های پولی ناموفق بود");
    if (request !== state.request) return;
    if (!Array.isArray(payload.indicators) || !payload.quality) throw new Error("ساختار پاسخ داده‌های پولی معتبر نیست");
    state.payload = payload;
    if (scope === "all") {
      const snapshot = await loadCentralBankMcp();
      const cbiSeries = (snapshot?.series_catalog || []).map((item) => ({...item, comparison_source:"cbi_mcp"}));
      state.payload.indicators = [...state.payload.indicators, ...cbiSeries];
    }
    const synced = document.getElementById(scope === "main" ? "economicSyncedAt" : "monetaryDetailsSyncedAt");
    if (synced) synced.textContent = new Intl.DateTimeFormat("fa-IR", {dateStyle: "short", timeStyle: "short", timeZone: "Asia/Tehran"}).format(new Date(payload.generated_at));
    if (document.getElementById("updatedAt")) document.getElementById("updatedAt").textContent = synced?.textContent || "—";
    renderMonetary(scope);
    if (typeof setStatus === "function") setStatus("success", `${payload.indicators.length.toLocaleString("fa-IR")} شاخص پولی بارگذاری شد`);
  } catch (error) {
    if (error.name === "AbortError" || request !== state.request) return;
    root.setAttribute("aria-busy", "false");
    root.innerHTML = `<section class="economic-error" role="alert"><h2>دریافت داده‌های پولی انجام نشد</h2><p>${monetaryEsc(error.message || "خطای ناشناخته")}</p><button type="button" data-monetary-retry>تلاش دوباره</button></section>`;
    root.querySelector("[data-monetary-retry]")?.addEventListener("click", () => loadMonetaryIndicators(scope, true));
    if (typeof setStatus === "function") setStatus("error", error.message || "دریافت داده‌های پولی ناموفق بود");
  } finally {
    if (request === state.request && refresh) {refresh.disabled = false; refresh.removeAttribute("aria-busy");}
  }
}

window.loadMonetaryIndicators = loadMonetaryIndicators;
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("monetaryRefreshButton")?.addEventListener("click", () => loadMonetaryIndicators("main", true));
  document.getElementById("monetaryDetailsRefreshButton")?.addEventListener("click", () => loadMonetaryIndicators("detailed", true));
});
