"""阶段一：LLM 任务分解。"""

from __future__ import annotations

from config import MAX_TASKS, MIN_TASKS, Settings, agent_catalog_text, build_decompose_messages
from .llm_client import LLMClient
from .llm_json import StageResult, call_json_stage
from .schema import normalize_decomposition


class DecomposeStage:
    """把需求拆成一组原子任务。"""

    name = "任务分解"

    def __init__(self, client: LLMClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def run(self, requirement: str) -> StageResult:
        messages = build_decompose_messages(
            requirement,
            agent_catalog_text(),
            MIN_TASKS,
            MAX_TASKS,
        )
        return call_json_stage(
            self.client,
            messages,
            lambda payload: normalize_decomposition(payload, requirement),
            max_attempts=self.settings.max_retries + 1,
            max_tokens=5000,
        )
