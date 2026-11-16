"""Prompt 模板配置（集中管理，便于调优）。

两阶段调用：
1. 任务分解（DECOMPOSE）：需求 → 一组原子任务；
2. Agent 编排（ORCHESTRATE）：任务清单 → 依赖边 / 分层阶段 / 并行分组 / Agent 指派。

模板中使用 `$变量` 占位，由 `build_*_messages` 注入实际内容；
JSON 示例中的花括号不需要转义。修改这里即可调整大模型的输出口径。
"""

from __future__ import annotations

from string import Template

PROMPT_VERSION = "v5.1"

DECOMPOSE_SYSTEM = Template(
    """你是一名资深软件工程负责人（SE），擅长把一句话需求或一份专业规格拆成可执行、可验收的原子任务。

你只输出**严格 JSON**：不要 Markdown、不要代码围栏、不要任何解释文字。

输出结构必须为：
{
  "summary": "一句话概括这个需求的目标（不超过 60 字）",
  "domain": "需求所属领域，如 内容社区 / 即时通讯 / 电商",
  "scale": "小型 | 中型 | 大型",
  "platforms": ["Web", "iOS / Android", "微信小程序"],
  "tasks": [
    {
      "id": "T01",
      "name": "任务名称（不超过 24 字）",
      "description": "这个任务具体要做什么、关键产出是什么（40-120 字）",
      "module": "所属模块或工作流阶段，如 需求与规划 / 架构设计 / 后端服务 / 前端体验 / 质量保障",
      "priority": "P0 | P1 | P2",
      "effort": 2.0,
      "agent": "承接该任务的 Agent 类型 id",
      "acceptance": "可验证的验收标准（不超过 80 字）"
    }
  ]
}

硬性要求：
1. 任务数量控制在 $min_tasks-$max_tasks 个；需求越复杂任务越多，但不要为了凑数拆分。
2. id 必须从 T01 连续编号；每个任务都必须可独立交付、可验收。
3. priority 只能是 P0 / P1 / P2：P0 是阻塞上线的核心能力，P1 是重要能力，P2 是增强项。
4. effort 为预估人天，0.5-10 之间的数字，可用 0.5 步进。
5. agent 只能从下面的 Agent 清单中选择 id，禁止自创：
$agent_catalog
6. 必须覆盖需求中的关键功能与质量要求（性能、安全、合规、多端等），不要遗漏。
7. 任务之间不要互相包含，避免同一件事拆成多个重复任务。
8. 只输出 JSON 对象本身，不要输出任何其他内容。"""
)

DECOMPOSE_USER = Template(
    """请把下面的需求分解为任务清单。

【需求】
$requirement

请严格按系统提示中的 JSON 结构输出。"""
)

ORCHESTRATE_SYSTEM = Template(
    """你是一名多 Agent 系统的编排专家。你会拿到一份已经分解好的任务清单，
需要决定任务之间的依赖关系、执行分层、并行分组，并为每个任务指派承接 Agent。

你只输出**严格 JSON**：不要 Markdown、不要代码围栏、不要任何解释文字。

输出结构必须为：
{
  "summary": "一句话说明编排策略（如：先架构后并行研发，最后统一联调）",
  "edges": [
    {"from": "T01", "to": "T02", "kind": "dependency", "label": ""}
  ],
  "stages": [
    {"level": 0, "name": "阶段名称", "parallel": false, "nodes": ["T01"]}
  ],
  "assignments": [
    {"node": "T01", "agent": "pm", "role": "负责需求边界与验收口径"}
  ],
  "parallel_groups": [
    {"name": "可并行组名称", "nodes": ["T03", "T04"]}
  ]
}

硬性要求：
1. edges 必须构成有向无环图（DAG），禁止环、禁止自环、禁止重复边；from 是前置任务，to 是后继任务。
2. edges 中的 id 必须来自输入任务清单；kind 取值只能是 dependency（交付依赖）、flow（流转/交接）、review（评审/验收）。
3. stages 必须覆盖全部任务，level 从 0 开始连续递增；同一 level 的任务表示可以并行推进。
4. stages 的划分必须与 edges 一致：若 A → B，则 B 的 level 必须大于 A 的 level。
5. assignments 必须覆盖全部任务；agent 只能从下面的 Agent 清单中选择 id：
$agent_catalog
6. 每个任务只指派一个主责 Agent；需要协作时，在 role 里说明协作对象。
7. parallel_groups 可选，用来显式标注同一阶段内可以并行推进的任务组，每组至少 2 个任务。
8. 起点任务与终点任务要清晰：至少有 1 个无前置的起点、1 个无后继的收口任务。
9. 只输出 JSON 对象本身，不要输出任何其他内容。"""
)

ORCHESTRATE_USER = Template(
    """请为下面的需求与任务清单生成 Agent 编排。

【原始需求】
$requirement

【任务清单】
$tasks_json

请严格按系统提示中的 JSON 结构输出。"""
)

REPAIR_USER = Template(
    """你上一次的输出无法被解析或校验为合规 JSON。错误信息：
$error

上一次输出的开头如下（可能被截断）：
$previous

请修复它，并只输出一个合法的 JSON 对象；字段结构必须与最初的要求一致。
不要输出解释、Markdown 代码围栏或任何额外文字。"""
)

CONNECTION_TEST_SYSTEM = "你是一个 API 连通性测试助手。"
CONNECTION_TEST_USER = "只回复两个字：正常"


def _agent_catalog_block(agent_catalog: str) -> str:
    return "\n".join(f"   {line}" for line in agent_catalog.splitlines() if line.strip())


def build_decompose_messages(
    requirement: str,
    agent_catalog: str,
    min_tasks: int,
    max_tasks: int,
) -> list[dict]:
    system = DECOMPOSE_SYSTEM.safe_substitute(
        min_tasks=min_tasks,
        max_tasks=max_tasks,
        agent_catalog=_agent_catalog_block(agent_catalog),
    )
    user = DECOMPOSE_USER.safe_substitute(requirement=requirement.strip())
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_orchestrate_messages(requirement: str, tasks_json: str, agent_catalog: str) -> list[dict]:
    system = ORCHESTRATE_SYSTEM.safe_substitute(agent_catalog=_agent_catalog_block(agent_catalog))
    user = ORCHESTRATE_USER.safe_substitute(
        requirement=requirement.strip(),
        tasks_json=tasks_json,
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_repair_message(error: str, previous_output: str) -> str:
    previous = (previous_output or "").strip()
    if len(previous) > 6000:
        previous = previous[:6000] + "\n…（已截断）"
    return REPAIR_USER.safe_substitute(error=error, previous=previous)
