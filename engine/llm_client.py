"""LLM 客户端：兼容 OpenAI 风格 `/chat/completions` 接口。

适配范围：OpenAI / DeepSeek / 通义千问（DashScope 兼容模式） / Moonshot /
智谱 / 本地 vLLM、Ollama 的 OpenAI 兼容端点等。

设计要点：
- 只依赖 `requests`，超时、重试、错误信息都在这一层收敛；
- HTTP 错误转换成对用户友好的中文提示，绝不把 Authorization 头写进日志；
- 兼容 `content` 为字符串或分段数组的返回格式。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from config import Settings

LOGGER = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """调用大模型失败（网络 / HTTP / 返回格式）。"""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        hint: str = "",
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.hint = hint
        self.detail = detail

    def as_dict(self) -> dict:
        return {
            "error": self.message,
            "hint": self.hint,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class ChatResult:
    """一次对话调用的结果。"""

    content: str
    model: str
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0


def _join_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")


class LLMClient:
    """最小可用的 OpenAI 兼容对话客户端。"""

    def __init__(self, settings: Settings, *, session: requests.Session | None = None) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.endpoint = self._endpoint(settings.base_url)

    @staticmethod
    def _endpoint(base_url: str) -> str:
        base = (base_url or "").strip().rstrip("/")
        if not base:
            return ""
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "se-workflow-studio/2.0",
            "Authorization": f"Bearer {self.settings.api_key}",
        }

    # ------------------------------------------------------------------ 主入口
    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> ChatResult:
        if not self.settings.configured:
            raise LLMError(
                "尚未配置 LLM_API_KEY",
                hint="复制 .env.example 为 .env，填入自己的 API Key 后重启服务。",
            )
        if not messages:
            raise LLMError("消息列表为空", hint="请检查 Prompt 构造逻辑。")

        use_json_mode = self.settings.json_mode if json_mode is None else bool(json_mode)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        response = self._post(payload, allow_json_mode_fallback=use_json_mode)
        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError(
                "模型接口返回的不是 JSON",
                hint="请确认 LLM_BASE_URL 指向 OpenAI 兼容接口（通常以 /v1 结尾）。",
                detail=response.text[:400],
            ) from exc

        choices = data.get("choices") or []
        if not choices:
            error = data.get("error") if isinstance(data, dict) else None
            message = ""
            if isinstance(error, dict):
                message = str(error.get("message", ""))[:400]
            raise LLMError(
                "模型接口未返回 choices",
                hint="请检查模型名 LLM_MODEL 是否可用。",
                detail=message or str(data)[:400],
            )

        choice = choices[0] or {}
        content = _join_content((choice.get("message") or {}).get("content"))
        finish_reason = str(choice.get("finish_reason") or "")
        if finish_reason == "length":
            raise LLMError(
                "模型输出被长度限制截断",
                hint="请减少任务数量，或在 .env 中调大 LLM_TIMEOUT 并适当调整 max_tokens。",
            )
        if not content.strip():
            raise LLMError(
                "模型返回内容为空",
                hint="请检查模型是否支持 JSON 输出，或稍后重试。",
            )

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return ChatResult(
            content=content.strip(),
            model=str(data.get("model") or self.settings.model),
            usage=usage,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------ HTTP
    def _post(self, payload: dict, *, allow_json_mode_fallback: bool) -> requests.Response:
        if not self.endpoint:
            raise LLMError(
                "LLM_BASE_URL 为空",
                hint="请在 .env 中填写兼容 OpenAI 的 base_url，例如 https://api.deepseek.com/v1。",
            )

        last_error: LLMError | None = None
        for attempt in range(2):
            try:
                response = self.session.post(
                    self.endpoint,
                    headers=self._headers(),
                    json=payload,
                    timeout=(min(15.0, self.settings.timeout), self.settings.timeout),
                )
            except requests.exceptions.Timeout as exc:
                raise LLMError(
                    "调用模型超时",
                    hint="请检查网络或在 .env 中调大 LLM_TIMEOUT（秒）。",
                    detail=str(exc)[:300],
                ) from exc
            except requests.exceptions.SSLError as exc:
                raise LLMError(
                    "访问模型接口时 SSL 校验失败",
                    hint="请确认 LLM_BASE_URL 正确，或检查代理 / 证书配置。",
                    detail=str(exc)[:300],
                ) from exc
            except requests.exceptions.ConnectionError as exc:
                raise LLMError(
                    "无法连接到模型接口",
                    hint="请检查 LLM_BASE_URL、网络连通性或代理设置。",
                    detail=str(exc)[:300],
                ) from exc
            except requests.exceptions.RequestException as exc:
                raise LLMError(
                    "调用模型接口失败",
                    hint="请检查网络与 base_url 配置。",
                    detail=str(exc)[:300],
                ) from exc

            body = response.text or ""
            if response.status_code < 400:
                return response

            # 某些 OpenAI 兼容服务不支持 response_format，自动去掉后重试一次
            if (
                allow_json_mode_fallback
                and response.status_code in {400, 422}
                and "response_format" in body.lower()
            ):
                LOGGER.info("模型不支持 response_format，改为提示词约束 JSON 输出")
                payload = {key: value for key, value in payload.items() if key != "response_format"}
                allow_json_mode_fallback = False
                continue

            if response.status_code in _RETRYABLE_STATUS and attempt == 0:
                time.sleep(1.0)
                continue

            last_error = self._http_error(response.status_code, body)
            raise last_error

        raise last_error or LLMError("调用模型接口失败")

    @staticmethod
    def _http_error(status: int, body: str) -> LLMError:
        detail = body.strip()[:500]
        if status == 401:
            return LLMError(
                "API Key 无效或已过期（401）",
                status=status,
                hint="请检查 .env 中的 LLM_API_KEY 是否正确、是否有多余空格。",
                detail=detail,
            )
        if status == 403:
            return LLMError(
                "当前 Key 无权访问该模型（403）",
                status=status,
                hint="请检查账号权限或更换 LLM_MODEL。",
                detail=detail,
            )
        if status == 404:
            return LLMError(
                "接口或模型不存在（404）",
                status=status,
                hint="请检查 LLM_BASE_URL 是否为兼容接口，以及 LLM_MODEL 是否可用。",
                detail=detail,
            )
        if status == 429:
            return LLMError(
                "请求过于频繁或额度不足（429）",
                status=status,
                hint="请稍后重试，或检查账号额度 / 速率限制。",
                detail=detail,
            )
        if status >= 500:
            return LLMError(
                f"模型服务暂时不可用（{status}）",
                status=status,
                hint="请稍后重试；如持续失败，可先用 Mock 演示模式。",
                detail=detail,
            )
        return LLMError(
            f"模型接口返回错误（{status}）",
            status=status,
            hint="请检查 LLM_BASE_URL、模型名与请求参数。",
            detail=detail,
        )

    # ------------------------------------------------------------------ 连通性
    def test_connection(self) -> dict:
        """设置页的“测试连接”：发一条极短的对话。"""
        result = self.chat(
            [
                {"role": "system", "content": "你是一个 API 连通性测试助手。"},
                {"role": "user", "content": "只回复两个字：正常"},
            ],
            json_mode=False,
            temperature=0.0,
            max_tokens=16,
        )
        return {
            "ok": True,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "reply": result.content[:40],
            "usage": result.usage,
        }
