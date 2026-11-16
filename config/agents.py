"""Agent 类型配置。

新增一种 Agent 只需在这里追加条目；任务模板、编排结果和前端图例都会自动读取。
字段说明：
    name  展示名
    role  职责说明
    color 主题色（任务 DAG、Agent 协作图、任务树共用）
    icon  界面上的小图标
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
