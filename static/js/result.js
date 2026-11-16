/* 结果页：任务树 / DAG 图 / 执行波次 / 数据导出 */
(() => {
  "use strict";

  const planEl = document.getElementById("plan-data");
  if (!planEl) return;

  let plan;
  try {
    plan = JSON.parse(planEl.textContent);
  } catch (error) {
    console.error("方案数据解析失败", error);
    return;
  }

  const tasks = plan.tasks || [];
  const tasksById = new Map(tasks.map((task) => [task.id, task]));
  const modules = plan.modules || [];
  const modulesById = new Map(modules.map((module) => [module.id, module]));
  const agents = (plan.orchestration && plan.orchestration.agents) || [];
  const agentsById = new Map(agents.map((agent) => [agent.id, agent]));
  const orchestration = plan.orchestration || {};
  const stats = plan.stats || {};
  const profile = plan.profile || {};

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const esc = (value) =>
    String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  const fmt = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return "0";
    return Number.isInteger(number) ? String(number) : number.toFixed(1);
  };
  const tint = (hex, alpha) => {
    let value = String(hex || "#64748b").replace("#", "");
    if (value.length === 3) value = value.split("").map((char) => char + char).join("");
    const red = parseInt(value.slice(0, 2), 16) || 100;
    const green = parseInt(value.slice(2, 4), 16) || 116;
    const blue = parseInt(value.slice(4, 6), 16) || 139;
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  };

  /* ---------------------------------------------------------------- 概览 */
  const renderProfileChips = () => {
    const host = $("#profile-chips");
    if (!host) return;
    const chips = [];
    if (profile.domain) {
      chips.push(`<span class="chip domain">产品域 <b>${esc(profile.domain.label)}</b></span>`);
    }
    if (profile.scale) {
      chips.push(
        `<span class="chip scale" title="${esc((profile.scale.reasons || []).join("；"))}">规模 <b>${esc(profile.scale.label)}</b></span>`
      );
    }
    (profile.platforms || []).forEach((platform) => {
      chips.push(`<span class="chip">平台 <b>${esc(platform)}</b></span>`);
    });
    (profile.features || []).slice(0, 6).forEach((feature) => {
      chips.push(
        `<span class="chip feature" title="${esc(feature.source)}">${esc(feature.label)}</span>`
      );
    });
    if ((profile.custom_modules || []).length) {
      chips.push(
        `<span class="chip">补充需求 <b>${profile.custom_modules.length}</b></span>`
      );
    }
    host.innerHTML = chips.join("");
  };

  const renderStats = () => {
    const host = $("#stat-grid");
    if (!host) return;
    const cards = [
      { value: stats.tasks, unit: "个", label: "原子任务" },
      { value: stats.modules, unit: "个", label: "任务模块" },
      { value: stats.agents, unit: "个", label: "执行 Agent" },
      { value: fmt(stats.total_effort), unit: "人天", label: "总工作量" },
      { value: fmt(stats.critical_days), unit: "天", label: "关键路径工期" },
      { value: Math.round((stats.parallel_ratio || 0) * 100), unit: "%", label: "可并行任务占比" },
    ];
    host.innerHTML = cards
      .map(
        (card) => `
        <div class="stat-card">
          <div class="stat-value">${esc(card.value)}<small>${esc(card.unit)}</small></div>
          <div class="stat-label">${esc(card.label)}</div>
        </div>`
      )
      .join("");
  };

  /* ---------------------------------------------------------------- 任务树 */
  const treeRoot = $("#tree-root");
  const treeCount = $("#tree-count");
  const searchInput = $("#tree-search");
  const agentFilter = $("#filter-agent");
  const priorityFilter = $("#filter-priority");

  const dependencyText = (task) =>
    task.depends_on && task.depends_on.length ? task.depends_on.join("、") : "无";

  const atomHtml = (task) => {
    const agent = agentsById.get(task.agent);
    const agentColor = agent ? agent.color : task.agent_color;
    return `
      <li class="atom" data-id="${esc(task.id)}" data-agent="${esc(task.agent)}" data-priority="${esc(task.priority)}">
        <button class="atom-head" type="button" aria-expanded="false">
          <span class="atom-id">${esc(task.id)}</span>
          <span class="atom-name" title="${esc(task.name)}">${esc(task.name)}</span>
          <span class="atom-meta">
            <span class="pill small pri-${esc(task.priority)}">${esc(task.priority)}</span>
            <span>${fmt(task.effort)} 人天</span>
            <span class="agent-tag"><i class="agent-dot" style="--agent-color:${esc(agentColor)}"></i>${esc(task.agent_name)}</span>
          </span>
          <span class="chevron" aria-hidden="true">▶</span>
        </button>
        <div class="atom-detail" hidden>
          <p class="atom-desc">${esc(task.description)}</p>
          <dl class="atom-facts">
            <div><dt>所属</dt><dd>${esc(task.module)} / ${esc(task.subtask)}</dd></div>
            <div><dt>时间窗</dt><dd>第 ${fmt(task.earliest_start)}–${fmt(task.earliest_finish)} 天 · 第 ${task.wave + 1} 波</dd></div>
            <div><dt>依赖任务</dt><dd>${esc(dependencyText(task))}</dd></div>
            <div><dt>验收标准</dt><dd>${esc(task.acceptance)}</dd></div>
          </dl>
        </div>
      </li>`;
  };

  const subtaskHtml = (subtask) => `
    <div class="subtask" data-subtask="${esc(subtask.id)}">
      <div class="subtask-head">
        <span class="subtask-id">${esc(subtask.id)}</span>
        <span>${esc(subtask.name)}</span>
        ${subtask.parallel ? '<span class="parallel-badge">并行分支</span>' : ""}
        <span class="muted">${subtask.task_count} 个任务 · ${fmt(subtask.effort)} 人天</span>
      </div>
      <ul class="atom-list">${subtask.children.map(atomHtml).join("")}</ul>
    </div>`;

  const moduleHtml = (module) => {
    const agent = agentsById.get(module.agent);
    const agentName = agent ? agent.name : module.agent_name;
    const agentColor = agent ? agent.color : "#64748b";
    return `
      <article class="module-card" data-module="${esc(module.id)}" style="--module-color:${esc(module.color)}">
        <button class="module-head" type="button" aria-expanded="false">
          <span class="chevron" aria-hidden="true">▶</span>
          <span class="module-dot"></span>
          <span class="module-title"><span class="mid">${esc(module.id)}</span><span class="mname">${esc(module.name)}</span></span>
          <span class="module-pills">
            ${module.custom ? '<span class="pill custom-pill">补充需求</span>' : ""}
            <span class="pill pri-${esc(module.priority)}">${esc(module.priority)}</span>
            <span class="pill agent-pill" style="--agent-color:${esc(agentColor)}"><i></i>${esc(agentName)}</span>
            <span class="pill">${module.task_count} 任务</span>
            <span class="pill">${fmt(module.effort)} 人天</span>
          </span>
        </button>
        <div class="module-body" hidden>
          <p class="module-desc">${esc(module.summary)}</p>
          ${module.children.map(subtaskHtml).join("")}
        </div>
      </article>`;
  };

  const applyFilters = () => {
    if (!treeRoot) return;
    const keyword = (searchInput?.value || "").trim().toLowerCase();
    const agentValue = agentFilter?.value || "";
    const priorityValue = priorityFilter?.value || "";
    const filtering = Boolean(keyword || agentValue || priorityValue);
    let visible = 0;

    $$(".module-card", treeRoot).forEach((card) => {
      let moduleVisible = false;
      $$(".atom", card).forEach((atomEl) => {
        const task = tasksById.get(atomEl.dataset.id);
        if (!task) return;
        let match = true;
        if (keyword) {
          const haystack = `${task.id} ${task.name} ${task.description} ${task.module} ${task.subtask} ${task.agent_name}`.toLowerCase();
          match = haystack.includes(keyword);
        }
        if (match && agentValue) match = task.agent === agentValue;
        if (match && priorityValue) match = task.priority === priorityValue;
        atomEl.classList.toggle("is-hidden", !match);
        if (match) {
          moduleVisible = true;
          visible += 1;
        }
      });

      $$(".subtask", card).forEach((subtaskEl) => {
        const hasVisible = $$(".atom", subtaskEl).some((atomEl) => !atomEl.classList.contains("is-hidden"));
        subtaskEl.classList.toggle("is-hidden", !hasVisible);
      });

      card.classList.toggle("is-hidden", !moduleVisible);
      if (moduleVisible && filtering) {
        card.classList.add("open");
        const body = $(".module-body", card);
        if (body) body.hidden = false;
        const head = $(".module-head", card);
        if (head) head.setAttribute("aria-expanded", "true");
      }
    });

    const empty = $("#tree-empty");
    if (empty) empty.hidden = visible !== 0;
    if (treeCount) {
      treeCount.textContent = filtering
        ? `筛选结果：${visible} / ${tasks.length} 个任务`
        : `共 ${modules.length} 个模块 · ${stats.subtasks || 0} 个子任务 · ${tasks.length} 个原子任务`;
    }
  };

  const bindTree = () => {
    if (!treeRoot) return;

    $$(".module-head", treeRoot).forEach((head) => {
      head.addEventListener("click", () => {
        const card = head.closest(".module-card");
        const body = $(".module-body", card);
        const open = !card.classList.contains("open");
        card.classList.toggle("open", open);
        if (body) body.hidden = !open;
        head.setAttribute("aria-expanded", String(open));
      });
    });

    $$(".atom-head", treeRoot).forEach((head) => {
      head.addEventListener("click", () => {
        const atom = head.closest(".atom");
        const detail = $(".atom-detail", atom);
        const open = detail && detail.hidden;
        if (detail) detail.hidden = !open;
        head.setAttribute("aria-expanded", String(Boolean(open)));
      });
    });

    if (searchInput) searchInput.addEventListener("input", applyFilters);
    if (agentFilter) agentFilter.addEventListener("change", applyFilters);
    if (priorityFilter) priorityFilter.addEventListener("change", applyFilters);

    const expandAll = $("#expand-all");
    if (expandAll) {
      expandAll.addEventListener("click", () => {
        $$(".module-card", treeRoot).forEach((card) => {
          card.classList.add("open");
          const body = $(".module-body", card);
          if (body) body.hidden = false;
          const head = $(".module-head", card);
          if (head) head.setAttribute("aria-expanded", "true");
        });
        $$(".atom-detail", treeRoot).forEach((detail) => (detail.hidden = false));
      });
    }

    const collapseAll = $("#collapse-all");
    if (collapseAll) {
      collapseAll.addEventListener("click", () => {
        $$(".module-card", treeRoot).forEach((card) => {
          card.classList.remove("open");
          const body = $(".module-body", card);
          if (body) body.hidden = true;
          const head = $(".module-head", card);
          if (head) head.setAttribute("aria-expanded", "false");
        });
        $$(".atom-detail", treeRoot).forEach((detail) => (detail.hidden = true));
      });
    }
  };

  const renderTree = () => {
    if (!treeRoot) return;
    const treeModules = Array.isArray(plan.tree) && plan.tree.length ? plan.tree : modules;
    treeRoot.innerHTML = treeModules.map(moduleHtml).join("") + '<p class="tree-empty" id="tree-empty" hidden>没有匹配的任务，试试更换关键词或筛选条件。</p>';
    if (agentFilter) {
      agentFilter.innerHTML =
        '<option value="">全部 Agent</option>' +
        agents
          .slice()
          .sort((a, b) => a.name.localeCompare(b.name))
          .map((agent) => `<option value="${esc(agent.id)}">${esc(agent.name)}</option>`)
          .join("");
    }
    bindTree();
    applyFilters();

    // 默认展开第一个模块，让三层结构一眼可见
    const firstModule = $(".module-card", treeRoot);
    if (firstModule) {
      firstModule.classList.add("open");
      const body = $(".module-body", firstModule);
      if (body) body.hidden = false;
      const head = $(".module-head", firstModule);
      if (head) head.setAttribute("aria-expanded", "true");
    }
  };

  /* ---------------------------------------------------------------- 标签页 */
  const tabs = $$(".tab");
  const panels = {
    tree: $("#panel-tree"),
    graph: $("#panel-graph"),
    waves: $("#panel-waves"),
    data: $("#panel-data"),
  };
  let wavesRendered = false;
  let dataRendered = false;

  const activateTab = (name) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    Object.entries(panels).forEach(([key, panel]) => {
      if (panel) panel.hidden = key !== name;
    });
    if (name === "graph") ensureGraph();
    if (name === "waves" && !wavesRendered) {
      wavesRendered = true;
      renderWaves();
    }
    if (name === "data" && !dataRendered) {
      dataRendered = true;
      renderData();
    }
  };

  tabs.forEach((tab) =>
    tab.addEventListener("click", () => {
      activateTab(tab.dataset.tab);
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, "", `#${tab.dataset.tab}`);
      }
    })
  );

  /* ---------------------------------------------------------------- DAG 图 */
  const graphEl = $("#graph");
  const asideEl = $("#graph-aside");
  const graphState = {
    view: "module",
    layout: "hierarchical",
    color: "module",
    critical: false,
    module: "",
    network: null,
    initialized: false,
  };

  const successors = new Map();
  (plan.edges || []).forEach((edge) => {
    if (!successors.has(edge.from)) successors.set(edge.from, []);
    successors.get(edge.from).push(edge.to);
  });

  const showDefaultAside = () => {
    if (!asideEl) return;
    const critical = orchestration.critical_tasks || [];
    const risks = orchestration.risks || [];
    const criticalPathHtml = critical.length
      ? critical
          .slice(0, 7)
          .map(
            (task) => `
            <div class="path-item">
              <span class="tid">${esc(task.id)}</span>
              <span>${esc(task.name.length > 16 ? task.name.slice(0, 15) + "…" : task.name)}</span>
            </div>`
          )
          .join('<div class="path-arrow">↓</div>')
      : '<p class="aside-tip">暂无关键路径</p>';

    const riskHtml = risks.length
      ? risks
          .map(
            (risk) =>
              `<div class="path-item"><span class="pill small ${risk.level === "warn" ? "pri-P0" : "pri-P2"}">${
                risk.level === "warn" ? "风险" : "提示"
              }</span><span>${esc(risk.text)}</span></div>`
          )
          .join("")
      : "";

    asideEl.innerHTML = `
      <div class="aside-empty">
        <div>
          <h3>解读编排</h3>
          <p class="aside-tip">滚轮缩放、拖拽画布平移、拖动节点微调位置；悬停查看任务详情，单击节点固定到这一栏。</p>
        </div>
        <div class="aside-block">
          <h4>关键路径 · ${fmt(orchestration.critical_days)} 天</h4>
          <div class="aside-path">${criticalPathHtml}</div>
          ${critical.length > 7 ? `<p class="path-more">… 共 ${critical.length} 个关键任务</p>` : ""}
        </div>
        <div class="aside-block">
          <h4>并行提示</h4>
          <p class="aside-tip">共 ${(orchestration.waves || []).length} 个执行波次，最大同一波次 ${Math.max(
            0,
            ...(orchestration.waves || []).map((wave) => wave.count)
          )} 个任务并行。</p>
        </div>
        ${riskHtml ? `<div class="aside-block"><h4>排期提示</h4><div class="aside-path">${riskHtml}</div></div>` : ""}
      </div>`;
  };

  const showTaskAside = (task) => {
    if (!asideEl) return;
    const dependencies = (task.depends_on || []).map((id) => tasksById.get(id)).filter(Boolean);
    const downstream = (successors.get(task.id) || []).map((id) => tasksById.get(id)).filter(Boolean);
    const chip = (item) => `<button type="button" class="dep-chip" data-focus="${esc(item.id)}">${esc(item.id)}</button>`;

    asideEl.innerHTML = `
      <div class="aside-head">
        <span class="node-badge">${esc(task.id)}</span>
        <button type="button" class="aside-close" aria-label="关闭详情">×</button>
      </div>
      <h3 class="aside-title">${esc(task.name)}</h3>
      <p class="aside-sub">${esc(task.module)} / ${esc(task.subtask)}</p>
      <div class="aside-tags">
        <span class="pill small pri-${esc(task.priority)}">${esc(task.priority)}</span>
        <span class="pill small">${fmt(task.effort)} 人天</span>
        <span class="pill small"><i class="agent-dot" style="--agent-color:${esc(task.agent_color)}"></i>${esc(task.agent_name)}</span>
        ${task.critical ? '<span class="pill small pri-P0">关键路径</span>' : ""}
      </div>
      <dl class="aside-facts">
        <div><dt>说明</dt><dd>${esc(task.description)}</dd></div>
        <div><dt>时间窗</dt><dd>第 ${fmt(task.earliest_start)}–${fmt(task.earliest_finish)} 天 · 第 ${task.wave + 1} 波 · 浮动 ${fmt(task.slack)} 天</dd></div>
        <div><dt>验收标准</dt><dd>${esc(task.acceptance)}</dd></div>
      </dl>
      <div class="aside-block">
        <h4>依赖任务（${dependencies.length}）</h4>
        <div class="dep-chips">${dependencies.length ? dependencies.map(chip).join("") : '<span class="aside-tip">无前置依赖</span>'}</div>
      </div>
      <div class="aside-block">
        <h4>下游任务（${downstream.length}）</h4>
        <div class="dep-chips">${downstream.length ? downstream.slice(0, 10).map(chip).join("") : '<span class="aside-tip">无下游任务</span>'}</div>
      </div>`;

    $(".aside-close", asideEl)?.addEventListener("click", () => {
      graphState.network?.unselectAll();
      showDefaultAside();
    });
    $$(".dep-chip", asideEl).forEach((button) => {
      button.addEventListener("click", () => focusTask(button.dataset.focus));
    });
  };

  const showAgentAside = (agent) => {
    if (!asideEl) return;
    const agentTasks = (agent.task_ids || []).map((id) => tasksById.get(id)).filter(Boolean);
    asideEl.innerHTML = `
      <div class="aside-head">
        <span class="node-badge">${esc(agent.icon)} ${esc(agent.name)}</span>
        <button type="button" class="aside-close" aria-label="关闭详情">×</button>
      </div>
      <h3 class="aside-title">${esc(agent.name)}</h3>
      <p class="aside-sub">${esc(agent.role)}</p>
      <div class="aside-tags">
        <span class="pill small">${agent.task_count} 个任务</span>
        <span class="pill small">${fmt(agent.effort)} 人天</span>
        <span class="pill small">占比 ${Math.round(agent.share * 100)}%</span>
      </div>
      <dl class="aside-facts">
        <div><dt>覆盖模块</dt><dd>${esc(agent.modules.join("、"))}</dd></div>
      </dl>
      <div class="aside-block">
        <h4>负责任务</h4>
        <div class="dep-chips">
          ${agentTasks
            .slice(0, 14)
            .map((task) => `<button type="button" class="dep-chip" data-switch="${esc(task.id)}">${esc(task.id)}</button>`)
            .join("")}
        </div>
        ${agentTasks.length > 14 ? `<p class="path-more">… 共 ${agentTasks.length} 个任务</p>` : ""}
      </div>`;

    $(".aside-close", asideEl)?.addEventListener("click", () => {
      graphState.network?.unselectAll();
      showDefaultAside();
    });
    $$("[data-switch]", asideEl).forEach((button) => {
      button.addEventListener("click", () => switchToTask(button.dataset.switch));
    });
  };

  const drillDown = (moduleId, taskId) => {
    const moduleSelect = $("#graph-module");
    if (moduleSelect) moduleSelect.value = moduleId || "";
    graphState.module = moduleId || "";
    const viewSelect = $("#view-mode");
    if (viewSelect) viewSelect.value = "task";
    graphState.view = "task";
    syncGraphControls();
    rebuildGraph();
    if (taskId) requestAnimationFrame(() => focusTask(taskId));
  };

  const switchToTask = (taskId) => {
    const task = tasksById.get(taskId);
    drillDown(task ? task.module_id : "", taskId);
  };

  const showModuleAside = (module) => {
    if (!asideEl) return;
    const moduleTasks = tasks.filter((task) => task.module_id === module.id);
    asideEl.innerHTML = `
      <div class="aside-head">
        <span class="node-badge">${esc(module.id)}</span>
        <button type="button" class="aside-close" aria-label="关闭详情">×</button>
      </div>
      <h3 class="aside-title">${esc(module.name)}</h3>
      <p class="aside-sub">${esc(module.summary || "")}</p>
      <div class="aside-tags">
        <span class="pill small pri-${esc(module.priority)}">${esc(module.priority)}</span>
        <span class="pill small">${module.task_count} 个任务</span>
        <span class="pill small">${fmt(module.effort)} 人天</span>
        <span class="pill small">${esc(module.agent_name)}</span>
      </div>
      <div class="aside-block">
        <h4>模块任务（${moduleTasks.length}）</h4>
        <div class="dep-chips">
          ${moduleTasks
            .map((task) => `<button type="button" class="dep-chip" data-module-task="${esc(task.id)}" title="${esc(task.name)}">${esc(task.id)}</button>`)
            .join("")}
        </div>
        <p class="aside-tip" style="margin-top:8px">点击任务编号切到「任务 DAG」并定位节点。</p>
      </div>`;

    $(".aside-close", asideEl)?.addEventListener("click", () => {
      graphState.network?.unselectAll();
      showDefaultAside();
    });
    $$("[data-module-task]", asideEl).forEach((button) => {
      button.addEventListener("click", () => drillDown(module.id, button.dataset.moduleTask));
    });
  };

  const focusTask = (taskId) => {
    const task = tasksById.get(taskId);
    if (!task) return;
    showTaskAside(task);
    if (graphState.network && graphState.view === "task") {
      graphState.network.selectNodes([taskId]);
      graphState.network.focus(taskId, { scale: 1.15, animation: { duration: 420, easingFunction: "easeInOutQuad" } });
    }
  };

  const moduleGraphData = () => {
    const nodes = plan.graph.module.nodes.map((node) => {
      const colorSet = node.colors.module;
      const critical = graphState.critical && node.critical;
      return {
        id: node.id,
        label: node.label,
        title: node.title,
        level: node.level,
        shape: "box",
        margin: 10,
        widthConstraint: { maximum: 200 },
        borderWidth: critical ? 3 : 1.2,
        borderWidthSelected: 3,
        color: {
          background: colorSet.background,
          border: critical ? "#ef4444" : colorSet.border,
          highlight: { background: colorSet.background, border: critical ? "#ef4444" : colorSet.border },
          hover: { background: colorSet.background, border: critical ? "#ef4444" : colorSet.border },
        },
        font: { color: "#1e293b", size: 13 },
        shadow: { enabled: true, color: "rgba(15,23,42,0.08)", size: 6, x: 0, y: 2 },
      };
    });
    const edges = plan.graph.module.edges.map((edge) => ({
      id: edge.id,
      from: edge.from,
      to: edge.to,
      title: edge.title,
      width: 1.3,
      color: { color: "#94a3b8", highlight: "#4f46e5", hover: "#4f46e5" },
      arrows: { to: { enabled: true, scaleFactor: 0.6, type: "arrow" } },
    }));
    return { nodes, edges };
  };

  const taskGraphData = () => {
    const visibleNodes = graphState.module
      ? plan.graph.task.nodes.filter((node) => node.module_id === graphState.module)
      : plan.graph.task.nodes;
    const allowed = new Set(visibleNodes.map((node) => node.id));
    const nodes = visibleNodes.map((node) => {
      const colorSet = node.colors[graphState.color] || node.colors.module;
      const critical = graphState.critical && node.critical;
      return {
        id: node.id,
        label: node.label,
        title: node.title,
        level: graphState.module ? node.rank : node.level,
        shape: "box",
        margin: 8,
        widthConstraint: { maximum: 190 },
        borderWidth: critical ? 3 : 1.2,
        borderWidthSelected: 3,
        color: {
          background: colorSet.background,
          border: critical ? "#ef4444" : colorSet.border,
          highlight: {
            background: colorSet.background,
            border: critical ? "#ef4444" : colorSet.border,
          },
          hover: {
            background: colorSet.hover ? colorSet.hover.background : colorSet.background,
            border: critical ? "#ef4444" : colorSet.border,
          },
        },
        font: node.font,
        shadow: { enabled: true, color: "rgba(15,23,42,0.08)", size: 6, x: 0, y: 2 },
      };
    });

    const edges = plan.graph.task.edges
      .filter((edge) => allowed.has(edge.from) && allowed.has(edge.to))
      .map((edge) => {
      const critical = graphState.critical && edge.critical;
      const dependency = edge.kind === "dep";
      return {
        id: edge.id,
        from: edge.from,
        to: edge.to,
        title: edge.title,
        dashes: dependency && !critical ? [5, 4] : false,
        width: critical ? 2.6 : dependency ? 1.1 : 1.3,
        color: {
          color: critical ? "#ef4444" : dependency ? "#94a3b8" : "#c2cad8",
          highlight: "#4f46e5",
          hover: "#4f46e5",
        },
        arrows: { to: { enabled: true, scaleFactor: 0.55, type: "arrow" } },
      };
    });
    return { nodes, edges };
  };

  const agentGraphData = () => {
    const sourceNodes = plan.graph.agent.nodes;
    const radiusX = 340;
    const radiusY = 230;
    const nodes = sourceNodes.map((node, index) => {
      const angle = (Math.PI * 2 * index) / sourceNodes.length - Math.PI / 2;
      return {
        id: node.id,
        label: node.label,
        title: node.title,
        shape: "box",
        margin: 10,
        widthConstraint: { maximum: 190 },
        borderWidth: 2,
        borderWidthSelected: 3,
        x: Math.round(Math.cos(angle) * radiusX),
        y: Math.round(Math.sin(angle) * radiusY),
        color: {
          background: tint(node.color, 0.16),
          border: node.color,
          highlight: { background: tint(node.color, 0.3), border: node.color },
          hover: { background: tint(node.color, 0.24), border: node.color },
        },
        font: { color: "#1e293b", size: 12 },
      };
    });
    const edges = plan.graph.agent.edges.map((edge) => ({
      id: edge.id,
      from: edge.from,
      to: edge.to,
      label: edge.label,
      title: edge.title,
      width: edge.width,
      color: { color: "#94a3b8", highlight: "#4f46e5", hover: "#4f46e5" },
      font: { size: 10, color: "#475569", background: "#ffffff", strokeWidth: 0 },
      arrows: { to: { enabled: true, scaleFactor: 0.6 } },
    }));
    return { nodes, edges };
  };

  const graphOptions = (hierarchical) => {
    const isModule = graphState.view === "module";
    const isAgent = graphState.view === "agent";
    return {
      autoResize: true,
      layout: hierarchical
        ? {
            hierarchical: {
              enabled: true,
              direction: "UD",
              sortMethod: "directed",
              levelSeparation: isModule ? 132 : 118,
              nodeSpacing: isModule ? 210 : 200,
              treeSpacing: isModule ? 260 : 210,
              blockShifting: true,
              edgeMinimization: true,
              parentCentralization: true,
            },
          }
        : { hierarchical: false },
      physics:
        hierarchical || isAgent
          ? { enabled: false }
          : {
              enabled: true,
              solver: "barnesHut",
              barnesHut: {
                gravitationalConstant: -14000,
                centralGravity: 0.32,
                springLength: 150,
                springConstant: 0.05,
                damping: 0.42,
                avoidOverlap: 0.55,
              },
              stabilization: { enabled: true, iterations: 260, updateInterval: 30, fit: true },
            },
      edges: {
        smooth: hierarchical
          ? { enabled: true, type: "cubicBezier", forceDirection: "vertical", roundness: 0.35 }
          : { enabled: true, type: "continuous", roundness: 0.35 },
        arrows: { to: { enabled: true, scaleFactor: 0.55 } },
        selectionWidth: 1.5,
        hoverWidth: 0.2,
      },
      interaction: {
        hover: true,
        tooltipDelay: 140,
        navigationButtons: false,
        zoomView: true,
        dragView: true,
        multiselect: false,
      },
    };
  };

  const renderLegend = () => {
    const host = $("#graph-legend");
    if (!host) return;
    const legend = plan.legend || {};
    let items = [];
    let modeLabel = "模块";
    if (graphState.view === "agent") {
      items = legend.agent || [];
      modeLabel = "Agent";
    } else if (graphState.view === "module") {
      items = legend.module || [];
      modeLabel = "模块";
    } else {
      const map = { module: "模块", agent: "Agent", priority: "优先级", wave: "波次" };
      modeLabel = map[graphState.color] || "模块";
      items = legend[graphState.color] || [];
    }

    const itemsHtml = items
      .map(
        (item) =>
          `<span class="legend-item"><span class="legend-dot" style="--c:${esc(item.color)}"></span>${esc(item.label)}</span>`
      )
      .join("");

    host.innerHTML = `
      <div class="legend-group"><span class="lg-label">${esc(modeLabel)}</span>${itemsHtml}</div>
      <div class="legend-group">
        <span class="lg-label">连线</span>
        <span class="legend-item"><span class="legend-line"></span>任务流转</span>
        <span class="legend-item"><span class="legend-line dashed"></span>模块依赖</span>
        <span class="legend-item"><span class="legend-line critical"></span>关键路径</span>
      </div>`;
  };

  const buildGraph = () => {
    if (!graphEl) return;
    if (typeof vis === "undefined" || !vis.Network) {
      graphEl.innerHTML = '<p class="tree-empty">可视化库未加载：请确认 static/vendor/vis-network.min.js 存在。</p>';
      return;
    }
    if (graphState.network) {
      graphState.network.destroy();
      graphState.network = null;
    }
    const hint = $("#graph-hint");
    graphEl.innerHTML = "";
    if (hint) hint.hidden = true;

    const isTask = graphState.view === "task";
    const isModule = graphState.view === "module";
    const hierarchical = !(!isTask && !isModule) && graphState.layout === "hierarchical";
    const data = isModule ? moduleGraphData() : isTask ? taskGraphData() : agentGraphData();
    const network = new vis.Network(graphEl, data, graphOptions(hierarchical));
    graphState.network = network;

    network.on("selectNode", (params) => {
      const id = params.nodes && params.nodes[0];
      if (!id) return;
      if (graphState.view === "module") {
        const module = modulesById.get(id);
        if (module) showModuleAside(module);
      } else if (graphState.view === "task") {
        const task = tasksById.get(id);
        if (task) showTaskAside(task);
      } else {
        const agent = agentsById.get(id);
        if (agent) showAgentAside(agent);
      }
    });
    network.on("deselectNode", () => showDefaultAside());
    network.on("stabilizationIterationsDone", () => network.fit({ animation: { duration: 280 } }));
    if (hierarchical) {
      network.once("afterDrawing", () => network.fit({ animation: false }));
    }

    renderLegend();
    updateGraphHint();
    showDefaultAside();
  };

  const updateGraphHint = () => {
    const hint = $("#graph-hint");
    if (!hint) return;
    hint.hidden = !(graphState.view === "task" && !graphState.module && tasks.length > 40);
  };

  const ensureGraph = () => {
    if (!graphEl) return;
    if (graphState.initialized) {
      graphState.network?.redraw();
      return;
    }
    graphState.initialized = true;
    requestAnimationFrame(() => requestAnimationFrame(buildGraph));
  };

  const rebuildGraph = () => {
    if (!graphState.initialized) {
      ensureGraph();
      return;
    }
    buildGraph();
  };

  const syncGraphControls = () => {
    const layoutMode = $("#layout-mode");
    const colorMode = $("#color-mode");
    const moduleSelect = $("#graph-module");
    if (layoutMode) layoutMode.disabled = graphState.view === "agent";
    if (colorMode) colorMode.disabled = graphState.view !== "task";
    if (moduleSelect) moduleSelect.disabled = graphState.view !== "task";
  };

  const bindGraphControls = () => {
    const viewMode = $("#view-mode");
    const layoutMode = $("#layout-mode");
    const colorMode = $("#color-mode");
    const moduleSelect = $("#graph-module");
    const critical = $("#show-critical");

    if (moduleSelect) {
      moduleSelect.innerHTML =
        '<option value="">全部模块</option>' +
        modules
          .map((module) => `<option value="${esc(module.id)}">${esc(module.name)}</option>`)
          .join("");
      moduleSelect.addEventListener("change", () => {
        graphState.module = moduleSelect.value;
        rebuildGraph();
      });
    }

    viewMode?.addEventListener("change", () => {
      graphState.view = viewMode.value;
      syncGraphControls();
      rebuildGraph();
    });
    layoutMode?.addEventListener("change", () => {
      graphState.layout = layoutMode.value;
      rebuildGraph();
    });
    colorMode?.addEventListener("change", () => {
      graphState.color = colorMode.value;
      rebuildGraph();
    });
    critical?.addEventListener("change", () => {
      graphState.critical = critical.checked;
      rebuildGraph();
    });

    $("#graph-zoom-in")?.addEventListener("click", () => {
      const network = graphState.network;
      if (network) network.moveTo({ scale: network.getScale() * 1.25, animation: { duration: 180 } });
    });
    $("#graph-zoom-out")?.addEventListener("click", () => {
      const network = graphState.network;
      if (network) network.moveTo({ scale: network.getScale() * 0.8, animation: { duration: 180 } });
    });
    $("#graph-fit")?.addEventListener("click", () => {
      graphState.network?.fit({ animation: { duration: 280 } });
    });

    window.addEventListener("resize", () => graphState.network?.redraw());
  };

  /* ---------------------------------------------------------------- 执行波次 */
  const renderWaves = () => {
    const host = $("#waves-root");
    const summary = $("#wave-summary");
    if (!host) return;
    const waves = orchestration.waves || [];
    const maxParallel = Math.max(0, ...waves.map((wave) => wave.count));
    const average = waves.length ? waves.reduce((total, wave) => total + wave.count, 0) / waves.length : 0;

    if (summary) {
      summary.innerHTML = `
        <span class="pill">${waves.length} 个波次</span>
        <span class="pill">最大并行 ${maxParallel} 个任务</span>
        <span class="pill">平均每波 ${fmt(average)} 个任务</span>`;
    }

    host.innerHTML = waves
      .map((wave) => {
        const items = wave.tasks
          .map((id) => tasksById.get(id))
          .filter(Boolean)
          .map((task) => {
            const agent = agentsById.get(task.agent);
            return `
              <li>
                <button type="button" class="wave-task" data-task="${esc(task.id)}">
                  <span class="agent-dot" style="--c:${esc(agent ? agent.color : "#94a3b8")}"></span>
                  <span class="tid">${esc(task.id)}</span>
                  <span class="tname" title="${esc(task.name)}">${esc(task.name)}</span>
                  <span class="pill small pri-${esc(task.priority)}">${esc(task.priority)}</span>
                  <span class="agent-name">${esc(task.agent_name)}</span>
                </button>
              </li>`;
          })
          .join("");

        return `
          <article class="wave-card ${wave.parallel ? "is-parallel" : ""}">
            <div class="wave-head">
              <span class="wave-no">第 ${wave.index + 1} 波</span>
              <span class="wave-range">第 ${fmt(wave.start)}–${fmt(wave.end)} 天</span>
              <span class="wave-badge ${wave.parallel ? "" : "serial"}">${wave.parallel ? `并行 ${wave.count} 个任务` : "串行任务"}</span>
            </div>
            <p class="wave-effort">${wave.agents.length} 个 Agent · 合计 ${fmt(wave.effort)} 人天</p>
            <ul class="wave-tasks">${items}</ul>
          </article>`;
      })
      .join("");

    $$(".wave-task", host).forEach((button) => {
      button.addEventListener("click", () => {
        const task = tasksById.get(button.dataset.task);
        activateTab("graph");
        requestAnimationFrame(() => {
          if (task) drillDown(task.module_id, task.id);
        });
      });
    });
  };

  /* ---------------------------------------------------------------- 数据页 */
  const planJson = () => JSON.stringify(plan, null, 2);

  const renderData = () => {
    const pre = $("#plan-json");
    if (pre) pre.textContent = planJson();
  };

  const downloadPlan = () => {
    const blob = new Blob([planJson()], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "se-workflow-plan.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  };

  const copyPlan = async () => {
    const button = $("#copy-json");
    try {
      await navigator.clipboard.writeText(planJson());
      if (button) {
        const original = button.textContent;
        button.textContent = "已复制 ✓";
        setTimeout(() => (button.textContent = original), 1600);
      }
    } catch (error) {
      console.warn("复制失败", error);
    }
  };

  const bindDataActions = () => {
    $("#download-json")?.addEventListener("click", downloadPlan);
    $("#download-json-2")?.addEventListener("click", downloadPlan);
    $("#copy-json")?.addEventListener("click", copyPlan);
  };

  /* ---------------------------------------------------------------- 启动 */
  renderProfileChips();
  renderStats();
  renderTree();
  bindGraphControls();
  syncGraphControls();
  bindDataActions();

  // 支持 ?view=task / module / agent 直接打开指定视图，便于分享与截图
  const params = new URLSearchParams(window.location.search);
  const urlView = params.get("view");
  const initialViewSelect = $("#view-mode");
  if (initialViewSelect && ["module", "task", "agent"].includes(urlView)) {
    initialViewSelect.value = urlView;
    graphState.view = urlView;
    syncGraphControls();
  }

  const urlModule = params.get("module");
  const initialModuleSelect = $("#graph-module");
  if (initialModuleSelect && urlModule && modulesById.has(urlModule)) {
    initialModuleSelect.value = urlModule;
    graphState.module = urlModule;
  }

  const urlTab = params.get("tab");
  const initialTab = urlTab && panels[urlTab] ? urlTab : window.location.hash.replace("#", "");
  if (initialTab && panels[initialTab]) {
    activateTab(initialTab);
  }
})();
