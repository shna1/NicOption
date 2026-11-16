/* Economic indicators: UI contract only. The production API supplies all observations. */
const ECONOMIC_CATALOG = Object.freeze([
  {code:"IR_M2",name_fa:"نقدینگی",name_en:"Money Supply (M2)",category:"macro",frequency:"monthly"},
  {code:"IR_M2_YOY_GROWTH",name_fa:"رشد سالانه نقدینگی",name_en:"Liquidity YoY Growth",category:"macro",frequency:"monthly"},
  {code:"IR_M2_MOM_GROWTH",name_fa:"رشد ماهانه نقدینگی",name_en:"Liquidity MoM Growth",category:"macro",frequency:"monthly"},
  {code:"IR_MONETARY_BASE",name_fa:"پایه پولی",name_en:"Monetary Base",category:"macro",frequency:"monthly"},
  {code:"IR_MONETARY_BASE_YOY_GROWTH",name_fa:"رشد سالانه پایه پولی",name_en:"Monetary Base YoY Growth",category:"macro",frequency:"monthly"},
  {code:"IR_MONETARY_BASE_MOM_GROWTH",name_fa:"رشد ماهانه پایه پولی",name_en:"Monetary Base MoM Growth",category:"macro",frequency:"monthly"},
  {code:"IR_MONEY_MULTIPLIER",name_fa:"ضریب فزاینده نقدینگی",name_en:"Money Multiplier",category:"macro",frequency:"monthly"},
  {code:"IR_QUASI_MONEY_TO_MONEY",name_fa:"شبه‌پول به پول",name_en:"Quasi-money to Money Ratio",category:"macro",frequency:"monthly"},
  {code:"IR-INF",name_fa:"تورم مصرف‌کننده",name_en:"Consumer Inflation",category:"macro",frequency:"monthly"},
  {code:"IR-INF_MOM",name_fa:"تورم مصرف‌کننده ماهانه",name_en:"Consumer Inflation MoM",category:"macro",frequency:"monthly"},
  {code:"IR_CPI",name_fa:"نرخ تورم مصرف‌کننده",name_en:"Consumer Price Inflation (CPI)",category:"macro",frequency:"monthly"},
  {code:"IR_USD_FREE_MARKET",name_fa:"قیمت ماهانه دلار بازار آزاد",name_en:"Monthly Free-Market USD/IRR",category:"fx",frequency:"monthly"},
  {code:"IR_USD_FREE_MARKET_MOM_CHANGE",name_fa:"رشد ماهانه قیمت دلار بازار آزاد",name_en:"Free-Market USD/IRR MoM Growth",category:"fx",frequency:"monthly"},
  {code:"IR_USD_FREE_MARKET_YOY_CHANGE",name_fa:"رشد سالانه قیمت دلار بازار آزاد",name_en:"Free-Market USD/IRR YoY Growth",category:"fx",frequency:"monthly"},
  {code:"IR_COIN_BAHAR_AZADI",name_fa:"قیمت ماهانه سکه بهار آزادی",name_en:"Monthly Bahar Azadi Coin Price",category:"commodity",frequency:"monthly"},
  {code:"IR_COIN_BAHAR_AZADI_MOM_CHANGE",name_fa:"رشد ماهانه قیمت سکه بهار آزادی",name_en:"Bahar Azadi Coin Price MoM Growth",category:"commodity",frequency:"monthly"},
  {code:"IR_COIN_BAHAR_AZADI_YOY_CHANGE",name_fa:"رشد سالانه قیمت سکه بهار آزادی",name_en:"Bahar Azadi Coin Price YoY Growth",category:"commodity",frequency:"monthly"},
  {code:"IR_GOLD_18K",name_fa:"قیمت ماهانه طلای ۱۸ عیار",name_en:"Monthly 18K Gold Price",category:"commodity",frequency:"monthly"},
  {code:"IR_GOLD_18K_MOM_CHANGE",name_fa:"رشد ماهانه قیمت طلای ۱۸ عیار",name_en:"18K Gold Price MoM Growth",category:"commodity",frequency:"monthly"},
  {code:"IR_GOLD_18K_YOY_CHANGE",name_fa:"رشد سالانه قیمت طلای ۱۸ عیار",name_en:"18K Gold Price YoY Growth",category:"commodity",frequency:"monthly"},
  {code:"IR_TETHER",name_fa:"قیمت ماهانه تتر",name_en:"Monthly Tether Price",category:"fx",frequency:"monthly"},
  {code:"IR_TETHER_MOM_CHANGE",name_fa:"رشد ماهانه قیمت تتر",name_en:"Tether Price MoM Growth",category:"fx",frequency:"monthly"},
  {code:"IR_TETHER_YOY_CHANGE",name_fa:"رشد سالانه قیمت تتر",name_en:"Tether Price YoY Growth",category:"fx",frequency:"monthly"},
  {code:"IR_TEDPIX",name_fa:"شاخص ماهانه کل بورس تهران",name_en:"Monthly Tehran Stock Exchange Total Index (TEDPIX)",category:"capital",frequency:"monthly"},
  {code:"IR_TEDPIX_MOM_CHANGE",name_fa:"رشد ماهانه شاخص کل بورس تهران",name_en:"Tehran Stock Exchange Total Index MoM Growth",category:"capital",frequency:"monthly"},
  {code:"IR_TEDPIX_YOY_CHANGE",name_fa:"رشد سالانه شاخص کل بورس تهران",name_en:"Tehran Stock Exchange Total Index YoY Growth",category:"capital",frequency:"monthly"},
]);
const ECONOMIC_FILTERS = Object.freeze({kind:["all","official","analytical"],category:["all","macro","fx","capital","commodity"],frequency:["all","daily","monthly","quarterly","annual"],freshness:["all","fresh","pending","stale"]});
const ECONOMIC_LABELS = Object.freeze({official:"داده رسمی",analytical:"شاخص تحلیلی nicoption",macro:"اقتصاد کلان",fx:"ارز و رمزارز",capital:"بازار سرمایه",commodity:"طلا و سکه",daily:"روزانه",monthly:"ماهانه",quarterly:"فصلی",annual:"سالانه",fresh:"به‌روز",pending:"در انتظار انتشار",stale:"داده قدیمی"});
const ECONOMIC_CATEGORY_ORDER = Object.freeze(["macro","fx","commodity","capital"]);
const ECONOMIC_HEADLINE_SPECS = Object.freeze([
  {code:"IR-INF_MOM",label:"تورم ماهانه",source:"مرکز آمار ایران"},
  {code:"IR_M2_MOM_GROWTH",label:"رشد ماهانه نقدینگی",source:"بانک مرکزی"},
  {code:"IR_USD_FREE_MARKET_MOM_CHANGE",label:"رشد ماهانه دلار",source:"بازار ارز"},
  {code:"IR_GOLD_18K_MOM_CHANGE",label:"رشد ماهانه طلا",source:"بازار طلا"},
  {code:"IR_TEDPIX_MOM_CHANGE",label:"رشد ماهانه بورس",source:"بورس تهران"},
]);
const economicState = {payload:null,statisticalPayload:null,controller:null,seriesControllers:new Map(),loadingSeries:new Set(),request:0,selected:new Set(),normalize:true,composing:false,deepLinkOpened:false};

