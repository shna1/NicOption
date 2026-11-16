/* Broad Statistical Centre explorer backed by a durable amar-mcp snapshot. */
const amarStatisticsState={payload:null,controller:null,topicController:null,selected:"",request:0};
const AMAR_COLLECTION_LABELS=Object.freeze({new:"آمارهای جدید",complementary:"داده‌های تکمیلی"});
function amarEsc(value){return economicEsc(value??"");}
function amarNumber(value,digits=1){if(value===null||value===undefined||value==="")return "—";return new Intl.NumberFormat("fa-IR",{maximumFractionDigits:digits}).format(Number(value));}
function amarLatest(items){return Array.isArray(items)&&items.length?items[0]:null;}
function amarMetric(label,value,unit,period){return `<article><span>${amarEsc(label)}</span><strong dir="ltr">${amarNumber(value)}</strong><small>${amarEsc(unit||"")}${period?` · ${amarEsc(period)}`:""}</small></article>`;}
function amarHighlights(direct,calendar){
  const labour=direct.labour_force||{},youth=direct.youth_unemployment||{},gdp=amarLatest(direct.gdp_quarterly?.series),population=direct.population?.country||{},unemployment=amarLatest(labour.unemployment),participation=amarLatest(labour.participation),youthPoint=amarLatest(youth.youth_unemployment);
  return `<section class="amar-highlight-grid" aria-label="آخرین نماگرهای گسترده مرکز آمار">
    ${amarMetric("نرخ بیکاری کشور",unemployment?.country,"درصد",unemployment?.period)}
    ${amarMetric("نرخ مشارکت اقتصادی",participation?.country,"درصد",participation?.period)}
    ${amarMetric("بیکاری جوانان ۱۵ تا ۲۴ سال",youthPoint?.country,"درصد",youthPoint?.period)}
    ${amarMetric("رشد تولید ناخالص داخلی",gdp?.growth_pct,"درصد",gdp?.period)}
    ${amarMetric("رشد بدون نفت",gdp?.gdp_ex_oil_pct,"درصد",gdp?.period)}
    ${amarMetric("جمعیت سرشماری ۱۳۹۵",population.population,"نفر",direct.population?.census)}
    ${amarMetric("خانوار سرشماری ۱۳۹۵",population.households,"خانوار",direct.population?.census)}
    ${amarMetric("اقلام تقویم انتشار",calendar.count,"محصول آماری",calendar.year)}
  </section>`;
}
function amarTopicCard(topic){return `<article class="amar-topic-card"><header><span>${amarEsc(topic.source_org)}</span><h4>${amarEsc(topic.label)}</h4></header><p>${amarEsc(topic.description)}</p><footer><small>${amarNumber(topic.table_count,0)} جدول</small><button type="button" data-amar-topic="${amarEsc(topic.id)}" aria-pressed="${String(amarStatisticsState.selected===topic.id)}">مشاهده جداول</button></footer></article>`;}
function amarCollections(topics){
  return ["new","complementary"].map((collection)=>{const items=topics.filter((topic)=>topic.collection===collection);return `<section class="amar-collection" aria-labelledby="amar-${collection}-title"><header><div><small>${collection==="new"?"حوزه‌های غایب از نسخه قبلی":"جزئیات بیشتر برای داده‌های موجود"}</small><h3 id="amar-${collection}-title">${AMAR_COLLECTION_LABELS[collection]}</h3></div><span>${amarNumber(items.reduce((sum,item)=>sum+item.table_count,0),0)} جدول</span></header><div class="amar-topic-grid">${items.map(amarTopicCard).join("")}</div></section>`;}).join("");
}
function amarCalendar(calendar){
  const items=calendar.items||[];if(!items.length)return "";
  return `<section class="amar-calendar"><header><div><small>تقویم ${amarEsc(calendar.year)}</small><h3>انتشارهای پیش رو</h3></div><span>${amarNumber(calendar.count,0)} قلم در سال</span></header><ol>${items.slice(0,6).map((item)=>`<li><time>${amarNumber(item.day,0)} / ${amarNumber(item.month,0)}</time><div><strong>${amarEsc(item.product)}</strong><small>${amarEsc(item.covers||item.office||"")}</small></div></li>`).join("")}</ol></section>`;
}
function amarReleases(releases){
  const labels={tourism:"گردشگری",research:"تحقیق و توسعه",environment:"محیط‌زیست",social_justice:"عدالت اجتماعی"},groups=Object.entries(releases||{}).map(([key,value])=>[key,value?.results||[]]).filter(([,items])=>items.length);if(!groups.length)return "";
  return `<section class="amar-release-catalog"><header><div><small>کاتالوگ انتشارات</small><h3>موضوعات آماری بیشتر</h3></div></header><div>${groups.map(([key,items])=>`<article><h4>${amarEsc(labels[key]||key)}</h4><ul>${items.slice(0,3).map((item)=>`<li><strong>${amarEsc(item.title)}</strong><small>${amarEsc(item.period||item.updated||item.year||"")}</small></li>`).join("")}</ul></article>`).join("")}</div></section>`;
}
function amarTable(table,index){
  const columns=Array.isArray(table.columns)?table.columns:[],rows=Array.isArray(table.rows)?table.rows:[];
  return `<details class="amar-data-table"${index===0?" open":""}><summary><span>${amarEsc(table.title||`جدول ${table.n}`)}</span><b>${amarNumber(table.total_rows||rows.length,0)} ردیف</b></summary><div class="amar-table-meta"><span>منبع جدول: ${amarEsc(table.source||"در فایل منبع ثبت نشده")}</span></div><div class="amar-table-wrap" tabindex="0" role="region" aria-label="${amarEsc(table.title||"جدول آماری")}; برای ستون‌های بیشتر افقی پیمایش کنید"><table><caption class="sr-only">${amarEsc(table.title||"جدول آماری")}</caption><thead><tr><th scope="col">دوره یا شرح</th>${columns.map((column)=>`<th scope="col">${amarEsc(column||"مقدار")}</th>`).join("")}</tr></thead><tbody>${rows.map((row)=>`<tr>${row.map((cell,cellIndex)=>cellIndex===0?`<th scope="row">${amarEsc(cell??"—")}</th>`:`<td dir="auto">${amarEsc(cell??"—")}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
}
function amarTopicDetail(topic){return `<section class="amar-topic-detail" aria-labelledby="amarTopicDetailTitle"><header><div><small>${AMAR_COLLECTION_LABELS[topic.collection]||"آمار رسمی"} · ${amarEsc(topic.source_org)}</small><h3 id="amarTopicDetailTitle" tabindex="-1">${amarEsc(topic.label)}</h3><p>${amarEsc(topic.description)}</p></div><button type="button" data-amar-topic-close>بستن جزئیات</button></header>${topic.tables.length?topic.tables.map(amarTable).join(""):`<section class="economic-empty"><h4>جدولی دریافت نشد</h4><p>در همگام‌سازی بعدی دوباره بررسی کنید.</p></section>`}</section>`;}
function amarCredit(payload){const errorCount=Object.keys(payload.errors||{}).length;return `<footer class="amar-credit"><span>داده‌های عمومیِ سازمان‌های درج‌شده در هر جدول · اتصال فقط‌خواندنی</span><a href="${amarEsc(payload.source.repository)}" target="_blank" rel="noreferrer">amar-mcp؛ ساخته سپهر رادمرد</a>${errorCount?`<small>${amarNumber(errorCount,0)} جدول یا بخش در آخرین همگام‌سازی در دسترس نبود.</small>`:""}</footer>`;}
function bindAmarTopics(){
  document.querySelectorAll("[data-amar-topic]").forEach((button)=>button.addEventListener("click",()=>loadAmarTopic(button.dataset.amarTopic,button)));
  document.querySelector("[data-amar-topic-close]")?.addEventListener("click",()=>{amarStatisticsState.selected="";document.getElementById("amarTopicDetail")?.replaceChildren();document.querySelectorAll("[data-amar-topic]").forEach((button)=>button.setAttribute("aria-pressed","false"));const params=new URLSearchParams(location.search);params.delete("a_topic");history.replaceState(history.state,"",`${location.pathname}${params.size?`?${params}`:""}${location.hash}`);});
}
function renderAmarStatistics(){
  const root=document.getElementById("amarStatisticsApp"),payload=amarStatisticsState.payload;if(!root||!payload)return;root.setAttribute("aria-busy","false");
  if(!payload.available){root.innerHTML=`<section class="cbi-mcp-empty"><h3>هنوز تصویر گسترده مرکز آمار ثبت نشده است</h3><p>مدیر سامانه باید فرمان <code dir="ltr">python manage.py sync_amar_mcp</code> را اجرا کند. فهرست قیمت و تورم پایین صفحه همچنان در دسترس است.</p></section>`;return;}
  root.innerHTML=`${payload.is_stale?'<p class="amar-stale" role="status">این تصویر بیش از هفت روز قدمت دارد؛ تاریخ هر جدول را هنگام استفاده بررسی کنید.</p>':""}${amarHighlights(payload.direct,payload.calendar)}${amarCollections(payload.topics)}${amarCalendar(payload.calendar)}${amarReleases(payload.releases)}<div id="amarTopicDetail"></div>${amarCredit(payload)}`;
  const synced=document.getElementById("amarStatisticsSyncedAt");if(synced)synced.textContent=economicDate(payload.generated_at,true);bindAmarTopics();
}
async function loadAmarTopic(topic,trigger){
  const target=document.getElementById("amarTopicDetail");if(!target)return;amarStatisticsState.topicController?.abort();amarStatisticsState.topicController=new AbortController();amarStatisticsState.selected=topic;document.querySelectorAll("[data-amar-topic]").forEach((button)=>button.setAttribute("aria-pressed",String(button.dataset.amarTopic===topic)));target.innerHTML=`<section class="statistical-center-loading"><span class="spinner"></span><p>در حال آماده‌سازی جداول…</p></section>`;
  try{const response=await fetch(`/api/amar-statistics?topic=${encodeURIComponent(topic)}`,{cache:"no-store",credentials:"same-origin",signal:amarStatisticsState.topicController.signal}),payload=await response.json();if(!response.ok)throw new Error(payload.error||"دریافت جدول‌های آماری ناموفق بود");target.innerHTML=amarTopicDetail(payload.selected_topic);bindAmarTopics();const params=new URLSearchParams(location.search);params.set("a_topic",topic);history.replaceState(history.state,"",`${location.pathname}?${params}${location.hash}`);document.getElementById("amarTopicDetailTitle")?.focus({preventScroll:true});target.scrollIntoView({block:"start",behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});}catch(error){if(error.name==="AbortError")return;target.innerHTML=`<section class="economic-error" role="alert"><h3>جداول این حوزه دریافت نشد</h3><p>${amarEsc(error.message)}</p><button type="button" data-amar-topic-retry>تلاش دوباره</button></section>`;target.querySelector("[data-amar-topic-retry]")?.addEventListener("click",()=>loadAmarTopic(topic,trigger));}
}
async function loadAmarStatistics(){
  const root=document.getElementById("amarStatisticsApp");if(!root)return;amarStatisticsState.controller?.abort();amarStatisticsState.controller=new AbortController();const request=++amarStatisticsState.request;root.setAttribute("aria-busy","true");
  try{const response=await fetch("/api/amar-statistics",{cache:"no-store",credentials:"same-origin",signal:amarStatisticsState.controller.signal}),payload=await response.json();if(response.status===401||response.status===403){location.assign(`/login?next=${encodeURIComponent(location.pathname+location.search)}`);return;}if(!response.ok)throw new Error(payload.error||"دریافت آمارهای گسترده ناموفق بود");if(request!==amarStatisticsState.request)return;amarStatisticsState.payload=payload;renderAmarStatistics();const topic=new URLSearchParams(location.search).get("a_topic");if(topic&&payload.topics.some((item)=>item.id===topic))loadAmarTopic(topic);}catch(error){if(error.name==="AbortError"||request!==amarStatisticsState.request)return;root.setAttribute("aria-busy","false");root.innerHTML=`<section class="economic-error" role="alert"><h3>آمارهای گسترده دریافت نشد</h3><p>${amarEsc(error.message)}</p><button type="button" data-amar-retry>تلاش دوباره</button></section>`;root.querySelector("[data-amar-retry]")?.addEventListener("click",loadAmarStatistics);}
}
document.addEventListener("DOMContentLoaded",()=>{if(document.body.dataset.page!=="statistical-center"||!document.getElementById("amarStatisticsApp"))return;loadAmarStatistics();});
