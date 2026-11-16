import fs from "node:fs";

const port = process.env.NICOPTION_CDP_PORT || "9227";
const base = process.env.NICOPTION_TEST_BASE || "http://127.0.0.1:8017";
const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const targetOrigin = new URL(base).origin;
const page = pages.find((item) => item.type === "page" && item.url.startsWith(targetOrigin))
  || pages.find((item) => item.type === "page");
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
const navigate = async (path, delay = 2200) => {
  await send("Page.navigate", {url:`${base}${path}`});
  await wait(delay);
};
const screenshot = async (name) => {
  const capture = await send("Page.captureScreenshot", {format:"png", captureBeyondViewport:false});
  fs.writeFileSync(`/tmp/${name}.png`, Buffer.from(capture.result.data, "base64"));
};

await send("Emulation.setDeviceMetricsOverride", {width:1440, height:1000, deviceScaleFactor:1, mobile:false});
await navigate("/trades/open");
const opened = await evaluate(`(async()=>{
  const assert=(value,message)=>{if(!value)throw new Error(message)};
  assert(location.pathname==='/trades/open','authenticated test profile did not reach open trades');
  document.documentElement.dataset.theme='light';
  await document.fonts.load('400 16px Dana');
  await document.fonts.load('600 16px Dana');
  await document.fonts.load('700 16px Dana');
  const trigger=[...document.querySelectorAll('[data-open-trade-form],#newTradeButton')].find(element=>element.getClientRects().length);
  assert(trigger,'trade modal trigger is missing');
  trigger.focus();
  trigger.click();
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const backdrop=document.getElementById('tradeEditModal');
  const surface=backdrop.querySelector('.trade-edit-modal');
  const close=document.getElementById('tradeEditDismiss');
  const bs=getComputedStyle(backdrop),ss=getComputedStyle(surface),cs=getComputedStyle(close),body=getComputedStyle(document.body);
  assert(!backdrop.classList.contains('hidden'),'trade modal did not open');
  assert(backdrop.dataset.modalActive==='true','active modal state is missing');
  assert(surface.contains(document.activeElement),'focus did not move inside the modal');
  assert(ss.backgroundColor==='rgb(245, 245, 246)','modal surface token drifted');
  assert(ss.borderRadius==='0px','modal surface is not editorial-square');
  assert(ss.boxShadow!=='none','modal elevation is missing: '+JSON.stringify({shadow:ss.boxShadow,token:getComputedStyle(document.documentElement).getPropertyValue('--shadow-lg'),insideMain:Boolean(surface.closest('#mainContent'))}));
  assert(cs.width==='44px'&&cs.height==='44px','modal close target is smaller than 44px');
  assert(body.fontFamily.includes('Dana')&&ss.fontFamily.includes('Dana'),'Dana is not the active UI/modal font');
  assert(document.fonts.check('400 16px Dana')&&document.fonts.check('600 16px Dana')&&document.fonts.check('700 16px Dana'),'one or more Dana weights failed to load');
  assert(document.documentElement.scrollWidth===innerWidth,'open modal introduces horizontal overflow');
  const bodyPanel=document.getElementById('tradeEditModalBody');
  const actionRow=bodyPanel.querySelector('.trade-form-actions');
  const actionRect=actionRow.getBoundingClientRect(),bodyRect=bodyPanel.getBoundingClientRect();
  const firstField=bodyPanel.querySelector('input:not([type="hidden"]),select');
  const firstLabel=bodyPanel.querySelector('label > span');
  assert(surface.getBoundingClientRect().width<=960,'trade modal is too wide for focused form entry');
  assert(firstField.getBoundingClientRect().height>=44,'trade modal control is shorter than 44px');
  assert(parseFloat(getComputedStyle(firstLabel).fontSize)>=14,'trade modal label is too small');
  assert(actionRect.top>=bodyRect.top&&actionRect.bottom<=bodyRect.bottom+1,'trade modal primary action is not initially reachable');
  return {path:location.pathname,bodyFont:body.fontFamily,surfaceFont:ss.fontFamily,surfaceBackground:ss.backgroundColor,surfaceRadius:ss.borderRadius,surfaceShadow:ss.boxShadow,backdrop:bs.backgroundColor,close:[cs.width,cs.height],width:surface.getBoundingClientRect().width,controlHeight:firstField.getBoundingClientRect().height,labelSize:getComputedStyle(firstLabel).fontSize,actionVisible:true,active:document.activeElement.id,fontWeights:[400,600,700].map(weight=>document.fonts.check(weight+' 16px Dana'))};
})()`);
await screenshot("nicoption-popup-editorial-desktop");

