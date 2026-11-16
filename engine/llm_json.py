"""带纠错的 JSON 阶段调用。

流程：
    chat → 提取 JSON → 校验
      ├─ 成功：返回校验后的结构
      └─ 失败：把错误与上一次输出一起回给模型，要求只修复 JSON，再试一次

网络 / 鉴权错误（LLMError）不在这里重试，直接交给上层决定是否回退 Mock。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from config import build_repair_message
from .json_utils import JSONParseError, extract_json
from .llm_client import LLMClient
from .schema import ValidationError

LOGGER = logging.getLogger(__name__)


class StageError(RuntimeError):
    """阶段调用在多次纠错后仍失败。"""

    def __init__(self, message: str, *, attempts: int, raw_text: str = "", errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.attempts = attempts
        self.raw_text = raw_text
        self.errors = list(errors or [])

    def as_dict(self) -> dict:
        return {
            "error": self.message,
            "attempts": self.attempts,
            "errors": self.errors,
            "raw_preview": self.raw_text[:600],
        }


@dataclass
class StageResult:
    value: Any
    attempts: int = 1
    latency_ms: int = 0
    usage: dict = field(default_factory=dict)
    raw_text: str = ""


def call_json_stage(
    client: LLMClient,
    messages: list[dict],
    validator: Callable[[Any], Any],
    *,
    max_attempts: int = 3,
    max_tokens: int = 5000,
) -> StageResult:
    """调用模型并把返回解析成校验后的结构，失败时自动纠错重试。"""
    history = list(messages)
    total_latency = 0
    usage: dict[str, int] = {}
    errors: list[str] = []
    last_text = ""

    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        result = client.chat(history, json_mode=True, max_tokens=max_tokens)
        total_latency += result.latency_ms
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if isinstance(result.usage.get(key), (int, float)):
                usage[key] = usage.get(key, 0) + int(result.usage[key])
        last_text = result.content

        try:
            parsed = extract_json(result.content)
        except JSONParseError as exc:
            errors.append(exc.message)
            LOGGER.warning("第 %s 次调用 JSON 解析失败：%s", attempt, exc.message)
            if attempt >= attempts:
                break
            history = list(messages) + [
                {"role": "assistant", "content": result.content},
                {"role": "user", "content": build_repair_message(exc.message, result.content)},
            ]
            continue

        try:
            value = validator(parsed)
        except ValidationError as exc:
            detail = "；".join(exc.errors) if exc.errors else exc.message
            errors.append(f"{exc.message}：{detail}")
            LOGGER.warning("第 %s 次调用结构校验失败：%s", attempt, detail)
            if attempt >= attempts:
                break
            history = list(messages) + [
                {"role": "assistant", "content": result.content},
                {
                    "role": "user",
                    "content": build_repair_message(f"{exc.message}：{detail}", result.content),
                },
            ]
            continue

        return StageResult(
            value=value,
            attempts=attempt,
            latency_ms=total_latency,
            usage=usage,
            raw_text=result.content,
        )

    raise StageError(
        "模型返回的 JSON 多次校验失败：" + (errors[-1] if errors else "未知错误"),
        attempts=attempts,
        raw_text=last_text,
        errors=errors,
    )
