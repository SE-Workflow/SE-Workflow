"""分析流水线：输入解析 → 任务分解 → Agent 编排 → 视图渲染。"""

from __future__ import annotations

from config import CUSTOM_MODULE_LIMIT
from .breaker import TaskBreaker
from .llm import LLMAdapter, get_adapter
from .orchestrator import Orchestrator
from .parser import RequirementParser, guess_agent
from .render import PlanRenderer


def analyze(requirement: str, adapter: LLMAdapter | None = None) -> dict:
    """跑完整条 SE Workflow（任务分解 + Agent 编排）并返回可直接序列化的方案。"""
    adapter = adapter or get_adapter()
    profile = RequirementParser().parse(requirement)

    # 预留的大模型增强：只补充需求模块，失败自动回退
    extra = adapter.enhance(requirement, profile)
    if extra and extra.get("custom_modules"):
        merged = profile.get("custom_modules", [])
        existing = {module["name"] for module in merged}
        for module in extra["custom_modules"]:
            if len(merged) >= CUSTOM_MODULE_LIMIT:
                break
            name = str(module.get("name", "")).strip()[:20]
            capabilities = [str(item).strip()[:26] for item in module.get("capabilities", []) if str(item).strip()]
            if not name or not capabilities or name in existing:
                continue
            merged.append(
                {
                    "name": name,
                    "summary": str(module.get("summary", "由 LLM 补充的需求模块"))[:80],
                    "capabilities": capabilities[:3],
                    "agent": module.get("agent") or guess_agent(" ".join(capabilities)),
                }
            )
            existing.add(name)
        profile["custom_modules"] = merged

    built = TaskBreaker().build(profile)
    orchestration = Orchestrator().build(built["tasks"], built["edges"], profile)
    return PlanRenderer().render(profile, built, orchestration, adapter.describe())
