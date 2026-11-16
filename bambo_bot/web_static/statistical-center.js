/* Paginated Statistical Center explorer backed by the prepared official snapshot. */
const statisticalCenterState={payload:null,controller:null,detailController:null,previewController:null,seriesCache:new Map(),selected:"",request:0,composing:false};
const statisticalCenterDefaults=Object.freeze({q:"",classification:"اصلی",lifecycle:"جاری",frequency:"all",economic_group:"all",page:"1",page_size:"25"});
const statisticalCenterUnitLabels=Object.freeze({index:"شاخص",percent:"درصد",irr:"ریال",gini:"ضریب جینی"});
function statisticalCenterFilters(){
  const params=new URLSearchParams(location.search),filters={...statisticalCenterDefaults};
  Object.keys(filters).forEach((key)=>{const value=params.get(`s_${key}`);if(value!==null)filters[key]=value;});
  return filters;
}
function statisticalCenterSetUrl(filters){
  const params=new URLSearchParams(location.search);
  Object.entries(statisticalCenterDefaults).forEach(([key,defaultValue])=>{const value=String(filters[key]??defaultValue);if(value===defaultValue)params.delete(`s_${key}`);else params.set(`s_${key}`,value);});
  history.replaceState(history.state,"",`${location.pathname}${params.size?`?${params}`:""}${location.hash}`);
}
function statisticalCenterOption(value,label,selected){return `<option value="${economicEsc(value)}"${value===selected?" selected":""}>${economicEsc(label)}</option>`;}
function statisticalCenterNumber(value,digits=0){return new Intl.NumberFormat("fa-IR",{maximumFractionDigits:digits}).format(Number(value)||0);}
function statisticalCenterNormalizeSearch(value){return String(value||"").normalize("NFKC").replace(/[يى]/g,"ی").replace(/ك/g,"ک").replace(/[\u200c\s]+/g," ").trim().toLocaleLowerCase("fa-IR");}
function statisticalCenterUnit(value){return statisticalCenterUnitLabels[value]||value||"—";}
function statisticalCenterOneLineDescription(item){
  if(item.description_fa)return item.description_fa;
  const title=statisticalCenterDisplayTitle(item),frequency={monthly:"ماهانه",quarterly:"فصلی",annual:"سالانه"}[item.frequency]||"در دوره‌های ثبت‌شده",unit=statisticalCenterUnit(item.unit);
  return `این سری، ${title} را ${frequency}${unit&&unit!=="—"?` و با واحد ${unit}`:""} گزارش می‌کند.`;
}
function statisticalCenterDisplayTitle(value){
  if(value&&typeof value==="object"&&value.display_title_fa)return value.display_title_fa;
  const raw=value&&typeof value==="object"?value.title_fa:value,parts=String(raw||"").split("|").map((part)=>part.trim()).filter(Boolean),unique=[];
  parts.forEach((part)=>{if(!unique.includes(part))unique.push(part);});
  return unique.join(" — ");
}
function statisticalCenterForm(payload){
  const f=payload.filters,facets=payload.facets;
  return `<form id="statisticalCenterFilters" class="statistical-center-filters" novalidate>
    <label class="statistical-center-search"><span>جست‌وجو در سری‌های مرکز آمار و amar-mcp</span><span><input id="statisticalCenterSearch" name="q" type="search" value="${economicEsc(f.q)}" placeholder="نام شاخص، گروه یا شناسه فنی" autocomplete="off"><button type="button" data-statistical-center-clear aria-label="پاک‌کردن جست‌وجوی مرکز آمار"${f.q?"":" hidden"}>×</button></span></label>
    <label><span>سطح داده</span><select name="classification">${statisticalCenterOption("اصلی","سری‌های اصلی",f.classification)}${statisticalCenterOption("تفکیکی","سری‌های تفکیکی",f.classification)}${statisticalCenterOption("all","همه سری‌ها",f.classification)}</select></label>
    <label><span>وضعیت</span><select name="lifecycle">${statisticalCenterOption("جاری","جاری",f.lifecycle)}${statisticalCenterOption("all","جاری و آرشیوی",f.lifecycle)}${facets.lifecycles.filter((value)=>value!=="جاری").map((value)=>statisticalCenterOption(value,value,f.lifecycle)).join("")}</select></label>
    <label><span>تناوب</span><select name="frequency">${statisticalCenterOption("all","ماهانه و فصلی",f.frequency)}${statisticalCenterOption("monthly","ماهانه",f.frequency)}${statisticalCenterOption("quarterly","فصلی",f.frequency)}</select></label>
    <label><span>گروه اقتصادی</span><select name="economic_group">${statisticalCenterOption("all","همه گروه‌ها",f.economic_group)}${facets.economic_groups.map((value)=>statisticalCenterOption(value,value,f.economic_group)).join("")}</select></label>
    <label><span>تعداد ردیف</span><select name="page_size">${[10,25,50].map((value)=>statisticalCenterOption(String(value),String(value),String(payload.pagination.page_size))).join("")}</select></label>
    <div class="statistical-center-filter-actions"><button type="button" data-statistical-center-all>نمایش همه داده‌ها</button><button type="button" data-statistical-center-reset>بازگشت به سری‌های اصلی</button></div>
  </form>`;
}
function statisticalCenterSummary(summary){
  return `<dl class="statistical-center-summary"><div><dt>کل سری‌ها</dt><dd>${statisticalCenterNumber(summary.total_series)}</dd></div><div><dt>سری اصلی</dt><dd>${statisticalCenterNumber(summary.main_series)}</dd></div><div><dt>سری تفکیکی</dt><dd>${statisticalCenterNumber(summary.detailed_series)}</dd></div><div><dt>ماهانه</dt><dd>${statisticalCenterNumber(summary.monthly_series)}</dd></div><div><dt>فصلی</dt><dd>${statisticalCenterNumber(summary.quarterly_series)}</dd></div></dl>`;
}
function statisticalCenterAmarMcpItems(items,query=""){
  const normalizedQuery=statisticalCenterNormalizeSearch(query);
  return (items||[]).filter((item)=>!normalizedQuery||statisticalCenterNormalizeSearch([item.name_fa,item.name_en,item.economic_group,item.code].join(" ")).includes(normalizedQuery)).map((item)=>{
    const points=item.series||[],latest=points.at(-1)||{},trend=item.frequency==="annual"?points.slice(-2):points.slice(-8),values=trend.map((point)=>Number(point.value)).filter(Number.isFinite),signal=values.length>1?(values.at(-1)>values[0]?1:values.at(-1)<values[0]?-1:0):0;
    const unit=item.unit==="درصد"?"percent":item.unit==="ضریب"?"gini":item.unit||"—";
    const adapted={series_key:item.code,technical_id:item.code,title_fa:item.name_fa,display_title_fa:item.name_fa,description_fa:item.description_fa||"",unit,frequency:item.frequency||"quarterly",economic_group:item.economic_group||"سایر شاخص‌ها",classification:"اصلی",lifecycle:"جاری",metric_type:"سری زمانی",latest:{value:latest.value},last_available_label_fa:latest.period_date_jalali||latest.period_date||"—",analytics:{trend_2y:trend.map((point)=>({date:point.period_date,value:point.value})),signal},series:points.map((point)=>({...point,period_label_fa:point.period_date_jalali||point.period_date||"—"})),source:{name:"amar-mcp",organization:"مرکز آمار ایران"}};
    adapted.description_fa=statisticalCenterOneLineDescription(adapted);
    statisticalCenterState.seriesCache.set(adapted.series_key,adapted);return adapted;
  });
}
function statisticalCenterLatest(item){
  const latest=item.latest||{};
  if(latest.value===null||latest.value===undefined||latest.value==="")return `<span class="economic-value-missing">—<small>بدون مشاهده</small></span>`;
  return `<strong dir="ltr">${economicNumber(latest.value)}</strong><small>${economicEsc(statisticalCenterUnit(item.unit))}</small>`;
}
function statisticalCenterSparkline(item){
  const points=item.analytics?.trend_2y||[];
  if(points.length<2)return `<span class="institutional-trend-empty">داده ناکافی</span>`;
  const values=points.map((point)=>Number(point.value)),min=Math.min(...values),max=Math.max(...values),span=max-min||1,signal=Number(item.analytics?.signal)||0,tone=signal>0?"up":signal<0?"down":"flat";
  const coords=values.map((value,index)=>`${3+index*(114/Math.max(1,values.length-1))},${29-(value-min)/span*24}`);
  return `<svg class="institutional-sparkline ${tone}" viewBox="0 0 120 34" role="img" aria-label="روند دوساله ${economicEsc(statisticalCenterDisplayTitle(item))} از ${economicNumber(values[0])} تا ${economicNumber(values.at(-1))}"><title>روند دوساله ${economicEsc(statisticalCenterDisplayTitle(item))}</title><path d="M${coords.join(" L")}" vector-effect="non-scaling-stroke"/><circle cx="117" cy="${29-(values.at(-1)-min)/span*24}" r="2.6"/></svg>`;
}
function statisticalCenterChange(item){
  const value=item.analytics?.change_3m;
  if(value===null||value===undefined)return `<span class="economic-value-missing">—<small>داده کافی نیست</small></span>`;
  const tone=Number(value)>0?"up":Number(value)<0?"down":"flat",sign=Number(value)>0?"+":"",unit=item.analytics?.change_3m_kind==="point"?" واحد درصد":"٪",label=Number(value)>0?"افزایش":Number(value)<0?"کاهش":"بدون تغییر";
  return `<span class="institutional-change ${tone}" dir="ltr">${sign}${economicNumber(value)}${unit}</span><small>${label}</small>`;
}
function statisticalCenterSignal(item){
  const signal=Number(item.analytics?.signal)||0,tone=signal>0?"up":signal<0?"down":"flat",label=signal>0?"صعودی":signal<0?"نزولی":"خنثی",score=signal>0?"+1":String(signal);
  return `<span class="institutional-signal ${tone}"><b dir="ltr">${score}</b><small>${label}</small></span>`;
}
function statisticalCenterRows(items){
  return items.map((item)=>`<tr><th scope="row"><button type="button" data-statistical-center-preview="${economicEsc(item.series_key)}" aria-pressed="false"><strong title="${economicEsc(statisticalCenterDisplayTitle(item))}">${economicEsc(statisticalCenterDisplayTitle(item))}</strong></button></th><td class="statistical-center-latest">${statisticalCenterLatest(item)}<small>${economicEsc(item.last_available_label_fa||item.last_available_jalali||"—")}</small></td><td>${statisticalCenterSparkline(item)}</td><td class="institutional-analysis-cell"><button type="button" data-statistical-center-analysis="${economicEsc(item.series_key)}">تحلیل کامل</button></td></tr>`).join("");
}
function statisticalCenterTable(payload,amarItems=[]){
  const {pagination,indicators}=payload;
  if(!indicators.length&&!amarItems.length)return `<section class="economic-empty statistical-center-empty"><h3>سری مطابق این فیلترها پیدا نشد</h3><p>عبارت جست‌وجو یا فیلترهای مرکز آمار را تغییر دهید.</p><button type="button" data-statistical-center-reset>بازگشت به سری‌های اصلی</button></section>`;
  const first=(pagination.page-1)*pagination.page_size+1,last=Math.min(pagination.page*pagination.page_size,pagination.total);
  const groups=[...new Set(indicators.map((item)=>item.economic_group))],amarGroups=[...new Set(amarItems.map((item)=>item.economic_group))],combinedCount=pagination.total+amarItems.length;
  return `<div class="statistical-center-results-heading"><p><strong>${statisticalCenterNumber(combinedCount)}</strong> سری مطابق فیلترها</p><span>مرکز آمار ${statisticalCenterNumber(pagination.total)} · amar-mcp ${statisticalCenterNumber(amarItems.length)}</span></div><div class="institutional-master-detail"><div class="institutional-master"><div class="statistical-center-table-wrap institutional-table-wrap" tabindex="0" role="region" aria-label="جدول شاخص‌های مرکز آمار و amar-mcp؛ برای مشاهده ستون‌های بیشتر افقی پیمایش کنید"><table class="statistical-center-table institutional-table"><caption class="sr-only">شاخص‌های مرکز آمار و amar-mcp با آخرین مقدار، روند دوساله و دسترسی به تحلیل کامل</caption><thead><tr><th scope="col">شاخص</th><th scope="col">آخرین مقدار</th><th scope="col">روند ۲ساله</th><th scope="col">تحلیل</th></tr></thead>${groups.map((group)=>`<tbody><tr class="institutional-group-row"><th colspan="4" scope="rowgroup">${economicEsc(group)} <span>${statisticalCenterNumber(indicators.filter((item)=>item.economic_group===group).length)} شاخص</span></th></tr>${statisticalCenterRows(indicators.filter((item)=>item.economic_group===group))}</tbody>`).join("")}${amarGroups.map((group)=>`<tbody><tr class="institutional-group-row"><th colspan="4" scope="rowgroup">${economicEsc(group)} <span>${statisticalCenterNumber(amarItems.filter((item)=>item.economic_group===group).length)} شاخص</span></th></tr>${statisticalCenterRows(amarItems.filter((item)=>item.economic_group===group))}</tbody>`).join("")}</table></div>${statisticalCenterPager(pagination)}</div><aside class="institutional-side" data-statistical-center-side aria-label="جزئیات شاخص انتخاب‌شده" aria-live="polite" aria-busy="true"><section class="institutional-side-loading"><span class="spinner"></span><p>در حال دریافت جزئیات شاخص…</p></section></aside></div>`;
}
function statisticalCenterPager(pagination){
  return `<nav class="statistical-center-pagination" aria-label="صفحه‌بندی داده‌های مرکز آمار"><button type="button" data-statistical-center-page="${pagination.page-1}"${pagination.page<=1?" disabled":""}>صفحه قبل</button><span>صفحه ${statisticalCenterNumber(pagination.page)} از ${statisticalCenterNumber(pagination.pages)}</span><button type="button" data-statistical-center-page="${pagination.page+1}"${pagination.page>=pagination.pages?" disabled":""}>صفحه بعد</button></nav>`;
}
function renderStatisticalCenter(){
  const root=document.getElementById("statisticalCenterApp"),payload=statisticalCenterState.payload;if(!root||!payload)return;
  const searchWasFocused=document.activeElement?.id==="statisticalCenterSearch",search=document.getElementById("statisticalCenterSearch"),selectionStart=searchWasFocused?search.selectionStart:0,selectionEnd=searchWasFocused?search.selectionEnd:0,scrollY=window.scrollY;
  const amarItems=statisticalCenterAmarMcpItems(payload.amar_mcp_series||[],payload.filters?.q||"");
  root.setAttribute("aria-busy","false");root.innerHTML=`${statisticalCenterSummary(payload.summary)}${statisticalCenterForm(payload)}${statisticalCenterTable(payload,amarItems)}`;bindStatisticalCenterInteractions();
  if(searchWasFocused){const replacement=document.getElementById("statisticalCenterSearch");replacement?.focus({preventScroll:true});replacement?.setSelectionRange(selectionStart,selectionEnd);window.scrollTo({top:scrollY,behavior:"instant"});}
}
function statisticalCenterCurrentForm(){const form=document.getElementById("statisticalCenterFilters");return form?{...statisticalCenterDefaults,...Object.fromEntries(new FormData(form)),page:"1"}:statisticalCenterFilters();}
function bindStatisticalCenterInteractions(){
  const form=document.getElementById("statisticalCenterFilters"),search=document.getElementById("statisticalCenterSearch");if(!form||!search)return;let timer;
  const commit=(filters=statisticalCenterCurrentForm())=>{statisticalCenterSetUrl(filters);loadStatisticalCenter(filters);};
  form.querySelectorAll("select").forEach((select)=>select.addEventListener("change",()=>commit()));
  search.addEventListener("compositionstart",()=>{statisticalCenterState.composing=true;});
  search.addEventListener("compositionend",()=>{statisticalCenterState.composing=false;clearTimeout(timer);timer=setTimeout(()=>commit(),500);});
  search.addEventListener("input",()=>{form.querySelector("[data-statistical-center-clear]").hidden=!search.value;if(statisticalCenterState.composing)return;clearTimeout(timer);timer=setTimeout(()=>commit(),500);});
  search.addEventListener("keydown",(event)=>{if(event.key==="Enter"&&!event.isComposing){event.preventDefault();clearTimeout(timer);commit();}});
  form.querySelector("[data-statistical-center-clear]")?.addEventListener("click",()=>{search.value="";commit();search.focus();});
  document.querySelectorAll("[data-statistical-center-reset]").forEach((button)=>button.addEventListener("click",()=>commit({...statisticalCenterDefaults})));
  form.querySelector("[data-statistical-center-all]")?.addEventListener("click",()=>commit({...statisticalCenterDefaults,classification:"all",lifecycle:"all"}));
  document.querySelectorAll("[data-statistical-center-page]").forEach((button)=>button.addEventListener("click",()=>{if(button.disabled)return;const filters={...statisticalCenterFilters(),page:button.dataset.statisticalCenterPage};statisticalCenterSetUrl(filters);loadStatisticalCenter(filters).then(()=>document.getElementById("statisticalCenterTitle")?.focus({preventScroll:true}));}));
  document.querySelectorAll("[data-statistical-center-preview]").forEach((button)=>button.addEventListener("click",()=>showStatisticalCenterPreview(button.dataset.statisticalCenterPreview,true)));
  document.querySelectorAll("[data-statistical-center-analysis]").forEach((button)=>button.addEventListener("click",()=>openStatisticalCenterDetail(button.dataset.statisticalCenterAnalysis,button)));
  const visible=statisticalCenterState.payload?.indicators||[];if(visible.length){if(!visible.some((item)=>item.series_key===statisticalCenterState.selected))statisticalCenterState.selected=visible[0].series_key;showStatisticalCenterPreview(statisticalCenterState.selected);}
}
function statisticalCenterChartItem(item,compactCaption=false){return {name_fa:statisticalCenterDisplayTitle(item),code:item.technical_id,unit:statisticalCenterUnit(item.unit),frequency:item.frequency,group:item.economic_group,source:{name:"مرکز آمار ایران"},series:item.series,compactCaption};}
function statisticalCenterMovement(point,item,field,pointsField){
  const coefficientField=field==="period_change_percent"?"period_change_coefficient":"yearly_change_coefficient",usePoints=item.unit==="percent"&&point?.[pointsField]!==null&&point?.[pointsField]!==undefined,useCoefficient=item.unit==="gini"&&point?.[coefficientField]!==null&&point?.[coefficientField]!==undefined,value=usePoints?point?.[pointsField]:useCoefficient?point?.[coefficientField]:point?.[field];if(value===null||value===undefined||!Number.isFinite(Number(value)))return {value:"—",tone:"flat",detail:"داده کافی نیست"};
  const numeric=Number(value),sign=numeric>0?"+":"",unit=usePoints?" واحد درصد":useCoefficient?" واحد":"٪",tone=numeric>0?"up":numeric<0?"down":"flat";return {value:`${sign}${economicNumber(numeric)}${unit}`,tone,detail:numeric>0?"افزایش":numeric<0?"کاهش":"بدون تغییر"};
}
function statisticalCenterSideStats(item){
  const latest=item.series?.at(-1),period=statisticalCenterMovement(latest,item,"period_change_percent","period_change_percentage_points"),yearly=statisticalCenterMovement(latest,item,"yearly_change_percent","yearly_change_percentage_points");
  return `<dl class="institutional-detail-stats statistical-center-side-stats"><div><dt>آخرین مقدار</dt><dd dir="ltr">${latest?economicNumber(latest.value):"—"}</dd><small>${latest?economicPointDate(latest):"بدون داده"} · ${economicEsc(statisticalCenterUnit(item.unit))}</small></div><div><dt>تغییر نسبت به دوره قبل</dt><dd class="${period.tone}" dir="ltr">${period.value}</dd><small>${period.detail}</small></div><div><dt>تغییر نقطه‌به‌نقطه</dt><dd class="${yearly.tone}" dir="ltr">${yearly.value}</dd><small>نسبت به دوره مشابه سال قبل</small></div></dl>`;
}
function statisticalCenterDetailMarkup(item){
  const chartItem=statisticalCenterChartItem(item);
  const frequencyLabel={monthly:"ماهانه",quarterly:"فصلی",annual:"سالانه"}[item.frequency]||"نامشخص";
  const after=`<section class="economic-detail-definition institutional-detail-definition"><h3>مشخصات رسمی شاخص</h3><dl><div><dt>نوع شاخص</dt><dd>${economicEsc(item.metric_type)}</dd></div><div><dt>دوره انتشار</dt><dd>${frequencyLabel}</dd></div><div><dt>سال پایه</dt><dd>${economicEsc(item.base_year||"—")}</dd></div><div><dt>سطح انتشار</dt><dd>${economicEsc(item.classification)}</dd></div><div><dt>وضعیت انتشار</dt><dd>${economicEsc(item.lifecycle)}</dd></div><div><dt>آغاز پوشش</dt><dd>${economicEsc(item.first_available_label_fa||item.first_available_jalali)}</dd></div><div><dt>پایان پوشش</dt><dd>${economicEsc(item.last_available_label_fa||item.last_available_jalali)}</dd></div></dl></section><p class="statistical-center-method-note">مقادیر رسمی بدون اصلاح نمایش داده می‌شوند؛ صدک و سیگنال صرفاً خلاصه تحلیلی تاریخچه‌اند.</p><footer class="economic-detail-actions"><button type="button" data-statistical-center-export>دریافت CSV این شاخص</button><a href="https://amar.org.ir/statistical-information/statid/28595" target="_blank" rel="noreferrer">مشاهده در مرکز آمار ایران</a></footer>`;
  return {markup:economicInstitutionalDetailMarkup(chartItem,{kicker:"قیمت و تورم · مرکز آمار ایران",after}),chartItem};
}
async function fetchStatisticalCenterSeries(seriesKey,signal){
  if(statisticalCenterState.seriesCache.has(seriesKey))return statisticalCenterState.seriesCache.get(seriesKey);
  const response=await fetch(`/api/statistical-center-series?series_key=${encodeURIComponent(seriesKey)}`,{cache:"no-store",credentials:"same-origin",signal});if(!response.ok)throw new Error(response.status===404?"این سری پیدا نشد.":"دریافت تاریخچه سری ناموفق بود.");const payload=await response.json();statisticalCenterState.seriesCache.set(seriesKey,payload.indicator);return payload.indicator;
}
async function showStatisticalCenterPreview(seriesKey,reveal=false){
  const aside=document.querySelector("[data-statistical-center-side]");if(!aside)return;
  statisticalCenterState.selected=seriesKey;statisticalCenterState.previewController?.abort();statisticalCenterState.previewController=new AbortController();aside.setAttribute("aria-busy","true");aside.innerHTML=`<section class="institutional-side-loading"><span class="spinner"></span><p>در حال دریافت جزئیات شاخص…</p></section>`;document.querySelectorAll("[data-statistical-center-preview]").forEach((button)=>button.setAttribute("aria-pressed",String(button.dataset.statisticalCenterPreview===seriesKey)));
  try{const item=await fetchStatisticalCenterSeries(seriesKey,statisticalCenterState.previewController.signal),chartItem=statisticalCenterChartItem(item,true);aside.innerHTML=economicInstitutionalSideMarkup(chartItem,{kicker:"قیمت و تورم · مرکز آمار ایران",stats:statisticalCenterSideStats(item),note:statisticalCenterOneLineDescription(item),compactSignal:true,latinRanges:true});aside.setAttribute("aria-busy","false");bindEconomicInstitutionalDetail(aside,chartItem);if(reveal&&matchMedia("(max-width: 980px)").matches)aside.scrollIntoView({block:"start"});}catch(error){if(error.name==="AbortError")return;aside.setAttribute("aria-busy","false");aside.innerHTML=`<section class="economic-error" role="alert"><h3>جزئیات شاخص دریافت نشد</h3><p>${economicEsc(error.message)}</p><button type="button" data-statistical-center-preview-retry>تلاش دوباره</button></section>`;aside.querySelector("[data-statistical-center-preview-retry]")?.addEventListener("click",()=>showStatisticalCenterPreview(seriesKey,true));}
}
async function openStatisticalCenterDetail(seriesKey,trigger){
  const dialog=document.getElementById("economicDetailDialog"),body=document.getElementById("economicDetailBody"),title=document.getElementById("economicDetailTitle");if(!dialog||!body||!title)return;
  statisticalCenterState.detailController?.abort();statisticalCenterState.detailController=new AbortController();title.textContent="داده مرکز آمار";body.innerHTML=`<section class="statistical-center-detail-loading" aria-label="در حال دریافت تاریخچه سری"><span class="spinner"></span><p>در حال دریافت تاریخچه…</p></section>`;modalManager.open(dialog,{trigger,initialFocus:document.getElementById("economicDetailClose"),close:()=>{statisticalCenterState.detailController?.abort();closeEconomicDetail();}});
  try{const item=await fetchStatisticalCenterSeries(seriesKey,statisticalCenterState.detailController.signal),displayTitle=statisticalCenterDisplayTitle(item),detail=statisticalCenterDetailMarkup(item);title.textContent=displayTitle;body.innerHTML=detail.markup;bindEconomicInstitutionalDetail(body,detail.chartItem);body.querySelector("[data-statistical-center-export]")?.addEventListener("click",()=>exportStatisticalCenterCsv(item));}catch(error){if(error.name==="AbortError")return;body.innerHTML=`<section class="economic-error" role="alert"><h3>تاریخچه دریافت نشد</h3><p>${economicEsc(error.message)}</p></section>`;}
}
function exportStatisticalCenterCsv(item){
  if(!item.series?.length)return;const quote=(value)=>`"${String(value??"").replaceAll('"','""')}"`,header="technical_id,period_date_jalali,period_date_gregorian,value,unit,period_change_percent,yearly_change_percent",rows=item.series.map((point)=>[item.technical_id,point.period_date_jalali,point.period_date,point.value,item.unit,point.period_change_percent,point.yearly_change_percent].map(quote).join(",")),blob=new Blob(["\uFEFF",[header,...rows].join("\r\n")],{type:"text/csv;charset=utf-8"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`amar-${item.technical_id.slice(0,80)}.csv`;link.click();URL.revokeObjectURL(url);
}
async function loadStatisticalCenter(filters=statisticalCenterFilters()){
  const root=document.getElementById("statisticalCenterApp");if(!root)return;statisticalCenterState.controller?.abort();statisticalCenterState.controller=new AbortController();const request=++statisticalCenterState.request,params=new URLSearchParams(filters);root.setAttribute("aria-busy","true");if(!statisticalCenterState.payload)root.innerHTML=`<section class="statistical-center-loading" aria-label="در حال دریافت داده‌های مرکز آمار"><span class="spinner"></span><p>در حال آماده‌سازی فهرست مرکز آمار…</p></section>`;
  try{const response=await fetch(`/api/statistical-center-indicators?${params}`,{cache:"no-store",credentials:"same-origin",signal:statisticalCenterState.controller.signal});if(response.status===401||response.status===403){location.assign(`/login?next=${encodeURIComponent(location.pathname+location.search)}`);return;}const payload=await response.json();if(!response.ok)throw new Error(payload.error||"دریافت داده‌های مرکز آمار ناموفق بود");if(request!==statisticalCenterState.request)return;statisticalCenterState.payload=payload;renderStatisticalCenter();}catch(error){if(error.name==="AbortError"||request!==statisticalCenterState.request)return;root.setAttribute("aria-busy","false");root.innerHTML=`<section class="economic-error" role="alert"><h3>داده‌های مرکز آمار دریافت نشد</h3><p>${economicEsc(error.message)}</p><button type="button" data-statistical-center-retry>تلاش دوباره</button></section>`;root.querySelector("[data-statistical-center-retry]")?.addEventListener("click",()=>loadStatisticalCenter(filters));}
}
document.addEventListener("DOMContentLoaded",()=>{if(document.body.dataset.page!=="statistical-center"||!document.getElementById("statisticalCenterApp"))return;loadStatisticalCenter();document.getElementById("statisticalCenterRefreshButton")?.addEventListener("click",()=>loadStatisticalCenter(statisticalCenterFilters()));document.getElementById("economicDetailClose")?.addEventListener("click",()=>statisticalCenterState.detailController?.abort());document.getElementById("economicDetailDialog")?.addEventListener("click",(event)=>{if(event.target===event.currentTarget)statisticalCenterState.detailController?.abort();});});
