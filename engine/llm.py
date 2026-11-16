"""大模型接入层（预留扩展点）。

默认不调用任何模型：`RuleOnlyAdapter` 直接返回 None，任务分解完全由
`config/` 中的模板与关键词映射驱动，因此离线、无密钥也能跑通全流程。

Key 与连接参数统一在 `config/llm_key.py` 维护，支持环境变量或本地私有文件
`config/llm_key_local.py`（模板见 `config/llm_key_local.example.py`）。

适配器只负责“补充需求模块”，任何网络/格式错误都会静默回退到规则结果，
不会阻塞网页流程。你也可以实现自己的 `LLMAdapter` 子类替换 `get_adapter()`。
"""

from __future__ import annotations

import json
import urllib.request

from config.llm_key import get_llm_settings


class LLMAdapter:
    """扩展点：返回额外的补充需求模块，或 None 表示沿用规则结果。"""

    name = "rule-only"
    enabled = False

    def describe(self) -> dict:
        return {"name": self.name, "enabled": self.enabled}

    def enhance(self, requirement: str, profile: dict) -> dict | None:  # noqa: ARG002
        return None


class RuleOnlyAdapter(LLMAdapter):
    """默认实现：纯规则引擎，不发起任何外部请求。"""


class OpenAICompatibleAdapter(LLMAdapter):
    """OpenAI 兼容接口的轻量适配器（只用于补充模块，失败即回退）。"""

    name = "openai-compatible"
    enabled = True

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def enhance(self, requirement: str, profile: dict) -> dict | None:
        prompt = (
            "你是资深产品经理。请把下面的需求补充成 1-3 个任务模块。"
            "只输出 JSON：{\"custom_modules\":[{\"name\":\"模块名\",\"capabilities\":[\"能力点1\",\"能力点2\"]}]}。\n"
            f"需求：{requirement}\n"
            f"已识别产品域：{profile['domain']['label']}；规模：{profile['scale']['label']}"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(content)
        except Exception:  # noqa: BLE001 - 外部依赖失败时回退到规则引擎
            return None

        modules = []
        for item in parsed.get("custom_modules", [])[:3]:
            name = str(item.get("name", "")).strip()[:20]
            capabilities = [
                str(capability).strip()[:26]
                for capability in item.get("capabilities", [])
                if str(capability).strip()
            ][:3]
            if name and capabilities:
                modules.append({"name": name, "summary": "由 LLM 补充的需求模块", "capabilities": capabilities})
        return {"custom_modules": modules} if modules else None


def get_adapter() -> LLMAdapter:
    """按 config/llm_key.py 的配置选择适配器；默认规则引擎。"""
    settings = get_llm_settings()
    if settings["configured"]:
        return OpenAICompatibleAdapter(
            settings["base_url"],
            settings["api_key"],
            settings["model"],
            timeout=settings["timeout"],
        )
    return RuleOnlyAdapter()
