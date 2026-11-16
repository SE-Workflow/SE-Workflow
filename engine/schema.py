"""结构化数据层：LLM 输出 → 可校验、可渲染的统一流程图 JSON。

关键设计：
- LLM 的输出永远不可信，先做字段归一化、类型收敛、ID 对齐、边的合法性检查；
- 所有节点最终都落在同一个计划结构里（nodes + edges + stages + agents + stats）；
- 校验失败抛 `ValidationError`，由上层触发“纠错重试”或回退 Mock；
- 前端编辑保存时也复用 `rebuild_plan`，保证图与数据始终一致。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable

from config import (
    AGENTS,
    CRITICAL_COLOR,
    EDGE_KIND_META,
    MAX_EFFORT,
    MAX_TASKS,
    MIN_EFFORT,
    PHASE_LABELS,
    PRIORITY_META,
    PROMPT_VERSION,
    resolve_agent,
)
from .graph import analyze_graph, build_adjacency, remove_cycle_edges, topological_order, would_create_cycle

PLAN_VERSION = "2.0.0"
PRIORITY_VALUES = ("P0", "P1", "P2")
EDGE_KINDS = tuple(EDGE_KIND_META)


class ValidationError(ValueError):
    """LLM 输出或保存数据不符合结构要求。"""

    def __init__(self, message: str, errors: Iterable[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.errors = list(errors or [])


# ======================================================================
# 基础工具
# ======================================================================
def _first(mapping: dict, keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return default


def _text(value: Any, limit: int = 500, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return default
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit] if text else default


def _as_float(value: Any, default: float, *, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return round(min(maximum, max(minimum, number)), 2)


def _optional_float(value: Any, *, limit: float = 1_000_000.0) -> float | None:
    """坐标等可选数值：非法 / 越界时返回 None，而不是把计划整体判错。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or abs(number) > limit:
        return None
    return round(number, 1)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y", "是", "并行"}


def _clean_id(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\s\r\n\t\"'`，。；、]+", "", text)
    return text[:32]


def _unwrap(payload: Any) -> Any:
    """兼容 {"data": {...}} / {"result": {...}} 这类多包一层的情况。"""
    if isinstance(payload, dict):
        for key in ("data", "result", "output", "plan"):
            nested = payload.get(key)
            if isinstance(nested, (dict, list)) and len(payload) <= 2:
                return nested
    return payload


