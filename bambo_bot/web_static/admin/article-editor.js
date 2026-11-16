(function () {
  "use strict";

  function escapeHTML(value) {
    const node = document.createElement("div");
    node.textContent = value;
    return node.innerHTML;
  }

  function initialMarkup(value) {
    const rich = /<(p|div|h2|h3|blockquote|ul|ol|figure|img)\b/i.test(value);
    if (rich) return value;
    return String(value || "")
      .split(/\n{2,}/)
      .map((paragraph) => `<p>${escapeHTML(paragraph).replace(/\n/g, "<br>")}</p>`)
      .join("");
  }

  function csrfToken() {
    return document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrftoken="))
      ?.slice("csrftoken=".length) || "";
  }

  function initialize(root) {
    if (root.dataset.ready === "true") return;
    root.dataset.ready = "true";
    root.classList.add("article-editor-ready");

    const source = root.querySelector(".article-editor-source");
    const canvas = root.querySelector("[data-editor-canvas]");
    const imagePanel = root.querySelector("[data-image-panel]");
    const imageToggle = root.querySelector("[data-toggle-image]");
    const imageFile = root.querySelector("[data-image-file]");
    const imageAlt = root.querySelector("[data-image-alt]");
    const imageStatus = root.querySelector("[data-image-status]");
    const uploadButton = root.querySelector("[data-upload-image]");
    const linkDialog = root.querySelector("[data-link-dialog]");
    const linkText = root.querySelector("[data-link-text]");
    const linkUrl = root.querySelector("[data-link-url]");
    const linkStatus = root.querySelector("[data-link-status]");
    let savedRange = null;

    const initialFragment = document.createRange().createContextualFragment(initialMarkup(source.value));
    canvas.replaceChildren(initialFragment);

    function sync() {
      source.value = canvas.innerHTML.trim();
    }

    function rememberSelection() {
      const selection = window.getSelection();
      if (selection && selection.rangeCount && canvas.contains(selection.anchorNode)) {
        savedRange = selection.getRangeAt(0).cloneRange();
      }
    }

    function restoreSelection() {
      canvas.focus();
      if (!savedRange) return;
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(savedRange);
    }

    function insertHTML(markup) {
      restoreSelection();
      document.execCommand("insertHTML", false, markup);
      sync();
      rememberSelection();
    }

    canvas.addEventListener("input", sync);
    canvas.addEventListener("keyup", rememberSelection);
    canvas.addEventListener("mouseup", rememberSelection);
    canvas.addEventListener("blur", rememberSelection);
    canvas.addEventListener("paste", () => window.setTimeout(sync));
    root.closest("form")?.addEventListener("submit", sync);

    root.querySelectorAll("[data-command]").forEach((button) => {
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => {
        restoreSelection();
        document.execCommand(button.dataset.command, false);
        sync();
        canvas.focus();
      });
    });

    root.querySelectorAll("[data-block]").forEach((button) => {
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => {
        restoreSelection();
        document.execCommand("formatBlock", false, button.dataset.block);
        sync();
        canvas.focus();
      });
    });

    imageToggle.addEventListener("click", () => {
      rememberSelection();
      imagePanel.hidden = !imagePanel.hidden;
      imageToggle.setAttribute("aria-expanded", String(!imagePanel.hidden));
      if (!imagePanel.hidden) imageFile.focus();
    });

    uploadButton.addEventListener("click", async () => {
      const file = imageFile.files?.[0];
      const alt = imageAlt.value.trim();
      imageStatus.classList.remove("is-error");
      if (!file) {
        imageStatus.textContent = "ابتدا فایل تصویر را انتخاب کنید.";
        imageStatus.classList.add("is-error");
        imageFile.focus();
        return;
      }
      if (!alt) {
        imageStatus.textContent = "متن جایگزین تصویر را بنویسید.";
        imageStatus.classList.add("is-error");
        imageAlt.focus();
        return;
      }

      const data = new FormData();
      data.append("image", file);
      data.append("alt_text", alt);
      uploadButton.disabled = true;
      uploadButton.setAttribute("aria-busy", "true");
      imageStatus.textContent = "در حال بارگذاری تصویر…";
      try {
        const response = await fetch(source.dataset.uploadUrl, {
          method: "POST",
          headers: {"X-CSRFToken": csrfToken()},
          body: data,
          credentials: "same-origin",
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "بارگذاری تصویر انجام نشد.");
        const safeUrl = escapeHTML(payload.url);
        const safeAlt = escapeHTML(payload.alt);
        insertHTML(`<figure><img src="${safeUrl}" alt="${safeAlt}"><figcaption>${safeAlt}</figcaption></figure><p><br></p>`);
        imageStatus.textContent = "تصویر در متن مقاله قرار گرفت.";
        imageFile.value = "";
        imageAlt.value = "";
        imagePanel.hidden = true;
        imageToggle.setAttribute("aria-expanded", "false");
      } catch (error) {
        imageStatus.textContent = error.message || "بارگذاری تصویر انجام نشد.";
        imageStatus.classList.add("is-error");
      } finally {
        uploadButton.disabled = false;
        uploadButton.removeAttribute("aria-busy");
      }
    });

    root.querySelector("[data-open-link]").addEventListener("click", () => {
      rememberSelection();
      const selection = window.getSelection()?.toString().trim() || "";
      linkText.value = selection;
      linkUrl.value = "";
      linkStatus.textContent = "";
      linkDialog.showModal();
      (selection ? linkUrl : linkText).focus();
    });
    root.querySelector("[data-close-link]").addEventListener("click", () => linkDialog.close());
    root.querySelector("[data-insert-link]").addEventListener("click", () => {
      const text = linkText.value.trim();
      const url = linkUrl.value.trim();
      if (!text || !/^https?:\/\//i.test(url)) {
        linkStatus.textContent = "متن و نشانی کامل پیوند (با http یا https) را وارد کنید.";
        linkStatus.classList.add("is-error");
        return;
      }
      insertHTML(`<a href="${escapeHTML(url)}">${escapeHTML(text)}</a>`);
      linkDialog.close();
    });
  }

  function boot() {
    document.querySelectorAll("[data-article-editor]").forEach(initialize);
  }

  document.addEventListener("DOMContentLoaded", boot);
  document.addEventListener("formset:added", boot);
})();
