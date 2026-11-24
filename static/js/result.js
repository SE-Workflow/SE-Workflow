/* =====================================================================
   SE Workflow Studio · V5 唯一结果页
   - 一幅工作流程图：方框 = 任务，连线 / 分层 = Agent 编排
   - 点击方框编辑任务、增删节点与依赖、导出 / 保存 JSON
   ===================================================================== */
(() => {
  "use strict";

  const bootstrapEl = document.getElementById("bootstrap-data");
  if (!bootstrapEl) return;
  let boot;
  try {
    boot = JSON.parse(bootstrapEl.textContent);
  } catch (error) {
    console.error("无法解析方案数据", error);
    return;
  }

  const PRIORITY_META = {
    P0: { label: "P0 · 必须", color: "#ef4444" },
    P1: { label: "P1 · 重要", color: "#f59e0b" },
    P2: { label: "P2 · 增强", color: "#64748b" },
  };
  const EDGE_KINDS = {
    dependency: { label: "交付依赖", dashed: false },
    flow: { label: "流转 / 交接", dashed: true },
    review: { label: "评审 / 验收", dashed: true, dotted: true },
  };
  const PHASE_LABELS = {
    0: "规划与需求",
    1: "设计与架构",
    2: "基础研发",
    3: "业务研发",
    4: "集成与质量",
    5: "发布与运维",
  };
  const CRITICAL_COLOR = "#ef4444";
  const AGENT_COLORS_FALLBACK = "#64748b";

  const state = {
    plan: boot.plan,
    initialPlan: deepClone(boot.plan),
    planId: boot.plan_id,
    settings: boot.settings || {},
    agentsCatalog: boot.agents_catalog || [],
    activeView: "graph",
    decomposeQuery: "",
    selectedNodeId: null,
    selectedEdgeId: null,
    dirty: false,
    linkMode: false,
    linkSource: null,
    layout: "hierarchical",
    showCritical: true,
    filters: { q: "", agent: "", priority: "" },
    computed: null,
    visibleMap: new Map(),
    nodesDS: null,
    edgesDS: null,
    network: null,
    toastTimer: null,
    saveTimer: null,
    saving: false,
    lastSavedAt: "",
  };

  const AGENTS = Object.fromEntries(state.agentsCatalog.map((agent) => [agent.id, agent]));

  const $ = (id) => document.getElementById(id);

  // ------------------------------------------------------------------
  // 基础工具
  // ------------------------------------------------------------------
  function deepClone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  const ESC_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ESC_MAP[char]);
  }

  function truncate(text, length) {
    const chars = Array.from(String(text || ""));
    return chars.length > length ? `${chars.slice(0, length - 1).join("")}…` : chars.join("");
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function round(value, digits = 1) {
    const factor = 10 ** digits;
    return Math.round(Number(value || 0) * factor) / factor;
  }

  function fmt(value) {
    return String(round(value, 1)).replace(/\.0$/, "");
  }

  function nowText() {
    return new Date().toLocaleTimeString("zh-CN", { hour12: false });
  }

  function agentMeta(id) {
    return (
      AGENTS[id] || {
        id,
        name: id || "未指派",
        color: AGENT_COLORS_FALLBACK,
        icon: "•",
        role: "",
      }
    );
  }

  function tint(hex, alpha) {
    const match = /^#?([a-f\d]{6})$/i.exec(String(hex || ""));
    if (!match) return `rgba(100, 116, 139, ${alpha})`;
    const value = parseInt(match[1], 16);
    return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
  }

  function edgeKindMeta(kind) {
    return EDGE_KINDS[kind] || EDGE_KINDS.dependency;
  }

  // ------------------------------------------------------------------
  // 图算法：分层、CPM、关键路径、并行分组
  // ------------------------------------------------------------------
  function reachable(start, target, successors) {
    if (start === target) return true;
    const stack = [start];
    const seen = new Set([start]);
    while (stack.length) {
      const current = stack.pop();
      for (const next of successors.get(current) || []) {
        if (next === target) return true;
        if (!seen.has(next)) {
          seen.add(next);
          stack.push(next);
        }
      }
    }
    return false;
  }

  function computePlan(plan) {
    const rawNodes = Array.isArray(plan.nodes) ? plan.nodes : [];
    if (!rawNodes.length) throw new Error("方案中没有任务节点");

    const nodes = [];
    const nodeMap = new Map();
    rawNodes.forEach((raw, index) => {
      if (!raw || typeof raw !== "object") return;
      let id = String(raw.id || `T${String(index + 1).padStart(2, "0")}`).trim();
      if (!id) id = `T${String(index + 1).padStart(2, "0")}`;
      while (nodeMap.has(id)) id = `${id}-2`;
      const agentId = AGENTS[raw.agent] ? raw.agent : Object.keys(AGENTS)[0] || "backend";
      const meta = agentMeta(agentId);
      const node = raw;
      node.id = id;
      node.name = String(node.name || `任务 ${index + 1}`).trim() || `任务 ${index + 1}`;
      node.description = String(node.description || "").trim();
      node.module = String(node.module || "通用").trim() || "通用";
      node.priority = PRIORITY_META[node.priority] ? node.priority : "P1";
      node.effort = round(clamp(Number(node.effort) || 1, 0.5, 15), 1);
      node.agent = agentId;
      node.agent_name = meta.name;
      node.agent_color = meta.color;
      node.agent_icon = meta.icon;
      node.agent_role = meta.role || "";
      node.role = String(node.role || meta.role || "").trim() || meta.role || "";
      node.order = Number.isFinite(Number(node.order)) ? Number(node.order) : index;
      node.is_new = Boolean(node.is_new);
      node.x = node.x === null || node.x === undefined || node.x === "" ? null : Number(node.x);
      node.y = node.y === null || node.y === undefined || node.y === "" ? null : Number(node.y);
      if (!Number.isFinite(node.x)) node.x = null;
      if (!Number.isFinite(node.y)) node.y = null;
      node.pinned = Boolean(node.pinned);
      nodes.push(node);
      nodeMap.set(id, node);
    });
    if (!nodes.length) throw new Error("方案中没有有效的任务节点");

    // ---- 连线：去掉悬空、自环、重复边与成环边
    const edges = [];
    const seenPairs = new Set();
    (Array.isArray(plan.edges) ? plan.edges : []).forEach((raw) => {
      if (!raw || typeof raw !== "object") return;
      const from = String(raw.from || "");
      const to = String(raw.to || "");
      if (!nodeMap.has(from) || !nodeMap.has(to) || from === to) return;
      const pair = `${from}\u0000${to}`;
      if (seenPairs.has(pair)) return;
      seenPairs.add(pair);
      const kind = EDGE_KINDS[raw.kind] ? raw.kind : "dependency";
      edges.push({
        id: String(raw.id || ""),
        from,
        to,
        kind,
        label: String(raw.label || "").trim(),
        critical: false,
      });
    });

    const successors = new Map(nodes.map((node) => [node.id, []]));
    const keptEdges = [];
    edges.forEach((edge) => {
      if (reachable(edge.to, edge.from, successors)) return; // 会形成环
      keptEdges.push(edge);
      successors.get(edge.from).push(edge.to);
    });

    const predecessors = new Map(nodes.map((node) => [node.id, []]));
    successors.forEach((list, id) => {
      list.sort();
      list.forEach((target) => predecessors.get(target).push(id));
    });
    predecessors.forEach((list) => list.sort());

    // ---- 拓扑排序
    const orderIndex = new Map(nodes.map((node) => [node.id, node.order]));
    const indegree = new Map(nodes.map((node) => [node.id, predecessors.get(node.id).length]));
    const queue = nodes
      .filter((node) => indegree.get(node.id) === 0)
      .sort((a, b) => orderIndex.get(a.id) - orderIndex.get(b.id) || a.id.localeCompare(b.id))
      .map((node) => node.id);
    const topo = [];
    while (queue.length) {
      const current = queue.shift();
      topo.push(current);
      for (const next of successors.get(current) || []) {
        indegree.set(next, indegree.get(next) - 1);
        if (indegree.get(next) === 0) {
          queue.push(next);
          queue.sort((a, b) => orderIndex.get(a) - orderIndex.get(b) || a.localeCompare(b));
        }
      }
    }

    // ---- 分层：最长路径 + 原阶段 / 层级提示，最后压缩为连续层
    const levels = new Map(nodes.map((node) => [node.id, 0]));
    topo.forEach((id) => {
      const parents = predecessors.get(id);
      if (parents.length) {
        levels.set(id, Math.max(...parents.map((parent) => levels.get(parent))) + 1);
      }
    });
    const oldStagesForLevels = Array.isArray(plan.stages) ? plan.stages : [];
    oldStagesForLevels.forEach((stage) => {
      const hint = Number(stage.level);
      if (!Number.isFinite(hint)) return;
      (stage.node_ids || []).forEach((id) => {
        if (nodeMap.has(id)) levels.set(id, Math.max(levels.get(id), Math.max(0, hint)));
      });
    });
    nodes.forEach((node) => {
      const hint = Number(node.level);
      if (Number.isFinite(hint)) levels.set(node.id, Math.max(levels.get(node.id), Math.max(0, hint)));
    });
    topo.forEach((id) => {
      for (const next of successors.get(id) || []) {
        levels.set(next, Math.max(levels.get(next), levels.get(id) + 1));
      }
    });
    const uniqueLevels = [...new Set(levels.values())].sort((a, b) => a - b);
    const levelRemap = new Map(uniqueLevels.map((value, index) => [value, index]));
    levels.forEach((value, id) => levels.set(id, levelRemap.get(value)));

    // ---- CPM：最早 / 最晚 / 时差 / 关键路径
    const effort = new Map(nodes.map((node) => [node.id, node.effort]));
    const earliestStart = new Map();
    const earliestFinish = new Map();
    topo.forEach((id) => {
      const parents = predecessors.get(id);
      const start = parents.length ? Math.max(...parents.map((parent) => earliestFinish.get(parent))) : 0;
      earliestStart.set(id, round(start, 2));
      earliestFinish.set(id, round(start + effort.get(id), 2));
    });
    const makespan = Math.max(0, ...earliestFinish.values());
    const latestStart = new Map();
    const latestFinish = new Map();
    const slack = new Map();
    const critical = new Map();
    [...topo].reverse().forEach((id) => {
      const children = successors.get(id);
      const finish = children.length ? Math.min(...children.map((child) => latestStart.get(child))) : makespan;
      latestFinish.set(id, finish);
      const start = round(finish - effort.get(id), 2);
      latestStart.set(id, start);
      const slackValue = round(start - earliestStart.get(id), 2);
      slack.set(id, slackValue);
      critical.set(id, slackValue <= 1e-6);
    });

    let criticalPath = [];
    const finals = nodes.filter((node) => critical.get(node.id));
    if (finals.length) {
      let current = finals.sort(
        (a, b) =>
          earliestFinish.get(b.id) - earliestFinish.get(a.id) ||
          effort.get(b.id) - effort.get(a.id) ||
          a.id.localeCompare(b.id)
      )[0].id;
      criticalPath = [current];
      for (let guard = 0; guard < nodes.length + 1; guard += 1) {
        const candidates = predecessors
          .get(current)
          .filter(
            (parent) =>
              critical.get(parent) &&
              Math.abs(earliestFinish.get(parent) - earliestStart.get(current)) < 1e-6
          )
          .sort((a, b) => earliestFinish.get(b) - earliestFinish.get(a) || effort.get(b) - effort.get(a));
        if (!candidates.length) break;
        current = candidates[0];
        criticalPath.push(current);
      }
      criticalPath.reverse();
    }

    // ---- 阶段名称：优先沿用原阶段名，再按节点投票兜底
    const oldStages = Array.isArray(plan.stages) ? plan.stages : [];
    const oldNamesByLevel = new Map();
    const stageVotes = new Map();
    oldStages.forEach((stage) => {
      const name = String(stage.name || "").trim();
      const oldLevel = Number(stage.level);
      if (name && Number.isFinite(oldLevel) && !oldNamesByLevel.has(oldLevel)) {
        oldNamesByLevel.set(oldLevel, name);
      }
      if (!name) return;
      (stage.node_ids || []).forEach((id) => {
        if (!nodeMap.has(id)) return;
        const level = levels.get(id);
        if (!stageVotes.has(level)) stageVotes.set(level, new Map());
        const votes = stageVotes.get(level);
        votes.set(name, (votes.get(name) || 0) + 1);
      });
    });
    const stageName = (level) => {
      const votes = stageVotes.get(level);
      if (votes && votes.size) {
        return [...votes.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0][0];
      }
      if (oldNamesByLevel.has(level)) return oldNamesByLevel.get(level);
      return PHASE_LABELS[level] || `阶段 ${level + 1}`;
    };

    const stageBuckets = new Map();
    nodes.forEach((node) => {
      const level = levels.get(node.id);
      if (!stageBuckets.has(level)) stageBuckets.set(level, []);
      stageBuckets.get(level).push(node.id);
    });
    const stages = [...stageBuckets.keys()]
      .sort((a, b) => a - b)
      .map((level) => {
        const ids = stageBuckets
          .get(level)
          .sort((a, b) => orderIndex.get(a) - orderIndex.get(b) || a.localeCompare(b));
        return {
          level,
          name: stageName(level),
          parallel: ids.length > 1,
          node_ids: ids,
          effort: round(ids.reduce((sum, id) => sum + effort.get(id), 0), 1),
        };
      });

    // ---- 回写节点
    nodes.forEach((node) => {
      const id = node.id;
      node.level = levels.get(id);
      const stage = stages.find((item) => item.level === node.level);
      node.stage = stage ? stage.name : stageName(node.level);
      node.critical = Boolean(critical.get(id));
      node.earliest_start = earliestStart.get(id);
      node.earliest_finish = earliestFinish.get(id);
      node.latest_start = latestStart.get(id);
      node.slack = slack.get(id);
      node.depends_on = [...predecessors.get(id)];
      node.successors = [...successors.get(id)];
    });

    // ---- 回写边
    keptEdges.forEach((edge, index) => {
      edge.id = `E${String(index + 1).padStart(3, "0")}`;
      edge.critical = Boolean(
        critical.get(edge.from) &&
          critical.get(edge.to) &&
          Math.abs(earliestFinish.get(edge.from) - earliestStart.get(edge.to)) < 1e-6
      );
    });

    // ---- 并行分组：保留 LLM 显式标注，再自动补同层分组
    const namedGroups = (Array.isArray(plan.parallel_groups) ? plan.parallel_groups : [])
      .filter((group) => group && group.source === "llm")
      .map((group) => ({
        name: String(group.name || "可并行任务"),
        level: levels.get((group.node_ids || [])[0]),
        node_ids: (group.node_ids || []).filter((id) => nodeMap.has(id)),
        source: "llm",
      }))
      .filter((group) => group.node_ids.length >= 2);
    const parallelGroups = [...namedGroups];
    stages.forEach((stage) => {
      if (stage.node_ids.length > 1) {
        parallelGroups.push({
          name: `${stage.name} · 可并行`,
          level: stage.level,
          node_ids: [...stage.node_ids],
          source: "auto",
        });
      }
    });

    // ---- Agent 负载
    const agentAggregate = new Map();
    nodes.forEach((node) => {
      const meta = agentMeta(node.agent);
      if (!agentAggregate.has(node.agent)) {
        agentAggregate.set(node.agent, {
          id: node.agent,
          name: meta.name,
          role: meta.role || "",
          color: meta.color,
          icon: meta.icon,
          node_ids: [],
          effort: 0,
          p0_count: 0,
        });
      }
      const record = agentAggregate.get(node.agent);
      record.node_ids.push(node.id);
      record.effort += node.effort;
      record.p0_count += node.priority === "P0" ? 1 : 0;
    });
    const totalEffort = round(
      nodes.reduce((sum, node) => sum + node.effort, 0),
      1
    );
    const agents = [...agentAggregate.values()]
      .map((record) => ({
        ...record,
        effort: round(record.effort, 1),
        node_count: record.node_ids.length,
        share: totalEffort ? round(record.effort / totalEffort, 3) : 0,
        node_ids: [...record.node_ids].sort(),
      }))
      .sort((a, b) => b.effort - a.effort || a.name.localeCompare(b.name));

    const modules = new Set(nodes.map((node) => node.module));
    const criticalNodeIds = nodes.filter((node) => node.critical).map((node) => node.id);
    const parallelIds = new Set(
      stages.filter((stage) => stage.node_ids.length > 1).flatMap((stage) => stage.node_ids)
    );
    const stats = {
      nodes: nodes.length,
      edges: keptEdges.length,
      agents: agents.length,
      modules: modules.size,
      stages: stages.length,
      total_effort: totalEffort,
      critical_days: round(makespan, 2),
      critical_nodes: criticalNodeIds.length,
      parallel_nodes: parallelIds.size,
      parallel_ratio: nodes.length ? round(parallelIds.size / nodes.length, 2) : 0,
      avg_parallelism: makespan ? round(totalEffort / makespan, 2) : 0,
      p0_nodes: nodes.filter((node) => node.priority === "P0").length,
    };

    const legend = {
      agents: agents.map((agent) => ({
        id: agent.id,
        label: agent.name,
        color: agent.color,
        icon: agent.icon,
      })),
      priorities: Object.entries(PRIORITY_META).map(([value, meta]) => ({
        value,
        label: meta.label,
        color: meta.color,
      })),
      edge_kinds: Object.entries(EDGE_KINDS)
        .filter(([kind]) => kind === "dependency" || keptEdges.some((edge) => edge.kind === kind))
        .map(([kind, meta]) => ({ kind, ...meta })),
      critical: { label: "关键路径", color: CRITICAL_COLOR },
      stages: stages.map((stage) => ({ level: stage.level, name: stage.name })),
      agents_used: agents.map((agent) => agent.id),
    };

    plan.nodes = nodes;
    plan.edges = keptEdges;
    plan.stages = stages;
    plan.critical_path = criticalPath;
    plan.parallel_groups = parallelGroups;
    plan.agents = agents;
    plan.stats = stats;
    plan.legend = legend;

    return {
      nodes,
      edges: keptEdges,
      nodeMap,
      edgeMap: new Map(keptEdges.map((edge) => [edge.id, edge])),
      predecessors,
      successors,
      stages,
      agents,
      stats,
      levels,
      criticalPath,
      critical,
      schedule: { earliestStart, earliestFinish, latestStart, slack, makespan },
      parallelGroups,
    };
  }

  // ------------------------------------------------------------------
  // 自定义分层排版
  // ------------------------------------------------------------------
  function orderedStageNodes(computed) {
    const stages = computed.stages.map((stage) => ({ ...stage, node_ids: [...stage.node_ids] }));
    const byLevel = new Map(stages.map((stage) => [stage.level, stage]));
    const maxLevel = stages.length ? Math.max(...stages.map((stage) => stage.level)) : 0;
    const orderOf = (id) => computed.nodeMap.get(id)?.order ?? 0;

    const indexMap = () => {
      const map = new Map();
      stages.forEach((stage) => stage.node_ids.forEach((id, index) => map.set(id, index)));
      return map;
    };

    // 重心法：多轮上下扫描，让子节点尽量靠近其前驱，减少连线交叉。
    let indices = indexMap();
    for (let iteration = 0; iteration < 4; iteration += 1) {
      for (let level = 1; level <= maxLevel; level += 1) {
        const stage = byLevel.get(level);
        if (!stage) continue;
        const scores = new Map();
        stage.node_ids.forEach((id) => {
          const parents = (computed.predecessors.get(id) || []).filter((parent) => indices.has(parent));
          scores.set(
            id,
            parents.length
              ? parents.reduce((sum, parent) => sum + indices.get(parent), 0) / parents.length
              : indices.get(id)
          );
        });
        stage.node_ids.sort(
          (a, b) =>
            scores.get(a) - scores.get(b) ||
            orderOf(a) - orderOf(b) ||
            a.localeCompare(b)
        );
        indices = indexMap();
      }
      for (let level = maxLevel - 1; level >= 0; level -= 1) {
        const stage = byLevel.get(level);
        if (!stage) continue;
        const scores = new Map();
        stage.node_ids.forEach((id) => {
          const children = (computed.successors.get(id) || []).filter((child) => indices.has(child));
          scores.set(
            id,
            children.length
              ? children.reduce((sum, child) => sum + indices.get(child), 0) / children.length
              : indices.get(id)
          );
        });
        stage.node_ids.sort(
          (a, b) =>
            scores.get(a) - scores.get(b) ||
            orderOf(a) - orderOf(b) ||
            a.localeCompare(b)
        );
        indices = indexMap();
      }
    }
    return stages;
  }

  function layoutNodes(computed) {
    const ordered = orderedStageNodes(computed);
    const spacingX = 224;
    const spacingY = 118;
    const positions = new Map();

    ordered.forEach((stage) => {
      const count = stage.node_ids.length;
      stage.node_ids.forEach((id, index) => {
        positions.set(id, {
          x: Math.round((index - (count - 1) / 2) * spacingX * 10) / 10,
          y: stage.level * spacingY,
        });
      });
    });

    // 保留重心法排好的同层顺序（影响连线走向与阶段列表展示）
    computed.stages.forEach((stage) => {
      const orderedStage = ordered.find((item) => item.level === stage.level);
      if (orderedStage) stage.node_ids = orderedStage.node_ids;
    });

    computed.nodes.forEach((node) => {
      const fallback = positions.get(node.id) || { x: 0, y: 0 };
      // 用户手动拖拽过的节点保留坐标；其余节点每次结构变化后自动重排。
      if (!node.pinned || !Number.isFinite(node.x) || !Number.isFinite(node.y)) {
        node.x = fallback.x;
        node.y = fallback.y;
      }
    });
  }

  function relayoutGraph() {
    if (!state.computed) return;
    const hadPinned = state.computed.nodes.some((node) => node.pinned);
    state.computed.nodes.forEach((node) => {
      node.pinned = false;
      node.x = null;
      node.y = null;
    });
    if (hadPinned) markDirty();
    renderGraph({ fit: true, preserveView: false });
    showToast("已恢复自动分层排版；拖拽方框可自由移动", "success");
  }

  // ------------------------------------------------------------------
  // 节点 / 边视图
  // ------------------------------------------------------------------
  function nodeCoreColor(node) {
    const agentColor = node.agent_color || AGENT_COLORS_FALLBACK;
    const isCritical = state.showCritical && node.critical;
    return {
      background: tint(agentColor, 0.1),
      border: isCritical ? CRITICAL_COLOR : agentColor,
      highlight: { background: tint(agentColor, 0.2), border: agentColor },
      hover: { background: tint(agentColor, 0.16), border: agentColor },
    };
  }

  function nodeView(node) {
    const isCritical = state.showCritical && node.critical;
    const view = {
      id: node.id,
      label: `${node.id} · ${truncate(node.name, 14)}\n${node.agent_icon || "•"} ${node.agent_name}`,
      title: nodeTooltip(node),
      shape: "box",
      margin: { top: 9, bottom: 9, left: 12, right: 12 },
      widthConstraint: { minimum: 156, maximum: 200 },
      color: nodeCoreColor(node),
      borderWidth: isCritical ? 3 : 1.8,
      font: {
        color: "#1e293b",
        size: 12.5,
        face: "Segoe UI, PingFang SC, Microsoft YaHei, Noto Sans SC, sans-serif",
        multi: false,
      },
      shadow: { enabled: true, color: "rgba(15, 23, 42, 0.09)", size: 8, x: 0, y: 4 },
    };
    if (Number.isFinite(node.x) && Number.isFinite(node.y)) {
      view.x = node.x;
      view.y = node.y;
    }
    if (state.layout === "force" && node.pinned) {
      view.fixed = true;
    }
    return view;
  }

  function edgeView(edge) {
    const critical = Boolean(state.showCritical && edge.critical);
    const kind = edgeKindMeta(edge.kind);
    return {
      id: edge.id,
      from: edge.from,
      to: edge.to,
      // 连线说明只在悬停提示里展示，画布上不渲染文字，避免长依赖图被标签淹没。
      label: "",
      title: edgeTooltip(edge),
      arrows: { to: { enabled: true, scaleFactor: 0.55 } },
      color: {
        color: critical ? CRITICAL_COLOR : "#b9c5d8",
        highlight: critical ? CRITICAL_COLOR : "#6366f1",
        hover: critical ? CRITICAL_COLOR : "#64748b",
        opacity: 1,
      },
      width: critical ? 2.4 : 1.25,
      dashes: kind.dotted ? [2, 4] : kind.dashed ? [6, 4] : false,
      smooth: {
        enabled: true,
        type: "cubicBezier",
        roundness: 0.3,
      },
    };
  }

  function nodeTooltip(node) {
    const dependencies = (node.depends_on || [])
      .map((id) => {
        const found = state.computed && state.computed.nodeMap.get(id);
        return found ? `${id} ${found.name}` : id;
      })
      .join("、");
    const successors = (node.successors || [])
      .map((id) => {
        const found = state.computed && state.computed.nodeMap.get(id);
        return found ? `${id} ${found.name}` : id;
      })
      .join("、");
    return [
      `<div class="tt-title">${esc(node.id)} · ${esc(node.name)}</div>`,
      node.critical ? '<span class="tt-badge">关键路径任务</span>' : "",
      node.description ? `<div style="margin-bottom:6px">${esc(node.description)}</div>` : "",
      `<div class="tt-row"><span class="tt-key">模块</span><span class="tt-val">${esc(node.module)}</span></div>`,
      `<div class="tt-row"><span class="tt-key">优先级</span><span class="tt-val">${esc(
        PRIORITY_META[node.priority].label
      )}</span></div>`,
      `<div class="tt-row"><span class="tt-key">工作量</span><span class="tt-val">${fmt(
        node.effort
      )} 人天</span></div>`,
      `<div class="tt-row"><span class="tt-key">Agent</span><span class="tt-val">${esc(
        node.agent_name
      )} · ${esc(node.role || node.agent_role)}</span></div>`,
      `<div class="tt-row"><span class="tt-key">阶段</span><span class="tt-val">${esc(
        node.stage
      )} · 第 ${node.level + 1} 层</span></div>`,
      `<div class="tt-row"><span class="tt-key">时间</span><span class="tt-val">第 ${fmt(
        node.earliest_start
      )}–${fmt(node.earliest_finish)} 天 · 时差 ${fmt(node.slack)} 天</span></div>`,
      `<div class="tt-row"><span class="tt-key">前置</span><span class="tt-val">${esc(
        dependencies || "无"
      )}</span></div>`,
      `<div class="tt-row"><span class="tt-key">后继</span><span class="tt-val">${esc(
        successors || "无"
      )}</span></div>`,
      `<div class="tt-row"><span class="tt-key">验收</span><span class="tt-val">${esc(
        node.acceptance
      )}</span></div>`,
    ]
      .filter(Boolean)
      .join("");
  }

  function edgeTooltip(edge) {
    const from = state.computed.nodeMap.get(edge.from);
    const to = state.computed.nodeMap.get(edge.to);
    return [
      `<div class="tt-title">${esc(edge.from)} → ${esc(edge.to)}</div>`,
      `<div class="tt-row"><span class="tt-key">类型</span><span class="tt-val">${esc(
        edgeKindMeta(edge.kind).label
      )}</span></div>`,
      `<div class="tt-row"><span class="tt-key">起点</span><span class="tt-val">${esc(
        from ? from.name : edge.from
      )}</span></div>`,
      `<div class="tt-row"><span class="tt-key">终点</span><span class="tt-val">${esc(
        to ? to.name : edge.to
      )}</span></div>`,
      edge.critical ? '<span class="tt-badge">关键路径连线</span>' : "",
      edge.label ? `<div class="tt-row"><span class="tt-key">说明</span><span class="tt-val">${esc(edge.label)}</span></div>` : "",
    ]
      .filter(Boolean)
      .join("");
  }

  // ------------------------------------------------------------------
  // 网络配置与渲染
  // ------------------------------------------------------------------
  function networkOptions() {
    const force = state.layout === "force";
    return {
      autoResize: true,
      // 分层坐标由 layoutNodes() 计算，关闭 vis 自带的 hierarchical，
      // 这样节点拖拽后不会被布局引擎吸回去。
      layout: { hierarchical: { enabled: false } },
      physics: force
        ? {
            enabled: true,
            stabilization: { enabled: true, iterations: 220, updateInterval: 25, fit: true },
            barnesHut: {
              gravitationalConstant: -9000,
              centralGravity: 0.25,
              springLength: 160,
              springConstant: 0.035,
              damping: 0.2,
              avoidOverlap: 0.2,
            },
          }
        : { enabled: false },
      interaction: {
        hover: true,
        tooltipDelay: 130,
        navigationButtons: false,
        keyboard: false,
        multiselect: false,
        selectConnectedEdges: false,
        dragNodes: true,
      },
      nodes: {
        shape: "box",
        borderWidth: 2,
        chosen: false,
      },
      edges: {
        selectionWidth: 0,
        hoverWidth: 0.4,
      },
      configure: false,
    };
  }

  function renderGraph({ fit = false, preserveView = true } = {}) {
    if (!window.vis || !window.vis.Network) {
      $("graph").innerHTML =
        '<div class="graph-empty"><p>vis-network 未能加载，请刷新页面或检查 static/vendor 目录。</p></div>';
      return;
    }
    const previousView =
      state.network && preserveView
        ? { position: state.network.getViewPosition(), scale: state.network.getScale() }
        : null;

    const computed = computePlan(state.plan);
    state.computed = computed;
    layoutNodes(computed);

    if (state.selectedNodeId && !computed.nodeMap.has(state.selectedNodeId)) {
      state.selectedNodeId = null;
    }
    if (state.selectedEdgeId && !computed.edgeMap.has(state.selectedEdgeId)) {
      state.selectedEdgeId = null;
    }
    if (state.linkSource && !computed.nodeMap.has(state.linkSource)) {
      state.linkSource = null;
    }

    const nodeViews = computed.nodes.map(nodeView);
    const edgeViews = computed.edges.map(edgeView);

    if (!state.network) {
      state.nodesDS = new vis.DataSet(nodeViews);
      state.edgesDS = new vis.DataSet(edgeViews);
      state.network = new vis.Network(
        $("graph"),
        { nodes: state.nodesDS, edges: state.edgesDS },
        networkOptions()
      );
      bindNetworkEvents();
    } else {
      state.nodesDS.clear();
      state.edgesDS.clear();
      state.nodesDS.add(nodeViews);
      state.edgesDS.add(edgeViews);
      if (previousView) {
        state.network.moveTo({ position: previousView.position, scale: previousView.scale, animation: false });
      }
    }

    renderAllPanels();
    applyFilters();
    if (fit) fitGraph();
    updateSaveState();
  }

  function fitGraph({ minScale = "auto" } = {}) {
    if (!state.network) return;
    const visibleIds = state.computed.nodes
      .filter((node) => state.visibleMap.get(node.id) !== false)
      .map((node) => node.id);
    window.requestAnimationFrame(() => {
      state.network.fit({
        nodes: visibleIds.length ? visibleIds : undefined,
        animation: false,
      });
      const scale = state.network.getScale();
      if (minScale === 0 || !visibleIds.length) return;

      // 大图自动适配后文字会小到不可读。默认按“宽度舒适缩放”显示，
      // 保证横向不裁切；竖向看不完可以拖拽平移。点「适应窗口」查看全图。
      const points = state.network.getPositions(visibleIds);
      const xs = Object.values(points).map((point) => point.x);
      const ys = Object.values(points).map((point) => point.y);
      const graphWidth = Math.max(...xs) - Math.min(...xs) + 200;
      const canvasWidth = $("graph").clientWidth || 900;
      const canvasHeight = $("graph").clientHeight || 640;
      const widthFit = (canvasWidth - 48) / Math.max(1, graphWidth);
      const comfort = Math.min(0.82, Math.max(0.6, widthFit));
      if (scale < comfort) {
        const position = {
          x: (Math.min(...xs) + Math.max(...xs)) / 2,
          y: Math.min(...ys) + (canvasHeight / 2 - 70) / comfort,
        };
        state.network.moveTo({ position, scale: comfort, animation: false });
      }
    });
  }

  function applyFilters() {
    if (!state.computed || !state.nodesDS) return;
    const query = state.filters.q.trim().toLowerCase();
    const visible = new Map();
    state.computed.nodes.forEach((node) => {
      let match = true;
      if (query) {
        const haystack = [
          node.id,
          node.name,
          node.module,
          node.description,
          node.acceptance,
          node.agent_name,
          node.stage,
        ]
          .join(" ")
          .toLowerCase();
        match = haystack.includes(query);
      }
      if (match && state.filters.agent) match = node.agent === state.filters.agent;
      if (match && state.filters.priority) match = node.priority === state.filters.priority;
      visible.set(node.id, match);
    });
    state.visibleMap = visible;

    const visibleCount = [...visible.values()].filter(Boolean).length;
    const empty = $("graph-empty");
    if (empty) empty.hidden = visibleCount > 0;

    applyHighlight();
  }

  function collectRelated(nodeId) {
    const related = new Set([nodeId]);
    const upstream = [nodeId];
    while (upstream.length) {
      const current = upstream.pop();
      for (const parent of state.computed.predecessors.get(current) || []) {
        if (!related.has(parent)) {
          related.add(parent);
          upstream.push(parent);
        }
      }
    }
    const downstream = [nodeId];
    while (downstream.length) {
      const current = downstream.pop();
      for (const child of state.computed.successors.get(current) || []) {
        if (!related.has(child)) {
          related.add(child);
          downstream.push(child);
        }
      }
    }
    return related;
  }

  function applyHighlight() {
    if (!state.computed || !state.nodesDS) return;
    const computed = state.computed;
    const selectingNode = state.selectedNodeId;
    const selectingEdge = state.selectedEdgeId;
    const hasSelection = Boolean(selectingNode || selectingEdge);
    const related = selectingNode ? collectRelated(selectingNode) : new Set();

    const nodeUpdates = computed.nodes.map((node) => {
      const base = nodeView(node);
      if (state.visibleMap.get(node.id) === false) return { ...base, hidden: true };
      if (!hasSelection || related.has(node.id)) {
        return {
          ...base,
          hidden: false,
          borderWidth: node.id === selectingNode ? 4 : base.borderWidth,
        };
      }
      return {
        ...base,
        hidden: false,
        color: {
          background: "#f8fafc",
          border: "#e2e8f0",
          highlight: { background: "#f8fafc", border: "#e2e8f0" },
          hover: { background: "#f8fafc", border: "#e2e8f0" },
        },
        borderWidth: 1.2,
        font: { ...base.font, color: "#94a3b8" },
      };
    });
    state.nodesDS.update(nodeUpdates);

    const edgeUpdates = computed.edges.map((edge) => {
      const base = edgeView(edge);
      const endpointsVisible =
        state.visibleMap.get(edge.from) !== false && state.visibleMap.get(edge.to) !== false;
      if (!endpointsVisible) return { ...base, hidden: true };
      let active = true;
      if (selectingEdge) active = edge.id === selectingEdge;
      else if (selectingNode) active = related.has(edge.from) && related.has(edge.to);
      if (active) return { ...base, hidden: false };
      return {
        ...base,
        hidden: false,
        color: { color: "#e2e8f0", highlight: "#e2e8f0", hover: "#e2e8f0", opacity: 1 },
        width: 1,
        font: { ...base.font, color: "#cbd5e1" },
      };
    });
    state.edgesDS.update(edgeUpdates);
  }

  function bindNetworkEvents() {
    state.network.on("click", (params) => {
      if (state.linkMode) {
        if (params.nodes.length) handleLinkClick(params.nodes[0]);
        return;
      }
      if (params.nodes.length) {
        selectNode(params.nodes[0]);
      } else if (params.edges.length) {
        selectEdge(params.edges[0]);
      } else {
        clearSelection();
      }
    });

    state.network.on("doubleClick", (params) => {
      if (params.nodes.length && state.network) {
        state.network.focus(params.nodes[0], {
          scale: 1.15,
          animation: { duration: 400, easingFunction: "easeInOutQuad" },
        });
      }
    });

    // 拖拽后记录坐标并固定该节点，后续编辑 / 重排不会把它吸回原位。
    state.network.on("dragEnd", (params) => {
      if (!params.nodes.length) return;
      const positions = state.network.getPositions(params.nodes);
      let changed = false;
      params.nodes.forEach((id) => {
        const node = state.computed.nodeMap.get(id);
        const position = positions[id];
        if (!node || !position) return;
        node.x = round(position.x, 1);
        node.y = round(position.y, 1);
        node.pinned = true;
        changed = true;
      });
      if (changed) {
        markDirty();
      }
    });
  }

  // ------------------------------------------------------------------
  // 选择与侧栏
  // ------------------------------------------------------------------
  function selectNode(nodeId) {
    if (!state.computed || !state.computed.nodeMap.has(nodeId)) return;
    state.selectedNodeId = nodeId;
    state.selectedEdgeId = null;
    renderInspector();
    applyHighlight();
  }

  function selectEdge(edgeId) {
    if (!state.computed || !state.computed.edgeMap.has(edgeId)) return;
    state.selectedEdgeId = edgeId;
    state.selectedNodeId = null;
    renderInspector();
    applyHighlight();
  }

  function clearSelection() {
    state.selectedNodeId = null;
    state.selectedEdgeId = null;
    renderInspector();
    applyHighlight();
  }

  function renderAllPanels() {
    renderStats();
    renderLegend();
    renderStages();
    renderAgents();
    renderParallel();
    renderInspector();
    renderDecompose();
    renderMetaChips();
    updateFooter();
  }

  function renderStats() {
    const stats = state.computed.stats;
    const cards = [
      [stats.nodes, "任务方框"],
      [stats.edges, "依赖连线"],
      [stats.agents, "承接 Agent"],
      [stats.stages, "执行阶段"],
      [`${fmt(stats.critical_days)}<small>天</small>`, "关键路径"],
      [`${fmt(stats.total_effort)}<small>人天</small>`, "总工作量"],
    ];
    $("stat-strip").innerHTML = cards
      .map(
        ([value, label]) =>
          `<div class="stat-card"><span class="stat-value">${value}</span><span class="stat-label">${label}</span></div>`
      )
      .join("");
  }

  function renderLegend() {
    const plan = state.plan;
    const agents = plan.agents || [];
    const usedKinds = new Set((plan.edges || []).map((edge) => edge.kind));
    const edgeItems = Object.entries(EDGE_KINDS)
      .filter(([kind]) => kind === "dependency" || usedKinds.has(kind))
      .map(([kind, meta]) => {
        const cls = meta.dotted ? "dotted" : meta.dashed ? "dashed" : "";
        return `<span class="legend-item"><i class="legend-line ${cls}"></i>${esc(meta.label)}</span>`;
      })
      .join("");

    $("legend").innerHTML = `
      <div class="legend-group">
        <span class="lg-label">Agent</span>
        ${agents
          .map(
            (agent) =>
              `<span class="legend-item" data-agent-filter="${esc(agent.id)}" style="cursor:pointer" title="${
                esc(agent.role)
              }"><i class="legend-dot" style="--c:${esc(agent.color)}"></i>${esc(agent.icon)} ${esc(
                agent.name
              )}</span>`
          )
          .join("")}
      </div>
      <div class="legend-group"><span class="lg-label">连线</span>${edgeItems}</div>
      <div class="legend-group">
        <span class="lg-label">标记</span>
        <span class="legend-item"><i class="legend-line critical"></i>关键路径（红框 / 红线）</span>
        <span class="legend-item">方框底色 / 标签 = 承接 Agent</span>
      </div>
      <div class="legend-group">
        <span class="lg-label">排版</span>
        <span class="legend-item">上下 = 依赖先后</span>
        <span class="legend-item">同层 = 可并行</span>
      </div>
    `;
  }

  function renderStages() {
    const stages = state.computed.stages;
    $("stage-card").innerHTML = `
      <div class="card-head"><h2>执行阶段</h2><span class="count-badge">${stages.length}</span></div>
      <ol class="stage-list">
        ${stages
          .map(
            (stage) => `
          <li class="stage-item">
            <span class="stage-index">${stage.level + 1}</span>
            <div class="stage-info">
              <div class="stage-name" title="${esc(stage.name)}">${esc(stage.name)}</div>
              <div class="stage-meta">${stage.node_ids.length} 个任务 · ${
                stage.parallel ? "可并行" : "串行"
              } · ${fmt(stage.effort)} 人天</div>
            </div>
            <button class="stage-jump" type="button" data-level="${stage.level}">定位</button>
          </li>`
          )
          .join("")}
      </ol>
    `;
  }

  function renderAgents() {
    const agents = state.computed.agents;
    const maxEffort = Math.max(1, ...agents.map((agent) => agent.effort));
    $("agent-card").innerHTML = `
      <div class="card-head"><h2>Agent 负载</h2><span class="count-badge">${agents.length}</span></div>
      <ul class="agent-load-list">
        ${agents
          .map(
            (agent) => `
          <li data-agent-filter="${esc(agent.id)}" style="cursor:pointer" title="${esc(agent.role)}">
            <i class="agent-dot" style="--c:${esc(agent.color)}"></i>
            <span class="agent-load-name">${esc(agent.icon)} ${esc(agent.name)}</span>
            <span class="agent-load-bar"><i style="--c:${esc(agent.color)};width:${Math.max(
              4,
              Math.round((agent.effort / maxEffort) * 100)
            )}%"></i></span>
            <span class="agent-load-val">${agent.node_count} 个 · ${fmt(agent.effort)} 人天</span>
          </li>`
          )
          .join("")}
      </ul>
    `;
  }

  function renderParallel() {
    const groups = state.computed.parallelGroups;
    const body = groups.length
      ? groups
          .map(
            (group) => `
          <div class="parallel-group">
            <b>${esc(group.name)} ${group.source === "auto" ? '<span class="muted">· 自动识别</span>' : ""}</b>
            <div class="dep-list">
              ${group.node_ids
                .map(
                  (id) =>
                    `<button type="button" class="dep-chip" data-node="${esc(id)}">${esc(id)}</button>`
                )
                .join("")}
            </div>
          </div>`
          )
          .join("")
      : '<p class="inspector-text">当前没有可并行任务组。串行链路越短，并行度越高。</p>';
    $("parallel-card").innerHTML = `
      <div class="card-head"><h2>可并行任务</h2><span class="count-badge">${groups.length}</span></div>
      <div class="parallel-list">${body}</div>
    `;
  }

  // ------------------------------------------------------------------
  // 任务分解视图（WBS 清单：阶段一产物的专属板块）
  // ------------------------------------------------------------------
  function renderDecompose() {
    const nodes = state.plan.nodes || [];
    const query = state.decomposeQuery.trim().toLowerCase();
    const matchNode = (node) => {
      if (!query) return true;
      return [
        node.id,
        node.name,
        node.module,
        node.description,
        node.acceptance,
        node.agent_name,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    };

    // 概览统计基于全量数据，不受搜索影响
    const moduleSet = new Set(nodes.map((node) => node.module));
    const totalEffort = nodes.reduce((sum, node) => sum + Number(node.effort || 0), 0);
    const p0Count = nodes.filter((node) => node.priority === "P0").length;
    const overviewCards = [
      [nodes.length, "分解任务"],
      [moduleSet.size, "涉及模块"],
      [p0Count, "P0 必须任务"],
      [`${fmt(totalEffort)}<small>人天</small>`, "估算总工作量"],
    ];
    $("decompose-overview").innerHTML = overviewCards
      .map(
        ([value, label]) =>
          `<div class="dc-stat"><span class="dc-value">${value}</span><span class="dc-label">${label}</span></div>`
      )
      .join("");

    // 按模块分组（保持模块首次出现顺序），组内按分解顺序排序
    const groups = new Map();
    nodes.forEach((node) => {
      if (!matchNode(node)) return;
      if (!groups.has(node.module)) groups.set(node.module, []);
      groups.get(node.module).push(node);
    });
    groups.forEach((list) =>
      list.sort((a, b) => Number(a.order || 0) - Number(b.order || 0))
    );

    let visibleCount = 0;
    let groupIndex = 0;
    const html = [...groups.entries()]
      .map(([module, list]) => {
        visibleCount += list.length;
        groupIndex += 1;
        const groupEffort = list.reduce((sum, node) => sum + Number(node.effort || 0), 0);
        return `
        <section class="wbs-group">
          <header class="wbs-group-head">
            <span class="wbs-group-index">${groupIndex}</span>
            <h2>${esc(module)}</h2>
            <span class="wbs-group-meta">${list.length} 个任务 · ${fmt(groupEffort)} 人天</span>
          </header>
          <div class="wbs-cards">${list.map(wbsCard).join("")}</div>
        </section>`;
      })
      .join("");

    $("decompose-body").innerHTML = html;
    $("decompose-empty").hidden = visibleCount > 0;
  }

  function wbsCard(node) {
    const priority = PRIORITY_META[node.priority] || PRIORITY_META.P2;
    const deps = node.depends_on || [];
    return `
    <article class="wbs-card" style="--agent:${esc(node.agent_color)}">
      <div class="wbs-card-top">
        <span class="wbs-id">${esc(node.id)}</span>
        <h3 class="wbs-name" title="${esc(node.name)}">${esc(node.name)}</h3>
        <span class="wbs-priority" style="--pc:${esc(priority.color)}">${esc(priority.label)}</span>
      </div>
      <p class="wbs-desc">${esc(node.description)}</p>
      <div class="wbs-acceptance">
        <span class="wbs-field-label">验收标准</span>
        <p>${esc(node.acceptance)}</p>
      </div>
      <div class="wbs-meta">
        <span class="wbs-agent">
          <i class="wbs-agent-dot" style="--c:${esc(node.agent_color)}"></i>
          ${esc(node.agent_icon || "")} ${esc(node.agent_name)}
        </span>
        <span class="wbs-effort">${fmt(node.effort)} 人天</span>
        <span class="wbs-deps">
          <span class="wbs-field-label">前置</span>
          ${
            deps.length
              ? deps
                  .map(
                    (id) =>
                      `<button type="button" class="dep-chip wbs-dep" data-jump-node="${esc(
                        id
                      )}">${esc(id)}</button>`
                  )
                  .join("")
              : '<span class="dep-empty">无</span>'
          }
        </span>
      </div>
    </article>`;
  }

  function switchView(view) {
    if (view !== "decompose" && view !== "graph") return;
    if (state.activeView === view) return;
    state.activeView = view;

    $("tab-decompose").classList.toggle("is-active", view === "decompose");
    $("tab-graph").classList.toggle("is-active", view === "graph");
    $("tab-decompose").setAttribute("aria-selected", String(view === "decompose"));
    $("tab-graph").setAttribute("aria-selected", String(view === "graph"));
    $("pane-decompose").hidden = view !== "decompose";
    $("pane-graph").hidden = view !== "graph";

    if (view === "graph" && state.network) {
      // 容器从隐藏恢复后，vis-network 需要按容器尺寸重绘，并恢复原视角
      const saved = {
        position: state.network.getViewPosition(),
        scale: state.network.getScale(),
      };
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          state.network.redraw();
          state.network.moveTo({
            position: saved.position,
            scale: saved.scale,
            animation: false,
          });
        })
      );
    }
  }

  function renderInspector() {
    const inspector = $("inspector");
    if (state.selectedEdgeId) {
      renderEdgeInspector(inspector);
      return;
    }
    if (state.selectedNodeId) {
      const node = state.computed.nodeMap.get(state.selectedNodeId);
      if (node) {
        renderNodeInspector(inspector, node);
        return;
      }
    }
    renderOverview(inspector);
  }

  function renderOverview(inspector) {
    const plan = state.plan;
    const computed = state.computed;
    const critical = computed.criticalPath
      .map((id) => {
        const node = computed.nodeMap.get(id);
        return node
          ? `<button type="button" class="chain-node" data-select-node="${esc(id)}" title="${esc(
              node.name
            )}">${esc(id)}</button>`
          : "";
      })
      .join('<span class="chain-arrow">→</span>');

    inspector.innerHTML = `
      <div class="inspector-head">
        <div>
          <span class="inspector-kicker">方案概览</span>
          <h2 class="inspector-title">${computed.nodes.length} 个任务 · ${computed.stages.length} 个阶段</h2>
        </div>
      </div>
      <p class="inspector-text">${esc(
        plan.requirement.summary || plan.requirement.raw || "点击任意方框开始编辑。"
      )}</p>
      <div class="inspector-section">
        <h3>关键路径 · ${fmt(computed.stats.critical_days)} 天 · ${computed.criticalPath.length} 个任务</h3>
        <div class="critical-chain">${critical || '<span class="dep-empty">暂无关键路径</span>'}</div>
      </div>
      <div class="inspector-section">
        <h3>怎么编辑</h3>
        <ul class="tip-list">
          <li>点击方框，在右侧修改名称、描述、优先级、工作量、Agent 与验收标准。</li>
          <li>在编辑面板中增删前置 / 后继依赖，或开启「连线模式」点两个方框添加连线。</li>
          <li>保存后立即重算分层与关键路径；点顶部「保存」写入服务端，点「导出」下载 JSON。</li>
        </ul>
      </div>
      <div class="form-actions">
        <button class="btn-primary small" type="button" data-action="add-node">＋ 新增任务</button>
        <button class="btn-ghost" type="button" data-action="fit">适应窗口</button>
      </div>
    `;
    bindInspectorDelegates(inspector);
  }

  function renderNodeInspector(inspector, node) {
    const agentOptions = state.agentsCatalog
      .map(
        (agent) =>
          `<option value="${esc(agent.id)}" ${agent.id === node.agent ? "selected" : ""}>${esc(
            agent.icon
          )} ${esc(agent.name)}</option>`
      )
      .join("");
    const priorityOptions = Object.entries(PRIORITY_META)
      .map(
        ([value, meta]) =>
          `<option value="${value}" ${value === node.priority ? "selected" : ""}>${esc(meta.label)}</option>`
      )
      .join("");

    const dependencies = node.depends_on || [];
    const successors = node.successors || [];
    const available = state.computed.nodes
      .filter((candidate) => candidate.id !== node.id && !dependencies.includes(candidate.id))
      .sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));

    const depChips = dependencies.length
      ? dependencies
          .map(
            (id) =>
              `<button type="button" class="dep-chip" data-remove-in="${esc(id)}" title="点击移除依赖">${esc(
                id
              )} ×</button>`
          )
          .join("")
      : '<span class="dep-empty">无前置任务</span>';
    const succChips = successors.length
      ? successors
          .map(
            (id) =>
              `<button type="button" class="dep-chip" data-remove-out="${esc(id)}" title="点击移除依赖">${esc(
                id
              )} ×</button>`
          )
          .join("")
      : '<span class="dep-empty">无后继任务</span>';

    inspector.innerHTML = `
      <form class="node-form" id="node-form" autocomplete="off">
        <div class="inspector-head">
          <div>
            <span class="inspector-kicker">编辑任务 · ${esc(node.id)}</span>
            <h2 class="inspector-title">${esc(node.name)}</h2>
          </div>
          <button type="button" class="icon-btn" data-action="cancel" aria-label="关闭编辑">×</button>
        </div>
        <label class="field"><span>任务名称</span>
          <input data-field="name" maxlength="60" value="${esc(node.name)}" required>
        </label>
        <div class="field-row three">
          <label class="field"><span>优先级</span><select data-field="priority">${priorityOptions}</select></label>
          <label class="field"><span>工作量（人天）</span>
            <input type="number" data-field="effort" min="0.5" max="15" step="0.5" value="${node.effort}">
          </label>
          <label class="field"><span>所属模块</span>
            <input data-field="module" maxlength="40" value="${esc(node.module)}">
          </label>
        </div>
        <label class="field"><span>承接 Agent</span>
          <select data-field="agent">${agentOptions}</select>
        </label>
        <label class="field"><span>职责 / 分工</span>
          <input data-field="role" maxlength="120" value="${esc(node.role || node.agent_role)}">
        </label>
        <label class="field"><span>任务描述</span>
          <textarea data-field="description" rows="3" maxlength="600">${esc(node.description)}</textarea>
        </label>
        <label class="field"><span>验收标准</span>
          <textarea data-field="acceptance" rows="2" maxlength="300">${esc(node.acceptance)}</textarea>
        </label>

        <div class="field">
          <span>前置依赖（${dependencies.length}）</span>
          <div class="dep-list">
            ${depChips}
            <select class="dep-add" id="dep-add" aria-label="添加前置依赖">
              <option value="">＋ 添加…</option>
              ${available
                .map(
                  (candidate) =>
                    `<option value="${esc(candidate.id)}">${esc(candidate.id)} · ${esc(
                      truncate(candidate.name, 18)
                    )}</option>`
                )
                .join("")}
            </select>
          </div>
        </div>
        <div class="field">
          <span>后继任务（${successors.length}）</span>
          <div class="dep-list">${succChips}</div>
        </div>

        <div class="node-meta-grid">
          <div><span>执行阶段</span><b>${esc(node.stage)}</b></div>
          <div><span>层级</span><b>第 ${node.level + 1} 层</b></div>
          <div><span>时间窗口</span><b>第 ${fmt(node.earliest_start)}–${fmt(node.earliest_finish)} 天</b></div>
          <div><span>时差</span><b>${fmt(node.slack)} 天 ${node.critical ? "· 关键" : ""}</b></div>
        </div>

        <div class="form-actions">
          <button class="btn-primary small" type="submit">保存修改</button>
          <button class="btn-ghost" type="button" data-action="cancel">取消</button>
          <button class="btn-danger" type="button" data-action="delete">删除任务</button>
        </div>
        <p class="form-hint">保存后立即更新流程图、分层与底层 JSON；顶部「保存」可写入服务端。</p>
      </form>
    `;
    bindNodeForm(inspector, node);
  }

  function renderEdgeInspector(inspector) {
    const edge = state.computed.edgeMap.get(state.selectedEdgeId);
    if (!edge) {
      renderOverview(inspector);
      return;
    }
    const from = state.computed.nodeMap.get(edge.from);
    const to = state.computed.nodeMap.get(edge.to);
    inspector.innerHTML = `
      <div class="inspector-head">
        <div>
          <span class="inspector-kicker">编辑连线 · ${esc(edge.id)}</span>
          <h2 class="inspector-title">${esc(edge.from)} → ${esc(edge.to)}</h2>
        </div>
        <button type="button" class="icon-btn" data-action="cancel" aria-label="关闭">×</button>
      </div>
      <div class="edge-endpoints">
        <button type="button" class="edge-node" data-select-node="${esc(edge.from)}">
          ${esc(from ? from.name : edge.from)}<small>${esc(edge.from)}</small>
        </button>
        <span class="edge-arrow">→</span>
        <button type="button" class="edge-node" data-select-node="${esc(edge.to)}">
          ${esc(to ? to.name : edge.to)}<small>${esc(edge.to)}</small>
        </button>
      </div>
      <div class="node-meta-grid">
        <div><span>连线类型</span><b>${esc(edgeKindMeta(edge.kind).label)}</b></div>
        <div><span>关键路径</span><b>${edge.critical ? "是" : "否"}</b></div>
        <div><span>起点 Agent</span><b>${esc(from ? from.agent_name : "-")}</b></div>
        <div><span>终点 Agent</span><b>${esc(to ? to.agent_name : "-")}</b></div>
      </div>
      ${edge.label ? `<p class="inspector-text">说明：${esc(edge.label)}</p>` : ""}
      <div class="form-actions">
        <button class="btn-danger" type="button" data-action="delete-edge">删除连线</button>
        <button class="btn-ghost" type="button" data-action="cancel">关闭</button>
      </div>
      <p class="form-hint">删除连线后，图层级与关键路径会自动重算。</p>
    `;
    bindInspectorDelegates(inspector);
  }

  function bindInspectorDelegates(container) {
    container.querySelectorAll("[data-select-node]").forEach((button) => {
      button.addEventListener("click", () => selectNode(button.dataset.selectNode));
    });
    container.querySelectorAll("[data-agent-filter]").forEach((element) => {
      element.addEventListener("click", () => {
        $("filter-agent").value = element.dataset.agentFilter;
        state.filters.agent = element.dataset.agentFilter;
        applyFilters();
      });
    });
    const cancel = container.querySelector('[data-action="cancel"]');
    if (cancel) cancel.addEventListener("click", clearSelection);
    const deleteEdge = container.querySelector('[data-action="delete-edge"]');
    if (deleteEdge) {
      deleteEdge.addEventListener("click", () => {
        if (!state.selectedEdgeId) return;
        const edge = state.computed.edgeMap.get(state.selectedEdgeId);
        if (!edge) return;
        removeEdge(edge.from, edge.to, `已删除连线 ${edge.from} → ${edge.to}`);
        state.selectedEdgeId = null;
        renderGraph({ preserveView: true });
      });
    }
    const addNode = container.querySelector('[data-action="add-node"]');
    if (addNode) addNode.addEventListener("click", addNodeAction);
    const fit = container.querySelector('[data-action="fit"]');
    if (fit) fit.addEventListener("click", () => fitGraph());
  }

  function bindNodeForm(container, node) {
    const form = container.querySelector("#node-form");
    if (!form) return;

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const read = (name) => form.querySelector(`[data-field="${name}"]`).value.trim();
      const name = read("name");
      if (!name) {
        showToast("任务名称不能为空", "error");
        form.querySelector('[data-field="name"]').focus();
        return;
      }
      const effort = clamp(Number(read("effort")) || 0.5, 0.5, 15);
      const agentId = AGENTS[read("agent")] ? read("agent") : node.agent;
      const oldAgent = node.agent;
      node.name = name;
      node.module = read("module") || "通用";
      node.priority = PRIORITY_META[read("priority")] ? read("priority") : "P1";
      node.effort = round(effort, 1);
      node.agent = agentId;
      const meta = agentMeta(agentId);
      node.agent_name = meta.name;
      node.agent_color = meta.color;
      node.agent_icon = meta.icon;
      node.agent_role = meta.role || "";
      node.role = read("role") || (oldAgent !== agentId ? meta.role : node.role) || meta.role || "";
      node.description = read("description");
      node.acceptance = read("acceptance");
      markDirty();
      state.selectedNodeId = node.id;
      state.selectedEdgeId = null;
      renderGraph({ preserveView: true });
      renderInspector();
      showToast("任务已更新，图层级与关键路径已重算", "success");
    });

    const cancel = form.querySelector('[data-action="cancel"]');
    if (cancel) cancel.addEventListener("click", clearSelection);

    const remove = form.querySelector('[data-action="delete"]');
    if (remove) {
      remove.addEventListener("click", () => {
        if (state.plan.nodes.length <= 1) {
          showToast("至少保留一个任务节点", "error");
          return;
        }
        if (!window.confirm(`确定删除任务「${node.name}」及与其相连的所有依赖吗？`)) return;
        state.plan.nodes = state.plan.nodes.filter((item) => item.id !== node.id);
        state.plan.edges = state.plan.edges.filter(
          (edge) => edge.from !== node.id && edge.to !== node.id
        );
        state.selectedNodeId = null;
        state.selectedEdgeId = null;
        state.linkSource = null;
        markDirty();
        renderGraph({ fit: true });
        showToast(`已删除任务 ${node.id}`, "success");
      });
    }

    form.querySelectorAll("[data-remove-in]").forEach((chip) => {
      chip.addEventListener("click", () => {
        removeEdge(chip.dataset.removeIn, node.id, `已移除依赖 ${chip.dataset.removeIn} → ${node.id}`);
        state.selectedNodeId = node.id;
        renderGraph({ preserveView: true });
        renderInspector();
      });
    });
    form.querySelectorAll("[data-remove-out]").forEach((chip) => {
      chip.addEventListener("click", () => {
        removeEdge(node.id, chip.dataset.removeOut, `已移除依赖 ${node.id} → ${chip.dataset.removeOut}`);
        state.selectedNodeId = node.id;
        renderGraph({ preserveView: true });
        renderInspector();
      });
    });

    const addDependency = form.querySelector("#dep-add");
    if (addDependency) {
      addDependency.addEventListener("change", () => {
        const source = addDependency.value;
        if (!source) return;
        addEdge(source, node.id);
        state.selectedNodeId = node.id;
        renderGraph({ preserveView: true });
        renderInspector();
      });
    }
  }

  // ------------------------------------------------------------------
  // 编辑操作
  // ------------------------------------------------------------------
  function markDirty() {
    state.dirty = true;
    state.plan.meta = state.plan.meta || {};
    state.plan.meta.edited = true;
    state.plan.meta.edited_at = new Date().toLocaleString("zh-CN", { hour12: false });
    updateSaveState();
    renderMetaChips();
  }

  function addEdge(from, to) {
    if (from === to) {
      showToast("不能连接到任务自身", "error");
      return false;
    }
    if (!state.computed.nodeMap.has(from) || !state.computed.nodeMap.has(to)) {
      showToast("连线端点不存在", "error");
      return false;
    }
    if (state.computed.edges.some((edge) => edge.from === from && edge.to === to)) {
      showToast("这条依赖已经存在", "error");
      return false;
    }
    if (reachable(to, from, state.computed.successors)) {
      showToast("该连线会形成环，已阻止", "error");
      return false;
    }
    state.plan.edges = state.plan.edges || [];
    state.plan.edges.push({ from, to, kind: "dependency", label: "" });
    markDirty();
    showToast(`已添加依赖 ${from} → ${to}`, "success");
    return true;
  }

  function removeEdge(from, to, message) {
    const before = (state.plan.edges || []).length;
    state.plan.edges = (state.plan.edges || []).filter(
      (edge) => !(edge.from === from && edge.to === to)
    );
    if ((state.plan.edges || []).length === before) {
      showToast("未找到这条连线", "error");
      return false;
    }
    markDirty();
    if (message) showToast(message, "success");
    return true;
  }

  function nextNodeId() {
    const numbers = state.computed.nodes
      .map((node) => /^T(\d+)$/.exec(node.id))
      .filter(Boolean)
      .map((match) => Number(match[1]));
    let number = (numbers.length ? Math.max(...numbers) : 0) + 1;
    let id = `T${String(number).padStart(2, "0")}`;
    while (state.computed.nodeMap.has(id)) {
      number += 1;
      id = `T${String(number).padStart(2, "0")}`;
    }
    return id;
  }

  function addNodeAction() {
    const id = nextNodeId();
    const selected = state.selectedNodeId ? state.computed.nodeMap.get(state.selectedNodeId) : null;
    const agentId = Object.keys(AGENTS)[0] || "backend";
    const meta = agentMeta(agentId);
    const order = Math.max(0, ...state.computed.nodes.map((node) => node.order || 0)) + 1;
    state.plan.nodes.push({
      id,
      name: "新任务",
      description: "待补充：说明任务目标、关键产出与范围。",
      module: selected ? selected.module : "通用",
      priority: "P1",
      effort: 1,
      agent: agentId,
      agent_name: meta.name,
      agent_color: meta.color,
      agent_icon: meta.icon,
      agent_role: meta.role,
      role: meta.role,
      acceptance: "待补充：写出可验证的验收标准。",
      order,
      is_new: true,
    });
    state.plan.edges = state.plan.edges || [];
    if (selected) {
      state.plan.edges.push({ from: selected.id, to: id, kind: "dependency", label: "" });
    }
    state.selectedNodeId = id;
    state.selectedEdgeId = null;
    markDirty();
    renderGraph({ preserveView: false });
    window.requestAnimationFrame(() => {
      if (state.network) {
        state.network.focus(id, {
          scale: 1.1,
          animation: { duration: 380, easingFunction: "easeInOutQuad" },
        });
      }
    });
    showToast(
      selected ? `已新增 ${id}，并从 ${selected.id} 连接` : `已新增任务 ${id}，请在右侧补充内容`,
      "success"
    );
  }

  // ------------------------------------------------------------------
  // 连线模式
  // ------------------------------------------------------------------
  function setLinkMode(enabled) {
    state.linkMode = enabled;
    state.linkSource = null;
    $("btn-link-mode").classList.toggle("is-active", enabled);
    $("link-mode-hint").hidden = !enabled;
    if (enabled) {
      updateLinkHint("连线模式：先点击起点任务，再点击终点任务；按 Esc 退出。");
    }
  }

  function updateLinkHint(text) {
    const hint = $("link-mode-hint");
    hint.hidden = false;
    hint.innerHTML = text;
  }

  function handleLinkClick(nodeId) {
    if (!state.linkSource) {
      state.linkSource = nodeId;
      selectNode(nodeId);
      updateLinkHint(
        `已选择起点 <b>${esc(nodeId)}</b>，请点击终点任务；按 <kbd>Esc</kbd> 退出。`
      );
      return;
    }
    if (state.linkSource === nodeId) {
      showToast("起点与终点不能是同一个任务", "error");
      return;
    }
    const added = addEdge(state.linkSource, nodeId);
    if (added) {
      state.linkSource = null;
      setLinkMode(false);
      renderGraph({ preserveView: true });
    }
  }

  // ------------------------------------------------------------------
  // 保存 / 导出 / 模态
  // ------------------------------------------------------------------
  async function savePlan() {
    if (state.saving) return;
    state.saving = true;
    const button = $("btn-save");
    if (button) button.disabled = true;
    setSaveState("正在保存…", "");
    try {
      const response = await fetch(`/api/plan/${encodeURIComponent(state.planId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: state.plan }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const hint = payload.hint ? ` · ${payload.hint}` : "";
        throw new Error(`${payload.error || `HTTP ${response.status}`}${hint}`);
      }
      state.plan = payload.plan;
      state.initialPlan = deepClone(payload.plan);
      state.dirty = false;
      state.lastSavedAt = nowText();
      renderGraph({ preserveView: true });
      setSaveState(`已保存 ${state.lastSavedAt}`, "is-saved");
      showToast("方案已保存到服务端", "success");
    } catch (error) {
      setSaveState("保存失败，修改仍在页面中", "is-dirty");
      showToast(`保存失败：${error.message || "网络错误"}`, "error");
    } finally {
      state.saving = false;
      if (button) button.disabled = false;
    }
  }

  function updateSaveState() {
    if (state.saving) return;
    if (state.dirty) {
      setSaveState("有未保存修改", "is-dirty");
    } else if (state.lastSavedAt) {
      setSaveState(`已保存 ${state.lastSavedAt}`, "is-saved");
    } else if (state.plan.meta && state.plan.meta.edited) {
      setSaveState("已保存的方案", "is-saved");
    } else {
      setSaveState("已生成，可编辑", "is-saved");
    }
  }

  function setSaveState(text, className) {
    const element = $("save-state");
    if (!element) return;
    element.textContent = text;
    element.className = `save-state ${className || ""}`.trim();
  }

  function currentPlanJson() {
    return JSON.stringify(state.plan, null, 2);
  }

  function openJsonModal() {
    $("json-view").textContent = currentPlanJson();
    $("json-meta").textContent = `${state.computed.stats.nodes} 个任务 · ${state.computed.stats.edges} 条依赖 · ${state.computed.stats.agents} 个 Agent`;
    $("json-modal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeJsonModal() {
    $("json-modal").hidden = true;
    document.body.style.overflow = "";
  }

  function downloadJson() {
    const blob = new Blob([currentPlanJson()], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `se-workflow-plan-${state.planId}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    showToast("已导出方案 JSON", "success");
  }

  async function copyJson() {
    const text = currentPlanJson();
    try {
      await navigator.clipboard.writeText(text);
      showToast("JSON 已复制到剪贴板", "success");
    } catch (error) {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand("copy");
        showToast("JSON 已复制到剪贴板", "success");
      } catch (copyError) {
        showToast("复制失败，请手动选择文本", "error");
      }
      textarea.remove();
    }
  }

  function resetPlan() {
    if (!window.confirm("确定放弃当前编辑，恢复为上次生成 / 保存的方案吗？")) return;
    state.plan = deepClone(state.initialPlan);
    state.selectedNodeId = null;
    state.selectedEdgeId = null;
    state.linkSource = null;
    state.dirty = false;
    setLinkMode(false);
    renderGraph({ fit: true });
    showToast("已恢复为上次生成 / 保存的方案", "success");
  }

  // ------------------------------------------------------------------
  // 提示 / 元信息
  // ------------------------------------------------------------------
  function showToast(message, kind = "") {
    const toast = $("toast");
    if (!toast) return;
    toast.hidden = false;
    toast.className = `toast ${kind === "error" ? "is-error" : kind === "success" ? "is-success" : ""}`.trim();
    toast.textContent = message;
    if (state.toastTimer) clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
      toast.hidden = true;
    }, 3600);
  }

  function renderMetaChips() {
    const container = $("meta-chips");
    if (!container) return;
    const plan = state.plan;
    const requirement = plan.requirement || {};
    const meta = plan.meta || {};
    const chips = [];
    if (requirement.domain) chips.push(`<span class="chip domain">${esc(requirement.domain)}</span>`);
    if (requirement.scale) chips.push(`<span class="chip scale">${esc(requirement.scale)}</span>`);
    (requirement.platforms || []).forEach((platform) => {
      chips.push(`<span class="chip">${esc(platform)}</span>`);
    });
    const isMock = meta.engine === "mock";
    chips.push(
      `<span class="chip mode ${isMock ? "is-mock" : "is-llm"}">${esc(
        meta.engine_label || (isMock ? "Mock 模式" : "LLM 编排")
      )}</span>`
    );
    if (meta.model) chips.push(`<span class="chip muted-chip">${esc(meta.model)}</span>`);
    if (meta.generated_at) chips.push(`<span class="chip muted-chip">生成于 ${esc(meta.generated_at)}</span>`);
    if (meta.edited) chips.push('<span class="chip edited-chip">已编辑</span>');
    container.innerHTML = chips.join("");
  }

  function updateFooter() {
    const stats = state.computed.stats;
    $("footer-meta").textContent = `${stats.nodes} 个任务 · ${stats.edges} 条依赖 · ${stats.agents} 个 Agent · 关键路径 ${fmt(
      stats.critical_days
    )} 天`;
  }

  // ------------------------------------------------------------------
  // 事件绑定
  // ------------------------------------------------------------------
  function bindEvents() {
    const search = $("search-input");
    let searchTimer = null;
    search.addEventListener("input", () => {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.filters.q = search.value.trim();
        applyFilters();
      }, 160);
    });

    $("filter-agent").addEventListener("change", (event) => {
      state.filters.agent = event.target.value;
      applyFilters();
    });
    $("filter-priority").addEventListener("change", (event) => {
      state.filters.priority = event.target.value;
      applyFilters();
    });
    $("layout-select").addEventListener("change", (event) => {
      state.layout = event.target.value;
      if (state.network) state.network.setOptions(networkOptions());
      renderGraph({ fit: true, preserveView: false });
    });
    $("toggle-critical").addEventListener("change", (event) => {
      state.showCritical = event.target.checked;
      renderGraph({ preserveView: true });
    });

    $("btn-link-mode").addEventListener("click", () => setLinkMode(!state.linkMode));
    $("btn-add-node").addEventListener("click", addNodeAction);
    $("btn-relayout").addEventListener("click", relayoutGraph);
    $("btn-reset").addEventListener("click", resetPlan);
    $("btn-zoom-in").addEventListener("click", () => {
      if (!state.network) return;
      state.network.moveTo({ scale: state.network.getScale() * 1.25, animation: true });
    });
    $("btn-zoom-out").addEventListener("click", () => {
      if (!state.network) return;
      state.network.moveTo({ scale: state.network.getScale() / 1.25, animation: true });
    });
    $("btn-fit").addEventListener("click", () => fitGraph({ minScale: 0 }));
    $("btn-clear-filters").addEventListener("click", () => {
      search.value = "";
      $("filter-agent").value = "";
      $("filter-priority").value = "";
      state.filters = { q: "", agent: "", priority: "" };
      applyFilters();
    });

    // 视图切换：任务分解 <-> 工作流程图
    document.querySelectorAll(".view-tab").forEach((tab) => {
      tab.addEventListener("click", () => switchView(tab.dataset.view));
    });

    // 任务分解视图：搜索
    const decomposeSearch = $("decompose-search");
    let decomposeTimer = null;
    decomposeSearch.addEventListener("input", () => {
      if (decomposeTimer) clearTimeout(decomposeTimer);
      decomposeTimer = setTimeout(() => {
        state.decomposeQuery = decomposeSearch.value;
        renderDecompose();
      }, 150);
    });
    $("btn-decompose-clear").addEventListener("click", () => {
      decomposeSearch.value = "";
      state.decomposeQuery = "";
      renderDecompose();
    });

    // 任务分解视图：点前置依赖编号 → 跳到流程图并选中该任务
    $("decompose-body").addEventListener("click", (event) => {
      const chip = event.target.closest("[data-jump-node]");
      if (!chip) return;
      switchView("graph");
      selectNode(chip.dataset.jumpNode);
    });

    $("btn-save").addEventListener("click", savePlan);
    $("btn-export").addEventListener("click", downloadJson);
    $("btn-json").addEventListener("click", openJsonModal);
    $("btn-json-close").addEventListener("click", closeJsonModal);
    $("btn-download-json").addEventListener("click", downloadJson);
    $("btn-copy-json").addEventListener("click", copyJson);
    $("json-modal").addEventListener("click", (event) => {
      if (event.target === $("json-modal")) closeJsonModal();
    });

    const closeBanner = $("btn-close-banner");
    if (closeBanner) {
      closeBanner.addEventListener("click", () => {
        $("warning-banner").hidden = true;
      });
    }

    // 侧栏卡片使用事件委托
    $("stage-card").addEventListener("click", (event) => {
      const button = event.target.closest("[data-level]");
      if (!button) return;
      const level = Number(button.dataset.level);
      const stage = state.computed.stages.find((item) => item.level === level);
      if (stage && state.network) {
        state.network.fit({
          nodes: stage.node_ids,
          animation: { duration: 360, easingFunction: "easeInOutQuad" },
        });
      }
    });

    ["agent-card", "legend"].forEach((id) => {
      $(id).addEventListener("click", (event) => {
        const element = event.target.closest("[data-agent-filter]");
        if (!element) return;
        $("filter-agent").value = element.dataset.agentFilter;
        state.filters.agent = element.dataset.agentFilter;
        applyFilters();
      });
    });

    $("parallel-card").addEventListener("click", (event) => {
      const chip = event.target.closest("[data-node]");
      if (chip) selectNode(chip.dataset.node);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (!$("json-modal").hidden) {
          closeJsonModal();
          return;
        }
        if (state.linkMode) {
          setLinkMode(false);
          return;
        }
        if (state.selectedNodeId || state.selectedEdgeId) clearSelection();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        savePlan();
      }
    });

    window.addEventListener("beforeunload", (event) => {
      if (!state.dirty) return undefined;
      event.preventDefault();
      event.returnValue = "";
      return "";
    });
  }

  function populateAgentFilter() {
    const select = $("filter-agent");
    const current = select.value;
    select.innerHTML =
      '<option value="">全部 Agent</option>' +
      state.agentsCatalog
        .map(
          (agent) =>
            `<option value="${esc(agent.id)}">${esc(agent.icon)} ${esc(agent.name)}</option>`
        )
        .join("");
    if (current) select.value = current;
  }

  // ------------------------------------------------------------------
  // 启动
  // ------------------------------------------------------------------
  function init() {
    populateAgentFilter();
    bindEvents();
    try {
      renderGraph({ fit: true, preserveView: false });
      state.lastSavedAt = "";
      updateSaveState();
      // 调试 / 自动化入口：方便在浏览器控制台检查图数据与编辑动作
      window.__SE_WORKFLOW__ = {
        state,
        get computed() {
          return state.computed;
        },
        selectNode,
        selectEdge,
        clearSelection,
        renderGraph,
        computePlan,
        addEdge,
        removeEdge,
        addNode: addNodeAction,
        savePlan,
        showToast,
        switchView,
      };
    } catch (error) {
      console.error(error);
      $("graph").innerHTML = `<div class="graph-empty"><p>方案渲染失败：${esc(
        error.message || error
      )}</p></div>`;
      showToast(`方案渲染失败：${error.message || error}`, "error");
    }
  }

  init();
})();
