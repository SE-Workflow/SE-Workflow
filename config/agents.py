"""Agent 类型配置。

新增一种 Agent 只需在这里追加条目；任务表单、图例、LLM Prompt 中的
可选 Agent 清单都会自动读取此处配置。
字段说明：
    name  展示名
    role  职责说明（同时作为 LLM 编排时的角色约束）
    color 主题色（流程图方框边框 / 图例）
    icon  流程图方框与图例上的小图标
"""

AGENTS = {
    "pm": {
        "name": "PM Agent",
        "role": "需求澄清、范围管理、验收把关",
        "color": "#6366f1",
        "icon": "🧭",
    },
    "ux": {
        "name": "UX Agent",
        "role": "信息架构、交互流程与视觉规范",
        "color": "#ec4899",
        "icon": "🎨",
    },
    "architect": {
        "name": "Architect Agent",
        "role": "总体架构、技术选型、接口契约",
        "color": "#f59e0b",
        "icon": "🏗️",
    },
    "backend": {
        "name": "Backend Agent",
        "role": "服务端业务逻辑、接口与数据层",
        "color": "#10b981",
        "icon": "⚙️",
    },
    "frontend": {
        "name": "Frontend Agent",
        "role": "Web 前端、组件与交互实现",
        "color": "#3b82f6",
        "icon": "🖥️",
    },
    "mobile": {
        "name": "Mobile Agent",
        "role": "iOS / Android / 小程序客户端",
        "color": "#8b5cf6",
        "icon": "📱",
    },
    "data": {
        "name": "Data Agent",
        "role": "数据模型、指标、推荐与实验",
        "color": "#14b8a6",
        "icon": "📊",
    },
    "ai": {
        "name": "AI Agent",
        "role": "模型接入、RAG、Agent 编排与评测",
        "color": "#a855f7",
        "icon": "🤖",
    },
    "security": {
        "name": "Security Agent",
        "role": "安全、风控、隐私与合规",
        "color": "#0ea5e9",
        "icon": "🛡️",
    },
    "qa": {
        "name": "QA Agent",
        "role": "测试设计、自动化、质量收口",
        "color": "#ef4444",
        "icon": "🧪",
    },
    "devops": {
        "name": "DevOps Agent",
        "role": "环境、CI/CD、监控与发布",
        "color": "#64748b",
        "icon": "🚀",
    },
    "ops": {
        "name": "Ops Agent",
        "role": "运营配置、内容管理与数据看板",
        "color": "#f97316",
        "icon": "📈",
    },
}

DEFAULT_AGENT = "backend"
AGENT_IDS = tuple(AGENTS)

# LLM 可能返回中文 / 近义写法，这里做一次归一化，避免因 Agent 名不规范而失败。
AGENT_ALIASES = {
    "产品经理": "pm",
    "产品": "pm",
    "项目经理": "pm",
    "pm": "pm",
    "product": "pm",
    "设计": "ux",
    "ui": "ux",
    "ux": "ux",
    "design": "ux",
    "架构师": "architect",
    "架构": "architect",
    "architect": "architect",
    "architecture": "architect",
    "后端": "backend",
    "服务端": "backend",
    "backend": "backend",
    "前端": "frontend",
    "front-end": "frontend",
    "frontend": "frontend",
    "客户端": "mobile",
    "移动端": "mobile",
    "mobile": "mobile",
    "ios": "mobile",
    "android": "mobile",
    "数据": "data",
    "算法": "data",
    "data": "data",
    "ai": "ai",
    "算法工程师": "ai",
    "模型": "ai",
    "llm": "ai",
    "安全": "security",
    "风控": "security",
    "合规": "security",
    "security": "security",
    "测试": "qa",
    "质量": "qa",
    "qa": "qa",
    "test": "qa",
    "运维": "devops",
    "部署": "devops",
    "devops": "devops",
    "运营": "ops",
    "ops": "ops",
}

# 自由输入的补充需求没有显式 Agent 归属时，用关键词推断一个合理的执行者。
AGENT_GUESS_RULES = [
    (("支付", "结算", "退款", "对账", "订单", "交易"), "backend"),
    (("推荐", "算法", "指标", "报表", "数据", "埋点", "分析", "实验"), "data"),
    (("审核", "风控", "合规", "隐私", "安全", "加密", "权限"), "security"),
    (("视频", "音频", "直播", "转码", "播放"), "backend"),
    (("页面", "界面", "交互", "前端", "设计", "视觉", "组件"), "frontend"),
    (("客户端", "app", "ios", "android", "小程序", "推送"), "mobile"),
    (("部署", "监控", "运维", "发布", "环境"), "devops"),
    (("ai", "大模型", "智能", "问答", "知识库", "agent", "llm"), "ai"),
    (("后台", "运营", "管理台", "看板"), "ops"),
    (("需求", "验收", "范围", "流程"), "pm"),
]


def agent_catalog_text() -> str:
    """给 LLM Prompt 用的 Agent 清单（每行一个，含职责）。"""
    return "\n".join(
        f'- `{agent_id}`：{meta["name"]} —— {meta["role"]}' for agent_id, meta in AGENTS.items()
    )


def resolve_agent(value: object, fallback: str = DEFAULT_AGENT) -> str:
    """把 LLM / 用户输入的 Agent 写法归一化到 AGENTS 的 key。"""
    raw = str(value or "").strip()
    if not raw:
        return fallback
    lowered = raw.lower()
    if lowered in AGENTS:
        return lowered
    if lowered in AGENT_ALIASES:
        return AGENT_ALIASES[lowered]
    # 去掉 Agent / agent 后缀与空格，再试一次
    simplified = lowered.replace(" agent", "").replace("agent", "").strip(" -_")
    if simplified in AGENTS:
        return simplified
    if simplified in AGENT_ALIASES:
        return AGENT_ALIASES[simplified]
    # 名称包含匹配："Backend Agent" / "后端 Agent"
    for agent_id, meta in AGENTS.items():
        if lowered in meta["name"].lower() or meta["name"].lower().split()[0] in lowered:
            return agent_id
    for alias, agent_id in AGENT_ALIASES.items():
        if alias in lowered:
            return agent_id
    return fallback
