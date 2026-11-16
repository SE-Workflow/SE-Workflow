"""配置包：所有可调参数集中在这里，引擎只读取、不硬编码业务规则。

分层：
- settings.py  从 .env 读取 LLM / Web 配置（API Key 只在这里出现）
- prompts.py   两阶段 LLM Prompt 模板
- agents.py    Agent 类型、职责、颜色与名称归一化
- rules.py     规模、优先级、阶段名称、示例需求等界面与编排元数据
- domains.py / modules.py  规则引擎（Mock 模式）使用的领域与任务模板
"""

from .agents import (
    AGENT_ALIASES,
    AGENT_GUESS_RULES,
    AGENT_IDS,
    AGENTS,
    DEFAULT_AGENT,
    agent_catalog_text,
    resolve_agent,
)
from .domains import DOMAIN_PLATFORMS, DOMAINS, FEATURE_MODULES, FEATURES
from .modules import MODULES
from .prompts import (
    PROMPT_VERSION,
    build_decompose_messages,
    build_orchestrate_messages,
    build_repair_message,
)
from .rules import (
    AGENT_SHARE_WARN,
    CAPABILITY_ACCEPTANCE,
    CAPABILITY_DESCRIPTIONS,
    CAPABILITY_EFFORT,
    CRITICAL_COLOR,
    CRITICAL_DAYS_WARN,
    CUSTOM_MODULE_LIMIT,
    CUSTOM_MODULE_TAG,
    EDGE_KIND_META,
    EXAMPLES,
    MAX_EFFORT,
    MAX_TASKS,
    MIN_EFFORT,
    MIN_TASKS,
    MODULE_COLORS,
    PARALLEL_MODULE_WARN,
    PHASE_LABELS,
    PRIORITY_META,
    SCALE_META,
    SEVERITY_ORDER,
    WAVE_TARGET,
)
from .settings import ENV_FILE, ROOT, Settings, load_env, load_settings, mask_secret

__all__ = [
    # settings
    "ENV_FILE",
    "ROOT",
    "Settings",
    "load_env",
    "load_settings",
    "mask_secret",
    # agents
    "AGENT_ALIASES",
    "AGENT_GUESS_RULES",
    "AGENT_IDS",
    "AGENTS",
    "DEFAULT_AGENT",
    "agent_catalog_text",
    "resolve_agent",
    # prompt
    "PROMPT_VERSION",
    "build_decompose_messages",
    "build_orchestrate_messages",
    "build_repair_message",
    # legacy rule engine
    "DOMAIN_PLATFORMS",
    "DOMAINS",
    "FEATURE_MODULES",
    "FEATURES",
    "MODULES",
    "AGENT_SHARE_WARN",
    "CAPABILITY_ACCEPTANCE",
    "CAPABILITY_DESCRIPTIONS",
    "CAPABILITY_EFFORT",
    "CRITICAL_DAYS_WARN",
    "CUSTOM_MODULE_LIMIT",
    "CUSTOM_MODULE_TAG",
    "EXAMPLES",
    "MODULE_COLORS",
    "PARALLEL_MODULE_WARN",
    "PRIORITY_META",
    "SCALE_META",
    "SEVERITY_ORDER",
    "WAVE_TARGET",
    # v5
    "CRITICAL_COLOR",
    "EDGE_KIND_META",
    "MAX_EFFORT",
    "MAX_TASKS",
    "MIN_EFFORT",
    "MIN_TASKS",
    "PHASE_LABELS",
]
