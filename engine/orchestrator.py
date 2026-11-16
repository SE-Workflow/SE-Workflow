"""Agent 编排（编排器模拟）。

输入任务清单与依赖边，输出：
- 拓扑排序与依赖校验（保证是一张 DAG）；
- 关键路径（CPM：最早/最晚开始、总时差）；
- 执行波次（按时间窗口把可并行任务分组）；
- Agent 负载与交接关系（用于 Agent 协作图）；
- 排期风险提示。
"""

from __future__ import annotations

import math
from collections import defaultdict

from config import (
    AGENT_SHARE_WARN,
    AGENTS,
    CRITICAL_DAYS_WARN,
    PARALLEL_MODULE_WARN,
    WAVE_TARGET,
)
from .models import Task


class Orchestrator:
    """把任务 DAG 转成可执行的编排方案。"""

    def __init__(self, agents: dict | None = None) -> None:
        self.agents = agents or AGENTS

    def build(self, tasks: list[Task], edges: list[dict], profile: dict) -> dict:
        if not tasks:
            raise ValueError("任务清单为空，无法编排")

        task_by_id = {task.id: task for task in tasks}
        predecessors: dict[str, list[str]] = {task.id: [] for task in tasks}
        successors: dict[str, list[str]] = {task.id: [] for task in tasks}
        for edge in edges:
            source, target = edge["from"], edge["to"]
            if source in task_by_id and target in task_by_id:
                predecessors[target].append(source)
                successors[source].append(target)

        order = self._topological_order(tasks, predecessors, successors)
        makespan = self._forward_pass(order, task_by_id, predecessors)
        self._backward_pass(order, task_by_id, successors, makespan)
        critical_path = self._critical_path(task_by_id, predecessors, makespan)

        bucket_days = max(1, math.ceil(makespan / WAVE_TARGET))
        waves = self._waves(tasks, makespan, bucket_days)

        agent_stats = self._agent_stats(tasks)
        agent_flow = self._agent_flow(edges, task_by_id)
        risks = self._risks(tasks, makespan, agent_stats, profile)

        return {
            "topological_order": order,
            "bucket_days": bucket_days,
            "waves": waves,
            "critical_path": critical_path,
            "critical_days": round(makespan, 1),
            "agents": agent_stats,
            "agent_flow": agent_flow,
            "risks": risks,
        }

    # ------------------------------------------------------------------ DAG 校验
    def _topological_order(
        self,
        tasks: list[Task],
        predecessors: dict[str, list[str]],
        successors: dict[str, list[str]],
    ) -> list[str]:
        indegree = {task.id: len(predecessors[task.id]) for task in tasks}
        queue = sorted([task_id for task_id, degree in indegree.items() if degree == 0])
        order: list[str] = []
        while queue:
            current = queue.pop(0)
            order.append(current)
            for successor in sorted(successors[current]):
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    queue.append(successor)
                    queue.sort()
        if len(order) != len(tasks):
            raise ValueError("任务依赖存在环，请检查 config/modules.py 中的 depends 配置")
        return order

    # ------------------------------------------------------------------ CPM
    @staticmethod
    def _forward_pass(order: list[str], task_by_id: dict[str, Task], predecessors: dict[str, list[str]]) -> float:
        makespan = 0.0
        for task_id in order:
            task = task_by_id[task_id]
            task.earliest_start = max(
                (task_by_id[pred].earliest_finish for pred in predecessors[task_id]), default=0.0
            )
            task.earliest_finish = task.earliest_start + task.effort_days
            task.rank = 1 + max((task_by_id[pred].rank for pred in predecessors[task_id]), default=-1)
            makespan = max(makespan, task.earliest_finish)
        return makespan

    @staticmethod
    def _backward_pass(
        order: list[str],
        task_by_id: dict[str, Task],
        successors: dict[str, list[str]],
        makespan: float,
    ) -> None:
        for task_id in reversed(order):
            task = task_by_id[task_id]
            if successors[task_id]:
                task.latest_finish = min(
                    task_by_id[successor].latest_start for successor in successors[task_id]
                )
            else:
                task.latest_finish = makespan
            task.latest_start = task.latest_finish - task.effort_days
            task.slack = round(task.latest_start - task.earliest_start, 6)
            task.critical = task.slack <= 1e-6

    def _critical_path(
        self,
        task_by_id: dict[str, Task],
        predecessors: dict[str, list[str]],
        makespan: float,
    ) -> list[str]:
        finals = [task for task in task_by_id.values() if abs(task.earliest_finish - makespan) <= 1e-6]
        if not finals:
            return []
        current = max(finals, key=lambda task: (task.effort_days, task.id))
        path = [current.id]
        while True:
            candidates = [
                task_by_id[pred]
                for pred in predecessors[current.id]
                if abs(task_by_id[pred].earliest_finish - current.earliest_start) <= 1e-6
            ]
            if not candidates:
                break
            current = max(candidates, key=lambda task: (task.earliest_finish, task.effort_days))
            path.append(current.id)
        return list(reversed(path))

    # ------------------------------------------------------------------ 波次
    @staticmethod
    def _waves(tasks: list[Task], makespan: float, bucket_days: int) -> list[dict]:
        buckets: dict[int, list[Task]] = defaultdict(list)
        for task in tasks:
            task.wave = int(task.earliest_start // bucket_days)
            task.level = task.wave
            buckets[task.wave].append(task)

        waves = []
        for index in sorted(buckets):
            items = sorted(buckets[index], key=lambda task: (task.agent, task.id))
            waves.append(
                {
                    "index": index,
                    "start": round(index * bucket_days, 1),
                    "end": round(min((index + 1) * bucket_days, makespan), 1),
                    "count": len(items),
                    "effort": round(sum(task.effort_days for task in items), 1),
                    "agents": sorted({task.agent for task in items}),
                    "tasks": [task.id for task in items],
                    "parallel": len(items) > 1,
                }
            )
        return waves

    # ------------------------------------------------------------------ Agent 负载
    def _agent_stats(self, tasks: list[Task]) -> list[dict]:
        total_effort = sum(task.effort_days for task in tasks) or 1.0
        aggregate: dict[str, dict] = {}
        for task in tasks:
            record = aggregate.setdefault(
                task.agent,
                {"tasks": [], "effort": 0.0, "modules": set(), "p0": 0},
            )
            record["tasks"].append(task)
            record["effort"] += task.effort_days
            record["modules"].add(task.module_name)
            record["p0"] += 1 if task.priority == "P0" else 0

        stats = []
        for agent_id, record in aggregate.items():
            meta = self.agents.get(agent_id, {})
            stats.append(
                {
                    "id": agent_id,
                    "name": meta.get("name", agent_id),
                    "role": meta.get("role", ""),
                    "color": meta.get("color", "#64748b"),
                    "icon": meta.get("icon", "•"),
                    "task_count": len(record["tasks"]),
                    "effort": round(record["effort"], 1),
                    "share": round(record["effort"] / total_effort, 3),
                    "p0_count": record["p0"],
                    "modules": sorted(record["modules"]),
                    "task_ids": [task.id for task in record["tasks"]],
                }
            )
        stats.sort(key=lambda item: item["effort"], reverse=True)
        return stats

    def _agent_flow(self, edges: list[dict], task_by_id: dict[str, Task]) -> dict:
        node_ids = {task.agent for task in task_by_id.values()}
        counts: dict[tuple[str, str], list[str]] = defaultdict(list)
        for edge in edges:
            source = task_by_id.get(edge["from"])
            target = task_by_id.get(edge["to"])
            if not source or not target or source.agent == target.agent:
                continue
            counts[(source.agent, target.agent)].append(f"{source.id}→{target.id}")

        nodes = []
        for agent_id in sorted(node_ids):
            meta = self.agents.get(agent_id, {})
            nodes.append(
                {
                    "id": agent_id,
                    "name": meta.get("name", agent_id),
                    "role": meta.get("role", ""),
                    "color": meta.get("color", "#64748b"),
                    "icon": meta.get("icon", "•"),
                }
            )
        flow_edges = [
            {
                "from": source,
                "to": target,
                "count": len(items),
                "samples": items[:4],
            }
            for (source, target), items in sorted(counts.items(), key=lambda item: len(item[1]), reverse=True)
        ]
        return {"nodes": nodes, "edges": flow_edges}

    # ------------------------------------------------------------------ 风险
    def _risks(self, tasks: list[Task], makespan: float, agent_stats: list[dict], profile: dict) -> list[dict]:
        risks: list[dict] = []
        if makespan > CRITICAL_DAYS_WARN:
            risks.append(
                {
                    "level": "warn",
                    "title": "关键路径偏长",
                    "text": f"关键路径约 {makespan:.1f} 人天，超过 {CRITICAL_DAYS_WARN} 天预警线，建议补充人力或把非 P0 任务后移。",
                }
            )
        if agent_stats:
            top = agent_stats[0]
            if top["share"] > AGENT_SHARE_WARN:
                risks.append(
                    {
                        "level": "warn",
                        "title": "Agent 负载集中",
                        "text": f"{top['name']} 承担了 {top['share'] * 100:.0f}% 的工作量（{top['effort']} 人天），建议拆分任务或增加并行执行者。",
                    }
                )
        business_modules = [task.module_name for task in tasks if task.module_name]
        if len(set(business_modules)) > PARALLEL_MODULE_WARN:
            risks.append(
                {
                    "level": "info",
                    "title": "并行模块较多",
                    "text": f"共 {len(set(business_modules))} 个模块并行推进，建议按依赖波次分批启动，避免同时占用全部 Agent。",
                }
            )
        p0 = sum(1 for task in tasks if task.priority == "P0")
        if p0 / len(tasks) > 0.7:
            risks.append(
                {
                    "level": "info",
                    "title": "P0 占比偏高",
                    "text": f"P0 任务占比 {p0 / len(tasks) * 100:.0f}%，建议复核优先级，为排期留出缓冲。",
                }
            )
        if not risks:
            risks.append(
                {
                    "level": "ok",
                    "title": "编排健康",
                    "text": "关键路径与 Agent 负载均在合理区间，可直接按波次推进。",
                }
            )
        return risks
