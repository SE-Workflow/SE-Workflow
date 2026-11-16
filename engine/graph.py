"""流程图算法：DAG 校验、分层、关键路径（CPM）与并行分组。

输入统一为：
    nodes: [{"id": "T01", "effort": 2.0, ...}]
    edges: [{"from": "T01", "to": "T02", ...}]

这里不做业务判断，只负责把“方框 + 连线”计算成一幅可读的流程图：
- 拓扑排序保证依赖方向；
- 层级 = 最长路径，用于 vis-network 的 hierarchical 排版；
- CPM 计算最早/最晚开始时间、时差与关键路径；
- 同一层内多于 1 个任务 → 可并行。
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable


def _ids(nodes: Iterable[dict]) -> list[str]:
    return [str(node["id"]) for node in nodes]


def _norm_edges(edges: Iterable[dict]) -> list[dict]:
    return [
        {"from": str(edge["from"]), "to": str(edge["to"])}
        for edge in edges
        if edge.get("from") and edge.get("to")
    ]


def build_adjacency(node_ids: list[str], edges: list[dict]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    valid = set(node_ids)
    predecessors: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    successors: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in _norm_edges(edges):
        source, target = edge["from"], edge["to"]
        if source == target or source not in valid or target not in valid:
            continue
        predecessors[target].append(source)
        successors[source].append(target)
    for node_id in node_ids:
        predecessors[node_id] = sorted(set(predecessors[node_id]))
        successors[node_id] = sorted(set(successors[node_id]))
    return predecessors, successors


def topological_order(node_ids: list[str], edges: list[dict]) -> list[str] | None:
    """Kahn 拓扑排序；有环时返回 None。"""
    predecessors, successors = build_adjacency(node_ids, edges)
    indegree = {node_id: len(predecessors[node_id]) for node_id in node_ids}
    queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for successor in successors[current]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    if len(order) != len(node_ids):
        return None
    return order


def _reachable(start: str, target: str, successors: dict[str, list[str]]) -> bool:
    """从 start 出发能否到达 target（用于加边时的环检测）。"""
    if start == target:
        return True
    stack = [start]
    seen = {start}
    while stack:
        current = stack.pop()
        for successor in successors[current]:
            if successor == target:
                return True
            if successor not in seen:
                seen.add(successor)
                stack.append(successor)
    return False


def remove_cycle_edges(node_ids: list[str], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """按输入顺序逐条保留不会产生环的边，返回 (保留, 丢弃)。"""
    kept: list[dict] = []
    dropped: list[dict] = []
    for edge in edges:
        source, target = str(edge.get("from") or ""), str(edge.get("to") or "")
        if not source or not target or source == target or source not in node_ids or target not in node_ids:
            dropped.append(edge)
            continue
        if any(item["from"] == source and item["to"] == target for item in kept):
            dropped.append(edge)
            continue
        _, successors = build_adjacency(node_ids, kept)
        if _reachable(target, source, successors):
            dropped.append(edge)
            continue
        kept.append(edge)
    return kept, dropped


def would_create_cycle(node_ids: list[str], edges: list[dict], source: str, target: str) -> bool:
    """给前端 / 编辑接口复用：新增 source→target 是否会形成环。"""
    if source == target or source not in node_ids or target not in node_ids:
        return True
    _, successors = build_adjacency(node_ids, edges)
    return _reachable(target, source, successors)


def transitive_reduction(node_ids: list[str], edges: list[dict]) -> list[dict]:
    """删除冗余的跨层依赖：若 A→B→C 已存在，则 A→C 可以省略。

    只用于让图更清爽，不改变任务之间的可达性（依赖语义等价）。
    """
    kept: list[dict] = []
    for index, edge in enumerate(edges):
        source, target = str(edge.get("from")), str(edge.get("to"))
        if source not in node_ids or target not in node_ids or source == target:
            continue
        others = [
            item
            for other_index, item in enumerate(edges)
            if other_index != index
            and item.get("from") in node_ids
            and item.get("to") in node_ids
        ]
        _, successors = build_adjacency(node_ids, others)
        if _reachable(source, target, successors):
            continue
        kept.append(edge)
    return kept


def compute_levels(node_ids: list[str], edges: list[dict]) -> dict[str, int]:
    """最长路径分层：根节点 level=0，保证每条边从低层指向高层。"""
    order = topological_order(node_ids, edges)
    if order is None:
        edges, _ = remove_cycle_edges(node_ids, edges)
        order = topological_order(node_ids, edges) or node_ids
    predecessors, _ = build_adjacency(node_ids, edges)
    levels = {node_id: 0 for node_id in node_ids}
    for node_id in order:
        if predecessors[node_id]:
            levels[node_id] = max(levels[pred] + 1 for pred in predecessors[node_id])
    return levels


def compute_schedule(nodes: list[dict], edges: list[dict]) -> dict:
    """CPM：最早/最晚开始、时差与关键路径。"""
    node_ids = _ids(nodes)
    effort = {str(node["id"]): max(0.5, float(node.get("effort") or 1.0)) for node in nodes}
    order = topological_order(node_ids, edges)
    if order is None:
        edges, _ = remove_cycle_edges(node_ids, edges)
        order = topological_order(node_ids, edges) or node_ids
    predecessors, successors = build_adjacency(node_ids, edges)

    earliest_start = {node_id: 0.0 for node_id in node_ids}
    earliest_finish = {node_id: 0.0 for node_id in node_ids}
    for node_id in order:
        earliest_start[node_id] = max(
            (earliest_finish[pred] for pred in predecessors[node_id]), default=0.0
        )
        earliest_finish[node_id] = earliest_start[node_id] + effort[node_id]
    makespan = max(earliest_finish.values(), default=0.0)

    latest_finish = {node_id: makespan for node_id in node_ids}
    latest_start = {node_id: makespan for node_id in node_ids}
    slack: dict[str, float] = {}
    critical: dict[str, bool] = {}
    for node_id in reversed(order):
        if successors[node_id]:
            latest_finish[node_id] = min(latest_start[successor] for successor in successors[node_id])
        else:
            latest_finish[node_id] = makespan
        latest_start[node_id] = latest_finish[node_id] - effort[node_id]
        slack[node_id] = round(latest_start[node_id] - earliest_start[node_id], 6)
        critical[node_id] = slack[node_id] <= 1e-6

    return {
        "order": order,
        "effort": effort,
        "earliest_start": earliest_start,
        "earliest_finish": earliest_finish,
        "latest_start": latest_start,
        "latest_finish": latest_finish,
        "slack": slack,
        "critical": critical,
        "makespan": round(makespan, 2),
    }


def find_critical_path(nodes: list[dict], edges: list[dict], schedule: dict) -> list[str]:
    """从终点沿关键前驱回溯，得到一条关键路径（可能不唯一，取工作量较大的一条）。"""
    node_ids = _ids(nodes)
    if not node_ids:
        return []
    effort = schedule["effort"]
    preds, _ = build_adjacency(node_ids, edges)
    makespan = schedule["makespan"]
    finals = [node_id for node_id in node_ids if schedule["critical"].get(node_id)]
    if not finals:
        finals = [node_id for node_id in node_ids if abs(schedule["earliest_finish"][node_id] - makespan) < 1e-6]
    if not finals:
        return []
    current = max(finals, key=lambda node_id: (schedule["earliest_finish"][node_id], effort.get(node_id, 0), node_id))
    path = [current]
    while True:
        candidates = [
            pred
            for pred in preds[current]
            if schedule["critical"].get(pred)
            and abs(schedule["earliest_finish"][pred] - schedule["earliest_start"][current]) < 1e-6
        ]
        if not candidates:
            break
        current = max(candidates, key=lambda node_id: (schedule["earliest_finish"][node_id], effort.get(node_id, 0)))
        path.append(current)
        if len(path) > len(node_ids) + 1:  # 防御性保护
            break
    return list(reversed(path))


def analyze_graph(nodes: list[dict], edges: list[dict]) -> dict:
    """一次性算出流程图需要的全部图指标。"""
    node_ids = _ids(nodes)
    clean_edges, dropped = remove_cycle_edges(node_ids, edges)
    levels = compute_levels(node_ids, clean_edges)
    schedule = compute_schedule(nodes, clean_edges)
    critical_path = find_critical_path(nodes, clean_edges, schedule)
    level_groups: dict[int, list[str]] = defaultdict(list)
    for node_id in node_ids:
        level_groups[levels[node_id]].append(node_id)
    parallel_levels = [
        {"level": level, "node_ids": member_ids}
        for level, member_ids in sorted(level_groups.items())
        if len(member_ids) > 1
    ]
    return {
        "edges": clean_edges,
        "dropped_edges": dropped,
        "levels": levels,
        "schedule": schedule,
        "critical_path": critical_path,
        "parallel_levels": parallel_levels,
    }
