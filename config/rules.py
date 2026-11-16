"""编排规则与界面元数据配置。

这里集中放“可调参数”：规模系数、优先级颜色、任务默认工作量、校验阈值、示例需求。
业务同学改这里即可调整排期口径与提示阈值，不需要改算法。
"""

SCALE_META = {
    "S": {
        "label": "小型",
        "description": "MVP / 小工具，单团队可在数周内交付",
        "factor": 0.6,
        "modules_limit": 8,
    },
    "M": {
        "label": "中型",
        "description": "标准产品版本，多团队协作",
        "factor": 1.0,
        "modules_limit": 16,
    },
    "L": {
        "label": "大型",
        "description": "平台级产品，多端、多模块、高并发",
        "factor": 1.4,
        "modules_limit": 30,
    },
}

PRIORITY_META = {
    "P0": {"label": "P0 · 必须", "color": "#ef4444", "weight": 3},
    "P1": {"label": "P1 · 重要", "color": "#f59e0b", "weight": 2},
    "P2": {"label": "P2 · 增强", "color": "#64748b", "weight": 1},
}

# 模块与波次的配色盘，按顺序循环取色。
MODULE_COLORS = [
    "#6366f1", "#3b82f6", "#06b6d4", "#10b981", "#84cc16", "#f59e0b",
    "#f97316", "#ef4444", "#ec4899", "#a855f7", "#8b5cf6", "#14b8a6",
    "#0ea5e9", "#d946ef", "#f43f5e", "#22c55e",
]

# 自动展开能力点时的原子任务工作量（人天，最终还会乘规模系数）。
CAPABILITY_EFFORT = {
    "build": 4.0,
    "verify": 1.5,
}

CAPABILITY_ACCEPTANCE = {
    "build": "功能按设计可用，主流程与异常分支自测通过，代码评审通过",
    "verify": "联调与验收用例通过，P0/P1 缺陷清零，文档已更新",
}

CAPABILITY_DESCRIPTIONS = {
    "build": "明确「{cap}」的规则、数据与接口，完成开发与自测，覆盖正常与异常路径。",
    "verify": "完成「{cap}」的联调、边界测试与验收，补充配置项与使用说明。",
}

# 自由文本里的补充需求，最多再拆出几个模块，避免抽象输入被过度拆解。
CUSTOM_MODULE_LIMIT = 3
CUSTOM_MODULE_TAG = "补充需求"

# 执行波次：把总工期切成若干段，每段内的任务视为同波次并行推进。
WAVE_TARGET = 11

# 排期风险提示阈值
CRITICAL_DAYS_WARN = 45
AGENT_SHARE_WARN = 0.42
PARALLEL_MODULE_WARN = 9

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}

# 首页示例：抽象短句 + 结构化专业规格，覆盖“通用性”验收。
EXAMPLES = [
    {
        "title": "我要做一个小红书",
        "tag": "抽象需求",
        "text": "我要做一个小红书",
    },
    {
        "title": "我要做微信",
        "tag": "抽象需求",
        "text": "我要做微信",
    },
    {
        "title": "健身会员运营 App",
        "tag": "专业规格",
        "text": (
            "为连锁健身房做一套会员运营 App（iOS / Android）：\n"
            "- 支持会员注册、扫码入场、课表预约与取消\n"
            "- 支持私教课时购买、支付、退款与发票\n"
            "- 教练端可查看排课、会员训练记录并布置训练计划\n"
            "- 支持多门店与多租户隔离，总部可配置各门店权限\n"
            "- 后台需要营收报表、会员分层与营销触达\n"
            "- 要求弱网可用、数据合规，可支撑千万级会员"
        ),
    },
    {
        "title": "轻量待办清单工具",
        "tag": "小规模",
        "text": "做一个简单的待办清单小工具，支持任务分组、提醒和完成统计，先出 MVP。",
    },
]
