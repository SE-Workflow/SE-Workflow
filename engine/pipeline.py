"""生成流水线：需求 → 阶段一任务分解 → 阶段二 Agent 编排 → 统一流程图。

真实模式：两阶段都走 LLM；任一步失败且允许 Mock 时自动降级。
Mock 模式：复用规则引擎生成同等结构，保证无 Key 也能完整演示。

降级策略：
- 阶段一失败 → 整个方案回退 Mock，结果页显示降级原因；
- 阶段二失败 → 保留 LLM 分解出的真实任务，编排回退为规则串行；
- 禁止 Mock（LLM_ALLOW_MOCK=false）时，把错误抛给页面 / API 友好展示。
"""

from __future__ import annotations

import logging
import time

from config import Settings, load_settings
from .decompose import DecomposeStage
from .llm_client import LLMClient, LLMError
from .llm_json import StageError, StageResult
from .mock import build_mock
from .orchestrate import OrchestrateStage
from .schema import build_plan, fallback_orchestration

LOGGER = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """生成失败，需要展示给用户的错误。"""

    def __init__(self, message: str, *, hint: str = "", detail: str = "", status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.detail = detail
        self.status = status

    def as_dict(self) -> dict:
        return {"error": self.message, "hint": self.hint, "detail": self.detail, "status": self.status}


def _call_trace(stage: str, result: StageResult, status: str = "ok") -> dict:
    return {
        "stage": stage,
        "status": status,
        "attempts": result.attempts,
        "latency_ms": result.latency_ms,
        "usage": result.usage,
    }


def _failure_trace(stage: str, exc: Exception) -> dict:
    attempts = getattr(exc, "attempts", 0)
    return {
        "stage": stage,
        "status": "error",
        "attempts": attempts,
        "latency_ms": 0,
        "error": getattr(exc, "message", str(exc))[:300],
    }


def _reason(exc: Exception) -> str:
    message = getattr(exc, "message", str(exc))
    hint = getattr(exc, "hint", "")
    return f"{message}{('。' + hint) if hint else ''}"


def generate(
    requirement: str,
    *,
    settings: Settings | None = None,
    force_mock: bool = False,
) -> dict:
    """生成一份可直接 JSON 序列化的统一流程图方案。"""
    raw = (requirement or "").strip()
    if not raw:
        raise PipelineError("请先输入需求内容", hint="可以点击示例快速填充。", status=400)
    if len(raw) > 20000:
        raise PipelineError("需求文本过长（超过 20000 字）", hint="请精简后再试。", status=400)

    settings = settings or load_settings()
    if not force_mock and not settings.configured and not settings.allow_mock:
        raise PipelineError(
            "未配置 LLM_API_KEY，且 LLM_ALLOW_MOCK=false",
            hint="请在 .env 中填入 Key，或把 LLM_ALLOW_MOCK 改为 true 使用 Mock 演示。",
            status=400,
        )

    started = time.perf_counter()
    warnings: list[str] = []
    llm_calls: list[dict] = []
    degraded = False
    degraded_reason = ""
    engine = "llm"

    decomposition: dict
    orchestration: dict

    use_mock = force_mock or settings.mock_active
    if use_mock:
        engine = "mock"
        decomposition, orchestration = build_mock(raw)
        if force_mock:
            warnings.append("已按请求使用 Mock 演示模式（未调用大模型）。")
        elif not settings.configured:
            warnings.append("未检测到 LLM_API_KEY：当前为 Mock 规则演示模式。在 .env 中配置 Key 后重启即可接入真实大模型。")
        else:
            warnings.append("LLM_MOCK_MODE=true：当前强制使用 Mock 演示模式。")
    else:
        client = LLMClient(settings)
        try:
            stage_one = DecomposeStage(client, settings).run(raw)
            decomposition = stage_one.value
            llm_calls.append(_call_trace("decompose", stage_one))
            LOGGER.info(
                "任务分解完成：%s 个任务，%s 次尝试，%s ms",
                len(decomposition["tasks"]),
                stage_one.attempts,
                stage_one.latency_ms,
            )
        except (LLMError, StageError) as exc:
            llm_calls.append(_failure_trace("decompose", exc))
            if not settings.allow_mock:
                raise PipelineError(
                    f"任务分解失败：{_reason(exc)}",
                    hint=getattr(exc, "hint", "") or "如暂时无法调用模型，可在 .env 中设置 LLM_ALLOW_MOCK=true 使用 Mock 演示。",
                    detail=getattr(exc, "raw_text", "")[:800],
                ) from exc
            LOGGER.warning("阶段一失败，回退 Mock：%s", _reason(exc))
            engine = "mock"
            degraded = True
            degraded_reason = f"LLM 任务分解失败，已回退 Mock：{_reason(exc)}"
            warnings.append(degraded_reason)
            decomposition, orchestration = build_mock(raw)
        else:
            try:
                stage_two = OrchestrateStage(client, settings).run(raw, decomposition["tasks"])
                orchestration = stage_two.value
                llm_calls.append(_call_trace("orchestrate", stage_two))
                LOGGER.info(
                    "Agent 编排完成：%s 条边，%s 次尝试，%s ms",
                    len(orchestration["edges"]),
                    stage_two.attempts,
                    stage_two.latency_ms,
                )
            except (LLMError, StageError) as exc:
                llm_calls.append(_failure_trace("orchestrate", exc))
                engine = "llm-fallback"
                degraded = True
                degraded_reason = f"阶段二（Agent 编排）失败，已回退规则串行编排：{_reason(exc)}"
                warnings.append(degraded_reason)
                LOGGER.warning("阶段二失败，回退规则编排：%s", _reason(exc))
                orchestration = fallback_orchestration(decomposition["tasks"])

    plan = build_plan(
        requirement=raw,
        decomposition=decomposition,
        orchestration=orchestration,
        meta={
            "engine": engine,
            "model": settings.model,
            "base_url": settings.base_url,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "llm_calls": llm_calls,
        },
        warnings=warnings,
    )
    return plan
