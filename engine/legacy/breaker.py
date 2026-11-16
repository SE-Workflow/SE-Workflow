"""任务分解（PM Agent 模拟）。

读取 config/modules.py 的模块模板，结合需求画像选择模块并展开成
「模块 → 子任务 → 原子任务」三层任务树，同时生成依赖边。

设计要点：
- 模块选择 = 核心模块 + 领域模块 + 能力特征模块 + 补充需求模块；
- 规模（S/M/L）决定模块取舍与工作量系数；
- 能力型模块按能力点自动展开，避免为每个新产品手写一遍任务；
- 模块出口固定为最后一个原子任务，依赖边只连“出口 → 入口”，保证 DAG 清晰。
"""

from __future__ import annotations

from config import (
    AGENTS,
    CAPABILITY_ACCEPTANCE,
    CAPABILITY_DESCRIPTIONS,
    CAPABILITY_EFFORT,
    DEFAULT_AGENT,
    DOMAINS,
    FEATURE_MODULES,
    MODULE_COLORS,
    MODULES,
    SCALE_META,
)
from .models import Task, task_id

CAPABILITY_NAMES = ("build", "verify")


class TaskBreaker:
    """把需求画像展开为任务树 + 任务清单 + 依赖边。"""

    def __init__(self, modules: dict | None = None, agents: dict | None = None) -> None:
        self.modules = modules or MODULES
        self.agents = agents or AGENTS

    # ------------------------------------------------------------------ 入口
    def build(self, profile: dict) -> dict:
        scale = profile["scale"]["code"]
        factor = SCALE_META.get(scale, {}).get("factor", 1.0)
        selected = self._select_modules(profile)
        built = self._build_modules(selected, profile, factor)
        built["modules"] = self._summarize_modules(built["records"], profile)
        built["warnings"] = self._warnings(built, profile)
        return built

    # ------------------------------------------------------------------ 选模块
    def _select_modules(self, profile: dict) -> list[dict]:
        scale = profile["scale"]["code"]
        feature_ids = {feature["id"] for feature in profile["features"]}
        platforms = profile["platforms"]
        web_only = platforms == ["Web"]

        chosen: list[str] = []

        def add(module_id: str) -> None:
            if module_id in self.modules and module_id not in chosen:
                chosen.append(module_id)

        # 1. 核心模块：所有产品共用
        for module_id, module in self.modules.items():
            if module.get("business"):
                continue
            if module_id == "mobile" and web_only:
                continue
            add(module_id)

        # 2. 领域模块
        domain = DOMAINS.get(profile["domain"]["id"], DOMAINS["generic"])
        for module_id in domain.get("modules", []):
            add(module_id)

        # 3. 能力特征模块
        for feature_id in feature_ids:
            for module_id in FEATURE_MODULES.get(feature_id, []):
                add(module_id)

        # 4. 规模过滤
        chosen = [
            module_id
            for module_id in chosen
            if scale in self.modules[module_id].get("scales", ["S", "M", "L"])
        ]

        # 稳定排序：阶段优先，其次保持配置顺序
        config_order = {module_id: index for index, module_id in enumerate(self.modules)}
        chosen.sort(key=lambda module_id: (self.modules[module_id].get("phase", 3), config_order[module_id]))

        selected: list[dict] = []
        for module_id in chosen:
            config = dict(self.modules[module_id])
            config["id"] = module_id
            selected.append(config)

        # 5. 补充需求模块（来自结构化输入里用户自己加的要求）
        for index, custom in enumerate(profile.get("custom_modules", []), start=1):
            selected.append(
                {
                    "id": f"custom_{index}",
                    "name": custom["name"],
                    "summary": custom.get("summary", "来自需求文本的补充模块"),
                    "phase": 3,
                    "priority": "P1",
                    "agent": custom.get("agent", DEFAULT_AGENT),
                    "depends": ["architecture"],
                    "mode": "parallel",
                    "capabilities": custom.get("capabilities", [custom["name"]]),
                    "business": True,
                    "custom": True,
                }
            )

        # 稳定排序，让补充模块排在同一阶段的业务模块之后、集成阶段之前
        selected.sort(key=lambda config: config.get("phase", 3))
        return selected

    # ------------------------------------------------------------------ 展开
    def _build_modules(self, selected: list[dict], profile: dict, factor: float) -> dict:
        tasks: list[Task] = []
        edges: list[dict] = []
        records: list[dict] = []
        tree: list[dict] = []
        index = 0

        for order, config in enumerate(selected, start=1):
            module_id = f"M{order:02d}"
            module_name = config["name"]
            priority = config.get("priority", "P1")
            module_agent = self._agent(config.get("agent"))
            color = MODULE_COLORS[(order - 1) % len(MODULE_COLORS)]
            subtasks = self._subtasks(config)

            subtask_nodes = []
            subtask_meta = []
            for sub_index, subtask in enumerate(subtasks, start=1):
                subtask_id = f"{module_id}-S{sub_index}"
                agent = self._agent(subtask.get("agent") or module_agent)
                atoms = subtask["atoms"]
                atom_tasks = []
                for atom_index, atom in enumerate(atoms, start=1):
                    index += 1
                    atom_agent = self._agent(atom.get("agent") or agent)
                    effort = max(0.5, round(float(atom.get("effort", 2.0)) * factor * 2) / 2)
                    task = Task(
                        id=task_id(index),
                        name=atom["name"],
                        description=atom.get(
                            "desc", f"完成「{atom['name']}」的设计、实现与自测。"
                        ),
                        module_id=module_id,
                        module_name=module_name,
                        subtask_id=subtask_id,
                        subtask_name=subtask["name"],
                        priority=atom.get("priority", priority),
                        effort_days=effort,
                        agent=atom_agent,
                        acceptance=atom.get(
                            "acceptance", "功能通过验收用例，代码评审与文档更新完成"
                        ),
                    )
                    atom_tasks.append(task)
                    tasks.append(task)

                subtask_meta.append(
                    {
                        "id": subtask_id,
                        "name": subtask["name"],
                        "agent": agent,
                        "parallel": subtask.get("parallel", config.get("mode") == "parallel"),
                        "tasks": atom_tasks,
                    }
                )
                subtask_nodes.append(
                    {
                        "id": subtask_id,
                        "type": "subtask",
                        "name": subtask["name"],
                        "agent": agent,
                        "agent_name": self.agents[agent]["name"],
                        "parallel": subtask.get("parallel", config.get("mode") == "parallel"),
                        "effort": round(sum(task.effort_days for task in atom_tasks), 1),
                        "task_count": len(atom_tasks),
                        "children": [task.to_dict(self.agents) for task in atom_tasks],
                    }
                )

            # ---------------- 模块内部依赖边
            mode = config.get("mode", "sequential")
            if mode == "parallel" and len(subtask_meta) > 1:
                first_task = subtask_meta[0]["tasks"][0]
                for sub in subtask_meta[1:]:
                    edges.append({"from": first_task.id, "to": sub["tasks"][0].id, "kind": "flow"})
                join_task = subtask_meta[-1]["tasks"][-1]
                for sub in subtask_meta[:-1]:
                    edges.append({"from": sub["tasks"][-1].id, "to": join_task.id, "kind": "flow"})
            else:
                # 串行模块：子任务首尾相接
                for previous, current in zip(subtask_meta, subtask_meta[1:]):
                    edges.append(
                        {"from": previous["tasks"][-1].id, "to": current["tasks"][0].id, "kind": "flow"}
                    )
            for sub in subtask_meta:
                for previous, current in zip(sub["tasks"], sub["tasks"][1:]):
                    edges.append({"from": previous.id, "to": current.id, "kind": "flow"})

            entry = subtask_meta[0]["tasks"][0]
            exit_task = subtask_meta[-1]["tasks"][-1]

            records.append(
                {
                    "id": module_id,
                    "config": config,
                    "entry": entry.id,
                    "exit": exit_task.id,
                    "tasks": [task for task in tasks if task.module_id == module_id],
                    "subtasks": subtask_meta,
                }
            )
            tree.append(
                {
                    "id": module_id,
                    "type": "module",
                    "name": module_name,
                    "summary": config.get("summary", ""),
                    "priority": priority,
                    "agent": module_agent,
                    "agent_name": self.agents[module_agent]["name"],
                    "color": color,
                    "phase": config.get("phase", 3),
                    "custom": bool(config.get("custom")),
                    "effort": round(sum(task.effort_days for task in tasks if task.module_id == module_id), 1),
                    "task_count": sum(len(sub["tasks"]) for sub in subtask_meta),
                    "children": subtask_nodes,
                }
            )

        module_edges = self._wire_dependencies(records, edges)
        # 依赖回填后再刷新任务树里的任务快照，保证前端拿到的依赖信息完整
        task_by_id = {task.id: task for task in tasks}
        for module_node in tree:
            for subtask_node in module_node["children"]:
                subtask_node["children"] = [
                    task_by_id[child["id"]].to_dict(self.agents)
                    for child in subtask_node["children"]
                ]
        return {
            "tasks": tasks,
            "edges": edges,
            "module_edges": module_edges,
            "records": records,
            "tree": tree,
            "profile": profile,
        }

    # ------------------------------------------------------------------ 跨模块依赖
    def _wire_dependencies(self, records: list[dict], edges: list[dict]) -> list[dict]:
        # 配置里的 depends 用的是模块 key（如 backend_core），记录用的是展示 id（M04）
        by_key = {record["config"]["id"]: record for record in records}
        seen = {(edge["from"], edge["to"]) for edge in edges}
        task_by_id = {task.id: task for record in records for task in record["tasks"]}
        business_keys = [record["config"]["id"] for record in records if record["config"].get("business")]
        module_edges: list[dict] = []
        module_seen: set[tuple[str, str]] = set()

        for record in records:
            config = record["config"]
            dependencies: list[str] = []
            for dependency in config.get("depends", []):
                if dependency == "*business":
                    dependencies.extend(business_keys)
                elif dependency in by_key:
                    dependencies.append(dependency)
            # 业务模块过滤后没有可依赖的模块时，至少挂在架构设计之后
            if not dependencies and config.get("business") and "architecture" in by_key:
                dependencies.append("architecture")

            for dependency in dict.fromkeys(dependencies):
                source = by_key.get(dependency)
                if source is None or source is record:
                    continue
                pair = (source["exit"], record["entry"])
                if pair not in seen:
                    seen.add(pair)
                    edges.append({"from": source["exit"], "to": record["entry"], "kind": "dep"})
                    task_by_id[record["entry"]].depends_on.append(source["exit"])
                module_pair = (source["id"], record["id"])
                if module_pair not in module_seen:
                    module_seen.add(module_pair)
                    module_edges.append({"from": source["id"], "to": record["id"]})

        # 完整依赖（含模块内部）供前端展示
        predecessors: dict[str, list[str]] = {}
        for edge in edges:
            predecessors.setdefault(edge["to"], []).append(edge["from"])
        for task in task_by_id.values():
            task.depends_on = sorted(set(predecessors.get(task.id, [])), key=lambda value: value)
        return module_edges

    # ------------------------------------------------------------------ 模板展开
    def _subtasks(self, config: dict) -> list[dict]:
        if config.get("subtasks"):
            return [
                {
                    "name": subtask["name"],
                    "agent": subtask.get("agent"),
                    "parallel": config.get("mode") == "parallel",
                    "atoms": subtask.get("atoms", []),
                }
                for subtask in config["subtasks"]
            ]

        subtasks = []
        for capability in config.get("capabilities", []):
            atoms = []
            for kind in CAPABILITY_NAMES:
                atoms.append(
                    {
                        "name": f"{capability} · {'方案与实现' if kind == 'build' else '联调与验收'}",
                        "desc": CAPABILITY_DESCRIPTIONS[kind].format(cap=capability),
                        "effort": CAPABILITY_EFFORT[kind],
                        "acceptance": CAPABILITY_ACCEPTANCE[kind],
                    }
                )
            subtasks.append({"name": capability, "atoms": atoms, "parallel": True})
        return subtasks

    # ------------------------------------------------------------------ 汇总
    def _summarize_modules(self, records: list[dict], profile: dict) -> list[dict]:
        summaries = []
        for record in records:
            config = record["config"]
            summaries.append(
                {
                    "id": record["id"],
                    "key": config["id"],
                    "name": config["name"],
                    "summary": config.get("summary", ""),
                    "phase": config.get("phase", 3),
                    "priority": config.get("priority", "P1"),
                    "agent": config.get("agent", DEFAULT_AGENT),
                    "agent_name": self.agents[self._agent(config.get("agent"))]["name"],
                    "business": bool(config.get("business")),
                    "custom": bool(config.get("custom")),
                    "depends": list(config.get("depends", [])),
                    "task_count": len(record["tasks"]),
                    "effort": round(sum(task.effort_days for task in record["tasks"]), 1),
                }
            )
        return summaries

    # ------------------------------------------------------------------ 提示
    @staticmethod
    def _warnings(built: dict, profile: dict) -> list[str]:
        warnings = []
        total = len(built["tasks"])
        if total > 110:
            warnings.append(f"本次共拆出 {total} 个原子任务，建议按模块分批排期与交付。")
        if profile["scale"]["code"] == "S":
            warnings.append("小型项目已自动裁剪部分模块，可在配置中放开 scales 限制。")
        return warnings

    def _agent(self, agent: str | None) -> str:
        return agent if agent in self.agents else DEFAULT_AGENT
