"""JSON 解析工具：从大模型返回文本里提取 JSON，并做常见的容错修复。

大模型常见的“脏输出”：
- 外面包了一层 ```json ... ``` 代码围栏；
- 前面写了一句“好的，以下是结果：”；
- 对象前后有多余文字；
- 末尾多一个逗号；
- 使用了中文引号「“ ”」。

`extract_json` 会尽量提取出第一个完整 JSON 对象/数组并解析；
失败时抛出 `JSONParseError`，由上层决定是否发起纠错重试。
"""

from __future__ import annotations

import json
import re
from typing import Any


class JSONParseError(ValueError):
    """无法从文本中解析出 JSON。"""

    def __init__(self, message: str, *, snippet: str = "", detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.snippet = snippet
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - 仅用于日志/提示
        return self.message


_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _strip_fences(text: str) -> str:
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    # 只有开头有围栏、结尾缺失的情况
    return re.sub(r"^```(?:json|JSON)?\s*", "", text.strip()).strip()


def _find_balanced(text: str, opener: str, closer: str) -> str | None:
    """从第一个 opener 开始，找到字符串感知的配对 closer。"""
    start = text.find(opener)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _repair_text(candidate: str) -> str:
    """低风险修复：中文引号、尾逗号、BOM。"""
    repaired = candidate.replace("\ufeff", "").strip()
    repaired = repaired.replace("“", '"').replace("”", '"')
    repaired = _TRAILING_COMMA_RE.sub(r"\1", repaired)
    return repaired


def _try_loads(candidate: str) -> Any:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = _repair_text(candidate)
        if repaired != candidate:
            return json.loads(repaired)
        raise


def extract_json(text: str) -> Any:
    """从模型输出中提取并解析 JSON 对象或数组。"""
    if text is None:
        raise JSONParseError("模型返回为空")
    raw = str(text).strip()
    if not raw:
        raise JSONParseError("模型返回为空")

    candidates: list[str] = []
    stripped = _strip_fences(raw)
    candidates.append(stripped)
    spans: list[tuple[int, str]] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        balanced = _find_balanced(stripped, opener, closer)
        if balanced:
            spans.append((stripped.find(balanced), balanced))
    for _, span in sorted(spans, key=lambda item: item[0]):
        candidates.append(span)

    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            return _try_loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue

    snippet = stripped[:280].replace("\n", " ")
    detail = ""
    if last_error is not None:
        detail = f"{last_error.msg}（第 {last_error.lineno} 行第 {last_error.colno} 列）"
    raise JSONParseError(
        f"无法解析模型返回的 JSON：{detail or '未找到合法的 JSON 对象'}",
        snippet=snippet,
        detail=detail,
    )


def dumps_compact(value: Any) -> str:
    """紧凑 JSON，用于放进 Prompt。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
