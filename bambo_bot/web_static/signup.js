const form = document.getElementById("signupForm");
const username = document.getElementById("username");
const password1 = document.getElementById("password1");
const password2 = document.getElementById("password2");
const humanAnswer = document.getElementById("humanAnswer");
const humanQuestion = document.getElementById("humanQuestion");
const refreshChallenge = document.getElementById("refreshChallenge");
const button = document.getElementById("signupButton");
const banner = document.getElementById("signupError");
const fieldErrors = {
  username: document.getElementById("usernameError"),
  password1: document.getElementById("password1Error"),
  password2: document.getElementById("password2Error"),
  humanAnswer: document.getElementById("humanAnswerError"),
};
const fieldHints = {
  username: "usernameHint",
  password1: "passwordHint",
  humanAnswer: "humanAnswerHint",
};
const fields = [username, password1, password2, humanAnswer];
let challengeReady = false;

function describedBy(field, errorElement) {
  const hint = fieldHints[field.id] || "";
  return [hint, errorElement.textContent ? errorElement.id : ""].filter(Boolean).join(" ");
}

function setFieldError(field, message) {
  const errorElement = fieldErrors[field.id];
  errorElement.textContent = message;
  field.setAttribute("aria-invalid", message ? "true" : "false");
  const description = describedBy(field, errorElement);
  if (description) field.setAttribute("aria-describedby", description);
  else field.removeAttribute("aria-describedby");
}

function showBanner(message) {
  banner.textContent = message;
  banner.classList.toggle("hidden", !message);
}

function destination(defaultPath = "/dashboard") {
  const requested = new URLSearchParams(window.location.search).get("next") || defaultPath;
  const url = new URL(requested, window.location.origin);
  return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : defaultPath;
}

function firstMessage(errors, name) {
  const messages = errors?.[name];
  return Array.isArray(messages) ? messages[0] || "" : "";
}

async function loadChallenge(focusAnswer = false, clearError = true) {
  challengeReady = false;
  refreshChallenge.disabled = true;
  humanQuestion.textContent = "در حال دریافت سؤال…";
  try {
    const response = await fetch("/api/v1/auth/signup-challenge", {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) throw new Error();
    const payload = await response.json();
    humanQuestion.textContent = payload.question;
    humanAnswer.value = "";
    if (clearError) setFieldError(humanAnswer, "");
    challengeReady = true;
    if (focusAnswer) humanAnswer.focus();
  } catch (_error) {
    humanQuestion.textContent = "سؤال بررسی انسانی دریافت نشد.";
    showBanner("دریافت بررسی انسانی ناموفق بود. «سؤال تازه» را انتخاب کنید.");
  } finally {
    refreshChallenge.disabled = false;
  }
}

document.querySelectorAll("[data-password-toggle]").forEach((toggle) => {
  toggle.addEventListener("click", () => {
    const field = document.getElementById(toggle.dataset.passwordToggle);
    const visible = field.type === "text";
    field.type = visible ? "password" : "text";
    toggle.textContent = visible ? "نمایش" : "پنهان";
    toggle.setAttribute("aria-pressed", String(!visible));
    toggle.setAttribute("aria-label", visible ? "نمایش رمز عبور" : "پنهان‌کردن رمز عبور");
    field.focus();
  });
});

refreshChallenge.addEventListener("click", () => loadChallenge(true));

for (const field of fields) {
  field.addEventListener("input", () => {
    showBanner("");
    setFieldError(field, "");
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (button.disabled) return;
  showBanner("");

  const values = {
    username: username.value.trim(),
    password1: password1.value,
    password2: password2.value,
    human_answer: humanAnswer.value.trim(),
  };
  setFieldError(username, values.username ? "" : "نام کاربری را وارد کنید.");
  setFieldError(password1, values.password1 ? "" : "رمز عبور را وارد کنید.");
  setFieldError(password2, values.password2 ? "" : "رمز عبور را دوباره وارد کنید.");
  setFieldError(humanAnswer, values.human_answer ? "" : "پاسخ بررسی انسانی را وارد کنید.");
  if (values.password1 && values.password2 && values.password1 !== values.password2) {
    setFieldError(password2, "تکرار رمز عبور با رمز عبور یکسان نیست.");
  }
  if (!challengeReady) {
    setFieldError(humanAnswer, "ابتدا سؤال بررسی انسانی را دریافت کنید.");
  }
  const firstInvalid = fields.find((field) => field.getAttribute("aria-invalid") === "true");
  if (firstInvalid) {
    firstInvalid.focus();
    return;
  }

  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.querySelector("span").textContent = "در حال ساخت حساب…";
  try {
    const csrfResponse = await fetch("/api/v1/auth/csrf", {credentials: "same-origin", cache: "no-store"});
    if (!csrfResponse.ok) throw new Error("دریافت مجوز امنیتی ناموفق بود. دوباره تلاش کنید.");
    const {csrf_token: csrfToken} = await csrfResponse.json();
    const response = await fetch("/api/v1/auth/signup", {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken},
      body: JSON.stringify(values),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setFieldError(username, firstMessage(payload.errors, "username"));
      setFieldError(password1, firstMessage(payload.errors, "password1"));
      setFieldError(password2, firstMessage(payload.errors, "password2"));
      setFieldError(humanAnswer, firstMessage(payload.errors, "human_answer"));
      if (payload.refresh_challenge) await loadChallenge(false, false);
      const serverInvalid = fields.find((field) => field.getAttribute("aria-invalid") === "true");
      if (serverInvalid) serverInvalid.focus();
      else {
        showBanner(payload.detail || "ساخت حساب انجام نشد. دوباره تلاش کنید.");
        banner.focus();
      }
      return;
    }
    window.location.assign(payload.home_path || "/verify-email");
  } catch (error) {
    showBanner(error.message || "ارتباط با سرور برقرار نشد. دوباره تلاش کنید.");
    banner.focus();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.querySelector("span").textContent = "ساخت حساب";
  }
});

loadChallenge();
