"""SE Workflow 引擎包。

对外入口：
    generate(requirement)  → 完整工作流程图 JSON
    build_view(plan)       → 页面统计 / 图例 / 阶段视图
    PlanStore              → 方案持久化
"""

from .pipeline import PipelineError, generate
from .render import build_view
from .schema import ValidationError, rebuild_plan, validate_saved_plan
from .store import PlanStore

__all__ = [
    "PipelineError",
    "PlanStore",
    "ValidationError",
    "build_view",
    "generate",
    "rebuild_plan",
    "validate_saved_plan",
]