await send("Input.dispatchKeyEvent", {type:"keyDown", key:"Escape", code:"Escape", windowsVirtualKeyCode:27, nativeVirtualKeyCode:27});
await send("Input.dispatchKeyEvent", {type:"keyUp", key:"Escape", code:"Escape", windowsVirtualKeyCode:27, nativeVirtualKeyCode:27});
await wait(50);
const escapeResult = await evaluate(`(()=>{
  const trigger=[...document.querySelectorAll('[data-open-trade-form],#newTradeButton')].find(element=>element.getClientRects().length);
  const before=document.activeElement===trigger;
  const inertAncestor=trigger.closest('[inert]');
  if(!before)trigger.focus({preventScroll:true});
  return {closed:document.getElementById('tradeEditModal').classList.contains('hidden'),focusRestored:before,manualFocusWorks:document.activeElement===trigger,activeId:document.activeElement?.id||'',activeText:document.activeElement?.textContent?.trim().slice(0,40)||'',triggerConnected:trigger.isConnected,triggerDisabled:trigger.disabled,triggerTabIndex:trigger.tabIndex,inertAncestor:inertAncestor?.id||inertAncestor?.className||null,bodyUnlocked:!document.body.classList.contains('modal-open')};
})()`);
if (!escapeResult.closed || !escapeResult.focusRestored || !escapeResult.bodyUnlocked) throw new Error(`Escape close or focus restoration failed: ${JSON.stringify(escapeResult)}`);

const confirmation = await evaluate(`(async()=>{
  const pendingConfirmation=requestConfirmation({title:'حذف معامله آزمایشی',description:'این اقدام فقط برای آزمون رابط نمایش داده شده است.',actionLabel:'حذف معامله'});
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const modal=document.getElementById('confirmationModal');
  const cancel=document.getElementById('confirmationCancel');
  const surface=modal.querySelector('.confirmation-modal');
  const result={open:!modal.classList.contains('hidden'),initialFocus:document.activeElement===cancel,radius:getComputedStyle(surface).borderRadius,font:getComputedStyle(surface).fontFamily};
  closeConfirmation(false);
  await pendingConfirmation;
  return result;
})()`);
if (!confirmation.open || !confirmation.initialFocus || confirmation.radius !== "0px" || !confirmation.font.includes("Dana")) throw new Error("confirmation modal contract failed");

const secondaryPopups = await evaluate(`(async()=>{
  const assert=(value,message)=>{if(!value)throw new Error(message)};
  const trigger=[...document.querySelectorAll('[data-open-trade-form],#newTradeButton')].find(element=>element.getClientRects().length);
  trigger.focus();
  trigger.click();
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const calendarButton=document.getElementById('entryDatePickerButton');
  calendarButton.click();
  await new Promise(resolve=>requestAnimationFrame(resolve));
  const calendar=document.getElementById('entryDatePicker');
  const calendarStyle=getComputedStyle(calendar),calendarRect=calendar.getBoundingClientRect();
  const calendarResult={open:!calendar.classList.contains('hidden'),background:calendarStyle.backgroundColor,radius:calendarStyle.borderRadius,font:calendarStyle.fontFamily,insideViewport:calendarRect.left>=0&&calendarRect.right<=innerWidth&&calendarRect.top>=0&&calendarRect.bottom<=innerHeight};
  closeTradeEdit();
  const dropdownTrigger=[...document.querySelectorAll('.nav-dropdown-trigger')].find(element=>element.getClientRects().length);
  dropdownTrigger.click();
  const dropdown=document.getElementById(dropdownTrigger.getAttribute('aria-controls'));
  const dropdownStyle=getComputedStyle(dropdown);
  const dropdownResult={open:dropdownTrigger.getAttribute('aria-expanded')==='true',background:dropdownStyle.backgroundColor,radius:dropdownStyle.borderRadius,font:dropdownStyle.fontFamily};
  setNavigationDropdown(null,false);
  assert(calendarResult.open&&calendarResult.insideViewport,'Jalali popup did not open inside the viewport');
  assert(calendarResult.background==='rgb(245, 245, 246)'&&calendarResult.radius==='2px'&&calendarResult.font.includes('Dana'),'Jalali popup visual contract failed');
  assert(dropdownResult.open&&dropdownResult.background==='rgb(245, 245, 246)'&&dropdownResult.radius==='2px'&&dropdownResult.font.includes('Dana'),'navigation popup visual contract failed');
  return {calendar:calendarResult,dropdown:dropdownResult};
})()`);

