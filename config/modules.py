"""任务模块模板库（PM Agent 的“知识”来源）。

每个模块描述一类可以独立交付的工作：
    name / summary / phase   名称、说明、所处阶段（0 需求 → 5 上线）
    agent / priority         默认执行 Agent、模块优先级
    depends                  依赖的模块 id；"*business" 表示依赖全部业务模块
    scales                   适用的项目规模（S / M / L）
    mode                     sequential（子任务串行）或 parallel（子任务并行分支）
    subtasks                 显式的 模块 → 子任务 → 原子任务 三层结构
    capabilities             未写 subtasks 时，按能力点自动展开为子任务与原子任务

只改本文件即可调整分解粒度与任务内容；无需改动分解算法。
"""

MODULES = {
    # ------------------------------------------------------------------ 核心模块
    "requirements": {
        "name": "需求与规划",
        "summary": "把一句话需求变成可执行的范围、里程碑与验收基线",
        "phase": 0,
        "priority": "P0",
        "agent": "pm",
        "depends": [],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "需求澄清",
                "atoms": [
                    {
                        "name": "需求背景与目标拆解",
                        "desc": "访谈关键干系人，明确业务目标、成功指标与不做什么。",
                        "effort": 1.5,
                        "acceptance": "目标、范围与非目标书面确认，干系人无异议",
                    },
                    {
                        "name": "用户画像与核心场景",
                        "desc": "梳理目标用户、核心使用场景与关键任务路径。",
                        "effort": 2,
                        "acceptance": "输出 3 个以上核心场景故事板，覆盖主路径与异常分支",
                    },
                ],
            },
            {
                "name": "范围与里程碑",
                "atoms": [
                    {
                        "name": "MVP 范围与优先级",
                        "desc": "拆出 MVP、增强项与未来项，形成优先级清单。",
                        "effort": 1.5,
                        "acceptance": "范围清单与 P0/P1/P2 优先级经评审通过",
                    },
                    {
                        "name": "里程碑与验收标准",
                        "desc": "定义版本节奏、交付物与每阶段验收口径。",
                        "effort": 1.5,
                        "acceptance": "里程碑计划与验收标准可被 QA 直接引用",
                    },
                ],
            },
            {
                "name": "风险与基线",
                "atoms": [
                    {
                        "name": "关键假设与风险清单",
                        "desc": "登记技术、资源、合规风险及应对预案。",
                        "effort": 1,
                        "agent": "architect",
                        "acceptance": "风险有责任人、触发条件与应对动作",
                    },
                    {
                        "name": "需求评审与基线确认",
                        "desc": "组织需求评审会，锁定第一版需求基线。",
                        "effort": 1.5,
                        "acceptance": "评审纪要归档，需求基线进入变更管理",
                    },
                ],
            },
        ],
    },
    "ux": {
        "name": "产品与体验设计",
        "summary": "信息架构、核心流程、设计规范与高保真稿",
        "phase": 1,
        "priority": "P0",
        "agent": "ux",
        "depends": ["requirements"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "信息架构与流程",
                "atoms": [
                    {
                        "name": "页面地图与导航结构",
                        "desc": "定义端到端页面清单、层级与导航方式。",
                        "effort": 2,
                        "acceptance": "页面地图覆盖全部 P0 场景，无孤立页面",
                    },
                    {
                        "name": "核心流程与状态设计",
                        "desc": "绘制主流程、空态、加载态、错误态与权限态。",
                        "effort": 2.5,
                        "acceptance": "流程覆盖异常分支，状态机与后端对齐",
                    },
                ],
            },
            {
                "name": "视觉与组件规范",
                "atoms": [
                    {
                        "name": "设计语言与组件库",
                        "desc": "确定色彩、字体、栅格、图标与基础组件规范。",
                        "effort": 3,
                        "acceptance": "组件规范可直接被前端复用，标注完整",
                    },
                    {
                        "name": "关键页面高保真设计",
                        "desc": "输出核心页面高保真稿与交互说明。",
                        "effort": 4,
                        "acceptance": "设计稿通过评审，切图与标注交付前端",
                    },
                ],
            },
            {
                "name": "可用性验证",
                "atoms": [
                    {
                        "name": "设计走查与可用性验收",
                        "desc": "对实现结果做像素级走查与可用性复盘。",
                        "effort": 1.5,
                        "agent": "qa",
                        "acceptance": "走查问题全部修复或进入遗留清单",
                    },
                ],
            },
        ],
    },
    "architecture": {
        "name": "技术架构与基础设施",
        "summary": "总体架构、数据模型、接口契约与非功能设计",
        "phase": 1,
        "priority": "P0",
        "agent": "architect",
        "depends": ["requirements"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "架构方案",
                "atoms": [
                    {
                        "name": "总体架构与技术选型",
                        "desc": "确定系统边界、服务拆分、技术栈与关键第三方依赖。",
                        "effort": 2.5,
                        "acceptance": "架构评审通过，选型有对比与取舍说明",
                    },
                    {
                        "name": "数据模型与存储设计",
                        "desc": "设计核心实体、关系、索引与分库分表策略。",
                        "effort": 2,
                        "acceptance": "核心 ER 图与表结构评审通过，容量估算合理",
                    },
                    {
                        "name": "接口契约与版本策略",
                        "desc": "定义接口规范、鉴权方式、错误码与兼容策略。",
                        "effort": 2,
                        "acceptance": "OpenAPI 契约可生成 Mock，前后端据此并行开发",
                    },
                ],
            },
            {
                "name": "非功能设计",
                "atoms": [
                    {
                        "name": "性能容量与弹性方案",
                        "desc": "给出 QPS、存储、带宽预估与扩容策略。",
                        "effort": 2,
                        "agent": "devops",
                        "acceptance": "压测目标与扩容阈值明确，写入运维手册",
                    },
                    {
                        "name": "安全与合规基线",
                        "desc": "梳理数据分级、加密、审计与个人信息保护要求。",
                        "effort": 2,
                        "agent": "security",
                        "acceptance": "安全基线检查表通过，合规风险有结论",
                    },
                ],
            },
        ],
    },
    "backend_core": {
        "name": "核心服务与数据层",
        "summary": "服务框架、鉴权网关、数据底座与通用基础能力",
        "phase": 2,
        "priority": "P0",
        "agent": "backend",
        "depends": ["architecture"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "服务框架",
                "atoms": [
                    {
                        "name": "服务脚手架与工程规范",
                        "desc": "搭建服务模板、分层规范、异常与日志约定。",
                        "effort": 3,
                        "acceptance": "新服务可在 1 天内完成初始化并跑通 CI",
                    },
                    {
                        "name": "统一鉴权与网关接入",
                        "desc": "接入网关、令牌校验、限流与灰度路由。",
                        "effort": 3,
                        "agent": "security",
                        "acceptance": "鉴权链路压测通过，未授权请求全部拦截",
                    },
                ],
            },
            {
                "name": "数据底座",
                "atoms": [
                    {
                        "name": "核心表结构与迁移",
                        "desc": "落地核心数据表、索引与版本化迁移脚本。",
                        "effort": 3,
                        "acceptance": "迁移可重复执行，回滚脚本验证通过",
                    },
                    {
                        "name": "缓存与异步任务",
                        "desc": "搭建缓存、消息队列与定时任务基础设施。",
                        "effort": 2.5,
                        "acceptance": "缓存击穿/雪崩防护与任务重试验证通过",
                    },
                ],
            },
            {
                "name": "通用能力",
                "atoms": [
                    {
                        "name": "文件存储与媒体上传",
                        "desc": "实现对象存储接入、分片上传与访问鉴权。",
                        "effort": 2,
                        "acceptance": "大文件上传/断点续传通过测试",
                    },
                    {
                        "name": "日志、配置与告警接入",
                        "desc": "统一日志采集、动态配置与基础告警。",
                        "effort": 2,
                        "agent": "devops",
                        "acceptance": "关键接口有日志与指标，告警可触达值班人",
                    },
                ],
            },
        ],
    },
    "frontend": {
        "name": "Web 客户端",
        "summary": "Web 端工程、组件、页面与前端质量",
        "phase": 2,
        "priority": "P0",
        "agent": "frontend",
        "depends": ["architecture", "ux"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "工程与组件",
                "atoms": [
                    {
                        "name": "前端工程与路由",
                        "desc": "搭建构建、路由、权限与多环境配置。",
                        "effort": 2.5,
                        "acceptance": "构建产物可部署，路由与权限校验生效",
                    },
                    {
                        "name": "组件库与主题适配",
                        "desc": "实现设计规范对应的基础组件与主题变量。",
                        "effort": 3,
                        "acceptance": "组件与设计稿一致，通过可访问性检查",
                    },
                ],
            },
            {
                "name": "页面开发",
                "atoms": [
                    {
                        "name": "核心页面与表单实现",
                        "desc": "实现核心业务页面、表单校验与异常提示。",
                        "effort": 4,
                        "acceptance": "页面主流程与异常态均可演示",
                    },
                    {
                        "name": "状态管理与接口联调",
                        "desc": "接入接口、处理加载/失败/重试与数据缓存。",
                        "effort": 3,
                        "acceptance": "接口联调完成，弱网与错误提示友好",
                    },
                ],
            },
            {
                "name": "前端质量",
                "atoms": [
                    {
                        "name": "性能与兼容性优化",
                        "desc": "首屏优化、资源压缩与主流浏览器兼容。",
                        "effort": 2,
                        "acceptance": "首屏耗时达标，兼容性清单全部通过",
                    },
                    {
                        "name": "埋点与错误上报",
                        "desc": "接入用户行为埋点与前端异常监控。",
                        "effort": 1.5,
                        "agent": "data",
                        "acceptance": "埋点数据可在看板查询，异常可定位",
                    },
                ],
            },
        ],
    },
    "mobile": {
        "name": "移动客户端",
        "summary": "iOS / Android 工程、核心交互与发布准备",
        "phase": 2,
        "priority": "P0",
        "agent": "mobile",
        "depends": ["architecture", "ux"],
        "scales": ["M", "L"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "工程基础",
                "atoms": [
                    {
                        "name": "客户端工程与 CI",
                        "desc": "搭建跨端工程、签名、构建与分发流水线。",
                        "effort": 3,
                        "acceptance": "可一键打包并分发内测包",
                    },
                    {
                        "name": "网络层与本地缓存",
                        "desc": "实现请求封装、重试、缓存与登录态管理。",
                        "effort": 3,
                        "acceptance": "弱网与登录失效场景通过测试",
                    },
                ],
            },
            {
                "name": "核心功能",
                "atoms": [
                    {
                        "name": "核心页面与交互实现",
                        "desc": "按设计稿实现核心页面、转场与手势交互。",
                        "effort": 5,
                        "acceptance": "核心路径在真机可完整走通",
                    },
                    {
                        "name": "推送、权限与系统能力",
                        "desc": "接入推送、相册、定位等系统权限与能力。",
                        "effort": 2.5,
                        "acceptance": "权限申请流程合规，拒绝后有降级方案",
                    },
                ],
            },
            {
                "name": "发布准备",
                "atoms": [
                    {
                        "name": "性能与弱网优化",
                        "desc": "启动速度、包体积、内存与弱网体验优化。",
                        "effort": 2.5,
                        "acceptance": "启动与包体积达到既定目标",
                    },
                    {
                        "name": "应用商店合规与发布",
                        "desc": "准备隐私清单、素材与提审流程。",
                        "effort": 1.5,
                        "agent": "devops",
                        "acceptance": "提审材料齐全，审核问题有响应预案",
                    },
                ],
            },
        ],
    },
    "account": {
        "name": "账号与安全",
        "summary": "注册登录、权限、风控与隐私合规",
        "phase": 2,
        "priority": "P0",
        "agent": "backend",
        "depends": ["architecture"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "账号体系",
                "atoms": [
                    {
                        "name": "注册登录与多端会话",
                        "desc": "实现账号注册、登录、令牌刷新与多端会话管理。",
                        "effort": 4,
                        "acceptance": "登录态安全可靠，多端互踢策略符合预期",
                    },
                    {
                        "name": "第三方登录与账号绑定",
                        "desc": "接入手机号、微信等登录方式与账号绑定。",
                        "effort": 2.5,
                        "acceptance": "绑定/解绑流程完整，异常有兜底",
                    },
                ],
            },
            {
                "name": "权限与风控",
                "atoms": [
                    {
                        "name": "角色权限与访问控制",
                        "desc": "实现 RBAC 权限模型与接口级鉴权。",
                        "effort": 3,
                        "agent": "security",
                        "acceptance": "越权测试全部拦截，权限变更实时生效",
                    },
                    {
                        "name": "异常登录与风控",
                        "desc": "实现设备指纹、频率限制与风险二次验证。",
                        "effort": 2.5,
                        "agent": "security",
                        "acceptance": "撞库/盗号场景可识别并拦截",
                    },
                ],
            },
            {
                "name": "资料与合规",
                "atoms": [
                    {
                        "name": "个人资料与隐私设置",
                        "desc": "资料编辑、可见范围与隐私开关。",
                        "effort": 2,
                        "acceptance": "隐私设置对全链路生效",
                    },
                    {
                        "name": "账号注销与数据合规",
                        "desc": "实现注销、数据导出与留存策略。",
                        "effort": 2,
                        "agent": "security",
                        "acceptance": "注销流程可审计，符合个人信息保护要求",
                    },
                ],
            },
        ],
    },
    "integration": {
        "name": "系统集成联调",
        "summary": "端到端联调、第三方对接与上线检查",
        "phase": 4,
        "priority": "P0",
        "agent": "backend",
        "depends": ["*business", "frontend", "mobile"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "端到端联调",
                "atoms": [
                    {
                        "name": "端到端链路联调",
                        "desc": "打通客户端、服务端与数据层的完整链路。",
                        "effort": 4,
                        "acceptance": "核心业务链路全部可演示，无阻塞缺陷",
                    },
                    {
                        "name": "第三方与开放接口对接",
                        "desc": "完成支付、推送、存储等外部依赖联调。",
                        "effort": 2.5,
                        "acceptance": "第三方回调与异常场景验证通过",
                    },
                ],
            },
            {
                "name": "集成验收",
                "atoms": [
                    {
                        "name": "集成问题修复与回归",
                        "desc": "收敛联调缺陷并做回归验证。",
                        "effort": 3,
                        "acceptance": "P0/P1 集成缺陷清零",
                    },
                    {
                        "name": "上线检查清单",
                        "desc": "逐项核对配置、数据、权限与回滚预案。",
                        "effort": 1.5,
                        "acceptance": "检查清单 100% 确认后进入测试阶段",
                    },
                ],
            },
        ],
    },
    "qa": {
        "name": "测试与质量保障",
        "summary": "测试设计、自动化、专项测试与质量收口",
        "phase": 4,
        "priority": "P0",
        "agent": "qa",
        "depends": ["integration"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "测试设计",
                "atoms": [
                    {
                        "name": "测试方案与用例设计",
                        "desc": "按需求基线设计功能、接口与异常场景用例。",
                        "effort": 2.5,
                        "acceptance": "用例覆盖全部 P0 需求，评审通过",
                    },
                    {
                        "name": "自动化测试框架搭建",
                        "desc": "搭建接口/UI 自动化与持续回归能力。",
                        "effort": 3,
                        "acceptance": "核心链路的自动化用例可稳定运行",
                    },
                ],
            },
            {
                "name": "专项测试",
                "atoms": [
                    {
                        "name": "性能与容量测试",
                        "desc": "按预估峰值做压测并定位瓶颈。",
                        "effort": 3,
                        "acceptance": "达到性能指标，瓶颈有优化结论",
                    },
                    {
                        "name": "安全与合规测试",
                        "desc": "越权、注入、敏感数据与合规检查。",
                        "effort": 2.5,
                        "agent": "security",
                        "acceptance": "高危问题全部修复，复查通过",
                    },
                ],
            },
            {
                "name": "质量收口",
                "atoms": [
                    {
                        "name": "回归测试与缺陷收敛",
                        "desc": "全量回归并跟踪缺陷修复。",
                        "effort": 3,
                        "acceptance": "P0/P1 缺陷清零，遗留问题有结论",
                    },
                    {
                        "name": "质量报告与发布评审",
                        "desc": "输出质量报告，参与上线评审。",
                        "effort": 1.5,
                        "acceptance": "质量结论明确，发布评审通过",
                    },
                ],
            },
        ],
    },
    "devops": {
        "name": "部署与运维",
        "summary": "环境、流水线、可观测性与灰度发布",
        "phase": 5,
        "priority": "P0",
        "agent": "devops",
        "depends": ["qa"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "环境与流水线",
                "atoms": [
                    {
                        "name": "环境与发布流水线",
                        "desc": "搭建开发/预发/生产环境与自动化发布流程。",
                        "effort": 3,
                        "acceptance": "一键发布到预发，生产发布需审批",
                    },
                    {
                        "name": "容器化与弹性伸缩",
                        "desc": "容器编排、资源配额与自动扩缩容。",
                        "effort": 3,
                        "acceptance": "扩容策略经压测验证",
                    },
                ],
            },
            {
                "name": "可观测性",
                "atoms": [
                    {
                        "name": "监控告警与日志平台",
                        "desc": "接入指标、日志、链路追踪与告警规则。",
                        "effort": 3,
                        "acceptance": "核心指标可观测，告警分级明确",
                    },
                    {
                        "name": "容灾与备份演练",
                        "desc": "制定容灾预案并完成一次演练。",
                        "effort": 2.5,
                        "acceptance": "演练达到 RTO/RPO 目标",
                    },
                ],
            },
            {
                "name": "发布上线",
                "atoms": [
                    {
                        "name": "灰度发布与回滚",
                        "desc": "建立灰度策略、回滚脚本与开关体系。",
                        "effort": 2.5,
                        "acceptance": "灰度与回滚演练通过",
                    },
                    {
                        "name": "上线值守与复盘",
                        "desc": "上线值守、问题响应与版本复盘。",
                        "effort": 2,
                        "acceptance": "上线无重大事故，复盘结论归档",
                    },
                ],
            },
        ],
    },
    "analytics": {
        "name": "数据与增长分析",
        "summary": "埋点、指标体系、看板与实验分析",
        "phase": 4,
        "priority": "P1",
        "agent": "data",
        "depends": ["integration"],
        "scales": ["M", "L"],
        "mode": "sequential",
        "subtasks": [
            {
                "name": "数据接入",
                "atoms": [
                    {
                        "name": "埋点方案与数据接入",
                        "desc": "定义事件模型、埋点规范与数据采集链路。",
                        "effort": 2.5,
                        "acceptance": "埋点可校验，数据无丢失",
                    },
                    {
                        "name": "指标体系与看板",
                        "desc": "搭建核心指标口径与运营看板。",
                        "effort": 3,
                        "acceptance": "指标口径统一，看板可支撑复盘",
                    },
                    {
                        "name": "实验与转化分析",
                        "desc": "设计 A/B 实验与漏斗转化分析。",
                        "effort": 2.5,
                        "acceptance": "实验流程可复用，结论可追踪",
                    },
                ],
            },
        ],
    },

    # ------------------------------------------------------------------ 业务模块
    "messaging": {
        "name": "即时通讯",
        "summary": "消息协议、长连接、可靠投递与多端同步",
        "phase": 3,
        "priority": "P0",
        "agent": "backend",
        "depends": ["backend_core", "account"],
        "business": True,
        "mode": "sequential",
        "subtasks": [
            {
                "name": "消息协议与通道",
                "atoms": [
                    {
                        "name": "消息模型与协议设计",
                        "desc": "定义消息结构、会话模型与协议版本演进策略。",
                        "effort": 3,
                        "agent": "architect",
                        "acceptance": "协议评审通过，兼容与扩展方案明确",
                    },
                    {
                        "name": "长连接网关与心跳保活",
                        "desc": "实现接入网关、心跳、重连与连接数治理。",
                        "effort": 5,
                        "acceptance": "百万级连接模拟下内存与重连表现稳定",
                    },
                ],
            },
            {
                "name": "可靠投递",
                "atoms": [
                    {
                        "name": "可靠投递与消息去重",
                        "desc": "实现 ACK、重试、顺序性与幂等去重。",
                        "effort": 4,
                        "acceptance": "弱网与断连场景不丢消息、不重复",
                    },
                    {
                        "name": "会话、已读与撤回",
                        "desc": "实现会话列表、已读回执与消息撤回。",
                        "effort": 3,
                        "acceptance": "多端状态一致，撤回有时效与审计",
                    },
                ],
            },
            {
                "name": "多端与富媒体",
                "atoms": [
                    {
                        "name": "离线消息与多端同步",
                        "desc": "实现离线补拉、多端已读同步与增量游标。",
                        "effort": 4,
                        "acceptance": "多端切换后消息状态一致",
                    },
                    {
                        "name": "图片、语音与视频消息",
                        "desc": "实现富媒体上传、压缩、转码与播放。",
                        "effort": 4,
                        "acceptance": "各类型消息发送成功率与清晰度达标",
                    },
                ],
            },
        ],
    },
    "contacts": {
        "name": "好友与通讯录",
        "summary": "关系链、通讯录同步与社交治理",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["account"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "好友关系链与添加申请",
            "通讯录导入与去重",
            "黑名单与举报治理",
        ],
    },
    "group_chat": {
        "name": "群聊",
        "summary": "群组、成员管理、群消息与治理",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["messaging"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "群组创建与成员管理",
            "群消息、@ 提醒与免打扰",
            "群权限与违规治理",
        ],
    },
    "moments": {
        "name": "朋友圈 / 动态",
        "summary": "动态发布、时间线、互动与可见性",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["contacts", "backend_core"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "动态发布与时间线",
            "点赞评论与可见性控制",
            "动态内容审核与举报",
        ],
    },
    "media_call": {
        "name": "音视频通话",
        "summary": "实时音视频通道、信令与弱网优化",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["messaging"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "实时音视频通道与房间",
            "通话信令与状态同步",
            "弱网优化与设备适配",
        ],
    },
    "mini_program": {
        "name": "小程序 / 开放平台",
        "summary": "小程序授权、包管理与开放能力",
        "phase": 3,
        "priority": "P2",
        "agent": "backend",
        "depends": ["account", "backend_core"],
        "business": True,
        "scales": ["M", "L"],
        "mode": "parallel",
        "capabilities": [
            "小程序授权与登录",
            "小程序包管理与发布",
            "开放接口与能力网关",
        ],
    },
    "notification": {
        "name": "消息推送",
        "summary": "推送通道、模板、偏好与频控",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["backend_core", "account"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "推送通道与厂商接入",
            "通知模板与用户偏好",
            "触达统计与频控策略",
        ],
    },
    "ops_console": {
        "name": "运营管理后台",
        "summary": "运营配置、内容管理、权限与数据看板",
        "phase": 3,
        "priority": "P1",
        "agent": "frontend",
        "depends": ["backend_core", "account"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "运营配置与内容管理",
            "用户、角色与权限管理",
            "数据看板与报表导出",
        ],
    },
    "compliance": {
        "name": "安全合规",
        "summary": "隐私合规、内容安全与审计",
        "phase": 3,
        "priority": "P1",
        "agent": "security",
        "depends": ["account", "backend_core"],
        "business": True,
        "scales": ["M", "L"],
        "mode": "parallel",
        "capabilities": [
            "隐私政策与数据合规",
            "内容安全与审核流程",
            "审计日志与权限复核",
        ],
    },
    "content_publish": {
        "name": "内容创作与发布",
        "summary": "图文/视频创作、发布流程与多端体验",
        "phase": 3,
        "priority": "P0",
        "agent": "backend",
        "depends": ["backend_core", "account"],
        "business": True,
        "mode": "sequential",
        "subtasks": [
            {
                "name": "创作工具",
                "atoms": [
                    {
                        "name": "图文编辑器与草稿",
                        "desc": "实现富文本编辑、图片排版与草稿自动保存。",
                        "effort": 4,
                        "acceptance": "编辑体验流畅，草稿不丢失",
                    },
                    {
                        "name": "视频上传与转码接入",
                        "desc": "实现分片上传、转码任务与进度反馈。",
                        "effort": 4,
                        "acceptance": "大视频上传成功率高，转码状态可追踪",
                    },
                ],
            },
            {
                "name": "发布流程",
                "atoms": [
                    {
                        "name": "发布流程与审核联动",
                        "desc": "实现发布、定时发布与审核状态流转。",
                        "effort": 3,
                        "acceptance": "发布状态机完整，审核驳回可修改重提",
                    },
                    {
                        "name": "话题、标签与位置",
                        "desc": "实现话题绑定、标签推荐与位置关联。",
                        "effort": 2,
                        "acceptance": "话题与标签可检索，位置展示正确",
                    },
                ],
            },
            {
                "name": "发布体验",
                "atoms": [
                    {
                        "name": "草稿同步与多端续写",
                        "desc": "实现草稿云端同步与多端续写。",
                        "effort": 2,
                        "acceptance": "多端草稿一致，冲突可恢复",
                    },
                    {
                        "name": "发布成功率与失败重试",
                        "desc": "补齐发布失败重试、补偿与用户提示。",
                        "effort": 2,
                        "acceptance": "弱网发布成功率达标，失败可一键重试",
                    },
                ],
            },
        ],
    },
    "feed": {
        "name": "推荐信息流",
        "summary": "召回排序、分页曝光与冷启动",
        "phase": 3,
        "priority": "P0",
        "agent": "data",
        "depends": ["content_publish"],
        "business": True,
        "mode": "sequential",
        "subtasks": [
            {
                "name": "推荐流",
                "atoms": [
                    {
                        "name": "召回与排序策略接入",
                        "desc": "接入多路召回与排序模型，支持策略配置。",
                        "effort": 4,
                        "acceptance": "推荐效果有基线对比，策略可灰度和回滚",
                    },
                    {
                        "name": "信息流分页与曝光去重",
                        "desc": "实现分页、刷新、曝光去重与状态保持。",
                        "effort": 3,
                        "acceptance": "刷新无重复内容，分页稳定",
                    },
                ],
            },
            {
                "name": "体验优化",
                "atoms": [
                    {
                        "name": "冷启动与兴趣探索",
                        "desc": "为新用户和新内容设计探索策略。",
                        "effort": 3,
                        "acceptance": "冷启动首屏点击率达标",
                    },
                    {
                        "name": "多样性与疲劳度控制",
                        "desc": "控制内容同质化与重复曝光疲劳。",
                        "effort": 2,
                        "acceptance": "多样性指标与用户负反馈率达标",
                    },
                ],
            },
        ],
    },
    "search": {
        "name": "搜索",
        "summary": "索引、检索排序与搜索运营",
        "phase": 3,
        "priority": "P1",
        "agent": "data",
        "depends": ["content_publish"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "索引构建与增量更新",
            "搜索排序与搜索联想",
            "搜索运营与干预",
        ],
    },
    "interaction": {
        "name": "互动体系",
        "summary": "点赞收藏、评论回复与互动通知",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["account", "content_publish"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "点赞收藏与计数",
            "评论与回复体系",
            "互动通知与消息聚合",
        ],
    },
    "ecommerce": {
        "name": "内容电商",
        "summary": "商品、订单、支付与售后",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["account", "content_publish"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "商品与 SKU 管理",
            "订单与履约",
            "支付与结算",
            "售后与退款",
        ],
    },
    "moderation": {
        "name": "内容审核",
        "summary": "机审人审、违规处置与申诉",
        "phase": 3,
        "priority": "P1",
        "agent": "security",
        "depends": ["content_publish"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "机审与人工审核流程",
            "违规处置与申诉",
            "内容风控策略与黑名单",
        ],
    },
    "creator_center": {
        "name": "创作者中心",
        "summary": "创作者数据、内容管理与成长体系",
        "phase": 3,
        "priority": "P2",
        "agent": "frontend",
        "depends": ["content_publish", "feed"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "创作者数据看板",
            "内容管理与收益结算",
            "成长体系与创作任务",
        ],
    },
    "video_pipeline": {
        "name": "视频处理与分发",
        "summary": "上传转码、审核抽帧与播放分发",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["content_publish"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "上传转码与多码率",
            "封面抽帧与机审对接",
            "播放器与 CDN 分发",
        ],
    },
    "live_room": {
        "name": "直播",
        "summary": "推拉流、直播间互动与直播治理",
        "phase": 3,
        "priority": "P0",
        "agent": "backend",
        "depends": ["video_pipeline", "messaging"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "推拉流与直播间",
            "弹幕、礼物与互动",
            "直播审核与连麦",
        ],
    },
    "catalog": {
        "name": "商品与类目",
        "summary": "商品模型、SKU、价格与商品检索",
        "phase": 3,
        "priority": "P0",
        "agent": "backend",
        "depends": ["backend_core"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "商品模型与类目体系",
            "SKU 与价格体系",
            "商品检索与筛选",
        ],
    },
    "cart_order": {
        "name": "购物车与订单",
        "summary": "购物车、下单、订单状态机与结算",
        "phase": 3,
        "priority": "P0",
        "agent": "backend",
        "depends": ["catalog", "account"],
        "business": True,
        "mode": "sequential",
        "subtasks": [
            {
                "name": "交易链路",
                "atoms": [
                    {
                        "name": "购物车与规格选择",
                        "desc": "实现购物车、规格选择与价格计算。",
                        "effort": 3,
                        "acceptance": "购物车价格与优惠计算准确",
                    },
                    {
                        "name": "下单与库存预占",
                        "desc": "实现下单、库存预占与超时释放。",
                        "effort": 4,
                        "acceptance": "并发下单不超卖，预占可释放",
                    },
                ],
            },
            {
                "name": "订单管理",
                "atoms": [
                    {
                        "name": "订单状态机与履约",
                        "desc": "实现订单状态流转、发货与签收。",
                        "effort": 4,
                        "acceptance": "状态流转完整，异常可人工干预",
                    },
                    {
                        "name": "取消、改址与售后入口",
                        "desc": "实现取消、修改地址与售后入口。",
                        "effort": 2.5,
                        "acceptance": "售后入口覆盖全生命周期订单",
                    },
                ],
            },
            {
                "name": "结算",
                "atoms": [
                    {
                        "name": "优惠与结算页",
                        "desc": "实现优惠计算、结算页与价格明细。",
                        "effort": 3,
                        "acceptance": "优惠叠加规则清晰，金额零误差",
                    },
                    {
                        "name": "订单对账与异常处理",
                        "desc": "实现订单对账、补偿与异常订单处理。",
                        "effort": 2,
                        "acceptance": "日对账差异可定位、可修复",
                    },
                ],
            },
        ],
    },
    "payment": {
        "name": "支付与结算",
        "summary": "支付渠道、回调幂等、对账退款与风控",
        "phase": 3,
        "priority": "P0",
        "agent": "backend",
        "depends": ["cart_order"],
        "business": True,
        "mode": "sequential",
        "subtasks": [
            {
                "name": "支付接入",
                "atoms": [
                    {
                        "name": "支付渠道与聚合收银台",
                        "desc": "接入主流支付渠道，统一收银台与下单参数。",
                        "effort": 4,
                        "acceptance": "支付成功率达标，渠道切换可配置",
                    },
                    {
                        "name": "支付回调与幂等",
                        "desc": "实现回调验签、幂等处理与补偿任务。",
                        "effort": 3,
                        "acceptance": "重复回调不产生重复扣款",
                    },
                ],
            },
            {
                "name": "资金与对账",
                "atoms": [
                    {
                        "name": "对账与结算",
                        "desc": "实现渠道对账、差异处理与结算单。",
                        "effort": 3,
                        "acceptance": "T+1 对账自动化，差异可追踪",
                    },
                    {
                        "name": "退款与争议处理",
                        "desc": "实现退款、部分退款与争议工单。",
                        "effort": 2.5,
                        "acceptance": "退款到账时效达标，争议流程闭环",
                    },
                ],
            },
            {
                "name": "支付风控",
                "atoms": [
                    {
                        "name": "支付风控与限额",
                        "desc": "实现交易限额、风险识别与拦截。",
                        "effort": 2.5,
                        "agent": "security",
                        "acceptance": "风险交易可拦截，误杀率可控",
                    },
                    {
                        "name": "支付合规与发票",
                        "desc": "落实资金合规、发票与审计要求。",
                        "effort": 2,
                        "agent": "security",
                        "acceptance": "合规检查通过，审计记录完整",
                    },
                ],
            },
        ],
    },
    "inventory": {
        "name": "库存",
        "summary": "库存模型、扣减、同步与盘点",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["catalog"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "库存模型与扣减",
            "库存同步与预警",
            "盘点与调拨",
        ],
    },
    "logistics": {
        "name": "履约与物流",
        "summary": "运费、发货、轨迹与逆向物流",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["cart_order"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "运费模板与发货",
            "物流轨迹接入",
            "逆向物流与售后",
        ],
    },
    "marketing": {
        "name": "营销与增长",
        "summary": "优惠券、秒杀与分销拉新",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["cart_order", "notification"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "优惠券与营销活动",
            "秒杀与防超卖",
            "分销与拉新",
        ],
    },
    "tenant": {
        "name": "多租户与权限",
        "summary": "租户隔离、组织架构与计费",
        "phase": 3,
        "priority": "P0",
        "agent": "backend",
        "depends": ["architecture", "account"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "多租户隔离与计费",
            "组织架构与角色",
            "租户配置与初始化",
        ],
    },
    "workflow": {
        "name": "流程与审批",
        "summary": "表单、流程引擎与审批通知",
        "phase": 3,
        "priority": "P1",
        "agent": "backend",
        "depends": ["tenant", "backend_core"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "表单与流程引擎",
            "审批与通知",
            "流程监控与统计",
        ],
    },
    "report_bi": {
        "name": "报表与 BI",
        "summary": "指标口径、报表看板与自助查询",
        "phase": 3,
        "priority": "P1",
        "agent": "data",
        "depends": ["backend_core"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "指标口径与数据仓库",
            "报表与看板",
            "自助查询与导出",
        ],
    },
    "ai_assistant": {
        "name": "AI 助手",
        "summary": "模型接入、RAG、对话编排与安全护栏",
        "phase": 3,
        "priority": "P0",
        "agent": "ai",
        "depends": ["backend_core", "account"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "模型接入与多模型路由",
            "RAG 知识库与检索",
            "对话编排与工具调用",
            "评测与安全护栏",
        ],
    },
    "ai_console": {
        "name": "AI 编排控制台",
        "summary": "Prompt 调试、Agent 编排与运行监控",
        "phase": 3,
        "priority": "P1",
        "agent": "ai",
        "depends": ["ai_assistant"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "Prompt 调试与版本管理",
            "Agent 编排与发布",
            "运行监控与成本分析",
        ],
    },
    "location": {
        "name": "LBS 定位",
        "summary": "地理编码、围栏与附近检索",
        "phase": 3,
        "priority": "P2",
        "agent": "backend",
        "depends": ["backend_core"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "地理编码与电子围栏",
            "附近检索与排序",
            "位置权限与隐私",
        ],
    },
    "offline_sync": {
        "name": "离线与同步",
        "summary": "本地数据、冲突解决与增量同步",
        "phase": 3,
        "priority": "P2",
        "agent": "mobile",
        "depends": ["backend_core"],
        "business": True,
        "mode": "parallel",
        "capabilities": [
            "本地数据模型与冲突解决",
            "增量同步与队列",
            "弱网与重试策略",
        ],
    },
}
