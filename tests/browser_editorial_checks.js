import fs from "node:fs";

const port = process.env.NICOPTION_CDP_PORT || "9227";
const base = process.env.NICOPTION_TEST_BASE || "http://127.0.0.1:8017";
const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const page = pages.find((item) => item.type === "page" && !item.url.startsWith("chrome://"));
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
const viewport = async (width, height) => {
  await send("Emulation.setDeviceMetricsOverride", {width, height, deviceScaleFactor:1, mobile:width < 768});
  await wait(250);
};
const navigate = async (path, delay = 3500) => {
  await send("Page.navigate", {url:`${base}${path}`});
  await wait(delay);
  await evaluate("scrollTo(0,0); true");
};
const screenshot = async (name) => {
  const capture = await send("Page.captureScreenshot", {format:"png", captureBeyondViewport:false});
  fs.writeFileSync(`/tmp/nicoption-ux-audit.YL8cLy/${name}.png`, Buffer.from(capture.result.data, "base64"));
};

await viewport(1440, 1000);
await navigate("/", 900);
const landing = await evaluate(`(()=>{
  const assert=(value,message)=>{if(!value)throw new Error(message)};
  const body=getComputedStyle(document.body);
  assert(document.title.includes('میزکار تحلیل اختیار معامله'),'landing title is stale');
  assert(getComputedStyle(document.documentElement).backgroundColor==='rgb(245, 245, 246)','landing root background does not use supplied palette');
  assert(document.querySelectorAll('.landing-ledger li').length===6,'landing research/tool ledgers are incomplete');
  assert(document.documentElement.scrollWidth===innerWidth,'landing has horizontal overflow');
  return {background:body.backgroundColor,backgroundImage:body.backgroundImage,rootBackground:getComputedStyle(document.documentElement).backgroundColor,color:body.color,font:body.fontFamily,height:document.documentElement.scrollHeight,overflow:document.documentElement.scrollWidth>innerWidth};
})()`);
await screenshot("editorial-landing-desktop");

await navigate("/trades/open");
await evaluate(`(()=>{state.userSettings.theme='light';applyUserSettings();return location.pathname})()`);
const openTrades = await evaluate(`(()=>{
  const assert=(value,message)=>{if(!value)throw new Error(message)};
  assert(location.pathname==='/trades/open','authenticated test profile did not reach open trades');
  assert(document.documentElement.dataset.editorial==='true','editorial profile is not active');
  assert(document.querySelectorAll('.open-kpi-grid>article').length===4,'open-trade KPIs are not semantic articles');
  assert(!document.querySelector('.open-kpi-grid>button'),'false KPI button affordance remains');
  const body=getComputedStyle(document.body),kpi=getComputedStyle(document.querySelector('.open-kpi-grid'));
  const tinyElements=[...document.querySelectorAll('#mainContent *')].filter(el=>el.children.length===0&&el.getClientRects().length&&parseFloat(getComputedStyle(el).fontSize)<11);
  const smallTargets=[...document.querySelectorAll('#mainContent a,#mainContent button,#mainContent input,#mainContent select,#mainContent summary')].filter(el=>el.getClientRects().length&&(el.getBoundingClientRect().height<44||el.getBoundingClientRect().width<24)).map(el=>({tag:el.tagName,className:el.className,text:el.textContent.trim().slice(0,24),w:Math.round(el.getBoundingClientRect().width),h:Math.round(el.getBoundingClientRect().height)}));
  assert(body.backgroundColor==='rgb(245, 245, 246)','open-trades background does not use the supplied palette');
  assert(tinyElements.length===0,'open-trades still contains visible text below 11px');
  assert(smallTargets.length===0,'open-trades still contains undersized interactive targets');
  assert(document.documentElement.scrollWidth===innerWidth,'open-trades has horizontal overflow');
  return {background:body.backgroundColor,color:body.color,kpiColumns:kpi.gridTemplateColumns,tinyText:tinyElements.length,tinyDetails:tinyElements.slice(0,30).map(el=>({tag:el.tagName,className:el.className,font:getComputedStyle(el).fontSize,text:el.textContent.trim().slice(0,28)})),smallTargets,overflow:document.documentElement.scrollWidth>innerWidth,height:document.documentElement.scrollHeight};
})()`);
await screenshot("editorial-open-trades-desktop");

