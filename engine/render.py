"""渲染视图：把计划数据整理成页面需要的统计、图例、阶段与并行提示。

真正的图形绘制由前端 `static/js/result.js` + vis-network 完成；
这一层负责“给图配一套可读的说明”，保证前后端对同一份计划的解读一致。
"""

from __future__ import annotations

from config import EDGE_KIND_META, PRIORITY_META


def build_view(plan: dict) -> dict:
    nodes = plan.get("nodes") or []
    edges = plan.get("edges") or []
    stages = plan.get("stages") or []
    agents = plan.get("agents") or []
    nodes_by_id = {node["id"]: node for node in nodes}

    stage_cards = []
    for stage in stages:
        member_ids = [node_id for node_id in stage.get("node_ids", []) if node_id in nodes_by_id]
        members = [nodes_by_id[node_id] for node_id in member_ids]
        stage_cards.append(
            {
                "level": stage["level"],
                "name": stage["name"],
                "parallel": bool(stage.get("parallel")),
                "node_ids": member_ids,
                "count": len(member_ids),
                "effort": round(sum(node["effort"] for node in members), 1),
                "agents": sorted({node["agent"] for node in members}),
                "start": min((node["earliest_start"] for node in members), default=0),
                "end": max((node["earliest_finish"] for node in members), default=0),
            }
        )

    critical_nodes = [nodes_by_id[node_id] for node_id in plan.get("critical_path") or [] if node_id in nodes_by_id]
    critical_chain = [
        {
            "id": node["id"],
            "name": node["name"],
            "agent_name": node["agent_name"],
            "agent_color": node["agent_color"],
            "effort": node["effort"],
        }
        for node in critical_nodes
    ]

    module_groups: dict[str, list[str]] = {}
    for node in nodes:
        module_groups.setdefault(node["module"], []).append(node["id"])

    edge_kind_legend = [
        {
            "kind": kind,
            "label": meta["label"],
            "dashed": meta["dashed"],
            "dotted": bool(meta.get("dotted")),
            "count": sum(1 for edge in edges if edge.get("kind") == kind),
        }
        for kind, meta in EDGE_KIND_META.items()
        if any(edge.get("kind") == kind for edge in edges)
    ]

    priority_legend = [
        {
            "value": value,
            "label": meta["label"],
            "color": meta["color"],
            "count": sum(1 for node in nodes if node["priority"] == value),
        }
        for value, meta in PRIORITY_META.items()
    ]

    return {
        "stats": plan.get("stats") or {},
        "legend": plan.get("legend") or {},
        "agents": agents,
        "agent_load": [
            {
                "id": agent["id"],
                "name": agent["name"],
                "color": agent["color"],
                "icon": agent["icon"],
                "role": agent["role"],
                "node_count": agent["node_count"],
                "effort": agent["effort"],
                "share": agent["share"],
            }
            for agent in agents
        ],
        "stages": stage_cards,
        "critical_path": plan.get("critical_path") or [],
        "critical_chain": critical_chain,
        "parallel_groups": plan.get("parallel_groups") or [],
        "module_groups": module_groups,
        "edge_kinds": edge_kind_legend,
        "priorities": priority_legend,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
