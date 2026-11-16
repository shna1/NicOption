const checkButton = document.getElementById("checkActivation");
const logoutButton = document.getElementById("logoutVerification");
const statusOutput = document.getElementById("verificationStatus");
const errorBanner = document.getElementById("verificationError");

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.toggle("hidden", !message);
  if (message) errorBanner.focus();
}

statusOutput.textContent = "در انتظار فعال‌سازی حساب توسط پشتیبانی.";

async function csrfToken() {
  const response = await fetch("/api/v1/auth/csrf", {credentials: "same-origin", cache: "no-store"});
  if (!response.ok) throw new Error("دریافت مجوز امنیتی ناموفق بود.");
  const payload = await response.json();
  return payload.csrf_token;
}

async function loadStatus(announce = false) {
  try {
    const response = await fetch("/api/v1/auth/verification-status", {credentials: "same-origin", cache: "no-store"});
    if (response.status === 403) {
      window.location.assign("/login");
      return;
    }
    if (!response.ok) throw new Error();
    const payload = await response.json();
    if (payload.email_verified) {
      window.location.assign(payload.home_path || "/dashboard");
      return;
    }
    if (announce) statusOutput.textContent = "حساب هنوز فعال نشده است. پس از پاسخ پشتیبانی دوباره بررسی کنید.";
  } catch (_error) {
    showError("وضعیت فعال‌سازی حساب دریافت نشد. صفحه را دوباره بارگذاری کنید.");
  }
}

checkButton.addEventListener("click", async () => {
  if (checkButton.disabled) return;
  showError("");
  checkButton.disabled = true;
  checkButton.setAttribute("aria-busy", "true");
  checkButton.querySelector("span").textContent = "در حال بررسی…";
  try {
    await loadStatus(true);
  } finally {
    checkButton.disabled = false;
    checkButton.removeAttribute("aria-busy");
    checkButton.querySelector("span").textContent = "بررسی وضعیت فعال‌سازی";
  }
});

logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  try {
    const token = await csrfToken();
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: {"X-CSRFToken": token},
    });
  } finally {
    window.location.assign("/login");
  }
});

loadStatus();
