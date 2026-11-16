(() => {
  "use strict";

  const invalidField = document.querySelector(
    ".economic-field--invalid input, .economic-field--invalid select, .economic-field--invalid textarea"
  );
  if (invalidField instanceof HTMLElement) {
    invalidField.focus({ preventScroll: true });
    invalidField.scrollIntoView({ block: "center", behavior: "auto" });
  }

  document.querySelectorAll(".economic-update form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const button = event.submitter;
      if (!(button instanceof HTMLButtonElement) || button.disabled) return;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.textContent = "در حال انجام…";
    });
  });
})();
