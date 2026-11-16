/* 设置页：测试 LLM 连通性 */
(() => {
  "use strict";

  const button = document.getElementById("btn-test-llm");
  const result = document.getElementById("test-result");
  if (!button || !result) return;

  const show = (text, kind) => {
    result.hidden = false;
    result.className = `test-result ${kind || ""}`.trim();
    result.textContent = text;
  };

  button.addEventListener("click", async () => {
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "测试中…";
    show("正在向模型发送一条极短的消息…", "");
    try {
      const response = await fetch("/api/llm/test", { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const hint = payload.hint ? `\n${payload.hint}` : "";
        show(`连接失败：${payload.error || `HTTP ${response.status}`}${hint}`, "error");
        return;
      }
      show(
        `连接成功：${payload.model} · ${payload.latency_ms} ms · 回复「${payload.reply || "OK"}」`,
        "ok"
      );
    } catch (error) {
      show(`连接失败：${error.message || "网络错误"}`, "error");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  });
})();
