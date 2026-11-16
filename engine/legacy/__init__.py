"""规则引擎（Mock 模式的数据来源）。

这里保留了项目早期实现的领域模板 + 任务拆解 + 依赖编排逻辑：
- `RequirementParser` 识别产品域 / 规模 / 平台 / 能力特征；
- `TaskBreaker` 基于 `config/modules.py` 展开模块 → 子任务 → 原子任务；
- `Orchestrator` 计算拓扑、关键路径与执行波次；
- `PlanRenderer` 汇总模块视图。

V5 的真实主路径是两阶段 LLM 调用；这里只在无 Key / 强制 Mock / 调用失败时
提供一份仍然有业务含义的兜底方案。`build_legacy_plan()` 是对外唯一入口。
"""

from __future__ import annotations

from .breaker import TaskBreaker
from .orchestrator import Orchestrator
from .parser import RequirementParser
from .render import PlanRenderer


def build_legacy_plan(requirement: str) -> dict:
    """跑一遍规则引擎，返回旧版方案结构（模块级视图）。"""
    profile = RequirementParser().parse(requirement)
    built = TaskBreaker().build(profile)
    orchestration = Orchestrator().build(built["tasks"], built["edges"], profile)
    return PlanRenderer().render(
        profile,
        built,
        orchestration,
        {"name": "legacy-rule-engine", "enabled": False},
    )


__all__ = ["build_legacy_plan"]
