"""配置层：把 `.env` / 环境变量收敛成一个不可变的 Settings 对象。

密钥安全约定：
- API Key 只从 `.env` 或进程环境变量读取，代码与仓库里不出现真实 Key；
- `Settings.public()` 只输出掩码后的 Key，供网页展示；
- 任何日志都不得打印完整 Key。

没有安装 python-dotenv 时，会退化为一个只支持 `KEY=VALUE` 的极简解析器，
保证项目在离线 / 精简环境里仍可启动（requirements.txt 仍推荐安装 python-dotenv）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

try:  # 首选 python-dotenv；缺失时使用内置解析器
    from dotenv import load_dotenv as _dotenv_load
except ImportError:  # pragma: no cover - 依赖缺失时的兜底分支
    _dotenv_load = None

_LOADED = False


def _parse_env_file(path: Path) -> dict[str, str]:
    """极简 .env 解析：KEY=VALUE、# 注释、可选引号。"""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env(*, override: bool = False) -> None:
    """加载项目根目录的 `.env`；默认不覆盖已存在的进程环境变量。"""
    global _LOADED
    if _LOADED and not override:
        return
    if ENV_FILE.exists():
        if _dotenv_load is not None:
            _dotenv_load(ENV_FILE, override=override)
        else:
            for key, value in _parse_env_file(ENV_FILE).items():
                if override or key not in os.environ:
                    os.environ[key] = value
    _LOADED = True


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(_env(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(float(_env(name, str(default))))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def mask_secret(secret: str) -> str:
    """把 Key 掩码成 `sk-1****abcd`，任何情况下都不回显完整值。"""
    secret = (secret or "").strip()
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * max(4, len(secret) - 8)}{secret[-4:]}"


@dataclass(frozen=True)
class Settings:
    """一次运行所需的 LLM 与 Web 配置快照。"""

    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    temperature: float = 0.2
    timeout: float = 90.0
    max_retries: int = 2
    allow_mock: bool = True
    force_mock: bool = False
    json_mode: bool = True
    host: str = "127.0.0.1"
    port: int = 5000

    # ------------------------------------------------------------------ 状态
    @property
    def configured(self) -> bool:
        """是否具备调用真实 LLM 的最小配置。"""
        return bool(self.api_key and self.base_url and self.model)

    @property
    def mock_active(self) -> bool:
        """当前是否必然走 Mock：强制 Mock 或缺少 Key。"""
        return self.force_mock or not self.configured

    @property
    def mode(self) -> str:
        return "mock" if self.mock_active else "llm"

    @property
    def mode_label(self) -> str:
        if self.mock_active:
            return "Mock 演示模式" if self.force_mock else "Mock 模式（未配置 Key）"
        return "LLM 真实调用"

    def public(self) -> dict:
        """可安全送到前端的配置状态：不包含完整 Key。"""
        return {
            "configured": self.configured,
            "mode": self.mode,
            "mode_label": self.mode_label,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_masked": mask_secret(self.api_key),
            "temperature": self.temperature,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "allow_mock": self.allow_mock,
            "force_mock": self.force_mock,
            "env_file": ENV_FILE.name,
            "env_exists": ENV_FILE.exists(),
        }


def load_settings() -> Settings:
    """每次调用都读取最新环境变量，修改 .env 后无需改代码。"""
    load_env()
    return Settings(
        api_key=_env("LLM_API_KEY"),
        base_url=_env("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/"),
        model=_env("LLM_MODEL", "deepseek-chat"),
        temperature=_env_float("LLM_TEMPERATURE", 0.2, minimum=0.0, maximum=1.5),
        timeout=_env_float("LLM_TIMEOUT", 90.0, minimum=10.0, maximum=600.0),
        max_retries=_env_int("LLM_MAX_RETRIES", 2, minimum=0, maximum=5),
        allow_mock=_env_bool("LLM_ALLOW_MOCK", True),
        force_mock=_env_bool("LLM_MOCK_MODE", False),
        json_mode=_env_bool("LLM_JSON_MODE", True),
        host=_env("HOST", "127.0.0.1") or "127.0.0.1",
        port=_env_int("PORT", 5000, minimum=1, maximum=65535),
    )
