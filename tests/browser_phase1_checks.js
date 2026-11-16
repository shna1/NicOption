// Run in the console of an authenticated nicoption page while device emulation
// is set to one of the supported drawer widths (320, 390, 768, or 959 CSS px).
(async () => {
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const toggle = document.getElementById("navigationToggle");
  const drawer = document.getElementById("mainNavigation");

  assert(matchMedia("(max-width: 959px)").matches, "Viewport must be 959px or narrower");
  syncNavigationMode();
  setNavigationOpen(false, {restoreFocus:false});
  toggle.focus();
  setNavigationOpen(true);
  await wait(250);

  const rect = drawer.getBoundingClientRect();
  assert(rect.left >= -1, `Drawer left edge is outside viewport: ${rect.left}`);
  assert(rect.right <= innerWidth + 1, `Drawer right edge is outside viewport: ${rect.right}`);
  assert(rect.width > 0, "Drawer has no rendered width");
  assert(drawer.contains(document.activeElement), "Initial focus did not move into drawer");
  assert(getComputedStyle(document.body).overflow === "hidden", "Background scroll is not locked");
  assert(toggle.getAttribute("aria-expanded") === "true", "aria-expanded is not true while open");

  const controls = [...drawer.querySelectorAll('a:not([hidden]),button:not([hidden])')]
    .filter((item) => !item.closest('[aria-hidden="true"]'));
  controls.at(-1)?.focus();
  controls.at(-1)?.dispatchEvent(new KeyboardEvent("keydown", {
    key:"Tab", bubbles:true, cancelable:true,
  }));
  assert(document.activeElement === controls[0], "Tab did not wrap to the first drawer control");

  document.activeElement.dispatchEvent(new KeyboardEvent("keydown", {
    key:"Escape", bubbles:true, cancelable:true,
  }));
  assert(toggle.getAttribute("aria-expanded") === "false", "Escape did not close drawer");
  assert(document.activeElement === toggle, "Focus did not return to the menu trigger");
  assert(getComputedStyle(document.body).overflow !== "hidden", "Background scroll remained locked");

  return {
    viewport: innerWidth,
    direction: document.documentElement.dir,
    drawer: {left:rect.left, right:rect.right, width:rect.width},
    status: "passed",
  };
})();