await send("Emulation.setDeviceMetricsOverride", {width:390, height:844, deviceScaleFactor:1, mobile:true});
await navigate("/trades/open");
const mobile = await evaluate(`(async()=>{
  document.documentElement.dataset.theme='light';
  const trigger=[...document.querySelectorAll('[data-open-trade-form],#newTradeButton')].find(element=>element.getClientRects().length);
  trigger.click();
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const backdrop=document.getElementById('tradeEditModal');
  const surface=backdrop.querySelector('.trade-edit-modal');
  const rect=surface.getBoundingClientRect();
  const body=document.getElementById('tradeEditModalBody');
  const bodyRect=body.getBoundingClientRect();
  const actionRect=body.querySelector('.trade-form-actions').getBoundingClientRect();
  const firstField=body.querySelector('input:not([type="hidden"]),select');
  const firstLabel=body.querySelector('label > span');
  const result={x:rect.x,y:rect.y,width:rect.width,height:rect.height,viewport:[innerWidth,innerHeight],overflow:document.documentElement.scrollWidth>innerWidth,font:getComputedStyle(surface).fontFamily,bodyScrollable:body.scrollHeight>body.clientHeight,actionVisible:actionRect.top>=bodyRect.top&&actionRect.bottom<=bodyRect.bottom+1,controlHeight:firstField.getBoundingClientRect().height,labelSize:parseFloat(getComputedStyle(firstLabel).fontSize)};
  closeTradeEdit();
  return result;
})()`);
if (mobile.x < 0 || mobile.y < 0 || mobile.width > mobile.viewport[0] || mobile.height > mobile.viewport[1] || mobile.overflow || !mobile.font.includes("Dana") || !mobile.bodyScrollable || !mobile.actionVisible || mobile.controlHeight < 44 || mobile.labelSize < 14) throw new Error(`mobile modal contract failed: ${JSON.stringify(mobile)}`);

await send("Emulation.setDeviceMetricsOverride", {width:1440, height:1000, deviceScaleFactor:1, mobile:false});
await navigate("/trades/open");
const dark = await evaluate(`(async()=>{
  document.documentElement.dataset.theme='dark';
  const trigger=[...document.querySelectorAll('[data-open-trade-form],#newTradeButton')].find(element=>element.getClientRects().length);
  trigger.click();
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const surface=document.querySelector('#tradeEditModal .trade-edit-modal');
  const style=getComputedStyle(surface);
  const result={background:style.backgroundColor,color:style.color,border:style.borderColor};
  closeTradeEdit();
  return result;
})()`);
if (dark.background !== "rgb(17, 17, 19)" || dark.color !== "rgb(245, 245, 246)" || dark.border === dark.background) throw new Error(`dark modal token mapping failed: ${JSON.stringify(dark)}`);

await send("Emulation.setEmulatedMedia", {features:[{name:"prefers-reduced-motion",value:"reduce"}]});
const reducedMotion = await evaluate("getComputedStyle(document.getElementById('tradeEditDismiss')).transitionDuration");
if (reducedMotion !== "0s") throw new Error("reduced motion is not respected in modal controls");

console.log(JSON.stringify({opened,escapeResult,confirmation,secondaryPopups,mobile,dark,reducedMotion}, null, 2));
socket.close();
