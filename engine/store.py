"""方案存储：内存 LRU + `data/plans/*.json` 持久化。

- 生成后的方案立即落盘，服务重启后结果链接仍可打开；
- 网页编辑保存后覆盖同一文件；
- 只用 UUID 风格的 plan_id 作为文件名，避免路径穿越。
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections import OrderedDict
from pathlib import Path

from config import ROOT

LOGGER = logging.getLogger(__name__)

PLAN_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,40}$")


class PlanStore:
    def __init__(self, directory: Path | None = None, *, memory_limit: int = 40, disk_limit: int = 80) -> None:
        self.directory = Path(directory or (ROOT / "data" / "plans"))
        self.memory_limit = memory_limit
        self.disk_limit = disk_limit
        self._memory: "OrderedDict[str, dict]" = OrderedDict()
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # 只读部署也能运行，只是不持久化
            LOGGER.warning("无法创建方案目录 %s：%s", self.directory, exc)

    # ------------------------------------------------------------------ 基础
    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]

    @staticmethod
    def valid_id(plan_id: str) -> bool:
        return bool(PLAN_ID_RE.fullmatch(plan_id or ""))

    def _path(self, plan_id: str) -> Path:
        return self.directory / f"{plan_id}.json"

    def _remember(self, plan_id: str, plan: dict) -> None:
        self._memory[plan_id] = plan
        self._memory.move_to_end(plan_id)
        while len(self._memory) > self.memory_limit:
            self._memory.popitem(last=False)

    # ------------------------------------------------------------------ 读写
    def save(self, plan_id: str, plan: dict) -> None:
        if not self.valid_id(plan_id):
            raise ValueError("非法的 plan_id")
        plan.setdefault("meta", {})["plan_id"] = plan_id
        self._remember(plan_id, plan)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temp_path = self._path(plan_id).with_suffix(".json.tmp")
            payload = json.dumps(plan, ensure_ascii=False, indent=2)
            temp_path.write_text(payload, encoding="utf-8")
            os.replace(temp_path, self._path(plan_id))
            self._prune()
        except OSError as exc:
            LOGGER.warning("方案 %s 落盘失败（仅保留内存）：%s", plan_id, exc)

    def get(self, plan_id: str) -> dict | None:
        if not self.valid_id(plan_id):
            return None
        if plan_id in self._memory:
            self._memory.move_to_end(plan_id)
            return self._memory[plan_id]
        path = self._path(plan_id)
        if not path.exists():
            return None
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("读取方案 %s 失败：%s", plan_id, exc)
            return None
        if not isinstance(plan, dict) or not plan.get("nodes"):
            return None
        self._remember(plan_id, plan)
        return plan

    def _prune(self) -> None:
        try:
            files = sorted(
                self.directory.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for path in files[self.disk_limit :]:
            try:
                path.unlink()
            except OSError:
                pass
