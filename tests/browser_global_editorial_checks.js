import fs from "node:fs";

const port = process.env.NICOPTION_CDP_PORT || "9227";
const base = process.env.NICOPTION_TEST_BASE || "http://127.0.0.1:8017";
const routes = [
  "/dashboard", "/opportunities", "/market", "/tehran-options",
  "/commodity-exchange", "/trades/open", "/trades/closed", "/performance",
  "/calculator", "/methodology", "/order-flow", "/forecast", "/settings",
];
const metricSelectors = [
  ".metric-grid", ".calculator-metrics", ".closed-summary-grid",
  ".portfolio-asset-ledger-metrics", ".portfolio-asset-allocation-metrics",
  ".portfolio-summary-metrics", ".account-growth-overview", ".account-growth-kpis",
  ".profit-recognition-kpis", ".risk-free-metrics", ".closed-covered-kpis",
  ".top-card-grid", ".market-data-kpis", ".analysis-metrics", ".covered-kpi-grid",
  ".long-exit-grid", ".forecast-metrics", ".order-flow-kpis", ".closed-primary-kpis",
  ".closed-detail-metrics", ".closed-advanced-grid", ".closed-distribution-summary",
  ".dashboard-kpis", ".dashboard-performance-summary", ".open-kpi-grid",
  ".open-expansion-grid", ".opportunities-kpis", ".underlying-detail-summary dl",
].join(",");

const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = pages.find((item) => item.type === "page");
if (!page) throw new Error("No Chrome page is available");
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
  if (response.result.exceptionDetails) throw new Error(response.result.exceptionDetails.exception?.description || response.result.exceptionDetails.text);
  return response.result.result.value;
};
const navigate = async (path, delay = 1900) => {
  await send("Page.navigate", {url:`${base}${path}`});
  await wait(delay);
  await evaluate("scrollTo(0,0); document.documentElement.dataset.theme='light'; true");
  await wait(80);
};

await send("Emulation.setDeviceMetricsOverride", {width:1440, height:1000, deviceScaleFactor:1, mobile:false});
const results = [];
for (const route of routes) {
  await navigate(route);
  const result = await evaluate(`(()=>{
    const assert=(value,message)=>{if(!value)throw new Error(message)};
    assert(location.pathname!=='/login','route redirected to login');
    assert(document.documentElement.dataset.editorial==='true','global editorial profile is missing');
    assert(getComputedStyle(document.body).backgroundColor==='rgb(245, 245, 246)','background token drifted');
    assert(document.documentElement.scrollWidth===innerWidth,'horizontal page overflow');
    const grids=[...document.querySelectorAll(${JSON.stringify(metricSelectors)})].filter(grid=>grid.getClientRects().length);
    const orphans=grids.flatMap(grid=>{
      const children=[...grid.children].filter(child=>child.getClientRects().length);
      if(children.length<2)return [];
      const rows=new Map();
      for(const child of children){const top=Math.round(child.getBoundingClientRect().top);rows.set(top,(rows.get(top)||0)+1)}
      return [...rows.values()].some(count=>count===1)?[{className:grid.className,count:children.length,rows:[...rows.values()]}]:[];
    });
    const tiny=[...document.querySelectorAll('#mainContent *')].filter(el=>el.children.length===0&&el.textContent.trim()&&el.getClientRects().length&&parseFloat(getComputedStyle(el).fontSize)<11);
    const positive=[...document.querySelectorAll('.profit-up,.positive-value,.profit-positive')].find(el=>el.getClientRects().length);
    const negative=[...document.querySelectorAll('.profit-down,.negative-value,.profit-negative')].find(el=>el.getClientRects().length);
    assert(orphans.length===0,'orphan KPI row: '+JSON.stringify(orphans));
    assert(tiny.length===0,'visible text below 11px: '+JSON.stringify(tiny.slice(0,5).map(el=>({text:el.textContent.trim().slice(0,30),font:getComputedStyle(el).fontSize,className:el.className}))));
    if(positive)assert(getComputedStyle(positive).color==='rgb(15, 107, 62)','positive P&L color drifted');
    if(negative)assert(getComputedStyle(negative).color==='rgb(180, 35, 24)','negative P&L color drifted');
    return {route:location.pathname,grids:grids.length,orphans,tiny:tiny.length,tinyExamples:tiny.slice(0,5).map(el=>({text:el.textContent.trim().slice(0,30),font:getComputedStyle(el).fontSize,className:el.className})),positive:positive?getComputedStyle(positive).color:null,negative:negative?getComputedStyle(negative).color:null,height:document.documentElement.scrollHeight};
  })()`);
  results.push(result);
}

await send("Emulation.setDeviceMetricsOverride", {width:390, height:844, deviceScaleFactor:1, mobile:true});
await navigate("/opportunities");
const mobile = await evaluate(`(()=>({overflow:document.documentElement.scrollWidth>innerWidth,columns:[...document.querySelectorAll(${JSON.stringify(metricSelectors)})].filter(el=>el.getClientRects().length).map(el=>getComputedStyle(el).gridTemplateColumns)}))()`);
if (mobile.overflow || mobile.columns.some((columns) => columns.trim().split(/\s+/).length !== 1)) throw new Error("mobile metric grids are not single-column or page overflows");

await send("Emulation.setEmulatedMedia", {features:[{name:"prefers-reduced-motion",value:"reduce"}]});
const reducedMotion = await evaluate("getComputedStyle(document.querySelector('#mainContent button')).transitionDuration");
if (reducedMotion !== "0s") throw new Error("reduced motion is not respected");
await send("Emulation.setEmulatedMedia", {features:[]});

await send("Emulation.setDeviceMetricsOverride", {width:1440, height:1000, deviceScaleFactor:1, mobile:false});
await navigate("/login", 700);
const login = await evaluate(`(()=>{const shell=document.querySelector('.login-shell');return {path:location.pathname,editorial:document.documentElement.dataset.editorial,background:getComputedStyle(document.body).backgroundColor,radius:shell?getComputedStyle(shell).borderRadius:null,overflow:document.documentElement.scrollWidth>innerWidth}})()`);
if (login.path === "/login" && (login.editorial !== "true" || login.background !== "rgb(245, 245, 246)" || login.radius !== "0px" || login.overflow)) throw new Error("login does not follow the global editorial profile");

fs.writeFileSync("/tmp/nicoption-ux-audit.YL8cLy/global-editorial-results.json", JSON.stringify({results,mobile,reducedMotion,login}, null, 2));
console.log(JSON.stringify({results,mobile,reducedMotion,login}, null, 2));
socket.close();
