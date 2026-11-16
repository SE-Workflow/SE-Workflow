"""阶段二：LLM Agent 编排。

输入是阶段一产出的任务清单，输出依赖边、分层阶段、并行分组与 Agent 指派。
"""

from __future__ import annotations

from config import Settings, agent_catalog_text, build_orchestrate_messages
from .json_utils import dumps_compact
from .llm_client import LLMClient
from .llm_json import StageResult, call_json_stage
from .schema import normalize_orchestration


class OrchestrateStage:
    """为任务清单生成 DAG 依赖、阶段分层与 Agent 指派。"""

    name = "Agent 编排"

    def __init__(self, client: LLMClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def run(self, requirement: str, tasks: list[dict]) -> StageResult:
        compact_tasks = [
            {
                "id": task["id"],
                "name": task["name"],
                "module": task["module"],
                "priority": task["priority"],
                "effort": task["effort"],
                "suggested_agent": task["agent"],
                "description": task["description"],
                "acceptance": task["acceptance"],
            }
            for task in tasks
        ]
        messages = build_orchestrate_messages(
            requirement,
            dumps_compact(compact_tasks),
            agent_catalog_text(),
        )
        return call_json_stage(
            self.client,
            messages,
            lambda payload: normalize_orchestration(payload, tasks),
            max_attempts=self.settings.max_retries + 1,
            max_tokens=5000,
        )
