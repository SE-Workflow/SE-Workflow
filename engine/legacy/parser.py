"""需求输入解析（输入层）。

把一段自然语言需求解析成结构化画像：
    产品域 / 项目规模 / 目标平台 / 能力特征 / 补充需求 / 置信度

全部基于可配置的关键词映射（config/domains.py），不依赖大模型，
因此任意输入都能得到稳定结果；后续接入 LLM 时只需替换本层或叠加结果。
"""

from __future__ import annotations

import re

from config import (
    AGENT_GUESS_RULES,
    CUSTOM_MODULE_LIMIT,
    DEFAULT_AGENT,
    DOMAIN_PLATFORMS,
    DOMAINS,
    FEATURES,
)

ACTION_VERBS = (
    "支持", "需要", "包含", "实现", "提供", "要求", "必须", "具备",
    "能够", "可以", "希望", "想要", "用于", "新增", "增加",
)

SCALE_LARGE_PATTERN = re.compile(
    r"亿级|千万级|百万级|高并发|海量|多端|跨端|全平台|国际化|平台化|生态|集团|双十一|大促"
)
SCALE_SMALL_PATTERN = re.compile(
    r"mvp|原型|轻量|小工具|简单|demo|最小可用|个人|练手|课程作业", re.IGNORECASE
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def keyword_hit(text: str, keyword: str) -> bool:
    """关键词匹配：英文按单词边界，中文按子串。"""
    keyword = keyword.lower()
    if not keyword:
        return False
    if keyword.isascii():
        pattern = r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return keyword in text


def guess_agent(text: str) -> str:
    lowered = text.lower()
    for keywords, agent in AGENT_GUESS_RULES:
        if any(keyword in lowered for keyword in keywords):
            return agent
    return DEFAULT_AGENT


class RequirementParser:
    """把需求文本解析成画像 dict。"""

    def __init__(self, domains: dict | None = None, features: dict | None = None) -> None:
        self.domains = domains or DOMAINS
        self.features = features or FEATURES

    # ------------------------------------------------------------------ 入口
    def parse(self, requirement: str) -> dict:
        raw = (requirement or "").strip()
        if not raw:
            raise ValueError("请先输入需求内容")
        if len(raw) > 20000:
            raw = raw[:20000]

        lowered = _normalize(raw).lower()
        domain_id, domain_hits = self._detect_domain(lowered)
        domain = self.domains[domain_id]
        scale = self._detect_scale(raw, lowered, domain)
        platforms = self._detect_platforms(lowered, domain_id)
        features = self._detect_features(lowered, domain)
        custom_modules = self._extract_custom(raw)
        summary = self._compose_summary(domain, scale, platforms, features, custom_modules)

        return {
            "raw": raw,
            "summary": summary,
            "domain": {
                "id": domain_id,
                "label": domain["label"],
                "description": domain["description"],
                "confidence": self._confidence(domain_hits),
            },
            "scale": scale,
            "platforms": platforms,
            "features": features,
            "custom_modules": custom_modules,
            "matched_keywords": domain_hits,
        }

    # ------------------------------------------------------------------ 领域
    def _detect_domain(self, lowered: str) -> tuple[str, list[str]]:
        best_id = "generic"
        best_score = 0.0
        best_hits: list[str] = []
        for domain_id, domain in self.domains.items():
            if domain_id == "generic":
                continue
            hits: list[str] = []
            score = 0.0
            for keyword in domain.get("keywords", []):
                if keyword_hit(lowered, keyword):
                    hits.append(keyword)
                    weight = 3.0 if keyword.lower() in domain.get("strong_keywords", {}) else 1.0
                    score += weight
            if score > best_score:
                best_id, best_score, best_hits = domain_id, score, hits
        return best_id, best_hits

    @staticmethod
    def _confidence(hits: list[str]) -> float:
        if not hits:
            return 0.3
        return round(min(0.95, 0.45 + 0.08 * len(hits)), 2)

    # ------------------------------------------------------------------ 规模
    def _detect_scale(self, raw: str, lowered: str, domain: dict) -> dict:
        base = domain.get("default_scale", "M")
        reasons: list[str] = [f"领域默认规模：{base}"]

        if SCALE_LARGE_PATTERN.search(raw):
            base = "L"
            reasons.append("文本出现「高并发 / 海量 / 多端 / 平台化」等大型项目信号")
        elif SCALE_SMALL_PATTERN.search(lowered):
            base = "S"
            reasons.append("文本出现「MVP / 轻量 / 简单 / 小工具」等小型项目信号")
        elif len(raw) > 600:
            base = "M" if base == "S" else base
            reasons.append("需求描述较长，按中型项目评估")
        elif len(raw) > 200 and base == "S":
            base = "M"
            reasons.append("需求描述较完整，上调为中型项目")

        return {
            "code": base,
            "label": {"S": "小型", "M": "中型", "L": "大型"}.get(base, "中型"),
            "reasons": reasons,
        }

    # ------------------------------------------------------------------ 平台
    def _detect_platforms(self, lowered: str, domain_id: str) -> list[str]:
        platforms: list[str] = []
        if "小程序" in lowered:
            platforms.append("微信小程序")
        if re.search(r"ios|android|\bapp\b|手机|移动端|客户端", lowered):
            platforms.append("iOS / Android")
        if re.search(r"\bweb\b|网页|网站|后台|管理系统|h5|pc 端|saas|浏览器", lowered):
            platforms.append("Web")
        if not platforms:
            platforms = list(DOMAIN_PLATFORMS.get(domain_id, ["Web"]))
        return platforms

    # ------------------------------------------------------------------ 特征
    def _detect_features(self, lowered: str, domain: dict) -> list[dict]:
        found: dict[str, dict] = {}
        for feature_id, meta in self.features.items():
            hits = [keyword for keyword in meta["keywords"] if keyword_hit(lowered, keyword)]
            if hits:
                found[feature_id] = {
                    "id": feature_id,
                    "label": meta["label"],
                    "source": "需求文本",
                    "keywords": hits,
                }

        for feature_id in domain.get("default_features", []):
            if feature_id in found or feature_id not in self.features:
                continue
            found[feature_id] = {
                "id": feature_id,
                "label": self.features[feature_id]["label"],
                "source": "领域默认",
                "keywords": [],
            }

        for keyword, extra_features in domain.get("strong_keywords", {}).items():
            if not keyword_hit(lowered, keyword):
                continue
            for feature_id in extra_features:
                if feature_id in found or feature_id not in self.features:
                    continue
                found[feature_id] = {
                    "id": feature_id,
                    "label": self.features[feature_id]["label"],
                    "source": f"关键词「{keyword}」",
                    "keywords": [keyword],
                }

        order = list(self.features.keys())
        return [found[key] for key in sorted(found, key=lambda item: order.index(item))]

    # ------------------------------------------------------------------ 补充需求
    def _extract_custom(self, raw: str) -> list[dict]:
        """从结构化需求的分行/分号短句中提取补充模块，保证专业输入不被“平均化”。"""
        modules: list[dict] = []
        seen_names: set[str] = set()

        for line in re.split(r"[\n。；;]+", raw):
            text = line.strip(" -•*#\t")
            text = re.sub(r"^\d+[.、)]\s*", "", text)
            if not (6 <= len(text) <= 90):
                continue
            if not any(verb in text for verb in ACTION_VERBS):
                continue

            body = text
            leading = re.match(r"^.{0,6}?(需要|要求|支持|包含|实现|提供|具备|能够|可以|希望|想要|必须)", text)
            if leading:
                body = text[leading.end():]
            body = body.strip(" ：:，,")
            parts = [
                part.strip(" ：:，,")
                for part in re.split(r"[、，,]", body)
                if 2 <= len(part.strip(" ：:，,")) <= 26
            ]
            if not parts:
                continue

            name = parts[0][:20]
            if name in seen_names:
                continue
            seen_names.add(name)
            capabilities = parts[:3]
            modules.append(
                {
                    "name": name,
                    "summary": text[:60],
                    "capabilities": capabilities,
                    "agent": guess_agent(" ".join(capabilities) + " " + text),
                }
            )
            if len(modules) >= CUSTOM_MODULE_LIMIT:
                break

        return modules

    # ------------------------------------------------------------------ 摘要
    @staticmethod
    def _compose_summary(
        domain: dict,
        scale: dict,
        platforms: list[str],
        features: list[dict],
        custom_modules: list[dict],
    ) -> str:
        parts = [f"面向{domain['label']}的{scale['label']}项目"]
        if features:
            labels = "、".join(feature["label"] for feature in features[:3])
            parts.append(f"重点能力覆盖 {labels}")
        if platforms:
            parts.append(f"目标平台：{' / '.join(platforms)}")
        if custom_modules:
            parts.append(f"包含 {len(custom_modules)} 项补充需求")
        return "，".join(parts) + "。"