def _normalize_priority(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in PRIORITY_VALUES:
        return text
    mapping = {
        "0": "P0",
        "1": "P1",
        "2": "P2",
        "高": "P0",
        "中": "P1",
        "低": "P2",
        "HIGH": "P0",
        "MEDIUM": "P1",
        "LOW": "P2",
        "CRITICAL": "P0",
    }
    return mapping.get(text, "P1")


def _agent_meta(agent_id: str) -> dict:
    meta = AGENTS.get(agent_id) or AGENTS["backend"]
    return {
        "agent": agent_id if agent_id in AGENTS else "backend",
        "agent_name": meta["name"],
        "agent_color": meta["color"],
        "agent_icon": meta["icon"],
        "agent_role": meta["role"],
    }


def _resolve_agent(value: Any, fallback: str = "backend") -> str:
    return resolve_agent(value, fallback=fallback)


def _public_requirement(requirement: str | dict) -> dict:
    if isinstance(requirement, dict):
        raw = _text(_first(requirement, ["raw", "text", "requirement"], ""), 20000)
        return {
            "raw": raw,
            "summary": _text(_first(requirement, ["summary"], ""), 200, raw[:120]),
            "domain": _text(_first(requirement, ["domain"], ""), 40),
            "scale": _text(_first(requirement, ["scale"], ""), 20),
            "platforms": [
                _text(item, 40) for item in (requirement.get("platforms") or []) if _text(item, 40)
            ][:6],
        }
    raw = str(requirement or "").strip()[:20000]
    return {"raw": raw, "summary": raw[:120], "domain": "", "scale": "", "platforms": []}


# ======================================================================
# 阶段一：任务分解
# ======================================================================
def _normalize_task(raw: dict, index: int, warnings: list[str]) -> dict | None:
    name = _text(_first(raw, ["name", "title", "task_name", "task"]), 60)
    if not name:
        return None
    task_id = _clean_id(_first(raw, ["id", "task_id", "key", "code"]))
    if not task_id:
        task_id = f"T{index:02d}"
    else:
        id_match = re.fullmatch(r"[Tt]0*(\d+)", task_id)
        if id_match:
            task_id = f"T{int(id_match.group(1)):02d}"
    description = _text(
        _first(raw, ["description", "desc", "detail", "goal"]),
        600,
        f"完成「{name}」的设计、实现与自测。",
    )
    module = _text(
        _first(raw, ["module", "module_name", "category", "phase", "area"]),
        40,
        "通用",
    )
    acceptance = _text(
        _first(raw, ["acceptance", "acceptance_criteria", "done", "definition_of_done"]),
        300,
        "功能按设计可用，主流程与异常分支验证通过，文档更新。",
    )
    agent_value = _first(raw, ["agent", "suggested_agent", "agent_type", "owner", "assignee"])
    agent_id = _resolve_agent(agent_value, fallback="backend")
    if agent_value and str(agent_value).strip() and agent_id == "backend" and str(agent_value).strip().lower() not in AGENTS:
        warnings.append(f"任务 {task_id} 的 Agent「{_text(agent_value, 20)}」不在配置清单中，已归一到 backend。")
    return {
        "id": task_id,
        "name": name,
        "description": description,
        "module": module,
        "priority": _normalize_priority(_first(raw, ["priority", "prio", "severity"])),
        "effort": _as_float(
            _first(raw, ["effort", "effort_days", "estimate", "estimated_effort", "days"]),
            2.0,
            minimum=MIN_EFFORT,
            maximum=MAX_EFFORT,
        ),
        "agent": agent_id,
        "acceptance": acceptance,
    }


def normalize_decomposition(payload: Any, requirement: str = "") -> dict:
    """校验并归一化阶段一输出。"""
    payload = _unwrap(payload)
    if isinstance(payload, list):
        payload = {"tasks": payload}
    if not isinstance(payload, dict):
        raise ValidationError("任务分解结果必须是 JSON 对象或数组")

    raw_tasks = _first(payload, ["tasks", "task_list", "nodes", "subtasks", "items"])
    if raw_tasks is None and _first(payload, ["name", "title"]):
        raw_tasks = [payload]
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValidationError("任务分解结果缺少 tasks 数组，或数组为空")

    warnings: list[str] = []
    tasks: list[dict] = []
    seen_ids: Counter[str] = Counter()
    for index, raw in enumerate(raw_tasks, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"第 {index} 个任务不是对象，已忽略。")
            continue
        task = _normalize_task(raw, index, warnings)
        if task is None:
            warnings.append(f"第 {index} 个任务缺少名称，已忽略。")
            continue
        base_id = task["id"]
        seen_ids[base_id] += 1
        if seen_ids[base_id] > 1:
            task["id"] = f"{base_id}-{seen_ids[base_id]}"
            warnings.append(f"任务 ID「{base_id}」重复，已改为 {task['id']}。")
        tasks.append(task)

    if len(tasks) < 3:
        raise ValidationError(f"有效任务只有 {len(tasks)} 个，至少需要 3 个任务")
    if len(tasks) > MAX_TASKS:
        warnings.append(f"任务数 {len(tasks)} 超过上限 {MAX_TASKS}，仅保留前 {MAX_TASKS} 个。")
        tasks = tasks[:MAX_TASKS]

    summary = _text(
        _first(payload, ["summary", "goal", "overview", "description"]),
        200,
        (requirement or "").strip()[:120] or "LLM 生成的工作流程",
    )
    scale = _text(_first(payload, ["scale", "project_scale"]), 20)
    platforms = payload.get("platforms") or payload.get("platform") or []
    if isinstance(platforms, str):
        platforms = [platforms]
    platforms = [_text(item, 40) for item in platforms if _text(item, 40)]

    return {
        "summary": summary,
        "domain": _text(_first(payload, ["domain", "domain_name", "industry"]), 40),
        "scale": scale,
        "platforms": platforms[:6],
        "tasks": tasks,
        "warnings": warnings,
    }


# ======================================================================
# 阶段二：Agent 编排
# ======================================================================
def _build_id_lookup(tasks: list[dict]) -> tuple[set[str], dict[str, str], dict[str, str]]:
    ids = {task["id"] for task in tasks}
    lowered = {task["id"].lower(): task["id"] for task in tasks}
    names = {task["name"].strip().lower(): task["id"] for task in tasks if task["name"].strip()}
    return ids, lowered, names


def _resolve_node_id(value: Any, ids: set[str], lowered: dict[str, str], names: dict[str, str]) -> str | None:
    text = str(value or "").strip().strip("\"'`#")
    if not text:
        return None
    if text in ids:
        return text
    if text.lower() in lowered:
        return lowered[text.lower()]
    if text.lower() in names:
        return names[text.lower()]
    # 纯数字 / T1 这类简写，尝试映射到 T01
    if text.isdigit():
        candidate = f"T{int(text):02d}"
        if candidate in ids:
            return candidate
    match = re.fullmatch(r"([A-Za-z]+)0*(\d+)", text)
    if match:
        candidate = f"{match.group(1).upper()}{int(match.group(2)):02d}"
        if candidate in ids:
            return candidate
    for task_id in ids:
        if text.lower() in task_id.lower() or task_id.lower() in text.lower():
            return task_id
    return None


def _normalize_edge_kind(value: Any) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "dependency": "dependency",
        "dep": "dependency",
        "block": "dependency",
        "serial": "dependency",
        "依赖": "dependency",
        "flow": "flow",
        "handoff": "flow",
        "交接": "flow",
        "流转": "flow",
        "review": "review",
        "approval": "review",
        "评审": "review",
        "验收": "review",
    }
    return mapping.get(text, "dependency")


