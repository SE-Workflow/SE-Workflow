"""需求域与能力特征配置。

- DOMAINS：产品类型识别（关键词命中 + 领域默认模块/规模/特征），换一个输入即可复用同一套流程。
- FEATURES：从需求文本里识别能力关键词（支付、推荐、直播……），并映射到需要补充的任务模块。
- FEATURE_MODULES：一个能力特征需要引入哪些模块。

新增产品类型 / 能力特征时只改本文件。
"""

# 能力特征：id -> 展示名 + 触发关键词 + 默认模块
FEATURES = {
    "realtime": {
        "label": "实时通讯",
        "keywords": ["即时通讯", "实时", "聊天", "消息", "长连接", "im", "会话"],
    },
    "voice": {
        "label": "语音 / 音频",
        "keywords": ["语音", "音频", "麦克风", "录音"],
    },
    "video": {
        "label": "视频能力",
        "keywords": ["视频", "短视频", "转码", "播放", "vlog"],
    },
    "live": {
        "label": "直播",
        "keywords": ["直播", "连麦", "弹幕", "主播", "打赏"],
    },
    "payment": {
        "label": "支付交易",
        "keywords": ["支付", "交易", "下单", "购买", "红包", "结算", "退款", "收银台"],
    },
    "recommendation": {
        "label": "推荐 / 信息流",
        "keywords": ["推荐", "信息流", "个性化", "feed", "算法", "排序"],
    },
    "search": {
        "label": "搜索",
        "keywords": ["搜索", "检索", "查找", "联想"],
    },
    "moderation": {
        "label": "内容审核",
        "keywords": ["审核", "风控", "举报", "违规", "不良信息"],
    },
    "notification": {
        "label": "消息推送",
        "keywords": ["推送", "通知", "提醒", "触达"],
    },
    "ai": {
        "label": "AI 能力",
        "keywords": ["ai", "大模型", "智能", "问答", "知识库", "llm", "agent", "生成式", "提示词"],
    },
    "location": {
        "label": "LBS 定位",
        "keywords": ["定位", "附近", "地图", "lbs", "地理"],
    },
    "tenant": {
        "label": "多租户 / 企业版",
        "keywords": ["多租户", "租户", "saas", "企业版", "组织架构", "多门店"],
    },
    "data": {
        "label": "数据分析",
        "keywords": ["数据", "报表", "指标", "分析", "bi", "看板", "埋点"],
    },
    "offline": {
        "label": "离线 / 弱网",
        "keywords": ["离线", "弱网", "断网", "同步"],
    },
    "security": {
        "label": "安全合规",
        "keywords": ["安全", "隐私", "合规", "加密", "等保", "审计"],
    },
    "miniprogram": {
        "label": "小程序",
        "keywords": ["小程序", "小程序平台", "开放平台"],
    },
}

# 能力特征 -> 需要补充的模块 id（模块定义见 config/modules.py）
FEATURE_MODULES = {
    "realtime": ["messaging"],
    "voice": ["media_call"],
    "video": ["video_pipeline"],
    "live": ["live_room"],
    "payment": ["payment"],
    "recommendation": ["feed"],
    "search": ["search"],
    "moderation": ["moderation"],
    "notification": ["notification"],
    "ai": ["ai_assistant"],
    "location": ["location"],
    "tenant": ["tenant"],
    "data": ["report_bi"],
    "offline": ["offline_sync"],
    "security": ["compliance"],
    "miniprogram": ["mini_program"],
}

