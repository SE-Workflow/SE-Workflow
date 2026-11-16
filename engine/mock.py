"""Mock 模式：不调用大模型时的规则兜底演示。

数据来源优先复用项目自带的领域模板规则引擎（`engine/legacy`），
把它的“模块级任务”转换成 V5 的统一流程图结构：
    模块 → 一个任务方框
    模块依赖 → 方框之间的连线
    模块所属阶段 → 分层
这样即使没有 API Key，也能得到一张有业务含义、可编辑的工作流程图。
"""

from __future__ import annotations

from collections import defaultdict

from config import AGENTS, MAX_TASKS, PHASE_LABELS
from .graph import analyze_graph, transitive_reduction
from .legacy import build_legacy_plan


def _phase_of(module: dict) -> int:
    try:
        return int(module.get("phase", 3))
    except (TypeError, ValueError):
        return 3


def _stage_name(phase: int, level: int) -> str:
    base = PHASE_LABELS.get(phase, f"阶段 {level + 1}")
    return f"阶段 {level + 1} · {base}"


def _from_legacy(legacy: dict) -> tuple[dict, dict]:
    profile = legacy["profile"]
    modules = legacy["modules"][:MAX_TASKS]
    module_ids = {module["id"] for module in modules}
    module_by_id = {module["id"]: module for module in modules}

    tree_by_id = {node["id"]: node for node in legacy.get("tree", [])}
    id_map = {
        module_id: f"T{index:02d}"
        for index, module_id in enumerate((module["id"] for module in modules), start=1)
    }

    tasks: list[dict] = []
    for module in modules:
        tree = tree_by_id.get(module["id"], {})
        subtasks = [child.get("name", "") for child in tree.get("children", []) if child.get("name")]
        description = module.get("summary") or "完成本模块的方案、实现与验收。"
        if subtasks:
            description = f"{description.rstrip('。')}；覆盖：{'、'.join(subtasks[:6])}。"
        name = module["name"]
        tasks.append(
            {
                "id": id_map[module["id"]],
                "name": name[:60],
                "description": description[:600],
                "module": PHASE_LABELS.get(module.get("phase", 3), "研发实现"),
                "priority": module.get("priority", "P1"),
                "effort": max(0.5, float(module.get("effort") or 1.0)),
                "agent": module.get("agent", "backend"),
                "acceptance": f"「{name}」范围内的功能、接口与页面验收通过，P0/P1 缺陷清零，配置与文档已更新。",
            }
        )

    raw_edges = legacy.get("graph", {}).get("module", {}).get("edges", [])
    edges = []
    seen: set[tuple[str, str]] = set()
    for edge in raw_edges:
        source = id_map.get(edge.get("from"))
        target = id_map.get(edge.get("to"))
        if not source or not target or source == target:
            continue
        pair = (source, target)
        if pair in seen:
            continue
        seen.add(pair)
        edges.append({"from": source, "to": target, "kind": "dependency", "label": ""})
    if not edges:
        edges = [
            {"from": previous["id"], "to": current["id"], "kind": "dependency", "label": ""}
            for previous, current in zip(tasks, tasks[1:])
        ]
    else:
        # 模块级依赖比较密，做一次传递约简，让图更清爽（依赖可达性不变）
        edges = transitive_reduction([task["id"] for task in tasks], edges)

    # 依据依赖关系计算分层，再用模块 phase 给阶段起一个业务名字
    graph = analyze_graph(tasks, edges)
    levels = graph["levels"]
    phase_by_level: dict[int, int] = {}
    for module_id, node_id in id_map.items():
        module = module_by_id.get(module_id)
        if not module:
            continue
        level = levels.get(node_id, 0)
        phase = _phase_of(module)
        if level not in phase_by_level or phase < phase_by_level[level]:
            phase_by_level[level] = phase

    stages = []
    for level in sorted(phase_by_level):
        member_ids = sorted(node_id for node_id, node_level in levels.items() if node_level == level)
        if not member_ids:
            continue
        stages.append(
            {
                "level": level,
                "name": _stage_name(phase_by_level[level], level),
                "parallel": len(member_ids) > 1,
                "nodes": member_ids,
            }
        )

    assignments = [
        {
            "node": task["id"],
            "agent": task["agent"],
            "role": f"承接「{task['name']}」：{AGENTS.get(task['agent'], {}).get('role', '')}",
        }
        for task in tasks
    ]

    decomposition = {
        "summary": profile.get("summary") or f"围绕「{legacy.get('profile', {}).get('raw', '')[:40]}」的交付计划",
        "domain": profile.get("domain", {}).get("label", ""),
        "scale": profile.get("scale", {}).get("label", ""),
        "platforms": profile.get("platforms", []),
        "tasks": tasks,
        "warnings": [],
    }
    orchestration = {
        "summary": "Mock 规则引擎：按模块依赖计算分层，模块内部并行、跨模块串行收口。",
        "edges": edges,
        "stages": stages,
        "assignments": {item["node"]: {"agent": item["agent"], "role": item["role"]} for item in assignments},
        "parallel_groups": [],
        "warnings": [],
    }
    return decomposition, orchestration