def normalize_orchestration(payload: Any, tasks: list[dict]) -> dict:
    """校验并归一化阶段二输出；边/阶段/指派都会对齐到阶段一的任务 ID。"""
    payload = _unwrap(payload)
    if isinstance(payload, list):
        payload = {"edges": payload}
    if not isinstance(payload, dict):
        raise ValidationError("编排结果必须是 JSON 对象")

    warnings: list[str] = []
    ids, lowered, names = _build_id_lookup(tasks)

    raw_edges = _first(payload, ["edges", "dependencies", "links", "relations", "connections"])
    if not isinstance(raw_edges, list):
        raw_edges = []
    edges: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_edges, start=1):
        if not isinstance(raw, dict):
            continue
        source = _resolve_node_id(
            _first(raw, ["from", "source", "from_id", "source_id", "parent", "predecessor"]), ids, lowered, names
        )
        target = _resolve_node_id(
            _first(raw, ["to", "target", "to_id", "target_id", "child", "successor"]), ids, lowered, names
        )
        if not source or not target:
            warnings.append(f"第 {index} 条依赖引用了不存在的任务，已忽略。")
            continue
        if source == target:
            warnings.append(f"任务 {source} 存在自环，已忽略。")
            continue
        pair = (source, target)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        edges.append(
            {
                "from": source,
                "to": target,
                "kind": _normalize_edge_kind(_first(raw, ["kind", "type", "relation"])),
                "label": _text(_first(raw, ["label", "name", "condition"]), 30),
            }
        )

    # 边必须是 DAG；删掉会形成环的边，并给出提示
    clean_edges, dropped = remove_cycle_edges([task["id"] for task in tasks], edges)
    if dropped:
        warnings.append(f"编排中存在 {len(dropped)} 条会形成环的依赖，已自动移除。")
    edges = clean_edges

    # 没有边时退化为串行链，保证图始终可读
    if not edges:
        warnings.append("布局阶段未返回有效依赖边，已按任务顺序生成串行依赖。")
        edges = [
            {"from": previous["id"], "to": current["id"], "kind": "dependency", "label": ""}
            for previous, current in zip(tasks, tasks[1:])
        ]

    # ---- 阶段（分层 / 并行分组）
    raw_stages = _first(payload, ["stages", "levels", "layers", "stage_groups", "phases"])
    if not isinstance(raw_stages, list):
        raw_stages = []
    stages: list[dict] = []
    stage_node_seen: set[str] = set()
    for index, raw in enumerate(raw_stages):
        if isinstance(raw, list):
            stage = {"level": index, "name": "", "parallel": len(raw) > 1, "nodes": raw}
        elif isinstance(raw, dict):
            level_value = _first(raw, ["level", "index", "order", "stage"], index)
            try:
                level = int(level_value)
            except (TypeError, ValueError):
                level = index
            stage = {
                "level": max(0, level),
                "name": _text(_first(raw, ["name", "title", "label", "stage_name"]), 40),
                "parallel": _as_bool(_first(raw, ["parallel", "concurrent", "is_parallel"]), False),
                "nodes": _first(raw, ["nodes", "tasks", "node_ids", "task_ids", "members"], []),
            }
        else:
            continue
        if isinstance(stage["nodes"], str):
            stage["nodes"] = [stage["nodes"]]
        resolved: list[str] = []
        for value in stage["nodes"] if isinstance(stage["nodes"], list) else []:
            node_id = _resolve_node_id(value, ids, lowered, names)
            if node_id and node_id not in stage_node_seen:
                stage_node_seen.add(node_id)
                resolved.append(node_id)
        if resolved:
            stage["nodes"] = resolved
            stages.append(stage)
    if stages and len(stage_node_seen) < len(tasks):
        missing = len(tasks) - len(stage_node_seen)
        warnings.append(f"有 {missing} 个任务未出现在阶段划分中，将按依赖关系自动补层。")

    # ---- Agent 指派
    raw_assignments = _first(payload, ["assignments", "agents", "agent_assignments", "agent_map", "owners"])
    assignments: dict[str, dict] = {}
    if isinstance(raw_assignments, dict):
        iterable = [
            {"node": key, "agent": value}
            for key, value in raw_assignments.items()
        ]
    elif isinstance(raw_assignments, list):
        iterable = raw_assignments
    else:
        iterable = []
    for raw in iterable:
        if not isinstance(raw, dict):
            continue
        node_id = _resolve_node_id(
            _first(raw, ["node", "id", "task", "task_id", "name"]), ids, lowered, names
        )
        if not node_id:
            continue
        agent_value = _first(raw, ["agent", "agent_id", "owner", "assignee", "role_owner"], "")
        if isinstance(agent_value, dict):
            agent_value = _first(agent_value, ["id", "agent", "name"], "")
        agent_id = _resolve_agent(agent_value, fallback="backend")
        assignments[node_id] = {
            "agent": agent_id,
            "role": _text(_first(raw, ["role", "responsibility", "duty"]), 120),
        }
    if assignments and len(assignments) < len(tasks):
        warnings.append(f"有 {len(tasks) - len(assignments)} 个任务未获得 Agent 指派，已沿用任务分解建议。")

    # ---- 显式并行组
    raw_groups = _first(payload, ["parallel_groups", "parallel_tasks", "concurrent_groups"])
    groups: list[dict] = []
    if isinstance(raw_groups, list):
        for index, raw in enumerate(raw_groups, start=1):
            if isinstance(raw, list):
                name, members = "", raw
            elif isinstance(raw, dict):
                name = _text(_first(raw, ["name", "title", "label"]), 40)
                members = _first(raw, ["nodes", "tasks", "node_ids", "task_ids", "members"], [])
            else:
                continue
            if isinstance(members, str):
                members = [members]
            resolved = []
            for value in members if isinstance(members, list) else []:
                node_id = _resolve_node_id(value, ids, lowered, names)
                if node_id and node_id not in resolved:
                    resolved.append(node_id)
            if len(resolved) >= 2:
                groups.append({"name": name or f"并行组 {index}", "node_ids": resolved})

    summary = _text(_first(payload, ["summary", "strategy", "overview", "description"]), 300)

    return {
        "summary": summary,
        "edges": edges,
        "stages": stages,
        "assignments": assignments,
        "parallel_groups": groups,
        "warnings": warnings,
    }


