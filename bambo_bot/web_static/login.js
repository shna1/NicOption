const form = document.getElementById("loginForm");
const username = document.getElementById("username");
const password = document.getElementById("password");
const button = document.getElementById("loginButton");
const banner = document.getElementById("loginError");
const usernameError = document.getElementById("usernameError");
const passwordError = document.getElementById("passwordError");

function setFieldError(field, element, message) {
  element.textContent = message;
  field.setAttribute("aria-invalid", message ? "true" : "false");
  if (message) field.setAttribute("aria-describedby", element.id);
  else field.removeAttribute("aria-describedby");
}

function showBanner(message, tone = "error") {
  banner.textContent = message;
  banner.classList.toggle("hidden", !message);
  banner.classList.toggle("is-success", Boolean(message) && tone === "success");
}

const verificationState = new URLSearchParams(window.location.search).get("verification");
if (verificationState === "success") {
  showBanner("ایمیل شما تأیید شد. اکنون وارد حساب شوید.", "success");
} else if (verificationState === "invalid") {
  showBanner("لینک تأیید معتبر نیست یا زمان آن گذشته است. وارد شوید و لینک تازه بگیرید.");
}

function destination(defaultPath = "/dashboard") {
  const requested = new URLSearchParams(window.location.search).get("next") || defaultPath;
  const url = new URL(requested, window.location.origin);
  return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : defaultPath;
}

document.getElementById("togglePassword").addEventListener("click", (event) => {
  const visible = password.type === "text";
  password.type = visible ? "password" : "text";
  event.currentTarget.textContent = visible ? "نمایش" : "پنهان";
  event.currentTarget.setAttribute("aria-pressed", String(!visible));
  event.currentTarget.setAttribute("aria-label", visible ? "نمایش رمز عبور" : "پنهان‌کردن رمز عبور");
  password.focus();
});

for (const field of [username, password]) {
  field.addEventListener("input", () => {
    showBanner("");
    if (field === username) setFieldError(username, usernameError, "");
    else setFieldError(password, passwordError, "");
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showBanner("");
  const missingUsername = !username.value.trim();
  const missingPassword = !password.value;
  setFieldError(username, usernameError, missingUsername ? "نام کاربری را وارد کنید." : "");
  setFieldError(password, passwordError, missingPassword ? "رمز عبور را وارد کنید." : "");
  if (missingUsername || missingPassword) {
    (missingUsername ? username : password).focus();
    return;
  }

  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.querySelector("span").textContent = "در حال ورود…";
  try {
    const csrfResponse = await fetch("/api/v1/auth/csrf", {credentials:"same-origin", cache:"no-store"});
    if (!csrfResponse.ok) throw new Error("دریافت مجوز امنیتی ناموفق بود. دوباره تلاش کنید.");
    const {csrf_token: csrfToken} = await csrfResponse.json();
    const response = await fetch("/api/v1/auth/login", {
      method:"POST",
      credentials:"same-origin",
      headers:{"Content-Type":"application/json", "X-CSRFToken":csrfToken},
      body:JSON.stringify({username:username.value.trim(), password:password.value}),
    });
    if (!response.ok) {
      password.value = "";
      password.focus();
      throw new Error(response.status === 400 ? "نام کاربری یا رمز عبور نادرست است." : "ورود انجام نشد. دوباره تلاش کنید.");
    }
    const identity = await response.json();
    window.location.assign(destination(identity.home_path));
  } catch (error) {
    showBanner(error.message || "ارتباط با سرور برقرار نشد. دوباره تلاش کنید.");
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.querySelector("span").textContent = "ورود به حساب";
  }
});