def _generic_mock(requirement: str) -> tuple[dict, dict]:
    """极端情况下的最小兜底：固定 8 个通用软件工程任务。"""
    template = [
        ("需求澄清与验收标准", "pm", "规划与需求", 2.0, "P0"),
        ("信息架构与交互设计", "ux", "规划与需求", 3.0, "P0"),
        ("技术方案与数据模型", "architect", "设计与架构", 3.0, "P0"),
        ("后端核心接口实现", "backend", "业务研发", 6.0, "P0"),
        ("前端页面与交互实现", "frontend", "业务研发", 5.0, "P0"),
        ("联调与端到端测试", "qa", "集成与质量", 3.0, "P0"),
        ("CI/CD 与部署上线", "devops", "发布与运维", 2.0, "P1"),
        ("运营配置与数据看板", "ops", "发布与运维", 2.0, "P1"),
    ]
    tasks = [
        {
            "id": f"T{index:02d}",
            "name": name,
            "description": f"完成「{name}」的方案、实现、自测与文档更新。",
            "module": module,
            "priority": priority,
            "effort": effort,
            "agent": agent,
            "acceptance": "关键产物通过评审，主流程与异常分支验证通过，文档更新。",
        }
        for index, (name, agent, module, effort, priority) in enumerate(template, start=1)
    ]
    edges = [
        {"from": previous["id"], "to": current["id"], "kind": "dependency", "label": ""}
        for previous, current in zip(tasks, tasks[1:])
    ]
    stages = []
    by_stage: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        by_stage[task["module"]].append(task["id"])
    for level, (name, node_ids) in enumerate(by_stage.items()):
        stages.append({"level": level, "name": name, "parallel": len(node_ids) > 1, "nodes": node_ids})
    return (
        {
            "summary": f"围绕「{requirement.strip()[:60]}」的通用软件交付工作流。",
            "domain": "通用软件",
            "scale": "中型",
            "platforms": ["Web"],
            "tasks": tasks,
            "warnings": ["规则引擎未能识别需求细节，已使用通用任务模板。"],
        },
        {
            "summary": "按通用软件工程阶段串行推进，测试与部署收口。",
            "edges": edges,
            "stages": stages,
            "assignments": {},
            "parallel_groups": [],
            "warnings": ["已使用通用 Mock 模板。"],
        },
    )


def build_mock(requirement: str) -> tuple[dict, dict]:
    """返回 (任务分解, Agent 编排) 两个阶段的结构，与 LLM 输出同构。"""
    try:
        legacy = build_legacy_plan(requirement)
        if legacy.get("modules"):
            return _from_legacy(legacy)
    except Exception:  # noqa: BLE001 - Mock 必须永远可用
        pass
    return _generic_mock(requirement)
