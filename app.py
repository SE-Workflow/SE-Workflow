"""SE Workflow Studio 入口（V5）。

启动：
    pip install -r requirements.txt
    copy .env.example .env   # 填入自己的 LLM_API_KEY
    python app.py

页面：
    GET  /                     输入页（需求 + 示例 + LLM 配置状态）
    POST /analyze              提交需求 → 生成工作流程图 → 跳转结果页
    GET  /result/<plan_id>     唯一结果页：一幅可编辑的工作流程图
    GET  /settings             LLM 配置状态 / 测试连接 / Prompt 预览

API：
    POST /api/analyze          生成方案（JSON）
    GET  /api/plan/<plan_id>   读取方案
    PUT  /api/plan/<plan_id>   保存网页编辑后的方案
    POST /api/llm/test         测试 LLM 连通性
    GET  /api/settings         配置状态（Key 已掩码）
    GET  /api/health           健康检查
"""

from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, redirect, render_template, request, url_for

from config import (
    AGENTS,
    EXAMPLES,
    MAX_TASKS,
    MIN_TASKS,
    PROMPT_VERSION,
    agent_catalog_text,
    build_decompose_messages,
    build_orchestrate_messages,
    load_settings,
)
from engine import (
    PipelineError,
    PlanStore,
    ValidationError,
    build_view,
    generate,
    validate_saved_plan,
)
from engine.llm_client import LLMClient, LLMError

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger(__name__)

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
app.config["JSON_SORT_KEYS"] = False

store = PlanStore()


# ----------------------------------------------------------------------
# 页面辅助
# ----------------------------------------------------------------------
def _base_context(**extra) -> dict:
    settings = load_settings()
    context = {
        "examples": EXAMPLES,
        "settings": settings.public(),
        "prompt_version": PROMPT_VERSION,
    }
    context.update(extra)
    return context


def _index_page(*, error: str = "", requirement: str = "", status: int = 200):
    return (
        render_template(
            "index.html",
            **_base_context(error=error, requirement=requirement),
        ),
        status,
    )


def _remember(plan: dict, plan_id: str | None = None) -> str:
    plan_id = plan_id or store.new_id()
    store.save(plan_id, plan)
    return plan_id


def _error_response(exc: Exception, *, want_json: bool, status: int = 500):
    if isinstance(exc, (PipelineError, ValidationError)):
        message = exc.message
        hint = getattr(exc, "hint", "")
        detail = getattr(exc, "detail", "")
        status = getattr(exc, "status", status)
    elif isinstance(exc, LLMError):
        message = exc.message
        hint = exc.hint
        detail = exc.detail
        status = 502
    else:
        message = "生成失败，请稍后重试。"
        hint = ""
        detail = str(exc)
    LOGGER.exception("生成工作流程图失败")
    if want_json:
        return jsonify({"error": message, "hint": hint, "detail": detail}), status
    text = message + (f"\n{hint}" if hint else "")
    return _index_page(error=text, status=status)


def _is_api() -> bool:
    return request.path.startswith("/api/")


# ----------------------------------------------------------------------
# 页面路由
# ----------------------------------------------------------------------
@app.get("/")
def index():
    return _index_page()


@app.post("/analyze")
def analyze_route():
    requirement = (request.form.get("requirement") or "").strip()
    force_mock = (request.form.get("mode") or "").strip().lower() == "mock"
    if not requirement:
        return _index_page(error="请先输入需求内容，或点击示例快速填充。", status=400)
    try:
        plan = generate(requirement, force_mock=force_mock)
    except Exception as exc:  # noqa: BLE001 - 统一转成页面友好提示
        return _error_response(exc, want_json=False)
    return redirect(url_for("result", plan_id=_remember(plan)))


@app.get("/result/<plan_id>")
def result(plan_id: str):
    plan = store.get(plan_id)
    if plan is None:
        return (
            render_template(
                "message.html",
                title="方案已过期",
                message="该方案不存在或已被清理，请回到首页重新输入需求生成。",
                settings=load_settings().public(),
            ),
            404,
        )
    settings = load_settings()
    return render_template(
        "result.html",
        plan=plan,
        view=build_view(plan),
        plan_id=plan_id,
        settings=settings.public(),
        agents_catalog=[
            {"id": agent_id, **meta} for agent_id, meta in AGENTS.items()
        ],
        prompt_version=PROMPT_VERSION,
    )


@app.get("/settings")
def settings_page():
    settings = load_settings()
    decompose_messages = build_decompose_messages(
        "（示例需求）我要做一个小红书",
        agent_catalog_text(),
        MIN_TASKS,
        MAX_TASKS,
    )
    orchestrate_messages = build_orchestrate_messages(
        "（示例需求）我要做一个小红书",
        '[{"id":"T01","name":"需求澄清","module":"规划","priority":"P0","effort":2,"suggested_agent":"pm"}]',
        agent_catalog_text(),
    )
    return render_template(
        "settings.html",
        settings=settings.public(),
        decompose_system=decompose_messages[0]["content"],
        decompose_user=decompose_messages[1]["content"],
        orchestrate_system=orchestrate_messages[0]["content"],
        orchestrate_user=orchestrate_messages[1]["content"],
        prompt_version=PROMPT_VERSION,
    )


