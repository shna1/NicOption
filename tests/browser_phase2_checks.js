// End-to-end verification for Phase 2/3 against an authenticated local Chrome
// exposed through the DevTools protocol (defaults to port 9227).
const port = process.env.NICOPTION_CDP_PORT || "9227";
const base = process.env.NICOPTION_TEST_BASE || "http://127.0.0.1:8017";
const performanceBudgets = Object.freeze({
  apiWarningBytes: 32 * 1024 * 1024,
  apiReleaseCapBytes: 40 * 1024 * 1024,
  opportunityNodes: 1500,
  medianRenderMs: 50,
  maximumRenderMs: 100,
});
const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = pages.find((item) => item.type === "page" && item.url.startsWith(base));
if (!page) throw new Error(`No authenticated page found for ${base}`);

const socket = new WebSocket(page.webSocketDebuggerUrl);
let sequence = 0;
const pending = new Map();
socket.onmessage = ({data}) => {
  const message = JSON.parse(data);
  if (message.id && pending.has(message.id)) {
    pending.get(message.id)(message);
    pending.delete(message.id);
  }
};
await new Promise((resolve) => { socket.onopen = resolve; });
const send = (method, params = {}) => new Promise((resolve) => {
  const id = ++sequence;
  pending.set(id, resolve);
  socket.send(JSON.stringify({id, method, params}));
});
const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const evaluate = async (expression) => {
  const response = await send("Runtime.evaluate", {expression, awaitPromise:true, returnByValue:true});
  if (response.result.exceptionDetails) throw new Error(response.result.exceptionDetails.text);
  return response.result.result.value;
};
const viewport = async (width, height) => {
  await send("Emulation.setDeviceMetricsOverride", {width, height, deviceScaleFactor:1, mobile:width < 768});
  await wait(350);
};
const navigate = async (path) => {
  await send("Page.navigate", {url:`${base}${path}`});
  await wait(3500);
};

await viewport(1440, 1000);
await navigate("/opportunities");
const desktop = await evaluate(`(async()=>{
  const assert=(value,message)=>{if(!value)throw new Error(message)};
  const wait=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));
  assert(document.querySelectorAll('.opportunities-table-wrap tbody tr').length===25,'desktop page is not 25 rows');
  assert(!document.querySelector('.opportunities-mobile-list'),'inactive mobile representation remained in DOM');
  assert(document.querySelectorAll('.opportunity-tabs button:disabled').length===3,'unsupported opportunity tabs are not disabled');
  assert(document.querySelector('.opportunities-page-controls'),'pagination controls are missing');
  const timings=[];
  for(let index=0;index<5;index++){const start=performance.now();renderOpportunitiesDashboard();timings.push(performance.now()-start)}
  const firstSymbol=document.querySelector('.opportunities-table-wrap tbody tr .opportunity-symbol small')?.textContent;
  document.querySelector('[data-opportunity-page="2"]').click();await wait(50);
  assert(new URLSearchParams(location.search).get('page')==='2','next page did not update URL state');
  assert(document.querySelector('.opportunities-page-controls [aria-current="page"]')?.textContent.includes('۲'),'next page did not render');
  assert(document.querySelector('.opportunities-table-wrap tbody tr .opportunity-symbol small')?.textContent!==firstSymbol,'next page did not change result set');
  history.back();await wait(100);
  assert(!new URLSearchParams(location.search).has('page'),'browser Back did not restore page 1');
  const trigger=document.querySelector('[data-opportunity-detail]');
  trigger.focus();trigger.click();await wait(350);
  assert(modalManager.active()?.id==='analysisModal','analysis dialog did not become active');
  assert(document.activeElement && modalManager.active().contains(document.activeElement),'focus did not enter analysis dialog');
  assert(document.querySelectorAll('[inert]').length>0 && !document.getElementById('analysisModal').inert,'background was not made inert');
  const controls=[...modalManager.active().querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')].filter(el=>el.getClientRects().length);
  controls.at(-1).focus();controls.at(-1).dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));
  assert(document.activeElement===controls[0],'Tab did not wrap in dialog');
  requestConfirmation({title:'آزمون تو‌در‌تو',description:'آزمون مدیر مودال'});await wait(100);
  assert(modalManager.size()===2 && modalManager.active()?.id==='confirmationModal','nested confirmation did not stack');
  assert(document.getElementById('analysisModal').inert,'underlying dialog was not made inert');
  document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));await wait(50);
  assert(modalManager.active()?.id==='analysisModal','Escape did not close only the top dialog');
  document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));await wait(50);
  assert(modalManager.size()===0,'analysis dialog remained open');
  assert(document.activeElement===trigger,'focus did not return to dialog trigger');
  const tinyElements=[...document.querySelectorAll('.opportunities-dashboard *')].filter(el=>el.children.length===0&&el.getClientRects().length&&parseFloat(getComputedStyle(el).fontSize)<12);
  const criticalElements=[...document.querySelectorAll('.opportunities-table-panel th,.opportunities-table-panel td,.opportunity-status,.liquidity,.pricing,.opportunity-symbol small')].filter(el=>el.getClientRects().length&&parseFloat(getComputedStyle(el).fontSize)<13);
  const helperElements=[...document.querySelectorAll('.opportunity-transparency p,.opportunity-transparency li,.opportunities-kpis small')].filter(el=>el.getClientRects().length&&parseFloat(getComputedStyle(el).fontSize)<14);
  assert(tinyElements.length===0,'visible opportunity text remains below 12px');
  assert(criticalElements.length===0,'decision-critical opportunity data remains below 13px');
  assert(helperElements.length===0,'normal opportunity helper text remains below 14px');
  const api=performance.getEntriesByType('resource').find(entry=>entry.name.endsWith('/api/data'));
  return {rows:document.querySelectorAll('.opportunities-table-wrap tbody tr').length,nodes:document.querySelector('.opportunities-dashboard').querySelectorAll('*').length,height:document.documentElement.scrollHeight,tinyText:tinyElements.length,criticalBelowTarget:criticalElements.length,helperBelowTarget:helperElements.length,renderMs:timings,apiEncodedBytes:api?.encodedBodySize||0,apiDecodedBytes:api?.decodedBodySize||0,chartThemeRequests:performance.getEntriesByType('resource').filter(entry=>entry.name.includes('chart-theme')).length,overflow:document.documentElement.scrollWidth>innerWidth};
})()`);
const measuredApiBytes = Math.max(desktop.apiEncodedBytes, desktop.apiDecodedBytes);
const sortedRenderMs = [...desktop.renderMs].sort((left,right)=>left-right);
const medianRenderMs = sortedRenderMs[Math.floor(sortedRenderMs.length/2)];
const maximumRenderMs = Math.max(...desktop.renderMs);
if (!measuredApiBytes) throw new Error('/api/data transfer size was not measurable');
if (measuredApiBytes > performanceBudgets.apiReleaseCapBytes) throw new Error('/api/data exceeded the 40 MiB release cap');
if (desktop.nodes > performanceBudgets.opportunityNodes) throw new Error('desktop opportunity DOM exceeded 1500 nodes');
if (medianRenderMs > performanceBudgets.medianRenderMs) throw new Error('median opportunity render exceeded 50ms');
if (maximumRenderMs > performanceBudgets.maximumRenderMs) throw new Error('opportunity render exceeded the 100ms main-thread ceiling');
if (desktop.chartThemeRequests) throw new Error('obsolete chart-theme.js was requested');
desktop.performanceBudget = {
  apiWarningExceeded: measuredApiBytes > performanceBudgets.apiWarningBytes,
  apiReleaseCapBytes: performanceBudgets.apiReleaseCapBytes,
  medianRenderMs,
  maximumRenderMs,
};

