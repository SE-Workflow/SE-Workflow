"""大模型 Key 与连接参数（唯一配置入口）。

优先级：环境变量 > config/llm_key_local.py（本地私有，不入库）> 默认值。

本地文件方式（首次接入推荐）：
    复制 config/llm_key_local.example.py 为 config/llm_key_local.py，
    填入 BASE_URL / API_KEY / MODEL 即可。

环境变量方式（部署常用）：
    SE_WORKFLOW_LLM=openai
    SE_LLM_BASE_URL=https://api.openai.com/v1
    SE_LLM_API_KEY=sk-...
    SE_LLM_MODEL=gpt-4o-mini

engine/llm.py 只读取这里的配置，不再直接访问环境变量。
"""

from __future__ import annotations

import os

try:  # 本地私有配置，可选；文件不存在时静默跳过
    from . import llm_key_local as _local
except ImportError:
    _local = None

_ENABLED_MODES = {"openai", "llm", "on"}


def _pick(env_name: str, local_name: str, default: str) -> str:
    value = os.getenv(env_name, "").strip()
    if value:
        return value
    local_value = getattr(_local, local_name, None) if _local is not None else None
    if local_value is not None and str(local_value).strip():
        return str(local_value).strip()
    return default


LLM_MODE = _pick("SE_WORKFLOW_LLM", "MODE", "off").lower()
LLM_BASE_URL = _pick("SE_LLM_BASE_URL", "BASE_URL", "")
LLM_API_KEY = _pick("SE_LLM_API_KEY", "API_KEY", "")
LLM_MODEL = _pick("SE_LLM_MODEL", "MODEL", "gpt-4o-mini")
LLM_TIMEOUT = float(_pick("SE_LLM_TIMEOUT", "TIMEOUT", "20"))
LLM_ENABLED = LLM_MODE in _ENABLED_MODES


def get_llm_settings() -> dict:
    """返回当前生效的连接参数；configured 为 True 时才会真正调用模型。"""
    return {
        "mode": LLM_MODE,
        "enabled": LLM_ENABLED,
        "configured": LLM_ENABLED and bool(LLM_BASE_URL and LLM_API_KEY),
        "base_url": LLM_BASE_URL,
        "api_key": LLM_API_KEY,
        "model": LLM_MODEL,
        "timeout": LLM_TIMEOUT,
    }
