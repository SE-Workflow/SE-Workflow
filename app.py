"""SE Workflow Studio 入口。

启动：
    python app.py
浏览器访问：
    http://127.0.0.1:5000

路由：
    GET  /                 输入页（需求输入 + 示例）
    POST /analyze          提交需求 → 分解 + 编排 → 跳转结果页
    GET  /result/<plan_id> 结果页（任务树 + Agent 编排 DAG）
    POST /api/analyze      JSON API，返回完整方案
    GET  /api/health       健康检查
"""

from __future__ import annotations

import os
import uuid
from collections import OrderedDict

from flask import Flask, jsonify, redirect, render_template, request, url_for

from config import EXAMPLES
from engine import analyze

app = Flask(__name__)
app.json.ensure_ascii = False

# 内存中保留最近生成的方案，保证结果页刷新/分享链接可用（重启即清空）。
_PLANS: "OrderedDict[str, dict]" = OrderedDict()
_PLAN_LIMIT = 24


def _remember(plan: dict) -> str:
    plan_id = uuid.uuid4().hex[:12]
    _PLANS[plan_id] = plan
    while len(_PLANS) > _PLAN_LIMIT:
        _PLANS.popitem(last=False)
    return plan_id


def _index_page(error: str | None = None, requirement: str = "", status: int = 200):
    return (
        render_template(
            "index.html",
            examples=EXAMPLES,
            error=error,
            requirement=requirement,
        ),
        status,
    )


@app.get("/")
def index():
    return _index_page()


@app.post("/analyze")
def analyze_route():
    requirement = (request.form.get("requirement") or "").strip()
    if not requirement:
        return _index_page("请先输入需求内容，或点击示例快速填充。", "", 400)
    try:
        plan = analyze(requirement)
    except Exception as exc:  # noqa: BLE001 - 展示可读错误，同时记录日志
        app.logger.exception("分析失败")
        return _index_page(f"生成失败：{exc}", requirement, 500)
    return redirect(url_for("result", plan_id=_remember(plan)))


@app.get("/result/<plan_id>")
def result(plan_id: str):
    plan = _PLANS.get(plan_id)
    if plan is None:
        return (
            render_template(
                "message.html",
                title="方案已过期",
                message="服务重启或链接过期后方案不再保留，请重新输入需求生成。",
            ),
            404,
        )
    return render_template("result.html", plan=plan)


@app.post("/api/analyze")
def api_analyze():
    payload = request.get_json(silent=True) or {}
    requirement = (payload.get("requirement") or "").strip()
    if not requirement:
        return jsonify({"error": "requirement 不能为空"}), 400
    try:
        plan = analyze(requirement)
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("API 分析失败")
        return jsonify({"error": str(exc)}), 500
    return jsonify(plan)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "plans_in_memory": len(_PLANS)})


@app.errorhandler(404)
def not_found(_error):
    return (
        render_template("message.html", title="页面不存在", message="请回到首页重新开始。"),
        404,
    )


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    print("=" * 56)
    print("  SE Workflow Studio")
    print(f"  打开浏览器访问 http://{host}:{port}")
    print("  Ctrl+C 停止服务")
    print("=" * 56)
    app.run(host=host, port=port, debug=False)