function economicEsc(value) {
  return String(value ?? "—").replace(/[&<>'"]/g,(char)=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}
function economicNumber(value,digits=2) {
  if (value == null || value === "" || !Number.isFinite(Number(value))) return "—";
  return Number(value).toLocaleString("fa-IR",{maximumFractionDigits:digits,minimumFractionDigits:0});
}
function economicDate(value,withTime=false) {
  if (!value) return "—";
  const date=new Date(value); if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("fa-IR-u-ca-persian",{year:"numeric",month:"long",day:"numeric",...(withTime?{hour:"2-digit",minute:"2-digit"}:{}),timeZone:"Asia/Tehran"}).format(date);
}
function economicChartDate(value) {
  if (!value) return "—";
  const date=new Date(value); if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("fa-IR-u-ca-persian",{year:"2-digit",month:"short",timeZone:"Asia/Tehran"}).format(date);
}
function economicPointDate(point,compact=false) {
  if(point?.period_label_fa)return point.period_label_fa;
  return compact?economicChartDate(point?.period_date):economicDate(point?.period_date);
}
function economicUrl(value) {
  try { const url=new URL(value); return ["http:","https:"].includes(url.protocol)?url.href:null; } catch { return null; }
}
function economicArray(value) { return Array.isArray(value)?value:[]; }
function economicSourceLabel(item) {
  const source=`${item?.source?.organization||""} ${item?.source?.name||""}`.trim();
  if(source.includes("مرکزآمار")||source.includes("مرکز آمار"))return "مرکز آمار ایران";
  if(source.includes("بانک مرکزی"))return "بانک مرکزی";
  if(source.includes("TSETMC")||source.includes("Tehran Securities"))return "بورس تهران";
  if(source.includes("PriceDB")||source.includes("PriceToDay"))return "داده بازار";
  if(source.includes("nicoption"))return "محاسبه nicoption";
  return item?.source?.organization||item?.source?.name||"منبع ثبت نشده";
}
function economicValidatedIndicator(raw) {
  if (!raw || typeof raw!=="object" || typeof raw.code!=="string") return null;
  const catalog=ECONOMIC_CATALOG.find((item)=>item.code===raw.code) || {};
  const series=economicArray(raw.series).filter((point)=>point&&point.period_date&&Number.isFinite(Number(point.value))).sort((a,b)=>new Date(a.period_date)-new Date(b.period_date));
  return {...catalog,...raw,current:raw.current&&typeof raw.current==="object"?raw.current:{},freshness:raw.freshness&&typeof raw.freshness==="object"?raw.freshness:{status:"pending",label:"در انتظار داده"},source:raw.source&&typeof raw.source==="object"?raw.source:{},access:raw.access&&typeof raw.access==="object"?raw.access:{free_history_years:5,full_history_requires_subscription:true},series};
}
function economicStatisticalIndicator(item) {
  const series=economicArray(item?.analytics?.trend_2y).map((point)=>({period_date:point.date,value:point.value})).filter((point)=>point.period_date&&Number.isFinite(Number(point.value))),latest=series.at(-1),unit={index:"شاخص",percent:"درصد",irr:"ریال"}[item.unit]||item.unit||"—";
  return economicValidatedIndicator({code:`SCI:${item.series_key}`,name_fa:item.display_title_fa||item.title_fa||item.technical_id,name_en:"",kind:"official",category:"macro",frequency:item.frequency,unit,classification:item.classification,economic_group:item.economic_group,comparison_source:"statistical_center",comparison_source_label:"مرکز آمار ایران",comparison_series_key:item.series_key,is_primary:item.classification==="اصلی",current:{value:item.latest?.value??latest?.value??null,period_date:item.latest?.date||latest?.period_date||null},freshness:{status:"fresh",label:"داده رسمی"},source:{name:"مرکز آمار ایران",organization:"مرکز آمار ایران"},access:{free_history_years:2,full_history_requires_subscription:false},series});
}
function economicFilters() {
  const params=new URLSearchParams(location.search), result={q:params.get("q")||""};
  Object.entries(ECONOMIC_FILTERS).forEach(([key,allowed])=>{const value=params.get(key)||"all";result[key]=allowed.includes(value)?value:"all";});
  return result;
}
function economicSetUrl(filters) {
  const params=new URLSearchParams(location.search);
  ["q","kind","category","frequency","freshness"].forEach((key)=>{const value=filters[key];if(value&&value!=="all")params.set(key,value);else params.delete(key);});
  history.replaceState(history.state,"",`${location.pathname}${params.size?`?${params}`:""}${location.hash}`);
}
function economicOption(value,label,selected) { return `<option value="${value}"${selected===value?" selected":""}>${label}</option>`; }
function economicFilterMarkup() {
  const f=economicFilters();
  return `<form id="economicFilters" class="economic-filters" novalidate>
    <label class="economic-search"><span>جست‌وجوی شاخص</span><span class="economic-search-control"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg><input id="economicSearch" name="q" type="search" value="${economicEsc(f.q)}" placeholder="نام یا کد شاخص" autocomplete="off"><button type="button" data-economic-clear aria-label="پاک‌کردن جست‌وجوی شاخص"${f.q?"":" hidden"}>×</button></span></label>
    <label><span>نوع</span><select name="kind">${economicOption("all","همه",f.kind)}${economicOption("official","رسمی",f.kind)}${economicOption("analytical","تحلیلی",f.kind)}</select></label>
    <label><span>حوزه</span><select name="category">${economicOption("all","همه حوزه‌ها",f.category)}${economicOption("macro","اقتصاد کلان",f.category)}${economicOption("fx","ارز و رمزارز",f.category)}${economicOption("capital","بازار سرمایه",f.category)}${economicOption("commodity","طلا و سکه",f.category)}</select></label>
    <label><span>تناوب</span><select name="frequency">${economicOption("all","همه تناوب‌ها",f.frequency)}${economicOption("daily","روزانه",f.frequency)}${economicOption("monthly","ماهانه",f.frequency)}${economicOption("quarterly","فصلی",f.frequency)}${economicOption("annual","سالانه",f.frequency)}</select></label>
    <label><span>تازگی</span><select name="freshness">${economicOption("all","همه وضعیت‌ها",f.freshness)}${economicOption("fresh","به‌روز",f.freshness)}${economicOption("pending","در انتظار انتشار",f.freshness)}${economicOption("stale","قدیمی",f.freshness)}</select></label>
    <button class="economic-reset" type="button" data-economic-reset>پاک‌کردن فیلترها</button>
  </form>`;
}
function economicDatedSeries(item) {
  return economicArray(item?.series).map((point)=>({...point,time:new Date(point.period_date).getTime()})).filter((point)=>Number.isFinite(point.time)&&Number.isFinite(Number(point.value))).sort((a,b)=>a.time-b.time);
}
function economicShiftUtcMonths(time,months) {
  const date=new Date(time); date.setUTCMonth(date.getUTCMonth()+months); return date.getTime();
}
function economicPeriodChange(item,months) {
  const points=economicDatedSeries(item); if(points.length<2)return null;
  const latest=points.at(-1),target=economicShiftUtcMonths(latest.time,-months),tolerance=(months===1?20:62)*24*60*60*1000;
  const prior=points.slice(0,-1).reduce((best,point)=>Math.abs(point.time-target)<Math.abs((best?.time??-Infinity)-target)?point:best,null);
  if(!prior||Math.abs(prior.time-target)>tolerance)return null;
  const delta=Number(latest.value)-Number(prior.value),isRate=Boolean(item.methodology?.primary_rate)||["درصد","%"].includes(item.unit);
  if(!isRate&&Number(prior.value)===0)return null;
  return {value:isRate?delta:delta/Number(prior.value)*100,kind:isRate?"point":"percent",prior_date:prior.period_date,latest_date:latest.period_date};
}
function economicTrendPoints(item,months=12) {
  const points=economicDatedSeries(item); if(!points.length)return [];
  const cutoff=economicShiftUtcMonths(points.at(-1).time,-months);
  return points.filter((point)=>point.time>=cutoff);
}
function economicSignal(item) {
  const change=economicPeriodChange(item,1); if(!change)return {score:null,label:"داده ناکافی",tone:"unavailable",change:null};
  if(change.value>0)return {score:1,label:"صعودی",tone:"up",change};
  if(change.value<0)return {score:-1,label:"نزولی",tone:"down",change};
  return {score:0,label:"خنثی",tone:"flat",change};
}
function economicKpiCard(spec,items) {
  const item=items.find((candidate)=>candidate.code===spec.code),value=Number(item?.current?.value),available=Number.isFinite(value),tone=!available?"unavailable":value>0?"up":value<0?"down":"flat",signed=available?`${value>0?"+":""}${economicNumber(value)}`:"—",period=item?.current?.period_date;
  return `<article class="economic-kpi ${tone}" data-economic-headline="${economicEsc(spec.code)}"><span>${economicEsc(spec.label)}</span><strong dir="ltr">${signed} <small>${available?"٪":""}</small></strong><p>${available?economicEsc(spec.source):"در انتظار داده"}</p><footer>${period?`آخرین دوره: ${economicDate(period)}`:"هنوز مقداری ثبت نشده است"}</footer></article>`;
}
function economicKpis(indicators) {
  return `<section id="economic-overview" class="economic-regime" aria-labelledby="economicRegimeTitle"><header><div><small>آخرین مقادیر منتشرشده</small><h2 id="economicRegimeTitle">تورم، نقدینگی و بازارها</h2></div></header><div class="economic-kpi-grid economic-kpi-grid--headlines">${ECONOMIC_HEADLINE_SPECS.map((spec)=>economicKpiCard(spec,indicators)).join("")}</div></section>`;
}
function economicTableSparkline(item) {
  const points=economicTrendPoints(item,12); if(points.length<2)return `<span class="economic-trend-empty">داده ناکافی</span>`;
  const values=points.map((point)=>Number(point.value)),min=Math.min(...values),max=Math.max(...values),span=max-min||1;
  const coords=points.map((point,index)=>`${3+index*(114/Math.max(1,points.length-1))},${29-(Number(point.value)-min)/span*24}`),tone=economicSignal(item).tone;
  return `<svg class="economic-table-sparkline ${tone}" viewBox="0 0 120 34" role="img" aria-label="روند یک‌ساله ${economicEsc(item.name_fa)} از ${economicNumber(values[0])} تا ${economicNumber(values.at(-1))}"><title>روند یک‌ساله ${economicEsc(item.name_fa)}</title><path d="M${coords.join(" L")}" vector-effect="non-scaling-stroke"/><circle cx="117" cy="${29-(values.at(-1)-min)/span*24}" r="2.6"/></svg>`;
}
function economicTableChange(item,months) {
  const change=economicPeriodChange(item,months); if(!change)return `<span class="economic-value-missing">—<small>داده کافی نیست</small></span>`;
  const sign=change.value>0?"+":"",tone=change.value>0?"up":change.value<0?"down":"flat",unit=change.kind==="point"?"واحد درصد":"٪";
  return `<span class="economic-table-change ${tone}" dir="ltr">${sign}${economicNumber(change.value)} ${unit}</span>`;
}
function economicTableRow(item) {
  if(item.error)return `<tr class="economic-table-error"><th scope="row"><strong>${economicEsc(item.name_fa)}</strong></th><td colspan="4"><span>دریافت این شاخص کامل نشد.</span> <button type="button" data-economic-retry>تلاش دوباره</button></td></tr>`;
  const current=item.current||{},rate=item.methodology?.primary_rate,unit=rate?`${item.unit||"—"} · ${rate.toUpperCase()}`:item.unit||"—";
  const detail=item.comparison_source==="statistical_center"?`<button class="economic-row-detail" type="button" data-economic-statistical-detail="${economicEsc(item.comparison_series_key)}">جزئیات <span class="sr-only">${economicEsc(item.name_fa)}</span></button>`:`<button class="economic-row-detail" type="button" data-economic-detail="${economicEsc(item.code)}">جزئیات <span class="sr-only">${economicEsc(item.name_fa)}</span></button>`;
  return `<tr>
    <th class="economic-indicator-name-cell" scope="row"><strong>${economicEsc(item.name_fa)}</strong>${detail}</th>
    <td><b class="economic-latest-value" dir="ltr">${economicNumber(current.value)}</b><small>${economicEsc(unit)} · ${economicDate(current.period_date)}</small></td>
    <td>${economicTableChange(item,1)}</td>
    <td>${economicTableChange(item,12)}</td>
    <td>${economicTableSparkline(item)}</td>
  </tr>`;
}
function economicIndicatorTable(indicators) {
  const groups=ECONOMIC_CATEGORY_ORDER.map((category)=>({category,items:indicators.filter((item)=>item.category===category)})).filter((group)=>group.items.length);
  return `<section id="economic-indicators-list" class="economic-indicator-panel" aria-labelledby="economicTableTitle"><header class="economic-results-heading"><div><small>فهرست شاخص‌ها</small><h2 id="economicTableTitle">داده‌های رسمی و تحلیلی</h2></div><span>${economicNumber(indicators.length,0)} نتیجه</span></header><div class="economic-indicator-note"><span>تغییر ماهانه و سالانه برای نرخ‌ها با واحد درصد و برای سطوح قیمت با درصد محاسبه شده است.</span><span>نمودار هر ردیف، مشاهدات یک سال اخیر را نشان می‌دهد.</span></div><div class="economic-table-wrap economic-indicator-table-wrap"><table class="economic-indicator-table"><caption class="sr-only">جدول کامل شاخص‌های اقتصادی</caption><thead><tr><th scope="col">شاخص</th><th scope="col">آخرین مقدار</th><th scope="col">تغییر ماهانه</th><th scope="col">تغییر سالانه</th><th scope="col">روند یک‌ساله</th></tr></thead>${groups.map((group)=>`<tbody><tr class="economic-group-row"><th colspan="5" scope="rowgroup">${economicEsc(ECONOMIC_LABELS[group.category]||group.category)} <span>${economicNumber(group.items.length,0)} شاخص</span></th></tr>${group.items.map(economicTableRow).join("")}</tbody>`).join("")}</table></div></section>`;
}
function economicFiltered(indicators) {
  const f=economicFilters(),q=f.q.trim().toLocaleLowerCase("fa-IR");
  return indicators.filter((item)=>(!q||[item.name_fa,item.name_en,item.code,item.source?.name,item.source?.organization,economicSourceLabel(item)].some((v)=>String(v||"").toLocaleLowerCase("fa-IR").includes(q)))&&(f.kind==="all"||item.kind===f.kind)&&(f.category==="all"||item.category===f.category)&&(f.frequency==="all"||item.frequency===f.frequency)&&(f.freshness==="all"||item.freshness?.status===f.freshness));
}
function economicEmpty(filtered,total) {
  if(total&&filtered===0)return `<section class="economic-empty"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg><h2>شاخصی با این فیلترها پیدا نشد</h2><p>فیلترها یا عبارت جست‌وجو را پاک کنید.</p><button type="button" data-economic-reset>پاک‌کردن فیلترها</button></section>`;
  return `<section class="economic-empty"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19V9m5 10V5m5 14v-7m5 7V3"/></svg><h2>هنوز داده رسمی متصل نشده است</h2><p>ساختار صفحه و API آماده است، اما تا اتصال منبع معتبر هیچ مقدار اقتصادی نمایش داده نمی‌شود.</p><span>با «تازه‌سازی» می‌توانید اتصال منبع را دوباره بررسی کنید.</span></section>`;
}
function economicEnsureComparisonSelection(indicators) {
  const available=new Set(indicators.map((item)=>item.code)),valid=[...economicState.selected].filter((code)=>available.has(code)).slice(0,3);
  if(!valid.length){
    const preferred=["IR_M2","IR_USD_FREE_MARKET","IR_TEDPIX"],withHistory=indicators.filter((item)=>item.series.length>=2);
    [...preferred.map((code)=>withHistory.find((item)=>item.code===code)),...withHistory].filter(Boolean).forEach((item)=>{if(valid.length<3&&!valid.includes(item.code))valid.push(item.code);});
  }
  economicState.selected=new Set(valid);
  return valid;
}
function economicComparisonSource(item) {
  return item.comparison_source_label||economicSourceLabel(item);
}
function economicComparisonOption(item,current,used) {
  const source=economicComparisonSource(item),search=[item.name_fa,item.name_en,item.code,source,item.economic_group,item.classification].filter(Boolean).join(" ");
  return `<option value="${economicEsc(item.code)}" data-economic-option-search="${economicEsc(search)}"${current===item.code?" selected":""}${used.has(item.code)?" disabled":""}>${economicEsc(item.name_fa)} — ${economicEsc(source)}</option>`;
}
function economicComparisonSelect(indicators,selectedCodes,index,label) {
  const current=selectedCodes[index]||"",used=new Set(selectedCodes.filter((_,slot)=>slot!==index));
  const empty=index?`<option value=""${current?"":" selected"}>بدون شاخص</option>`:"";
  const primary=indicators.filter((item)=>item.is_primary),others=indicators.filter((item)=>!item.is_primary),options=`<optgroup label="شاخص‌های اصلی">${primary.map((item)=>economicComparisonOption(item,current,used)).join("")}</optgroup><optgroup label="سایر شاخص‌ها">${others.map((item)=>economicComparisonOption(item,current,used)).join("")}</optgroup>`;
  return `<div class="economic-compare-control"><label for="economicCompareSearch${index}">${label}</label><div class="economic-compare-search"><input id="economicCompareSearch${index}" type="search" inputmode="search" autocomplete="off" placeholder="ابتدا نام، کد یا منبع را جست‌وجو کنید" aria-label="جست‌وجو برای ${label}" data-economic-compare-search="${index}"><button type="button" aria-label="پاک‌کردن جست‌وجوی ${label}" data-economic-compare-clear="${index}" hidden>×</button></div><select data-economic-compare-slot="${index}" aria-label="${label}">${empty}${options}</select><small data-economic-compare-empty="${index}" role="status" hidden>شاخصی مطابق جست‌وجو پیدا نشد.</small></div>`;
}
function economicComparison(indicators) {
  const selectedCodes=economicEnsureComparisonSelection(indicators),selected=selectedCodes.map((code)=>indicators.find((item)=>item.code===code)).filter(Boolean),chartable=selected.filter((item)=>item.series.length>=2),units=new Set(chartable.map((item)=>item.unit));
  const loading=selected.some((item)=>economicState.loadingSeries.has(item.code)),note=loading?"در حال دریافت تاریخچه شاخص انتخاب‌شده…":selected.some((item)=>item.series.length<2)?"شاخص فاقد سابقه کافی از نمودار کنار گذاشته شده است.":units.size>1&&!economicState.normalize?"مقیاس شاخص‌ها متفاوت است؛ برای مقایسه دقیق‌تر مبنای ۱۰۰ را فعال کنید.":"",summary=economicState.payload?.summary||{};
  const statisticalTotal=Number(summary.statistical_center||0)+Number(summary.amar_mcp||0);
  return `<section id="economic-comparison" class="economic-compare" aria-labelledby="economicCompareTitle"><header><div><small>مقایسه تعاملی</small><h2 id="economicCompareTitle">مقایسه شاخص‌ها</h2><p class="economic-comparison-catalog-summary"><span><b>${economicNumber(summary.total??indicators.length,0)}</b> شاخص</span><span>مرکز آمار ${economicNumber(statisticalTotal,0)}${summary.amar_mcp?` · ${economicNumber(summary.amar_mcp,0)} کلان`:""}</span><span>بانک مرکزی ${economicNumber(summary.central_bank??0,0)}</span></p></div><label class="economic-normalize"><input id="economicNormalize" type="checkbox"${economicState.normalize?" checked":""}> نرمال‌شده بر مبنای ۱۰۰</label></header><div class="economic-compare-picker">${economicComparisonSelect(indicators,selectedCodes,0,"شاخص اصلی")}${economicComparisonSelect(indicators,selectedCodes,1,"شاخص دوم")}${economicComparisonSelect(indicators,selectedCodes,2,"شاخص سوم")}</div>${note?`<p class="economic-compare-note" role="status">${note}</p>`:""}${economicComparisonChart(chartable)}</section>`;
}
function economicComparisonSeries(items) {
  return items.map((item)=>{const points=item.series,base=Number(points[0]?.value);return {...item,points:points.map((point)=>({...point,time:new Date(point.period_date).getTime(),display:economicState.normalize&&base?Number(point.value)/base*100:Number(point.value)})).filter((point)=>Number.isFinite(point.time)&&Number.isFinite(point.display))};}).filter((item)=>item.points.length>=2);
}
function economicComparisonDomain(items) {
  const original=economicComparisonSeries(items);
  if(!original.length)return {series:[],timeline:[],minTime:0,maxTime:0,timeSpan:1};
  const anchor=original.reduce((shortest,item)=>item.points.length<shortest.points.length?item:shortest,original[0]);
  const minTime=Math.min(...anchor.points.map((point)=>point.time)),maxTime=Math.max(...anchor.points.map((point)=>point.time)),timeSpan=maxTime-minTime||1;
  const series=original.map((item)=>({...item,points:item.points.filter((point)=>point.time>=minTime&&point.time<=maxTime)})).filter((item)=>item.points.length>=2);
  return {series,timeline:anchor.points,minTime,maxTime,timeSpan};
}
function economicComparisonScale(series) {
  const values=series.flatMap((item)=>item.points.map((point)=>point.display)),min=Math.min(...values),rawMax=Math.max(...values);
  const headroom=Math.abs(rawMax)*.05||Math.abs(rawMax-min)*.05||1,max=rawMax+headroom;
  return {min,max,span:max-min||1};
}
function economicComparisonTimeScale(minTime,maxTime) {
  const dataSpan=maxTime-minTime||1,padding=dataSpan*.05,axisMinTime=minTime-padding,axisMaxTime=maxTime+padding;
  return {axisMinTime,axisMaxTime,axisTimeSpan:axisMaxTime-axisMinTime};
}
function economicComparisonDetailUrl(item) {
  if(item.comparison_source==="central_bank")return `/central-bank?m_q=${encodeURIComponent(item.code.replace(/^CBI:/,""))}#central-bank-data`;
  if(item.comparison_source==="amar_mcp")return "/statistical-center#statistical-center-data";
  if(item.comparison_source==="statistical_center")return `/statistical-center?s_q=${encodeURIComponent(item.comparison_series_key||item.code.replace(/^SCI:/,""))}&s_classification=all&s_lifecycle=all#statistical-center-data`;
  return `/economic-indicators?indicator=${encodeURIComponent(item.code)}#economic-indicators-list`;
}
function economicComparisonChart(items) {
  const plot={x:44,y:12,width:402,height:184},{series,timeline,minTime,maxTime,timeSpan}=economicComparisonDomain(items);
  if(!series.length)return `<figure class="economic-comparison-chart economic-comparison-chart-empty"><svg viewBox="0 0 490 226" role="img" aria-label="نمودار مقایسه شاخص‌ها"><rect class="economic-chart-plot" x="44" y="12" width="402" height="184" fill="transparent"/><text x="245" y="108" text-anchor="middle">برای شاخص‌های انتخاب‌شده داده کافی موجود نیست.</text></svg></figure>`;
  const {min,max,span}=economicComparisonScale(series),{axisMinTime,axisTimeSpan}=economicComparisonTimeScale(minTime,maxTime);
  const position=(point)=>({x:plot.x+(point.time-axisMinTime)/axisTimeSpan*plot.width,y:plot.y+plot.height-(point.display-min)/span*plot.height});
  const grid=Array.from({length:5},(_,index)=>{const ratio=index/4,y=plot.y+ratio*plot.height,value=max-ratio*span;return `<g class="economic-chart-grid"><line x1="${plot.x}" y1="${y}" x2="${plot.x+plot.width}" y2="${y}"/><text x="${plot.x-8}" y="${y+4}" text-anchor="end" direction="ltr">${economicNumber(value)}</text></g>`;}).join("");
  const paths=series.map((item,index)=>`<path class="economic-comparison-line series-${index}" d="M${item.points.map((point)=>{const {x,y}=position(point);return `${x.toFixed(2)},${y.toFixed(2)}`;}).join(" L")}" vector-effect="non-scaling-stroke"/>`).join("");
  const nodes=timeline.map((point,index)=>{const {x,y}=position(point);return `<circle data-economic-comparison-point="${index}" data-time="${point.time}" cx="${x}" cy="${y}" r="4" tabindex="0" aria-label="${economicEsc(economicDate(point.period_date))}"></circle>`;}).join("");
  const labelTimes=[minTime,minTime+timeSpan/2,maxTime],labels=labelTimes.map((time,index)=>`<text class="economic-chart-date" x="${plot.x+(time-axisMinTime)/axisTimeSpan*plot.width}" y="217" text-anchor="${index===0?"start":index===2?"end":"middle"}">${economicEsc(economicChartDate(new Date(time).toISOString()))}</text>`).join("");
  const tooltipHeight=38+series.length*19,tooltipRows=series.map((item,index)=>{const y=39+index*19;return `<line class="economic-comparison-tooltip-swatch series-${index}" x1="178" y1="${y-3}" x2="198" y2="${y-3}" vector-effect="non-scaling-stroke"/><text data-economic-comparison-tooltip-row="${index}" x="168" y="${y}" text-anchor="start"></text>`;}).join(""),activePoints=series.map((_,index)=>`<circle class="economic-comparison-active series-${index} hidden" data-economic-comparison-active="${index}" r="5"/>`).join("");
  const legend=series.map((item,index)=>`<a href="${economicEsc(economicComparisonDetailUrl(item))}" aria-label="مشاهده جزئیات ${economicEsc(item.name_fa)}"><i class="series-${index}" aria-hidden="true"></i><b>${economicEsc(item.name_fa)}</b><small>${economicNumber(item.points.at(-1).display)}${economicState.normalize?" · مبنای ۱۰۰":` · ${economicEsc(item.unit)}`}</small></a>`).join("");
  const summary=series.map((item)=>`${item.name_fa}: ${economicNumber(item.points.at(-1).display)}`).join("، ");
  return `<figure class="economic-comparison-chart"><svg viewBox="0 0 490 226" role="img" aria-labelledby="economicComparisonChartTitle economicComparisonChartDescription"><title id="economicComparisonChartTitle">مقایسه روند شاخص‌های انتخاب‌شده</title><desc id="economicComparisonChartDescription">${economicEsc(summary)}. برای مشاهده مقدار هر دوره، نشانگر را روی نمودار حرکت دهید یا نقاط را با کلید Tab انتخاب کنید.</desc><rect class="economic-chart-plot" x="44" y="12" width="402" height="184" fill="transparent"/>${grid}${paths}${nodes}${labels}<line class="economic-chart-cursor hidden" x1="44" y1="12" x2="44" y2="196"/>${activePoints}<g class="economic-chart-tooltip economic-comparison-tooltip hidden" aria-hidden="true"><rect width="208" height="${tooltipHeight}" rx="3"/><text class="economic-chart-tooltip-date" x="198" y="19" text-anchor="start"></text>${tooltipRows}</g><rect class="economic-chart-hitbox" x="44" y="12" width="402" height="184" fill="transparent" data-economic-comparison-cursor aria-hidden="true"/></svg><figcaption class="economic-comparison-legend">${legend}<span class="economic-comparison-live sr-only" aria-live="polite">${economicEsc(summary)}</span></figcaption></figure>`;
}
function renderEconomicIndicators() {
  const comparisonPage=document.body.dataset.page==="economic-comparison",root=document.getElementById(comparisonPage?"economicComparisonApp":"economicIndicatorsApp"); if(!root||!economicState.payload)return;
  const official=economicArray(economicState.payload.indicators).map(economicValidatedIndicator).filter(Boolean),statistical=comparisonPage?[]:economicArray(economicState.statisticalPayload?.indicators).map(economicStatisticalIndicator).filter(Boolean),indicators=[...official,...statistical],filtered=economicFiltered(indicators);
  root.setAttribute("aria-busy","false");
  root.innerHTML=comparisonPage?economicComparison(indicators):`${economicKpis(indicators)}${economicFilterMarkup()}${filtered.length?economicIndicatorTable(filtered):economicEmpty(filtered.length,indicators.length)}`;
  bindEconomicInteractions();
  if(comparisonPage){const selectedInChartOrder=[...economicState.selected].map((code)=>indicators.find((item)=>item.code===code)).filter((item)=>item&&item.series.length>=2);bindEconomicComparisonChart(root.querySelector(".economic-comparison-chart"),selectedInChartOrder);}
  if(!comparisonPage&&!economicState.deepLinkOpened){const code=new URLSearchParams(location.search).get("indicator"),item=indicators.find((candidate)=>candidate.code===code);if(item){economicState.deepLinkOpened=true;openEconomicDetail(code,root.querySelector(`[data-economic-detail="${CSS.escape(code)}"]`));}}
}
async function economicLoadComparisonSeries(code) {
  const item=economicArray(economicState.payload?.indicators).find((candidate)=>candidate.code===code);
  if(!item||item.comparison_source!=="statistical_center"||item.series.length||economicState.loadingSeries.has(code))return;
  const controller=new AbortController();economicState.seriesControllers.set(code,controller);economicState.loadingSeries.add(code);renderEconomicIndicators();
  try {
    const response=await fetch(`/api/statistical-center-series?series_key=${encodeURIComponent(item.comparison_series_key)}`,{cache:"no-store",credentials:"same-origin",signal:controller.signal});
    if(response.status===401||response.status===403){location.assign(`/login?next=${encodeURIComponent(location.pathname+location.search)}`);return;}
    const payload=await response.json();if(!response.ok)throw new Error(payload.error||"دریافت تاریخچه مرکز آمار ناموفق بود");
    item.series=economicArray(payload.indicator?.series);item.current=item.series.at(-1)||item.current;
  } catch(error) {
    if(error.name!=="AbortError"&&typeof setStatus==="function")setStatus("error",error.message||"دریافت تاریخچه شاخص ناموفق بود");
  } finally {
    economicState.seriesControllers.delete(code);economicState.loadingSeries.delete(code);renderEconomicIndicators();
  }
}
function bindEconomicInteractions() {
  const form=document.getElementById("economicFilters"),search=document.getElementById("economicSearch");
  if(form&&search){let timer;const commit=()=>{const data=Object.fromEntries(new FormData(form));economicSetUrl(data);renderEconomicIndicators();};form.querySelectorAll("select").forEach((select)=>select.addEventListener("change",commit));search.addEventListener("compositionstart",()=>{economicState.composing=true;});search.addEventListener("compositionend",()=>{economicState.composing=false;clearTimeout(timer);timer=setTimeout(commit,300);});search.addEventListener("input",()=>{form.querySelector("[data-economic-clear]").hidden=!search.value;if(economicState.composing)return;clearTimeout(timer);timer=setTimeout(commit,300);});search.addEventListener("keydown",(event)=>{if(event.key==="Enter"&&!event.isComposing){event.preventDefault();clearTimeout(timer);commit();}});document.querySelectorAll("[data-economic-clear]").forEach((button)=>button.addEventListener("click",()=>{search.value="";commit();document.getElementById("economicSearch")?.focus();}));}
  document.querySelectorAll("[data-economic-reset]").forEach((button)=>button.addEventListener("click",()=>{economicSetUrl({});renderEconomicIndicators();document.getElementById("economicSearch")?.focus();}));
  document.querySelectorAll("[data-economic-retry]").forEach((button)=>button.addEventListener("click",()=>loadEconomicIndicators(true)));
  document.querySelectorAll("[data-economic-detail]").forEach((button)=>button.addEventListener("click",()=>openEconomicDetail(button.dataset.economicDetail,button)));
  document.querySelectorAll("[data-economic-statistical-detail]").forEach((button)=>button.addEventListener("click",()=>openStatisticalCenterDetail(button.dataset.economicStatisticalDetail,button)));
  document.querySelectorAll("[data-economic-compare-slot]").forEach((select)=>select.addEventListener("change",()=>{const slot=select.dataset.economicCompareSlot,codes=[...document.querySelectorAll("[data-economic-compare-slot]")].map((control)=>control.value).filter(Boolean);economicState.selected=new Set(codes);renderEconomicIndicators();document.querySelector(`[data-economic-compare-slot="${slot}"]`)?.focus();codes.forEach(economicLoadComparisonSeries);}));
  document.querySelectorAll("[data-economic-compare-search]").forEach((input)=>{const apply=()=>{const slot=input.dataset.economicCompareSearch,control=document.querySelector(`[data-economic-compare-slot="${slot}"]`),query=input.value.trim().toLocaleLowerCase("fa-IR"),clear=document.querySelector(`[data-economic-compare-clear="${slot}"]`),empty=document.querySelector(`[data-economic-compare-empty="${slot}"]`);let matches=0;[...control.options].forEach((option)=>{const haystack=option.dataset.economicOptionSearch||`${option.textContent} ${option.value}`,visible=!query||option.value===""||haystack.toLocaleLowerCase("fa-IR").includes(query);option.hidden=!visible;if(visible&&option.value)matches+=1;});[...control.querySelectorAll("optgroup")].forEach((group)=>{group.hidden=![...group.querySelectorAll("option")].some((option)=>!option.hidden);});clear.hidden=!input.value;empty.hidden=matches>0;};input.addEventListener("compositionstart",()=>{economicState.composing=true;});input.addEventListener("input",()=>{if(!economicState.composing)apply();});input.addEventListener("compositionend",()=>{economicState.composing=false;apply();});document.querySelector(`[data-economic-compare-clear="${input.dataset.economicCompareSearch}"]`)?.addEventListener("click",()=>{input.value="";apply();input.focus();});});
  document.getElementById("economicNormalize")?.addEventListener("change",(event)=>{economicState.normalize=event.target.checked;renderEconomicIndicators();});
}
function bindEconomicComparisonChart(container,items) {
  const svg=container?.querySelector("svg"),hitbox=svg?.querySelector("[data-economic-comparison-cursor]"),pointNodes=svg?[...svg.querySelectorAll("[data-economic-comparison-point]")]:[],{series,minTime,maxTime,timeSpan}=economicComparisonDomain(items);
  if(!svg||!hitbox||!pointNodes.length||!series.length)return;
  const plot={x:44,y:12,width:402,height:184},{min,max,span}=economicComparisonScale(series),{axisMinTime,axisTimeSpan}=economicComparisonTimeScale(minTime,maxTime),cursor=svg.querySelector(".economic-chart-cursor"),tooltip=svg.querySelector(".economic-comparison-tooltip"),dateText=tooltip.querySelector(".economic-chart-tooltip-date"),rows=[...tooltip.querySelectorAll("[data-economic-comparison-tooltip-row]")],active=[...svg.querySelectorAll("[data-economic-comparison-active]")],live=container.querySelector(".economic-comparison-live");
  const position=(point)=>({x:plot.x+(point.time-axisMinTime)/axisTimeSpan*plot.width,y:plot.y+plot.height-(point.display-min)/span*plot.height}),nearest=(points,time)=>points.reduce((best,point)=>Math.abs(point.time-time)<Math.abs(best.time-time)?point:best,points[0]);
  const hide=()=>{cursor.classList.add("hidden");tooltip.classList.add("hidden");active.forEach((point)=>point.classList.add("hidden"));};
  const show=(time,announce=false)=>{const target=Math.max(minTime,Math.min(maxTime,time)),x=plot.x+(target-axisMinTime)/axisTimeSpan*plot.width,tooltipX=x>plot.x+plot.width/2?x-218:x+10,chosen=series.map((item)=>nearest(item.points,target));cursor.setAttribute("x1",x);cursor.setAttribute("x2",x);tooltip.setAttribute("transform",`translate(${tooltipX} 18)`);dateText.textContent=economicDate(new Date(target).toISOString());chosen.forEach((point,index)=>{const pos=position(point);active[index].setAttribute("cx",pos.x);active[index].setAttribute("cy",pos.y);active[index].classList.remove("hidden");rows[index].textContent=`${series[index].name_fa}: ${economicNumber(point.display)}${economicState.normalize?"":" "+(series[index].unit||"")}`;});cursor.classList.remove("hidden");tooltip.classList.remove("hidden");if(announce)live.textContent=`${economicDate(new Date(target).toISOString())}، ${chosen.map((point,index)=>`${series[index].name_fa} ${economicNumber(point.display)}`).join("، ")}`;};
  const eventTime=(event)=>{const matrix=svg.getScreenCTM();if(!matrix)return minTime;const position=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()),ratio=Math.max(0,Math.min(1,(position.x-plot.x)/plot.width));return axisMinTime+ratio*axisTimeSpan;};
  hitbox.addEventListener("pointermove",(event)=>show(eventTime(event)));
  hitbox.addEventListener("pointerdown",(event)=>show(eventTime(event)));
  hitbox.addEventListener("pointerleave",()=>{if(!svg.contains(document.activeElement))hide();});
  pointNodes.forEach((node)=>{node.addEventListener("focus",()=>show(Number(node.dataset.time),true));node.addEventListener("blur",hide);});
}
function economicDetailChart(item) {
  const points=item.series;if(points.length<2)return `<div class="economic-detail-empty">برای این بازه داده کافی موجود نیست.</div>`;
  const plot={x:44,y:12,width:402,height:184},values=points.map((p)=>Number(p.value)),min=Math.min(...values),max=Math.max(...values),span=max-min||1;
  const position=(point,index)=>({x:plot.x+index*(plot.width/Math.max(1,points.length-1)),y:plot.y+plot.height-(Number(point.value)-min)/span*plot.height});
  const positioned=points.map(position),coords=positioned.map(({x,y})=>`${x.toFixed(2)},${y.toFixed(2)}`),baseline=plot.y+plot.height;
  const grid=Array.from({length:5},(_,index)=>{const ratio=index/4,y=plot.y+ratio*plot.height,value=max-ratio*span;return `<g class="economic-chart-grid"><line x1="${plot.x}" y1="${y}" x2="${plot.x+plot.width}" y2="${y}"/><text x="${plot.x-8}" y="${y+4}" text-anchor="end" direction="ltr">${economicNumber(value)}</text></g>`;}).join("");
  const labelIndexes=[0,Math.floor((points.length-1)/2),points.length-1].filter((value,index,array)=>array.indexOf(value)===index);
  const labels=labelIndexes.map((pointIndex,index)=>{const x=positioned[pointIndex].x,anchor=index===0?"start":index===labelIndexes.length-1?"end":"middle";return `<text class="economic-chart-date" x="${x}" y="${baseline+21}" text-anchor="${anchor}">${economicEsc(economicPointDate(points[pointIndex],true))}</text>`;}).join("");
  const nodes=points.map((point,index)=>{const {x,y}=positioned[index],period=economicPointDate(point);return `<circle data-economic-chart-point="${index}" cx="${x}" cy="${y}" r="4" tabindex="0" aria-label="${economicEsc(period)}، ${economicNumber(point.value)} ${economicEsc(item.unit)}"><title>${economicEsc(period)} · ${economicNumber(point.value)} ${economicEsc(item.unit)}</title></circle>`;}).join("");
  const summary=`از ${economicNumber(values[0])} در ${economicPointDate(points[0])} به ${economicNumber(values.at(-1))} در ${economicPointDate(points.at(-1))} رسیده است.`;
  const caption=item.compactCaption?`<span>منبع: ${economicEsc(item.source?.name)}</span>`:`<span>واحد: ${economicEsc(item.unit)}</span><span>منبع: ${economicEsc(item.source?.name)}</span><span>برای جزئیات، روی نمودار حرکت کنید.</span>`;
  return `<figure class="economic-detail-chart"><svg viewBox="0 0 490 226" role="img" aria-labelledby="economicChartTitle economicChartDescription"><title id="economicChartTitle">روند ${economicEsc(item.name_fa)}</title><desc id="economicChartDescription">${economicEsc(summary)} برای دیدن مقدار هر دوره، نشانگر را روی نمودار حرکت دهید یا نقاط را با کلید Tab انتخاب کنید.</desc><rect class="economic-chart-plot" x="44" y="12" width="402" height="184" fill="transparent"/>${grid}<path class="economic-chart-area" d="M${positioned[0].x},${baseline} L${coords.join(" L")} L${positioned.at(-1).x},${baseline} Z"/><path class="economic-chart-line" d="M${coords.join(" L")}" vector-effect="non-scaling-stroke"/>${nodes}${labels}<line class="economic-chart-cursor hidden" x1="44" y1="12" x2="44" y2="196"/><circle class="economic-chart-active-point hidden" cx="44" cy="12" r="5"/><g class="economic-chart-tooltip hidden" aria-hidden="true"><rect width="122" height="68" rx="3"/><text class="economic-chart-tooltip-date" x="112" y="18" text-anchor="start"></text><text class="economic-chart-tooltip-value" x="112" y="39" text-anchor="start"></text><text class="economic-chart-tooltip-unit" x="112" y="58" text-anchor="start"></text></g><rect class="economic-chart-hitbox" x="44" y="12" width="402" height="184" fill="transparent" data-economic-chart-cursor aria-hidden="true"/></svg><figcaption>${caption}<span class="economic-chart-live sr-only" aria-live="polite">${economicEsc(summary)}</span></figcaption></figure>`;
}
function bindEconomicDetailChart(container,item) {
  const svg=container?.querySelector(".economic-detail-chart svg"),hitbox=svg?.querySelector("[data-economic-chart-cursor]"),points=economicArray(item?.series),pointNodes=svg?[...svg.querySelectorAll("[data-economic-chart-point]")]:[];
  if(!svg||!hitbox||!points.length||!pointNodes.length)return;
  const plot={x:44,y:12,width:402,height:184},cursor=svg.querySelector(".economic-chart-cursor"),active=svg.querySelector(".economic-chart-active-point"),tooltip=svg.querySelector(".economic-chart-tooltip"),live=container.querySelector(".economic-chart-live"),dateText=tooltip.querySelector(".economic-chart-tooltip-date"),valueText=tooltip.querySelector(".economic-chart-tooltip-value"),unitText=tooltip.querySelector(".economic-chart-tooltip-unit");
  const hide=()=>{cursor.classList.add("hidden");active.classList.add("hidden");tooltip.classList.add("hidden");};
  const show=(index,announce=false)=>{const point=points[index],node=pointNodes[index];if(!point||!node)return;const x=Number(node.getAttribute("cx")),y=Number(node.getAttribute("cy")),tooltipX=x>plot.x+plot.width/2?x-132:x+10,tooltipY=Math.max(plot.y+4,Math.min(y-76,plot.y+plot.height-72)),period=economicPointDate(point),description=`${period}، ${economicNumber(point.value)} ${item.unit||""}`;cursor.setAttribute("x1",x);cursor.setAttribute("x2",x);active.setAttribute("cx",x);active.setAttribute("cy",y);tooltip.setAttribute("transform",`translate(${tooltipX} ${tooltipY})`);dateText.textContent=period;valueText.textContent=`مقدار: ${economicNumber(point.value)}`;unitText.textContent=item.unit||"";cursor.classList.remove("hidden");active.classList.remove("hidden");tooltip.classList.remove("hidden");if(announce)live.textContent=description;};
  const nearestIndex=(event)=>{const matrix=svg.getScreenCTM();if(!matrix)return 0;const position=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()),ratio=Math.max(0,Math.min(1,(position.x-plot.x)/plot.width));return Math.round(ratio*(points.length-1));};
  hitbox.addEventListener("pointermove",(event)=>show(nearestIndex(event)));
  hitbox.addEventListener("pointerdown",(event)=>show(nearestIndex(event)));
  hitbox.addEventListener("pointerleave",()=>{if(!svg.contains(document.activeElement))hide();});
  pointNodes.forEach((node,index)=>{node.addEventListener("focus",()=>show(index,true));node.addEventListener("blur",hide);});
}
function economicRangeSeries(item,range) {
  if(!item.series.length)return [];
  if(range==="all")return item.series;
  const latest=new Date(item.series.at(-1).period_date).getTime();
  const years=range==="5y"?5:1,cutoff=latest-years*365.25*24*60*60*1000;
  return item.series.filter((point)=>new Date(point.period_date).getTime()>=cutoff);
}
function economicLatestPublishedAt(item) {
  const published=economicArray(item?.series).map((point)=>point?.published_at).filter((value)=>value&&!Number.isNaN(new Date(value).getTime())).sort((a,b)=>new Date(a)-new Date(b));
  return published.at(-1)||item?.current?.published_at||null;
}
function economicDetailVisual(item,range) {
  return economicDetailChart({...item,series:economicRangeSeries(item,range)});
}
function economicInstitutionalSeries(item) {
  return economicArray(item?.series).filter((point)=>point?.period_date&&Number.isFinite(Number(point.value))).sort((a,b)=>new Date(a.period_date)-new Date(b.period_date));
}
function economicInstitutionalRangeSeries(item,range) {
  const series=economicInstitutionalSeries(item);if(range==="all"||!series.length)return series;
  const years=Number.parseInt(range,10);if(!Number.isFinite(years))return series;
  const latest=new Date(series.at(-1).period_date),cutoff=new Date(latest);cutoff.setUTCFullYear(cutoff.getUTCFullYear()-years);
  return series.filter((point)=>new Date(point.period_date)>=cutoff);
}
function economicInstitutionalAnalytics(item) {
  const series=economicInstitutionalSeries(item),latest=series.at(-1);if(!latest)return {series,latest:null,prior:null,percentile:null,change:null,signal:0,tone:"flat",label:"داده ناکافی"};
  const latestDate=new Date(latest.period_date),priorTarget=new Date(latestDate);priorTarget.setUTCMonth(priorTarget.getUTCMonth()-3);
  const prior=series.slice(0,-1).filter((point)=>new Date(point.period_date)<=priorTarget).at(-1)||null;
  const cutoff=new Date(latestDate);cutoff.setUTCFullYear(cutoff.getUTCFullYear()-2);
  const window=series.filter((point)=>new Date(point.period_date)>=cutoff),latestValue=Number(latest.value),priorValue=Number(prior?.value),percentile=window.length?Math.round(window.filter((point)=>Number(point.value)<=latestValue).length/window.length*100):null,isRate=String(item.unit||"").includes("درصد");
  const change=prior&&Number.isFinite(priorValue)?(isRate?latestValue-priorValue:priorValue?((latestValue/priorValue)-1)*100:null):null,signal=change>0?1:change<0?-1:0,tone=signal>0?"up":signal<0?"down":"flat",label=signal>0?"صعودی":signal<0?"نزولی":"خنثی";
  return {series,latest,prior,percentile,change,signal,tone,label,isRate};
}
function economicInstitutionalChange(analytics) {
  if(analytics.change===null||analytics.change===undefined)return "داده کافی نیست";
  const sign=analytics.change>0?"+":"",unit=analytics.isRate?" واحد درصد":"٪";
  return `${sign}${economicNumber(analytics.change)}${unit}`;
}
function economicInstitutionalDetailMarkup(item,{kicker="نمای تحلیلی",after="",showContext=true,stats="",compactSignal=false,latinRanges=false}={}) {
  const analytics=economicInstitutionalAnalytics(item),latest=analytics.latest,prior=analytics.prior,score=analytics.signal>0?"+1":String(analytics.signal),explanation=analytics.signal>0?"مقدار شاخص در سه ماه اخیر افزایش یافته و شیب روند مثبت است.":analytics.signal<0?"مقدار شاخص در سه ماه اخیر کاهش یافته و شیب روند منفی است.":"تغییر معناداری در سه ماه اخیر ثبت نشده است.";
  const signalLabel=analytics.label,signalDescription=analytics.signal>0?"در حال رشد و شتاب‌گیری":analytics.signal<0?"در حال کاهش و شتاب‌گیری نزولی":"بدون تغییر معنادار",signalText=`${signalLabel}، ${signalDescription}`;
  const rangeLabels=latinRanges?[["1y","1Y"],["3y","3Y"],["5y","5Y"],["10y","10Y"],["all","Max"]]:[["1y","۱ سال"],["3y","۳ سال"],["5y","۵ سال"],["10y","۱۰ سال"],["all","کل"]];
  return `<section class="institutional-detail" data-institutional-detail>
    ${showContext?`<header class="institutional-detail-context"><small>${economicEsc(kicker)}</small><span>${economicEsc(item.source?.name||"منبع رسمی")} · ${economicEsc(item.group||item.category||"")}</span></header>`:""}
    ${stats||`<dl class="institutional-detail-stats">
      <div><dt>آخرین مقدار</dt><dd dir="ltr">${latest?economicNumber(latest.value):"—"}</dd><small>${latest?economicPointDate(latest):"بدون داده"} · ${economicEsc(item.unit||"—")}</small></div>
      <div><dt>سه ماه قبل</dt><dd dir="ltr">${prior?economicNumber(prior.value):"—"}</dd><small>${prior?economicPointDate(prior):"داده کافی نیست"}</small></div>
      <div><dt>صدک دوساله</dt><dd dir="ltr">${analytics.percentile??"—"}</dd><small>${analytics.percentile===null?"داده کافی نیست":`جایگاه ${economicNumber(analytics.percentile,0)} از ۱۰۰`}</small></div>
    </dl>`}
    <div class="institutional-detail-ranges${latinRanges?" institutional-detail-ranges--latin":""}" role="group" aria-label="بازه نمودار شاخص">
      ${rangeLabels.map(([value,label])=>`<button type="button" data-institutional-range="${value}" aria-pressed="${value==="3y"}">${label}</button>`).join("")}
    </div>
    <div class="institutional-detail-chart" data-institutional-chart>${economicDetailChart({...item,series:economicInstitutionalRangeSeries(item,"3y")})}</div>
    ${compactSignal?`<div class="institutional-detail-signal institutional-detail-signal--compact ${analytics.tone}" dir="rtl" aria-label="${economicEsc(signalText)}"><span class="institutional-signal-chip ${analytics.tone}">${economicEsc(signalLabel)}</span><span class="institutional-signal-description">${economicEsc(signalDescription)}</span></div>`:`<section class="institutional-detail-signal ${analytics.tone}" aria-label="سیگنال ${analytics.label}">
      <div><b dir="ltr">${score}</b><span><strong>${analytics.label}</strong><small>${analytics.signal>0?"مثبت، رو به بالا":analytics.signal<0?"منفی، رو به پایین":"بدون جهت مشخص"}</small></span></div>
      <strong dir="ltr">${economicInstitutionalChange(analytics)}</strong>
      <p>${explanation}</p>
    </section>`}
    ${after}
  </section>`;
}
function economicInstitutionalSideMarkup(item,{kicker="نمای سریع شاخص",stats="",note="",compactSignal=false,latinRanges=false}={}) {
  return `<div class="institutional-side-content">
    <header class="institutional-side-heading"><small>${economicEsc(kicker)}</small><h3>${economicEsc(item.name_fa||item.title_fa||item.code||"شاخص")}</h3><span>${economicEsc(item.source?.name||"منبع رسمی")} · ${economicEsc(item.group||item.category||"")}</span></header>
    ${economicInstitutionalDetailMarkup(item,{showContext:false,stats,compactSignal,latinRanges})}
    ${note?`<p class="note institutional-side-note">${economicEsc(note)}</p>`:""}
  </div>`;
}
function bindEconomicInstitutionalDetail(body,item) {
  const visual=body.querySelector("[data-institutional-chart]");
  if(!visual)return;
  const render=(range)=>{const ranged={...item,series:economicInstitutionalRangeSeries(item,range)};visual.innerHTML=economicDetailChart(ranged);bindEconomicDetailChart(visual,ranged);};
  render("3y");
  body.querySelectorAll("[data-institutional-range]").forEach((button)=>button.addEventListener("click",()=>{body.querySelectorAll("[data-institutional-range]").forEach((candidate)=>candidate.setAttribute("aria-pressed",String(candidate===button)));render(button.dataset.institutionalRange);button.focus();}));
}
function openEconomicDetail(code,trigger) {
  const item=economicArray(economicState.payload?.indicators).map(economicValidatedIndicator).find((candidate)=>candidate?.code===code);if(!item)return;
  const dialog=document.getElementById("economicDetailDialog"),body=document.getElementById("economicDetailBody");
  document.getElementById("economicDetailTitle").textContent=item.name_fa;
  const historyNotice=item.access?.full_history_requires_subscription&&!item.access?.full_history_granted?"<span>تاریخچه بیش از پنج سال نیازمند اشتراک است.</span>":"";
  body.innerHTML=`<div class="economic-detail-ranges" role="group" aria-label="بازه نمودار"><button type="button" data-economic-range="all" aria-pressed="true">کل تاریخچه</button><button type="button" data-economic-range="5y" aria-pressed="false">پنج‌سال</button><button type="button" data-economic-range="1y" aria-pressed="false">یک‌سال</button>${historyNotice}</div><div id="economicDetailVisual">${economicDetailVisual(item,"all")}</div><section class="economic-detail-definition"><h3>تعریف شاخص</h3><p>${economicEsc(item.definition||"تعریف رسمی هنوز در منبع داده ثبت نشده است.")}</p><dl><div><dt>واحد</dt><dd>${economicEsc(item.unit)}</dd></div><div><dt>تناوب انتشار</dt><dd>${economicEsc(ECONOMIC_LABELS[item.frequency]||item.frequency)}</dd></div><div><dt>منبع اصلی</dt><dd>${economicEsc(item.source?.name)}</dd></div><div><dt>تاریخ انتشار</dt><dd>${economicDate(economicLatestPublishedAt(item),true)}</dd></div></dl></section>${item.kind==="analytical"&&item.source?.type!=="aggregator"?`<section class="economic-methodology"><h3>روش محاسبه</h3><p>${economicEsc(item.methodology?.description||"روش محاسبه ثبت نشده است.")}</p><span>نسخه مدل: <b dir="ltr">${economicEsc(item.methodology?.model_version)}</b></span><p>این شاخص برآورد تحلیلی است و داده رسمی یا توصیه سرمایه‌گذاری محسوب نمی‌شود.</p></section>`:""}<footer class="economic-detail-actions"><button type="button" data-economic-export="${economicEsc(item.code)}"${item.series.length?"":" disabled"}>خروجی CSV</button>${item.series.length?"":"<span>بدون داده، فایل خالی ساخته نمی‌شود.</span>"}</footer>`;
  modalManager.open(dialog,{trigger,initialFocus:document.getElementById("economicDetailClose"),close:closeEconomicDetail});
  bindEconomicDetailChart(document.getElementById("economicDetailVisual"),{...item,series:economicRangeSeries(item,"all")});
  body.querySelector("[data-economic-export]")?.addEventListener("click",()=>exportEconomicCsv(item));
  body.querySelectorAll("[data-economic-range]").forEach((button)=>button.addEventListener("click",()=>{body.querySelectorAll("[data-economic-range]").forEach((candidate)=>candidate.setAttribute("aria-pressed",String(candidate===button)));const ranged={...item,series:economicRangeSeries(item,button.dataset.economicRange)},visual=document.getElementById("economicDetailVisual");visual.innerHTML=economicDetailVisual(ranged,button.dataset.economicRange);bindEconomicDetailChart(visual,ranged);}));
}
function closeEconomicDetail() {const dialog=document.getElementById("economicDetailDialog");if(!dialog||dialog.classList.contains("hidden"))return;modalManager.close(dialog);}
function exportEconomicCsv(item) {
  if(!item.series.length)return;const rate=item.methodology?.primary_rate,header=rate?`code,period_date_jalali,period_date_gregorian,${rate}_percent,unit,source,published_at`:"code,period_date_jalali,period_date_gregorian,value,unit,source,published_at",quote=(v)=>`"${String(v??"").replaceAll('"','""')}"`,rows=item.series.map((point)=>[item.code,point.period_date_jalali||"",point.period_date,point.value,item.unit,item.source?.name,point.published_at].map(quote).join(","));
  const blob=new Blob(["\uFEFF",[header,...rows].join("\r\n")],{type:"text/csv;charset=utf-8"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`${item.code}.csv`;link.click();URL.revokeObjectURL(url);
}
async function loadEconomicIndicators(force=false) {
  const comparisonPage=document.body.dataset.page==="economic-comparison",root=document.getElementById(comparisonPage?"economicComparisonApp":"economicIndicatorsApp");if(!root)return;
  economicState.controller?.abort();economicState.controller=new AbortController();const request=++economicState.request;
  const buttons=[document.getElementById("economicRefreshButton"),document.getElementById("refreshButton")].filter(Boolean);buttons.forEach((b)=>{b.disabled=true;b.setAttribute("aria-busy","true");});root.setAttribute("aria-busy","true");
  if(!economicState.payload)root.innerHTML=`<section class="economic-loading" aria-label="در حال دریافت شاخص‌های اقتصادی"><div class="economic-loading-line"></div><div class="economic-loading-pulse"><i></i><i></i><i></i><i></i></div><div class="economic-loading-grid"><b></b></div></section>`;
  try {
    const endpoint=comparisonPage?"/api/economic-comparison-indicators":"/api/economic-indicators",requestOptions={cache:"no-store",credentials:"same-origin",signal:economicState.controller.signal},statisticalRequest=comparisonPage?Promise.resolve(null):fetch("/api/statistical-center-indicators?classification=%D8%A7%D8%B5%D9%84%DB%8C&lifecycle=%D8%AC%D8%A7%D8%B1%DB%8C&page_size=50",requestOptions),[response,statisticalResponse]=await Promise.all([fetch(`${endpoint}${force?"?refresh=1":""}`,requestOptions),statisticalRequest]);
    if(response.status===401||response.status===403){location.assign(`/login?next=${encodeURIComponent(location.pathname+location.search)}`);return;}
    if(!response.ok)throw new Error("دریافت شاخص‌های اقتصادی ناموفق بود");const payload=await response.json();if(request!==economicState.request)return;
    if(statisticalResponse){if(statisticalResponse.status===401||statisticalResponse.status===403){location.assign(`/login?next=${encodeURIComponent(location.pathname+location.search)}`);return;}const statisticalPayload=await statisticalResponse.json();if(!statisticalResponse.ok)throw new Error(statisticalPayload.error||"دریافت داده‌های مرکز آمار ناموفق بود");economicState.statisticalPayload=statisticalPayload;}
    if(!payload||!Array.isArray(payload.indicators)||(!comparisonPage&&!Array.isArray(payload.upcoming_releases)))throw new Error("ساختار پاسخ شاخص‌های اقتصادی معتبر نیست");economicState.payload=payload;
    const updatedAt=document.getElementById("updatedAt");if(updatedAt)updatedAt.textContent=economicDate(payload.generated_at,true);renderEconomicIndicators();
    if(typeof setStatus==="function")setStatus("success",payload.indicators.length?"شاخص‌های اقتصادی به‌روز شدند":"API آماده است؛ هنوز داده رسمی متصل نشده است");
  } catch(error) {
    if(error.name==="AbortError"||request!==economicState.request)return;const message=error instanceof TypeError?"ارتباط با سرور برقرار نشد؛ اتصال شبکه را بررسی و دوباره تلاش کنید.":error.message||"دریافت شاخص‌ها ناموفق بود.";root.setAttribute("aria-busy","false");root.innerHTML=`<section class="economic-error" role="alert"><h2>دریافت شاخص‌ها انجام نشد</h2><p>${economicEsc(message)}</p><button type="button" data-economic-retry>تلاش دوباره</button></section>`;root.querySelector("[data-economic-retry]").addEventListener("click",()=>loadEconomicIndicators(true));if(typeof setStatus==="function")setStatus("error",message);
  } finally {if(request===economicState.request)buttons.forEach((b)=>{b.disabled=false;b.removeAttribute("aria-busy");});}
}

document.addEventListener("DOMContentLoaded",()=>{
  document.getElementById("economicRefreshButton")?.addEventListener("click",()=>loadEconomicIndicators(true));
  document.getElementById("economicDetailClose")?.addEventListener("click",closeEconomicDetail);
  document.getElementById("economicDetailDialog")?.addEventListener("click",(event)=>{if(event.target===event.currentTarget)closeEconomicDetail();});
});