# 需求域：识别产品类型，给出默认模块、默认规模与默认能力特征。
DOMAINS = {
    "social": {
        "label": "社交 / 即时通讯",
        "description": "以关系链和消息通信为核心的产品",
        "keywords": [
            "微信", "wechat", "即时通讯", "聊天", "社交", "好友", "群聊", "朋友圈",
            "消息", "im", "qq", "陌生人", "语音通话", "视频通话", "通讯",
        ],
        "strong_keywords": {"微信": ["payment", "miniprogram"], "wechat": ["payment", "miniprogram"]},
        "default_scale": "L",
        "default_features": ["realtime", "voice", "video", "notification", "security"],
        "modules": [
            "messaging", "contacts", "group_chat", "moments",
            "media_call", "notification", "ops_console",
        ],
    },
    "content": {
        "label": "内容社区 / 短视频",
        "description": "以内容生产、推荐分发与互动为核心的产品",
        "keywords": [
            "小红书", "社区", "内容", "图文", "笔记", "种草", "短视频", "抖音",
            "快手", "微博", "知乎", "instagram", "b站", "视频号", "创作者",
        ],
        "strong_keywords": {"小红书": ["payment"], "抖音": ["live", "payment"], "快手": ["live", "payment"]},
        "default_scale": "M",
        "default_features": ["recommendation", "search", "video", "moderation", "notification"],
        "modules": [
            "content_publish", "feed", "search", "interaction",
            "ecommerce", "moderation", "creator_center", "video_pipeline",
            "notification", "ops_console",
        ],
    },
    "ecommerce": {
        "label": "电商 / 交易平台",
        "description": "以商品、订单、支付与履约为核心的产品",
        "keywords": [
            "电商", "商城", "购物", "商品", "订单", "交易", "淘宝", "京东",
            "拼多多", "秒杀", "购物车", "sku", "库存", "物流", "零售", "生鲜",
        ],
        "strong_keywords": {"淘宝": ["payment"], "京东": ["payment"], "拼多多": ["payment"]},
        "default_scale": "L",
        "default_features": ["payment", "search", "notification", "security", "data"],
        "modules": [
            "catalog", "cart_order", "payment", "inventory", "logistics",
            "marketing", "search", "moderation", "notification", "ops_console",
        ],
    },
    "saas": {
        "label": "SaaS / 企业系统",
        "description": "面向企业或组织的管理系统、协作工具",
        "keywords": [
            "管理系统", "后台", "平台", "saas", "crm", "erp", "工单", "审批",
            "权限", "多租户", "企业", "协作", "内部系统", "oa", "bi",
        ],
        "strong_keywords": {"crm": ["tenant"], "erp": ["tenant", "data"], "saas": ["tenant"]},
        "default_scale": "M",
        "default_features": ["tenant", "data", "notification", "security"],
        "modules": [
            "tenant", "workflow", "report_bi", "notification",
            "ops_console", "compliance",
        ],
    },
    "ai": {
        "label": "AI 应用",
        "description": "以大模型、智能问答或 Agent 编排为核心的产品",
        "keywords": [
            "ai", "大模型", "智能", "agent", "生成", "问答", "知识库",
            "llm", "提示词", "copilot", "智能体",
        ],
        "strong_keywords": {"大模型": ["ai"], "agent": ["ai"]},
        "default_scale": "M",
        "default_features": ["ai", "notification", "security", "data"],
        "modules": [
            "ai_assistant", "ai_console", "moderation",
            "notification", "ops_console", "compliance",
        ],
    },
    "live": {
        "label": "直播 / 音视频",
        "description": "以直播、连麦与实时互动为核心的产品",
        "keywords": ["直播", "连麦", "弹幕", "主播", "打赏", "音视频", "在线课堂"],
        "strong_keywords": {"直播": ["payment"]},
        "default_scale": "L",
        "default_features": ["live", "video", "realtime", "moderation", "payment", "notification"],
        "modules": [
            "live_room", "video_pipeline", "messaging", "payment",
            "moderation", "notification", "ops_console",
        ],
    },
    "education": {
        "label": "教育 / 培训",
        "description": "课程、学习与教学服务类产品",
        "keywords": ["教育", "课程", "学习", "题库", "培训", "考试", "教学", "学员"],
        "strong_keywords": {"课程": ["payment"]},
        "default_scale": "M",
        "default_features": ["video", "live", "payment", "notification", "search"],
        "modules": [
            "content_publish", "live_room", "interaction",
            "payment", "notification", "ops_console",
        ],
    },
    "generic": {
        "label": "通用产品",
        "description": "未命中特定领域时的通用产品形态",
        "keywords": [],
        "strong_keywords": {},
        "default_scale": "M",
        "default_features": ["notification"],
        "modules": ["notification", "ops_console"],
    },
}

# 抽象短句里没有领域词时，用于判断“移动端 / Web 端”的默认组合。
DOMAIN_PLATFORMS = {
    "social": ["iOS / Android", "Web"],
    "content": ["iOS / Android", "Web"],
    "ecommerce": ["iOS / Android", "Web"],
    "live": ["iOS / Android", "Web"],
    "education": ["iOS / Android", "Web"],
    "ai": ["Web"],
    "saas": ["Web"],
    "generic": ["Web"],
}