def fallback_orchestration(tasks: list[dict]) -> dict:
    """阶段二失败时的规则兜底：按任务顺序串行，Agent 沿用阶段一建议。"""
    return {
        "summary": "阶段二编排不可用，已按任务顺序生成串行依赖，Agent 沿用任务分解建议。",
        "edges": [
            {"from": previous["id"], "to": current["id"], "kind": "dependency", "label": ""}
            for previous, current in zip(tasks, tasks[1:])
        ],
        "stages": [],
        "assignments": {},
        "parallel_groups": [],
        "warnings": ["阶段二（Agent 编排）失败，已回退为规则串行编排。"],
    }


# ======================================================================
# 计划组装
# ======================================================================
def _stage_members(stage: dict) -> list[str]:
    """兼容阶段一的 LLM 输出（nodes）与前端保存后的结构（node_ids）。"""
    members = stage.get("nodes")
    if not isinstance(members, list):
        members = stage.get("node_ids")
    return [str(item) for item in (members or [])]


def _stage_names_by_level(stages: list[dict], levels: dict[str, int]) -> dict[int, str]:
    votes: dict[int, Counter[str]] = defaultdict(Counter)
    for stage in stages:
        name = _text(stage.get("name"), 40)
        if not name:
            continue
        for node_id in _stage_members(stage):
            if node_id in levels:
                votes[levels[node_id]][name] += 1
    names: dict[int, str] = {}
    for level, counter in votes.items():
        names[level] = counter.most_common(1)[0][0]
    return names