const themeAndMotion = await evaluate(`(async()=>{
  const toggle=document.getElementById('themeToggle');
  toggle.click();
  await new Promise(resolve=>setTimeout(resolve,100));
  const darkBackground=getComputedStyle(document.body).backgroundColor;
  const darkPressed=toggle.getAttribute('aria-pressed');
  toggle.click();
  await new Promise(resolve=>setTimeout(resolve,100));
  return {darkBackground,darkPressed,lightBackground:getComputedStyle(document.body).backgroundColor};
})()`);
if(themeAndMotion.darkBackground!=='rgb(17, 17, 19)'||themeAndMotion.darkPressed!=='true'||themeAndMotion.lightBackground!=='rgb(245, 245, 246)') throw new Error('theme toggle does not preserve the editorial palette');
await send("Emulation.setEmulatedMedia", {features:[{name:"prefers-reduced-motion",value:"reduce"}]});
const reducedMotion = await evaluate(`getComputedStyle(document.querySelector('#mainContent button')).transitionDuration`);
if(reducedMotion!=='0s') throw new Error('reduced-motion does not disable control transitions');
await send("Emulation.setEmulatedMedia", {features:[]});

await navigate("/performance");
await evaluate(`document.documentElement.dataset.theme='light'`);
const performance = await evaluate(`(()=>{
  const assert=(value,message)=>{if(!value)throw new Error(message)};
  assert(document.documentElement.dataset.editorial==='true','performance editorial profile is not active');
  const panels=[...document.querySelectorAll('.closed-dashboard-grid>.closed-panel')];
  assert(document.querySelector('.closed-performance-title'),'performance report header did not render');
  assert(panels.every(panel=>getComputedStyle(panel).gridColumnStart==='1'),'performance panels are not in a linear report flow');
  return {panels:panels.length,columns:document.querySelector('.closed-dashboard-grid')?getComputedStyle(document.querySelector('.closed-dashboard-grid')).gridTemplateColumns:'empty-data',overflow:document.documentElement.scrollWidth>innerWidth,height:document.documentElement.scrollHeight};
})()`);
await screenshot("editorial-performance-desktop");

await navigate("/dashboard");
await evaluate(`document.documentElement.dataset.theme='light'`);
const dashboard = await evaluate(`(()=>({editorial:document.documentElement.dataset.editorial,kpis:document.querySelectorAll('.dashboard-kpis>a').length,columns:getComputedStyle(document.querySelector('.dashboard-grid')).gridTemplateColumns,overflow:document.documentElement.scrollWidth>innerWidth,height:document.documentElement.scrollHeight}))()`);
await screenshot("editorial-dashboard-desktop");

await viewport(720, 900);
await navigate("/dashboard");
await evaluate(`document.documentElement.dataset.theme='light'`);
const zoomSafety = await evaluate(`(()=>({overflow:document.documentElement.scrollWidth>innerWidth,navToggleVisible:getComputedStyle(document.getElementById('navigationToggle')).display!=='none'}))()`);
if(zoomSafety.overflow||!zoomSafety.navToggleVisible) throw new Error('dashboard is not safe at the intermediate/zoom viewport');

await viewport(390, 844);
await navigate("/trades/open");
await evaluate(`document.documentElement.dataset.theme='light'`);
const mobile = await evaluate(`(()=>{
  const controls=[...document.querySelectorAll('#mainContent a,#mainContent button,#mainContent input,#mainContent select,#mainContent summary')].filter(el=>el.getClientRects().length);
  return {overflow:document.documentElement.scrollWidth>innerWidth,kpiColumns:getComputedStyle(document.querySelector('.open-kpi-grid')).gridTemplateColumns,minControlHeight:Math.min(...controls.map(el=>el.getBoundingClientRect().height)),cards:document.querySelectorAll('.open-trade-mobile-card').length};
})()`);
await screenshot("editorial-open-trades-mobile");

console.log(JSON.stringify({landing,openTrades,themeAndMotion,reducedMotion,performance,dashboard,zoomSafety,mobile}, null, 2));
socket.close();