await viewport(390, 844);
const mobile = await evaluate(`(()=>({
  rows:document.querySelectorAll('.opportunities-table-wrap tbody tr').length,
  cards:document.querySelectorAll('.opportunity-mobile-card').length,
  tablePresent:Boolean(document.querySelector('.opportunities-table-wrap')),
  nodes:document.querySelector('.opportunities-dashboard').querySelectorAll('*').length,
  tinyText:[...document.querySelectorAll('.opportunities-dashboard *')].filter(el=>el.children.length===0&&el.getClientRects().length&&parseFloat(getComputedStyle(el).fontSize)<12).length,
  criticalBelowTarget:[...document.querySelectorAll('.opportunity-mobile-card dd,.opportunity-mobile-card>header small,.opportunity-status,.liquidity,.pricing')].filter(el=>el.getClientRects().length&&parseFloat(getComputedStyle(el).fontSize)<13).length,
  overflow:document.documentElement.scrollWidth>innerWidth,
  pagerMinHeight:Math.min(...[...document.querySelectorAll('.opportunities-page-controls button,.opportunities-page-controls select')].map(el=>el.getBoundingClientRect().height))
}))()`);
if (mobile.tinyText) throw new Error('mobile opportunity text remains below 12px');
if (mobile.criticalBelowTarget) throw new Error('mobile decision-critical data remains below 13px');
if (mobile.pagerMinHeight < 44) throw new Error('mobile pagination target is below 44px');
if (mobile.overflow) throw new Error('mobile opportunities page overflows horizontally');
if (mobile.nodes > performanceBudgets.opportunityNodes) throw new Error('mobile opportunity DOM exceeded 1500 nodes');

await viewport(720, 1000);
const zoomEquivalent = await evaluate(`(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,overflow:document.documentElement.scrollWidth>innerWidth}))()`);
if (zoomEquivalent.overflow) throw new Error('200% zoom equivalent produces horizontal page overflow');

console.log(JSON.stringify({desktop,mobile,zoomEquivalent}, null, 2));
socket.close();