# ----------------------------------------------------------------------
# JSON API
# ----------------------------------------------------------------------
@app.post("/api/analyze")
def api_analyze():
    payload = request.get_json(silent=True) or {}
    requirement = (payload.get("requirement") or "").strip()
    mock_value = payload.get("mock")
    force_mock = (
        mock_value is True
        or str(mock_value).strip().lower() in {"1", "true", "yes"}
        or str(payload.get("mode") or "").lower() == "mock"
    )
    if not requirement:
        return jsonify({"error": "requirement 不能为空", "hint": "请传入需求文本。"}), 400
    try:
        plan = generate(requirement, force_mock=force_mock)
    except Exception as exc:  # noqa: BLE001
        return _error_response(exc, want_json=True)
    plan_id = _remember(plan)
    return jsonify({"plan_id": plan_id, "plan": plan}), 200


@app.get("/api/plan/<plan_id>")
def api_get_plan(plan_id: str):
    plan = store.get(plan_id)
    if plan is None:
        return jsonify({"error": "方案不存在或已过期"}), 404
    return jsonify({"plan_id": plan_id, "plan": plan})


@app.route("/api/plan/<plan_id>", methods=["PUT", "POST"])
def api_save_plan(plan_id: str):
    if store.get(plan_id) is None:
        return jsonify({"error": "方案不存在或已过期，无法保存"}), 404
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "请求体必须是 JSON"}), 400
    try:
        plan = validate_saved_plan(payload)
    except ValidationError as exc:
        return (
            jsonify({"error": exc.message, "errors": exc.errors, "hint": "请检查节点与连线是否完整。"}),
            400,
        )
    store.save(plan_id, plan)
    return jsonify(
        {
            "ok": True,
            "plan_id": plan_id,
            "plan": plan,
            "view": build_view(plan),
            "stats": plan["stats"],
        }
    )


@app.post("/api/llm/test")
def api_llm_test():
    settings = load_settings()
    if not settings.configured:
        return (
            jsonify(
                {
                    "error": "尚未配置 LLM_API_KEY",
                    "hint": "复制 .env.example 为 .env，填入 Key、base_url 与模型名后重启服务。",
                    "mode": settings.mode,
                }
            ),
            400,
        )
    try:
        result = LLMClient(settings).test_connection()
    except LLMError as exc:
        return jsonify({**exc.as_dict(), "mode": settings.mode}), exc.status or 502
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("LLM 连通性测试失败")
        return jsonify({"error": "连接测试失败", "detail": str(exc)[:400]}), 502
    return jsonify({"ok": True, "model": settings.model, "base_url": settings.base_url, **result})


@app.get("/api/settings")
def api_settings():
    settings = load_settings()
    return jsonify(settings.public())


@app.get("/api/health")
def health():
    settings = load_settings()
    return jsonify(
        {
            "status": "ok",
            "version": "2.0.0",
            "mode": settings.mode,
            "model": settings.model,
            "configured": settings.configured,
            "prompt_version": PROMPT_VERSION,
        }
    )


# ----------------------------------------------------------------------
# 错误处理
# ----------------------------------------------------------------------
@app.errorhandler(404)
def not_found(_error):
    if _is_api():
        return jsonify({"error": "接口不存在"}), 404
    return (
        render_template(
            "message.html",
            title="页面不存在",
            message="请回到首页重新开始。",
            settings=load_settings().public(),
        ),
        404,
    )


@app.errorhandler(413)
def too_large(_error):
    if _is_api():
        return jsonify({"error": "请求体过大"}), 413
    return render_template(
        "message.html",
        title="内容过大",
        message="需求或方案数据超过 4MB，请精简后重试。",
        settings=load_settings().public(),
    ), 413


@app.errorhandler(500)
def server_error(_error):
    if _is_api():
        return jsonify({"error": "服务器内部错误"}), 500
    return (
        render_template(
            "message.html",
            title="服务器开小差了",
            message="请稍后重试；如果问题持续存在，请查看启动终端里的日志。",
            settings=load_settings().public(),
        ),
        500,
    )


if __name__ == "__main__":
    settings = load_settings()
    print("=" * 64)
    print("  SE Workflow Studio · 任务分解 + Agent 编排")
    print(f"  模式：{settings.mode_label}")
    if settings.configured:
        print(f"  模型：{settings.model}  ·  {settings.base_url}")
    else:
        print("  未检测到 LLM_API_KEY：将使用 Mock 演示。")
        print("  接入真实大模型：copy .env.example .env 后填入 Key。")
    print(f"  打开浏览器访问 http://{settings.host}:{settings.port}")
    print("=" * 64)
    app.run(host=settings.host, port=settings.port, debug=False)
