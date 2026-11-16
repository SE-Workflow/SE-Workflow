"""领域模型：任务数据结构与序列化。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Task:
    """一个原子任务（任务树叶子节点）。"""

    id: str
    name: str
    description: str
    module_id: str
    module_name: str
    subtask_id: str
    subtask_name: str
    priority: str
    effort_days: float
    agent: str
    acceptance: str
    depends_on: list[str] = field(default_factory=list)

    # 由编排器计算
    level: int = 0
    wave: int = 0
    rank: int = 0
    earliest_start: float = 0.0
    earliest_finish: float = 0.0
    latest_start: float = 0.0
    latest_finish: float = 0.0
    slack: float = 0.0
    critical: bool = False

    def to_dict(self, agents: dict) -> dict:
        agent = agents.get(self.agent, {})
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "module_id": self.module_id,
            "module": self.module_name,
            "subtask_id": self.subtask_id,
            "subtask": self.subtask_name,
            "priority": self.priority,
            "effort": round(self.effort_days, 1),
            "agent": self.agent,
            "agent_name": agent.get("name", self.agent),
            "agent_color": agent.get("color", "#64748b"),
            "agent_icon": agent.get("icon", "•"),
            "acceptance": self.acceptance,
            "depends_on": list(self.depends_on),
            "level": self.level,
            "wave": self.wave,
            "rank": self.rank,
            "earliest_start": round(self.earliest_start, 1),
            "earliest_finish": round(self.earliest_finish, 1),
            "latest_start": round(self.latest_start, 1),
            "slack": round(self.slack, 1),
            "critical": self.critical,
        }


def task_id(index: int) -> str:
    """全局任务编号：T001、T002 ……"""
    return f"T{index:03d}"
