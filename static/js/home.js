/* 首页交互：示例填充、字数统计、提交加载态 */
(() => {
  "use strict";

  const form = document.getElementById("requirement-form");
  const textarea = document.getElementById("requirement");
  const charCount = document.getElementById("char-count");
  const loading = document.getElementById("loading");

  if (!form || !textarea) return;

  const updateCount = () => {
    const length = textarea.value.trim().length;
    if (charCount) charCount.textContent = `${length} 字`;
  };

  textarea.addEventListener("input", updateCount);
  updateCount();

  document.querySelectorAll(".example-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      textarea.value = chip.dataset.text || "";
      textarea.dispatchEvent(new Event("input"));
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    });
  });

  textarea.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", (event) => {
    if (!textarea.value.trim()) {
      event.preventDefault();
      textarea.focus();
      return;
    }
    if (loading) loading.hidden = false;
  });
})();
