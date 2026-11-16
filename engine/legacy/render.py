"""可视化渲染（渲染层）。

把编排结果转成前端直接可用的视图模型：
- 任务 DAG：节点（任务）+ 边（依赖/流转）+ 多套配色（模块/Agent/优先级/波次）；
- Agent 协作图：节点（Agent）+ 边（交接次数）；
- 图例、关键路径、统计与配置元信息。

节点/边的 tooltip 在这里统一做 HTML 转义，前端只负责渲染，避免 XSS。
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from config import AGENTS, MODULE_COLORS, PRIORITY_META, WAVE_TARGET

VERSION = "1.0.0"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(channel * 2 for channel in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _tint(hex_color: str, alpha: float) -> str:
    red, green, blue = _rgb(hex_color)
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _node_color(hex_color: str) -> dict:
    return {
        "background": _tint(hex_color, 0.14),
        "border": hex_color,
        "highlight": {
            "background": _tint(hex_color, 0.28),
            "border": hex_color,
        },
        "hover": {
            "background": _tint(hex_color, 0.22),
            "border": hex_color,
        },
    }


class PlanRenderer:
    """编排结果 → 页面视图模型。"""

    def __init__(self, agents: dict | None = None) -> None:
        self.agents = agents or AGENTS

    def render(
        self,
        profile: dict,
        built: dict,
        orchestration: dict,
        llm_status: dict | None = None,
    ) -> dict:
        modules = self._modules(built)
        tasks = [task.to_dict(self.agents) for task in built["tasks"]]
        module_colors = {module["id"]: module["color"] for module in modules}
        for task in tasks:
            task["module_color"] = module_colors.get(task["module_id"], "#64748b")

        tasks_by_id = {task["id"]: task for task in tasks}
        task_graph = self._task_graph(tasks, built["edges"], tasks_by_id, modules)
        module_graph = self._module_graph(modules, built.get("module_edges", []), tasks)
        agent_graph = self._agent_graph(orchestration)

        critical_tasks = [tasks_by_id[task_id] for task_id in orchestration["critical_path"] if task_id in tasks_by_id]
        stats = self._stats(modules, built, tasks, orchestration)

        profile = dict(profile)
        module_names = [module["name"] for module in modules[:3]]
        if module_names:
            summary = profile["summary"].rstrip("。")
            profile["summary"] = f"{summary}，覆盖「{'、'.join(module_names)}」等 {len(modules)} 个模块。"

        plan = {
            "meta": {
                "version": VERSION,
                "engine": "rule-based",
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "llm": llm_status or {"name": "rule-only", "enabled": False},
            },
            "profile": profile,
            "modules": modules,
            "tree": built["tree"],
            "tasks": tasks,
            "edges": built["edges"],
            "stats": stats,
            "orchestration": {
                **orchestration,
                "critical_tasks": critical_tasks,
                "wave_days": orchestration["bucket_days"],
            },
            "graph": {"task": task_graph, "module": module_graph, "agent": agent_graph},
            "legend": self._legend(modules, orchestration),
            "config_meta": self._config_meta(llm_status),
            "warnings": built.get("warnings", []),
        }
        return plan

    # ------------------------------------------------------------------ 模块
    def _modules(self, built: dict) -> list[dict]:
        colors = {node["id"]: node["color"] for node in built["tree"]}
        modules = []
        for module in built["modules"]:
            item = dict(module)
            item["color"] = colors.get(module["id"], MODULE_COLORS[0])
            modules.append(item)
        return modules

    # ------------------------------------------------------------------ 任务图
    def _task_graph(
        self,
        tasks: list[dict],
        edges: list[dict],
        tasks_by_id: dict[str, dict],
        modules: list[dict],
    ) -> dict:
        module_color = {module["id"]: module["color"] for module in modules}
        wave_colors = [MODULE_COLORS[index % len(MODULE_COLORS)] for index in range(max(1, WAVE_TARGET + 1))]

        nodes = []
        for task in tasks:
            agent = self.agents.get(task["agent"], {})
            priority_color = PRIORITY_META.get(task["priority"], {}).get("color", "#64748b")
            name = task["name"]
            short_name = name if len(name) <= 18 else f"{name[:17]}…"
            nodes.append(
                {
                    "id": task["id"],
                    "label": f"{task['id']}\n{short_name}",
                    "title": self._task_tooltip(task),
                    "level": task["wave"],
                    "rank": task["rank"],
                    "wave": task["wave"],
                    "critical": task["critical"],
                    "priority": task["priority"],
                    "agent": task["agent"],
                    "agent_name": task["agent_name"],
                    "module": task["module"],
                    "module_id": task["module_id"],
                    "effort": task["effort"],
                    "font": {"color": "#1e293b", "size": 12},
                    "shape": "box",
                    "margin": 8,
                    "widthConstraint": {"maximum": 210},
                    "colors": {
                        "module": _node_color(module_color.get(task["module_id"], "#64748b")),
                        "agent": _node_color(agent.get("color", "#64748b")),
                        "priority": _node_color(priority_color),
                        "wave": _node_color(wave_colors[task["wave"] % len(wave_colors)]),
                    },
                }
            )

        graph_edges = []
        for index, edge in enumerate(edges):
            source = tasks_by_id.get(edge["from"])
            target = tasks_by_id.get(edge["to"])
            critical = bool(
                source
                and target
                and source["critical"]
                and target["critical"]
                and abs(source["earliest_finish"] - target["earliest_start"]) <= 1e-6
            )
            kind_label = "模块依赖" if edge["kind"] == "dep" else "任务流转"
            graph_edges.append(
                {
                    "id": f"E{index:03d}",
                    "from": edge["from"],
                    "to": edge["to"],
                    "kind": edge["kind"],
                    "critical": critical,
                    "title": f"<b>{escape(edge['from'])} → {escape(edge['to'])}</b><br>{kind_label}",
                }
            )

        return {"nodes": nodes, "edges": graph_edges}

    def _task_tooltip(self, task: dict) -> str:
        dependencies = "、".join(task["depends_on"]) if task["depends_on"] else "无"
        rows = [
            f"<b>{escape(task['id'])} · {escape(task['name'])}</b>",
            f"{escape(task['module'])} / {escape(task['subtask'])}",
            f"Agent：{escape(task['agent_name'])}　优先级：{escape(task['priority'])}",
            f"工作量：{task['effort']} 人天　第 {task['wave'] + 1} 波（第 {task['earliest_start']:.1f}–{task['earliest_finish']:.1f} 天）",
            f"依赖：{escape(dependencies)}",
            f"验收：{escape(task['acceptance'])}",
        ]
        return "<br>".join(rows)

    # ------------------------------------------------------------------ 模块概览图
    def _module_graph(self, modules: list[dict], module_edges: list[dict], tasks: list[dict]) -> dict:
        module_ids = [module["id"] for module in modules]
        predecessors: dict[str, list[str]] = {module_id: [] for module_id in module_ids}
        for edge in module_edges:
            if edge["to"] in predecessors and edge["from"] in predecessors:
                predecessors[edge["to"]].append(edge["from"])

        # 模块级拓扑层级：用于分层布局，保证依赖从上往下
        levels = {module_id: 0 for module_id in module_ids}
        for _ in range(len(module_ids) + 1):
            changed = False
            for module_id in module_ids:
                level = max((levels[parent] + 1 for parent in predecessors[module_id]), default=0)
                if level > levels[module_id]:
                    levels[module_id] = level
                    changed = True
            if not changed:
                break

        critical_modules = {task["module_id"] for task in tasks if task["critical"]}
        modules_by_id = {module["id"]: module for module in modules}

        nodes = []
        for module in modules:
            nodes.append(
                {
                    "id": module["id"],
                    "label": f"{module['name']}\n{module['task_count']} 个任务 · {module['effort']} 人天",
                    "title": (
                        f"<b>{escape(module['name'])}</b><br>{escape(module.get('summary', ''))}"
                        f"<br>优先级：{escape(module['priority'])} · 主责：{escape(module['agent_name'])}"
                        f"<br>{module['task_count']} 个任务 · {module['effort']} 人天"
                    ),
                    "level": levels.get(module["id"], 0),
                    "critical": module["id"] in critical_modules,
                    "module": module["name"],
                    "task_count": module["task_count"],
                    "effort": module["effort"],
                    "priority": module["priority"],
                    "agent_name": module["agent_name"],
                    "colors": {"module": _node_color(module["color"])},
                }
            )

        edges = []
        for index, edge in enumerate(module_edges):
            source = modules_by_id.get(edge["from"])
            target = modules_by_id.get(edge["to"])
            if not source or not target:
                continue
            edges.append(
                {
                    "id": f"ME{index:03d}",
                    "from": edge["from"],
                    "to": edge["to"],
                    "kind": "dep",
                    "title": f"<b>{escape(source['name'])} → {escape(target['name'])}</b><br>模块依赖",
                }
            )

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------ Agent 图
    def _agent_graph(self, orchestration: dict) -> dict:
        nodes = []
        for agent in orchestration["agents"]:
            nodes.append(
                {
                    "id": agent["id"],
                    "label": f"{agent['icon']} {agent['name']}\n{agent['task_count']} 个任务 · {agent['effort']} 人天",
                    "title": (
                        f"<b>{escape(agent['name'])}</b><br>{escape(agent['role'])}"
                        f"<br>任务 {agent['task_count']} 个 · 工作量 {agent['effort']} 人天"
                        f"<br>覆盖模块：{escape('、'.join(agent['modules'][:5]))}"
                    ),
                    "color": agent["color"],
                    "shape": "dot",
                    "size": 18 + min(26, agent["effort"] ** 0.55),
                    "font": {"color": "#1e293b", "size": 12},
                }
            )

        edges = []
        for index, edge in enumerate(orchestration["agent_flow"]["edges"]):
            source = next((node for node in nodes if node["id"] == edge["from"]), None)
            target = next((node for node in nodes if node["id"] == edge["to"]), None)
            if not source or not target:
                continue
            edges.append(
                {
                    "id": f"A{index:03d}",
                    "from": edge["from"],
                    "to": edge["to"],
                    "label": str(edge["count"]),
                    "title": (
                        f"<b>{escape(source['label'].splitlines()[0])} → {escape(target['label'].splitlines()[0])}</b>"
                        f"<br>交接 {edge['count']} 次，例如：{escape('、'.join(edge['samples']))}"
                    ),
                    "arrows": {"to": {"enabled": True, "scaleFactor": 0.6}},
                    "width": 1 + min(5, edge["count"] ** 0.5),
                    "color": {"color": "#94a3b8", "highlight": source["color"]},
                }
            )
        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------ 图例
    def _legend(self, modules: list[dict], orchestration: dict) -> dict:
        wave_items = [
            {"label": f"第 {wave['index'] + 1} 波", "color": MODULE_COLORS[wave["index"] % len(MODULE_COLORS)]}
            for wave in orchestration["waves"]
        ]
        return {
            "module": [{"label": module["name"], "color": module["color"]} for module in modules],
            "agent": [
                {"label": agent["name"], "color": agent["color"]}
                for agent in orchestration["agents"]
            ],
            "priority": [
                {"label": meta["label"], "color": meta["color"]} for meta in PRIORITY_META.values()
            ],
            "wave": wave_items,
        }

    # ------------------------------------------------------------------ 统计
    @staticmethod
    def _stats(modules: list[dict], built: dict, tasks: list[dict], orchestration: dict) -> dict:
        total_effort = round(sum(task["effort"] for task in tasks), 1)
        non_critical = sum(1 for task in tasks if not task["critical"])
        subtasks = sum(len(module_node["children"]) for module_node in built["tree"])
        return {
            "modules": len(modules),
            "subtasks": subtasks,
            "tasks": len(tasks),
            "agents": len(orchestration["agents"]),
            "total_effort": total_effort,
            "critical_days": orchestration["critical_days"],
            "parallel_ratio": round(non_critical / len(tasks), 2) if tasks else 0,
            "avg_parallelism": round(total_effort / orchestration["critical_days"], 2)
            if orchestration["critical_days"]
            else 0,
            "p0_tasks": sum(1 for task in tasks if task["priority"] == "P0"),
            "waves": len(orchestration["waves"]),
        }

    # ------------------------------------------------------------------ 扩展说明
    @staticmethod
    def _config_meta(llm_status: dict | None) -> dict:
        return {
            "files": [
                {"path": "config/modules.py", "desc": "任务模块模板、三层任务与模块依赖"},
                {"path": "config/domains.py", "desc": "产品域识别、能力特征与特征→模块映射"},
                {"path": "config/agents.py", "desc": "Agent 类型、职责与主题色"},
                {"path": "config/rules.py", "desc": "规模系数、优先级、波次与风险阈值"},
            ],
            "llm": llm_status or {"name": "rule-only", "enabled": False},
            "extend": [
                "新增产品类型：在 config/domains.py 的 DOMAINS 增加关键词与模块列表",
                "新增任务模板：在 config/modules.py 增加模块（capabilities 或 subtasks）",
                "接入真实大模型：实现 engine/llm.py 的 LLMAdapter 并设置 SE_WORKFLOW_LLM",
                "前端样式：static/css/style.css；图交互：static/js/result.js",
            ],
        }