def _apply_level_hints(
    node_ids: list[str],
    edges: list[dict],
    levels: dict[str, int],
    stages: list[dict] | None,
) -> dict[str, int]:
    """把 LLM 的阶段层级当作排版提示，同时强制满足依赖方向。

    依赖边决定的下限不能被打破；LLM 希望把某个任务放得更靠后再抬高它。
    最后把层级压缩成连续的 0..N，避免 vis-network 出现大片空白层。
    """
    hinted = dict(levels)
    for stage in stages or []:
        try:
            stage_level = max(0, int(stage.get("level", 0)))
        except (TypeError, ValueError):
            continue
        for node_id in _stage_members(stage):
            if node_id in hinted:
                hinted[node_id] = max(hinted[node_id], stage_level)

    order = topological_order(node_ids, edges) or node_ids
    _, successors = build_adjacency(node_ids, edges)
    for node_id in order:
        for successor in successors.get(node_id, []):
            hinted[successor] = max(hinted[successor], hinted[node_id] + 1)

    unique = sorted(set(hinted.values()))
    remap = {value: index for index, value in enumerate(unique)}
    return {node_id: remap[value] for node_id, value in hinted.items()}


def _normalize_meta(meta: dict | None) -> dict:
    meta = dict(meta or {})
    engine = str(meta.get("engine") or "llm")
    labels = {
        "llm": "LLM 两阶段编排",
        "llm-fallback": "LLM 分解 + 规则编排兜底",
        "mock": "Mock 规则模拟",
        "edited": "人工编辑后的方案",
    }
    return {
        "version": PLAN_VERSION,
        "engine": engine,
        "engine_label": str(meta.get("engine_label") or labels.get(engine, engine)),
        "model": _text(meta.get("model"), 80),
        "base_url": _text(meta.get("base_url"), 200),
        "generated_at": str(meta.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "duration_ms": int(meta.get("duration_ms") or 0),
        "degraded": bool(meta.get("degraded")),
        "degraded_reason": _text(meta.get("degraded_reason"), 300),
        "llm_calls": list(meta.get("llm_calls") or []),
        "prompt_version": str(meta.get("prompt_version") or PROMPT_VERSION),
        "edited": bool(meta.get("edited")),
        "edited_at": _text(meta.get("edited_at"), 40),
        "plan_id": _text(meta.get("plan_id"), 40),
    }


def finalize_plan(
    *,
    requirement: str | dict,
    nodes: list[dict],
    edges: list[dict],
    stages: list[dict] | None = None,
    meta: dict | None = None,
    warnings: Iterable[str] | None = None,
    parallel_groups: list[dict] | None = None,
) -> dict:
    """把节点、边、阶段组装成最终计划：补齐层级、关键路径、统计、图例。"""
    warnings = list(warnings or [])
    if not isinstance(nodes, list) or not nodes:
        raise ValidationError("方案中没有任务节点")

    seen: set[str] = set()
    clean_nodes: list[dict] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        node_id = _clean_id(node.get("id")) or f"T{index + 1:02d}"
        if node_id in seen:
            node_id = f"{node_id}-{index + 1}"
        seen.add(node_id)
        agent_id = _resolve_agent(node.get("agent"))
        agent_meta = _agent_meta(agent_id)
        clean_nodes.append(
            {
                "id": node_id,
                "name": _text(node.get("name"), 60, f"任务 {index + 1}"),
                "description": _text(node.get("description"), 600, "暂无描述"),
                "module": _text(node.get("module"), 40, "通用"),
                "priority": _normalize_priority(node.get("priority")),
                "effort": _as_float(node.get("effort"), 2.0, minimum=MIN_EFFORT, maximum=MAX_EFFORT),
                "acceptance": _text(node.get("acceptance"), 300, "通过验收用例，文档更新。"),
                "agent": agent_meta["agent"],
                "agent_name": agent_meta["agent_name"],
                "agent_color": agent_meta["agent_color"],
                "agent_icon": agent_meta["agent_icon"],
                "agent_role": _text(node.get("agent_role"), 120, agent_meta["agent_role"]),
                "role": _text(node.get("role"), 120, agent_meta["agent_role"]),
                "order": int(node.get("order") or index),
                "is_new": bool(node.get("is_new")),
                # 前端自由拖拽后的坐标；pinned=True 表示用户手动固定过位置
                "x": _optional_float(node.get("x")),
                "y": _optional_float(node.get("y")),
                "pinned": bool(node.get("pinned")),
            }
        )

    node_ids = [node["id"] for node in clean_nodes]
    id_set = set(node_ids)
    clean_edges: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for edge in edges or []:
        if not isinstance(edge, dict):
            continue
        source = _clean_id(edge.get("from"))
        target = _clean_id(edge.get("to"))
        if source not in id_set or target not in id_set or source == target:
            continue
        pair = (source, target)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        clean_edges.append(
            {
                "from": source,
                "to": target,
                "kind": _normalize_edge_kind(edge.get("kind")),
                "label": _text(edge.get("label"), 30),
            }
        )

    graph = analyze_graph(clean_nodes, clean_edges)
    if graph["dropped_edges"]:
        warnings.append(f"存在 {len(graph['dropped_edges'])} 条非法或成环连线，已自动移除。")
    clean_edges = graph["edges"]
    schedule = graph["schedule"]
    levels = _apply_level_hints([node["id"] for node in clean_nodes], clean_edges, graph["levels"], stages)

    stage_names = _stage_names_by_level(stages or [], levels)
    level_groups: dict[int, list[str]] = defaultdict(list)
    for node in clean_nodes:
        level = levels[node["id"]]
        stage = stage_names.get(level) or PHASE_LABELS.get(level) or f"阶段 {level + 1}"
        node["level"] = level
        node["stage"] = stage
        node["critical"] = bool(schedule["critical"].get(node["id"]))
        node["earliest_start"] = round(schedule["earliest_start"][node["id"]], 2)
        node["earliest_finish"] = round(schedule["earliest_finish"][node["id"]], 2)
        node["latest_start"] = round(schedule["latest_start"][node["id"]], 2)
        node["slack"] = round(schedule["slack"][node["id"]], 2)
        node["depends_on"] = sorted(
            edge["from"] for edge in clean_edges if edge["to"] == node["id"]
        )
        node["successors"] = sorted(edge["to"] for edge in clean_edges if edge["from"] == node["id"])
        level_groups[level].append(node["id"])

    nodes_by_id = {node["id"]: node for node in clean_nodes}
    for index, edge in enumerate(clean_edges, start=1):
        source = nodes_by_id[edge["from"]]
        target = nodes_by_id[edge["to"]]
        edge["id"] = f"E{index:03d}"
        edge["critical"] = bool(
            source["critical"]
            and target["critical"]
            and abs(source["earliest_finish"] - target["earliest_start"]) <= 1e-6
        )

    stage_list = []
    for level in sorted(level_groups):
        member_ids = sorted(level_groups[level], key=lambda node_id: (nodes_by_id[node_id]["order"], node_id))
        stage_list.append(
            {
                "level": level,
                "name": stage_names.get(level) or PHASE_LABELS.get(level) or f"阶段 {level + 1}",
                "parallel": len(member_ids) > 1,
                "node_ids": member_ids,
                "effort": round(sum(nodes_by_id[node_id]["effort"] for node_id in member_ids), 1),
            }
        )

    # ---- 并行分组：合并 LLM 显式分组与自动同层分组
    merged_groups: list[dict] = []
    seen_groups: set[tuple[str, ...]] = set()
    for group in parallel_groups or []:
        members = [node_id for node_id in group.get("node_ids", []) if node_id in id_set]
        if len(members) < 2:
            continue
        key = tuple(sorted(members))
        if key in seen_groups:
            continue
        seen_groups.add(key)
        merged_groups.append(
            {
                "name": group.get("name") or "可并行任务",
                "level": levels.get(members[0]),
                "node_ids": members,
                "source": group.get("source") or "llm",
            }
        )
    for stage in stage_list:
        if len(stage["node_ids"]) < 2:
            continue
        key = tuple(sorted(stage["node_ids"]))
        if key in seen_groups:
            continue
        seen_groups.add(key)
        merged_groups.append(
            {
                "name": f"{stage['name']} · 可并行",
                "level": stage["level"],
                "node_ids": list(stage["node_ids"]),
                "source": "auto",
            }
        )
    merged_groups.sort(key=lambda item: (item["level"] if item["level"] is not None else 0, item["name"]))

    # ---- Agent 统计
    agent_aggregate: dict[str, dict] = {}
    for node in clean_nodes:
        record = agent_aggregate.setdefault(
            node["agent"],
            {
                "id": node["agent"],
                "name": node["agent_name"],
                "role": node["agent_role"],
                "color": node["agent_color"],
                "icon": node["agent_icon"],
                "node_ids": [],
                "effort": 0.0,
                "p0_count": 0,
            },
        )
        record["node_ids"].append(node["id"])
        record["effort"] += node["effort"]
        record["p0_count"] += 1 if node["priority"] == "P0" else 0
    total_effort = sum(node["effort"] for node in clean_nodes)
    agents = []
    for record in agent_aggregate.values():
        record["effort"] = round(record["effort"], 1)
        record["node_count"] = len(record["node_ids"])
        record["share"] = round(record["effort"] / total_effort, 3) if total_effort else 0
        record["node_ids"].sort()
        agents.append(record)
    agents.sort(key=lambda item: (-item["effort"], item["name"]))

    modules = []
    for node in clean_nodes:
        if node["module"] not in modules:
            modules.append(node["module"])
    critical_nodes = [node["id"] for node in clean_nodes if node["critical"]]
    parallel_ids = {
        node_id for stage in stage_list if len(stage["node_ids"]) > 1 for node_id in stage["node_ids"]
    }
    stats = {
        "nodes": len(clean_nodes),
        "edges": len(clean_edges),
        "agents": len(agents),
        "modules": len(modules),
        "stages": len(stage_list),
        "total_effort": round(total_effort, 1),
        "critical_days": schedule["makespan"],
        "critical_nodes": len(critical_nodes),
        "parallel_nodes": len(parallel_ids),
        "parallel_ratio": round(len(parallel_ids) / len(clean_nodes), 2) if clean_nodes else 0,
        "avg_parallelism": round(total_effort / schedule["makespan"], 2) if schedule["makespan"] else 0,
        "p0_nodes": sum(1 for node in clean_nodes if node["priority"] == "P0"),
    }

    used_agent_ids = {node["agent"] for node in clean_nodes}
    legend = {
        "agents": [
            {"id": agent["id"], "label": agent["name"], "color": agent["color"], "icon": agent["icon"]}
            for agent in agents
        ],
        "priorities": [
            {"value": value, "label": meta["label"], "color": meta["color"]}
            for value, meta in PRIORITY_META.items()
        ],
        "edge_kinds": [
            {
                "kind": kind,
                "label": meta["label"],
                "dashed": meta["dashed"],
                "dotted": bool(meta.get("dotted")),
            }
            for kind, meta in EDGE_KIND_META.items()
            if any(edge["kind"] == kind for edge in clean_edges) or kind == "dependency"
        ],
        "critical": {"label": "关键路径", "color": CRITICAL_COLOR},
        "stages": [{"level": stage["level"], "name": stage["name"]} for stage in stage_list],
        "agents_used": sorted(used_agent_ids),
    }

    return {
        "meta": _normalize_meta(meta),
        "requirement": _public_requirement(requirement),
        "nodes": clean_nodes,
        "edges": clean_edges,
        "stages": stage_list,
        "critical_path": graph["critical_path"],
        "parallel_groups": merged_groups,
        "stats": stats,
        "agents": agents,
        "legend": legend,
        "warnings": list(dict.fromkeys(str(item) for item in warnings if item)),
    }


def build_plan(
    *,
    requirement: str,
    decomposition: dict,
    orchestration: dict,
    meta: dict | None = None,
    warnings: Iterable[str] | None = None,
) -> dict:
    """阶段一 + 阶段二 → 统一计划。"""
    tasks = decomposition["tasks"]
    assignments = orchestration.get("assignments") or {}
    nodes: list[dict] = []
    for index, task in enumerate(tasks):
        assignment = assignments.get(task["id"]) or {}
        agent_id = _resolve_agent(assignment.get("agent") or task["agent"])
        agent_meta = _agent_meta(agent_id)
        nodes.append(
            {
                "id": task["id"],
                "name": task["name"],
                "description": task["description"],
                "module": task["module"],
                "priority": task["priority"],
                "effort": task["effort"],
                "acceptance": task["acceptance"],
                "agent": agent_id,
                "agent_name": agent_meta["agent_name"],
                "agent_color": agent_meta["agent_color"],
                "agent_icon": agent_meta["agent_icon"],
                "agent_role": agent_meta["agent_role"],
                "role": assignment.get("role") or agent_meta["agent_role"],
                "order": index,
                "is_new": False,
            }
        )
    plan = finalize_plan(
        requirement=requirement,
        nodes=nodes,
        edges=orchestration.get("edges") or [],
        stages=orchestration.get("stages") or [],
        meta=meta,
        warnings=list(warnings or []) + list(decomposition.get("warnings") or []) + list(orchestration.get("warnings") or []),
        parallel_groups=orchestration.get("parallel_groups") or [],
    )
    plan["requirement"].update(
        {
            "summary": decomposition.get("summary") or plan["requirement"]["summary"],
            "domain": decomposition.get("domain") or plan["requirement"]["domain"],
            "scale": decomposition.get("scale") or plan["requirement"]["scale"],
            "platforms": decomposition.get("platforms") or plan["requirement"]["platforms"],
        }
    )
    if orchestration.get("summary"):
        plan["meta"]["orchestration_summary"] = orchestration["summary"]
    return plan


def rebuild_plan(plan: dict) -> dict:
    """前端编辑保存后重新计算图指标，保证数据与图一致。"""
    if not isinstance(plan, dict):
        raise ValidationError("方案数据格式不正确")
    nodes = plan.get("nodes")
    edges = plan.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise ValidationError("方案缺少任务节点")
    if not isinstance(edges, list):
        edges = []
    stages = plan.get("stages") if isinstance(plan.get("stages"), list) else []
    warning_list = list(plan.get("warnings") or [])
    warning_list.append("方案已通过网页编辑并重新保存。")
    meta = dict(plan.get("meta") or {})
    meta["edited"] = True
    meta["edited_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rebuilt = finalize_plan(
        requirement=plan.get("requirement") or "",
        nodes=nodes,
        edges=edges,
        stages=stages,
        meta=meta,
        warnings=warning_list,
        parallel_groups=plan.get("parallel_groups") or [],
    )
    if plan.get("meta", {}).get("orchestration_summary"):
        rebuilt["meta"]["orchestration_summary"] = plan["meta"]["orchestration_summary"]
    return rebuilt


def validate_saved_plan(payload: Any) -> dict:
    """保存接口的入口：允许传 {plan: {...}} 或直接传 plan。"""
    if isinstance(payload, dict) and isinstance(payload.get("plan"), dict):
        plan = payload["plan"]
    else:
        plan = payload
    return rebuild_plan(plan)


def edge_would_cycle(plan: dict, source: str, target: str) -> bool:
    """给 API / 前端复用的加边环检测。"""
    nodes = plan.get("nodes") or []
    edges = plan.get("edges") or []
    return would_create_cycle(
        [str(node.get("id")) for node in nodes],
        [{"from": edge.get("from"), "to": edge.get("to")} for edge in edges],
        str(source),
        str(target),
    )
