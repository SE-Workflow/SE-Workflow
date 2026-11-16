/* 首页交互：示例填充、字数统计、提交加载态（含两阶段提示） */
(() => {
  "use strict";

  const form = document.getElementById("requirement-form");
  const textarea = document.getElementById("requirement");
  const charCount = document.getElementById("char-count");
  const loading = document.getElementById("loading");
  const loadingStage = document.getElementById("loading-stage");
  const primaryButton = form ? form.querySelector('button[value="llm"]') : null;

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
      if (!textarea.value.trim()) {
        textarea.focus();
        return;
      }
      if (primaryButton) form.requestSubmit(primaryButton);
      else form.requestSubmit();
    }
  });

  let timer = null;
  const startLoading = (mode) => {
    if (!loading) return;
    loading.hidden = false;
    if (timer) clearInterval(timer);
    if (mode === "mock") {
      if (loadingStage) loadingStage.textContent = "正在使用规则引擎生成 Mock 演示方案…";
      return;
    }
    const messages = [
      "阶段一：正在调用大模型分解任务…",
      "阶段二：正在调用大模型编排依赖与 Agent…",
      "正在解析并校验 JSON，绘制工作流程图…",
    ];
    let index = 0;
    if (loadingStage) loadingStage.textContent = messages[0];
    timer = setInterval(() => {
      index = Math.min(index + 1, messages.length - 1);
      if (loadingStage) loadingStage.textContent = messages[index];
    }, 3200);
  };

  form.addEventListener("submit", (event) => {
    if (!textarea.value.trim()) {
      event.preventDefault();
      textarea.focus();
      return;
    }
    const mode = (event.submitter && event.submitter.value) || "llm";
    startLoading(mode);
  });

  window.addEventListener("pageshow", () => {
    if (timer) clearInterval(timer);
    if (loading) loading.hidden = true;
  });
})();
