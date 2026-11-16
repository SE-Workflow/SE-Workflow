"""V5 引擎与 Web 路由测试。

覆盖：
- JSON 提取 / 容错 / 结构校验；
- 统一流程图的 DAG、分层、关键路径、Agent 统计；
- Mock 模式（无 Key）完整生成；
- 本地假 LLM 服务验证两阶段调用、JSON 纠错重试、阶段二降级、失败回退；
- Flask 页面与保存 API、密钥掩码安全。

运行：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app  # noqa: E402
import app as app_module  # noqa: E402
from config import Settings, mask_secret  # noqa: E402
from engine import PipelineError, PlanStore, build_view, generate, validate_saved_plan  # noqa: E402
from engine.json_utils import JSONParseError, extract_json  # noqa: E402
from engine.schema import (  # noqa: E402
    ValidationError,
    build_plan,
    normalize_decomposition,
    normalize_orchestration,
    rebuild_plan,
)

MOCK_SETTINGS = Settings(api_key="", force_mock=True, max_retries=1, timeout=10)


def make_tasks() -> list[dict]:
    return [
        {
            "id": "T01",
            "name": "需求澄清",
            "description": "明确目标、范围与验收口径",
            "module": "规划与需求",
            "priority": "P0",
            "effort": 2.0,
            "agent": "pm",
            "acceptance": "范围说明与验收标准评审通过",
        },
        {
            "id": "T02",
            "name": "架构设计",
            "description": "输出总体架构与接口契约",
            "module": "设计与架构",
            "priority": "P0",
            "effort": 3.0,
            "agent": "architect",
            "acceptance": "架构评审通过",
        },
        {
            "id": "T03",
            "name": "后端接口",
            "description": "实现核心服务与数据层",
            "module": "基础研发",
            "priority": "P0",
            "effort": 6.0,
            "agent": "backend",
            "acceptance": "接口联调通过",
        },
        {
            "id": "T04",
            "name": "前端页面",
            "description": "实现页面与交互",
            "module": "基础研发",
            "priority": "P1",
            "effort": 5.0,
            "agent": "frontend",
            "acceptance": "页面验收通过",
        },
        {
            "id": "T05",
            "name": "测试验收",
            "description": "端到端测试与缺陷收口",
            "module": "集成与质量",
            "priority": "P0",
            "effort": 3.0,
            "agent": "qa",
            "acceptance": "P0/P1 缺陷清零",
        },
        {
            "id": "T06",
            "name": "部署上线",
            "description": "CI/CD 与生产发布",
            "module": "发布与运维",
            "priority": "P1",
            "effort": 2.0,
            "agent": "devops",
            "acceptance": "生产环境发布成功",
        },
    ]


DECOMPOSITION = {
    "summary": "做一个内容社区，先规划与架构，再并行研发，最后联调发布。",
    "domain": "内容社区",
    "scale": "中型",
    "platforms": ["Web", "iOS / Android"],
    "tasks": make_tasks(),
}

ORCHESTRATION = {
    "summary": "先设计与架构，前后端并行研发，测试收口后发布。",
    "edges": [
        {"from": "T01", "to": "T02", "kind": "dependency"},
        {"from": "T02", "to": "T03", "kind": "dependency"},
        {"from": "T02", "to": "T04", "kind": "dependency"},
        {"from": "T03", "to": "T05", "kind": "dependency"},
        {"from": "T04", "to": "T05", "kind": "dependency"},
        {"from": "T05", "to": "T06", "kind": "flow"},
    ],
    "stages": [
        {"level": 0, "name": "规划与设计", "nodes": ["T01", "T02"], "parallel": False},
        {"level": 1, "name": "并行研发", "nodes": ["T03", "T04"], "parallel": True},
        {"level": 2, "name": "质量与发布", "nodes": ["T05", "T06"], "parallel": False},
    ],
    "assignments": [
        {"node": "T01", "agent": "pm", "role": "需求边界与验收口径"},
        {"node": "T02", "agent": "architect", "role": "架构与接口契约"},
        {"node": "T03", "agent": "backend", "role": "服务端实现"},
        {"node": "T04", "agent": "frontend", "role": "页面与交互"},
        {"node": "T05", "agent": "qa", "role": "质量收口"},
        {"node": "T06", "agent": "devops", "role": "发布上线"},
    ],
    "parallel_groups": [{"name": "前后端并行", "nodes": ["T03", "T04"]}],
}


# ======================================================================
# JSON 工具
# ======================================================================
class JsonUtilsTests(unittest.TestCase):
    def test_extract_fenced_json(self) -> None:
        payload = extract_json('```json\n{"tasks": [1, 2]}\n```')
        self.assertEqual(payload, {"tasks": [1, 2]})

    def test_extract_with_prose_and_array(self) -> None:
        self.assertEqual(extract_json('好的，结果是：\n[{"a": 1}]\n希望有帮助'), [{"a": 1}])

    def test_extract_repairs_trailing_comma(self) -> None:
        self.assertEqual(extract_json('{"a": 1, }'), {"a": 1})

    def test_extract_invalid_raises(self) -> None:
        with self.assertRaises(JSONParseError):
            extract_json("这不是 JSON")


# ======================================================================
# 结构校验 / 计划组装
# ======================================================================
class SchemaTests(unittest.TestCase):
    def test_normalize_decomposition_aliases_and_limits(self) -> None:
        payload = {
            "tasks": [
                {"id": "T01", "title": "需求", "priority": "高", "effort": 99, "agent": "产品经理"},
                {"id": "T01", "name": "设计", "effort": -1, "agent": "unknown-agent"},
                {"name": "开发", "priority": "低", "effort": 2, "agent": "backend"},
            ]
        }
        normalized = normalize_decomposition(payload, "测试需求")
        self.assertEqual(len(normalized["tasks"]), 3)
        self.assertEqual(normalized["tasks"][0]["priority"], "P0")
        self.assertEqual(normalized["tasks"][0]["effort"], 15.0)
        self.assertEqual(normalized["tasks"][0]["agent"], "pm")
        self.assertEqual(normalized["tasks"][1]["id"], "T01-2")
        self.assertEqual(normalized["tasks"][2]["priority"], "P2")

    def test_normalize_decomposition_requires_tasks(self) -> None:
        with self.assertRaises(ValidationError):
            normalize_decomposition({"tasks": []})

    def test_normalize_orchestration_cycles_and_names(self) -> None:
        tasks = make_tasks()
        payload = {
            "edges": [
                {"source": "需求澄清", "target": "T02"},
                {"source": "T02", "target": "T03"},
                {"source": "T03", "target": "T02"},
                {"source": "T03", "target": "T03"},
            ],
            "assignments": {"T01": "产品经理"},
        }
        normalized = normalize_orchestration(payload, tasks)
        self.assertEqual(normalized["assignments"]["T01"]["agent"], "pm")
        pairs = {(edge["from"], edge["to"]) for edge in normalized["edges"]}
        self.assertIn(("T01", "T02"), pairs)
        self.assertIn(("T02", "T03"), pairs)
        self.assertNotIn(("T03", "T02"), pairs)

    def test_build_plan_computes_levels_and_critical_path(self) -> None:
        decomposition = normalize_decomposition(DECOMPOSITION, "测试需求")
        orchestration = normalize_orchestration(ORCHESTRATION, decomposition["tasks"])
        plan = build_plan(
            requirement="测试需求",
            decomposition=decomposition,
            orchestration=orchestration,
            meta={"engine": "llm", "model": "fake"},
        )
        nodes = {node["id"]: node for node in plan["nodes"]}
        self.assertEqual(nodes["T01"]["level"], 0)
        self.assertGreater(nodes["T05"]["level"], nodes["T03"]["level"])
        self.assertTrue(nodes["T01"]["critical"])
        self.assertIn("T01", plan["critical_path"])
        self.assertEqual(plan["stats"]["nodes"], 6)
        self.assertEqual(plan["stats"]["agents"], 6)
        self.assertEqual(len(plan["stages"]), 5)
        self.assertTrue(
            any(set(group["node_ids"]) == {"T03", "T04"} for group in plan["parallel_groups"])
        )
        self.assertTrue(plan["legend"]["agents"])
        self.assertEqual(plan["legend"]["critical"]["color"], "#ef4444")

    def test_llm_stage_levels_influence_layout(self) -> None:
        tasks = make_tasks()
        decomposition = normalize_decomposition({"tasks": tasks}, "测试")
        orchestration = normalize_orchestration(
            {
                "edges": [],
                "stages": [
                    {"level": 0, "name": "起点", "nodes": ["T01"]},
                    {"level": 3, "name": "设计阶段", "nodes": ["T02"]},
                ],
            },
            tasks,
        )
        plan = build_plan(
            requirement="测试",
            decomposition=decomposition,
            orchestration=orchestration,
            meta={"engine": "llm"},
        )
        nodes = {node["id"]: node for node in plan["nodes"]}
        self.assertGreater(nodes["T02"]["level"], nodes["T01"]["level"])
        self.assertEqual(
            sorted({node["level"] for node in plan["nodes"]}),
            list(range(plan["stats"]["stages"])),
        )

    def test_rebuild_plan_after_edit(self) -> None:
        decomposition = normalize_decomposition(DECOMPOSITION, "测试需求")
        orchestration = normalize_orchestration(ORCHESTRATION, decomposition["tasks"])
        plan = build_plan(
            requirement="测试需求",
            decomposition=decomposition,
            orchestration=orchestration,
            meta={"engine": "llm"},
        )
        before = plan["stats"]["total_effort"]
        before_stages = [stage["name"] for stage in plan["stages"]]
        plan["nodes"][0]["name"] = "改名后的任务"
        plan["nodes"][0]["effort"] = 10
        rebuilt = rebuild_plan(plan)
        self.assertEqual(rebuilt["nodes"][0]["name"], "改名后的任务")
        self.assertGreater(rebuilt["stats"]["total_effort"], before)
        self.assertEqual([stage["name"] for stage in rebuilt["stages"]], before_stages)
        self.assertTrue(rebuilt["meta"]["edited"])
        self.assertTrue(rebuilt["meta"]["edited_at"])

    def test_rebuild_plan_preserves_drag_positions(self) -> None:
        decomposition = normalize_decomposition(DECOMPOSITION, "测试需求")
        orchestration = normalize_orchestration(ORCHESTRATION, decomposition["tasks"])
        plan = build_plan(
            requirement="测试需求",
            decomposition=decomposition,
            orchestration=orchestration,
            meta={"engine": "llm"},
        )
        plan["nodes"][0]["x"] = 120.5
        plan["nodes"][0]["y"] = -40
        plan["nodes"][0]["pinned"] = True
        rebuilt = rebuild_plan(plan)
        node = rebuilt["nodes"][0]
        self.assertEqual(node["x"], 120.5)
        self.assertEqual(node["y"], -40)
        self.assertTrue(node["pinned"])

    def test_validate_saved_plan_rejects_empty(self) -> None:
        with self.assertRaises(ValidationError):
            validate_saved_plan({"nodes": [], "edges": []})


# ======================================================================
# Mock 模式
# ======================================================================
class MockGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.xhs = generate("我要做一个小红书", settings=MOCK_SETTINGS)
        cls.wechat = generate("我要做微信", settings=MOCK_SETTINGS)
        cls.spec = generate(
            "为连锁健身房做一套会员运营 App（iOS / Android）：支持注册、扫码入场、课表预约、"
            "私教课时购买与退款、多门店多租户、后台报表与营销、弱网可用、数据合规。",
            settings=MOCK_SETTINGS,
        )

    def test_mock_plan_shape(self) -> None:
        for plan in (self.xhs, self.wechat, self.spec):
            self.assertGreaterEqual(plan["stats"]["nodes"], 5)
            self.assertGreater(plan["stats"]["edges"], 0)
            self.assertTrue(plan["critical_path"])
            self.assertEqual(plan["meta"]["engine"], "mock")
            self.assertIn("Mock", plan["meta"]["engine_label"])
            self.assertTrue(plan["warnings"])
            self.assertEqual(
                [stage["level"] for stage in plan["stages"]],
                list(range(len(plan["stages"]))),
            )

    def test_mock_dag_is_consistent(self) -> None:
        plan = self.wechat
        ids = {node["id"] for node in plan["nodes"]}
        pairs = set()
        for edge in plan["edges"]:
            self.assertIn(edge["from"], ids)
            self.assertIn(edge["to"], ids)
            self.assertNotEqual(edge["from"], edge["to"])
            pairs.add((edge["from"], edge["to"]))
        for node in plan["nodes"]:
            for parent in node["depends_on"]:
                self.assertIn((parent, node["id"]), pairs)

    def test_agents_cover_all_nodes(self) -> None:
        plan = self.spec
        assigned = {node_id for agent in plan["agents"] for node_id in agent["node_ids"]}
        self.assertEqual(assigned, {node["id"] for node in plan["nodes"]})
        self.assertAlmostEqual(
            sum(agent["effort"] for agent in plan["agents"]),
            plan["stats"]["total_effort"],
            places=1,
        )

    def test_plan_is_json_serializable(self) -> None:
        payload = json.dumps(self.xhs, ensure_ascii=False)
        self.assertGreater(len(payload), 2000)
        self.assertIn("critical_path", payload)

    def test_view_contains_stage_and_agent_panels(self) -> None:
        view = build_view(self.xhs)
        self.assertEqual(len(view["stages"]), self.xhs["stats"]["stages"])
        self.assertEqual(len(view["agent_load"]), self.xhs["stats"]["agents"])
        self.assertTrue(view["critical_chain"])
        self.assertTrue(view["edge_kinds"])
        self.assertEqual(sum(stage["count"] for stage in view["stages"]), self.xhs["stats"]["nodes"])


# ======================================================================
# 假 LLM 服务
# ======================================================================
class _FakeHandler(BaseHTTPRequestHandler):
    server: "_FakeLLMServer"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _chat_payload(self, content: str) -> dict:
        return {
            "model": "fake-model",
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            payload = {}
        self.server.requests.append(payload)
        messages = payload.get("messages") or []
        system = str((messages[0] or {}).get("content", ""))
        if "任务分解" in system or "软件工程负责人" in system:
            stage = "decompose"
        elif "编排专家" in system:
            stage = "orchestrate"
        else:
            stage = "test"
        self.server.calls.append(stage)

        if self.server.reject_response_format and "response_format" in payload:
            self._send(400, {"error": {"message": "response_format is not supported"}})
            return
        if self.server.fail_stage == stage and self.server.fail_status:
            self._send(self.server.fail_status, {"error": {"message": "fake upstream error"}})
            return
        if self.server.invalid_stage == stage and self.server.invalid_remaining > 0:
            self.server.invalid_remaining -= 1
            self._send(200, self._chat_payload("这不是合法 JSON，只是一段解释文字。"))
            return
        self._send(
            200,
            self._chat_payload(json.dumps(self.server.responses[stage], ensure_ascii=False)),
        )


class _FakeLLMServer:
    def __init__(self) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _FakeHandler)
        self.httpd.responses = {
            "decompose": DECOMPOSITION,
            "orchestrate": ORCHESTRATION,
            "test": {"ok": True},
        }
        self.httpd.requests = []
        self.httpd.calls = []
        self.httpd.fail_stage = ""
        self.httpd.fail_status = 0
        self.httpd.invalid_stage = ""
        self.httpd.invalid_remaining = 0
        self.httpd.reject_response_format = False
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    @property
    def requests(self) -> list[dict]:
        return self.httpd.requests

    @property
    def calls(self) -> list[str]:
        return self.httpd.calls

    def configure(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self.httpd, key, value)

    def __enter__(self) -> "_FakeLLMServer":
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)


def llm_settings(server: _FakeLLMServer, **overrides) -> Settings:
    values = dict(
        api_key="test-key-not-real",
        base_url=server.base_url,
        model="fake-model",
        max_retries=1,
        allow_mock=True,
        force_mock=False,
        json_mode=True,
        timeout=10,
    )
    values.update(overrides)
    return Settings(**values)


class LLMFlowTests(unittest.TestCase):
    def test_two_stage_llm_success(self) -> None:
        with _FakeLLMServer() as server:
            orchestration = json.loads(json.dumps(ORCHESTRATION))
            for item in orchestration["assignments"]:
                if item["node"] == "T01":
                    item["agent"] = "ux"
                    item["role"] = "由阶段二改派"
            server.configure(
                responses={"decompose": DECOMPOSITION, "orchestrate": orchestration, "test": {}}
            )
            plan = generate("做一个内容社区", settings=llm_settings(server))
            self.assertEqual(plan["meta"]["engine"], "llm")
            self.assertFalse(plan["meta"]["degraded"])
            self.assertEqual(plan["stats"]["nodes"], 6)
            self.assertEqual(server.calls, ["decompose", "orchestrate"])
            self.assertEqual(plan["meta"]["llm_calls"][0]["stage"], "decompose")
            self.assertEqual(plan["meta"]["llm_calls"][1]["stage"], "orchestrate")
            t01 = next(node for node in plan["nodes"] if node["id"] == "T01")
            self.assertEqual(t01["agent"], "ux")
            self.assertEqual(t01["role"], "由阶段二改派")
            self.assertTrue(server.requests[0]["messages"][0]["content"])
            self.assertEqual(server.requests[0]["response_format"], {"type": "json_object"})
            self.assertIn("做一个内容社区", server.requests[0]["messages"][1]["content"])

    def test_json_repair_retry(self) -> None:
        with _FakeLLMServer() as server:
            server.configure(invalid_stage="decompose", invalid_remaining=1)
            plan = generate("做一个内容社区", settings=llm_settings(server, max_retries=2))
            self.assertEqual(plan["meta"]["engine"], "llm")
            decompose_calls = [call for call in server.calls if call == "decompose"]
            self.assertEqual(len(decompose_calls), 2)
            self.assertEqual(plan["meta"]["llm_calls"][0]["attempts"], 2)
            repair_message = server.requests[1]["messages"][-1]["content"]
            self.assertIn("无法被解析", repair_message)

    def test_stage_two_failure_keeps_llm_tasks(self) -> None:
        with _FakeLLMServer() as server:
            server.configure(fail_stage="orchestrate", fail_status=401)
            plan = generate("做一个内容社区", settings=llm_settings(server))
            self.assertEqual(plan["meta"]["engine"], "llm-fallback")
            self.assertTrue(plan["meta"]["degraded"])
            self.assertIn("阶段二", plan["meta"]["degraded_reason"])
            self.assertEqual(plan["stats"]["nodes"], 6)
            self.assertEqual(plan["stats"]["edges"], 5)
            self.assertTrue(any("阶段二" in warning for warning in plan["warnings"]))

    def test_stage_one_failure_falls_back_to_mock(self) -> None:
        with _FakeLLMServer() as server:
            server.configure(fail_stage="decompose", fail_status=401)
            plan = generate("做一个内容社区", settings=llm_settings(server, allow_mock=True))
            self.assertEqual(plan["meta"]["engine"], "mock")
            self.assertTrue(plan["meta"]["degraded"])
            self.assertIn("回退 Mock", plan["meta"]["degraded_reason"])
            self.assertGreater(plan["stats"]["nodes"], 6)

    def test_failure_without_mock_raises_friendly_error(self) -> None:
        with _FakeLLMServer() as server:
            server.configure(fail_stage="decompose", fail_status=401)
            with self.assertRaises(PipelineError) as context:
                generate("做一个内容社区", settings=llm_settings(server, allow_mock=False))
            message = str(context.exception)
            self.assertIn("任务分解失败", message)
            self.assertIn("API Key 无效", message)

    def test_response_format_fallback(self) -> None:
        with _FakeLLMServer() as server:
            server.configure(reject_response_format=True)
            plan = generate("做一个内容社区", settings=llm_settings(server))
            self.assertEqual(plan["meta"]["engine"], "llm")
            self.assertTrue(
                any("response_format" not in request for request in server.requests[1:])
            )

    def test_force_mock_skips_network(self) -> None:
        with _FakeLLMServer() as server:
            plan = generate(
                "做一个内容社区",
                settings=llm_settings(server, force_mock=True),
                force_mock=True,
            )
            self.assertEqual(plan["meta"]["engine"], "mock")
            self.assertEqual(server.calls, [])

    def test_no_key_and_mock_disallowed_raises(self) -> None:
        with self.assertRaises(PipelineError) as context:
            generate(
                "做一个内容社区",
                settings=Settings(api_key="", allow_mock=False, max_retries=0),
            )
        self.assertIn("LLM_ALLOW_MOCK", str(context.exception))


# ======================================================================
# 方案持久化
# ======================================================================
class StorageTests(unittest.TestCase):
    def test_plan_store_roundtrip(self) -> None:
        directory = Path(__file__).resolve().parent.parent / "data" / "_store_test"
        directory.mkdir(parents=True, exist_ok=True)
        try:
            store = PlanStore(directory)
            plan = {"nodes": [{"id": "T01", "name": "任务"}], "edges": [], "meta": {}}
            store.save("abc123def456", plan)
            reloaded = PlanStore(directory).get("abc123def456")
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded["nodes"][0]["name"], "任务")
            self.assertEqual(reloaded["meta"]["plan_id"], "abc123def456")
            self.assertIsNone(store.get("../bad"))
        finally:
            shutil.rmtree(directory, ignore_errors=True)


# ======================================================================
# 密钥安全
# ======================================================================
class SecurityTests(unittest.TestCase):
    def test_mask_secret_never_returns_full_key(self) -> None:
        secret = "sk-1234567890abcdef"
        masked = mask_secret(secret)
        self.assertNotEqual(masked, secret)
        self.assertNotIn(secret, masked)
        self.assertTrue(masked.startswith("sk-1"))
        self.assertTrue(masked.endswith("cdef"))

    def test_public_settings_does_not_expose_key(self) -> None:
        secret = "sk-super-secret-value-123"
        settings = Settings(api_key=secret, base_url="https://api.example.com/v1", model="demo")
        public = settings.public()
        self.assertTrue(public["configured"])
        self.assertEqual(public["mode"], "llm")
        self.assertNotIn(secret, json.dumps(public, ensure_ascii=False))
        self.assertNotIn("api_key", public)

    def test_force_mock_mode(self) -> None:
        settings = Settings(api_key="sk-test", force_mock=True)
        self.assertEqual(settings.mode, "mock")
        self.assertEqual(settings.public()["mode"], "mock")


# ======================================================================
# Flask 路由
# ======================================================================
class RoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._old_env = {
            key: os.environ.get(key) for key in ("LLM_API_KEY", "LLM_MOCK_MODE", "LLM_ALLOW_MOCK")
        }
        os.environ["LLM_API_KEY"] = ""
        os.environ["LLM_MOCK_MODE"] = "true"
        os.environ["LLM_ALLOW_MOCK"] = "true"

    @classmethod
    def tearDownClass(cls) -> None:
        for key, value in cls._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def setUp(self) -> None:
        flask_app.config.update(TESTING=True)
        self.client = flask_app.test_client()
        self._old_store = app_module.store
        # 放在工作区 data/ 下，避免 Windows 沙箱对系统 Temp / 新建 ACL 目录的写入限制
        self._tempdir = Path(__file__).resolve().parent.parent / "data" / "_test_plans"
        self._tempdir.mkdir(parents=True, exist_ok=True)
        app_module.store = PlanStore(self._tempdir, memory_limit=5, disk_limit=5)

    def tearDown(self) -> None:
        app_module.store = self._old_store
        shutil.rmtree(self._tempdir, ignore_errors=True)

    def test_index_and_settings_pages(self) -> None:
        index = self.client.get("/")
        self.assertEqual(index.status_code, 200)
        self.assertIn("生成工作流程图", index.get_data(as_text=True))
        settings = self.client.get("/settings")
        self.assertEqual(settings.status_code, 200)
        self.assertIn("密钥安全", settings.get_data(as_text=True))
        self.assertIn("任务分解 Prompt", settings.get_data(as_text=True))

    def test_analyze_form_redirects_to_graph_page(self) -> None:
        response = self.client.post("/analyze", data={"requirement": "我要做微信"})
        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        self.assertTrue(location.startswith("/result/"))
        page = self.client.get(location)
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('id="graph"', html)
        self.assertIn('id="bootstrap-data"', html)
        self.assertIn("工作流程图", html)

    def test_api_analyze_and_save(self) -> None:
        response = self.client.post(
            "/api/analyze", json={"requirement": "我要做一个小红书", "mock": True}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("plan_id", payload)
        plan = payload["plan"]
        self.assertEqual(plan["meta"]["engine"], "mock")
        self.assertGreater(plan["stats"]["nodes"], 0)

        plan["nodes"][0]["name"] = "通过 API 修改的任务"
        plan["nodes"][0]["effort"] = 4.5
        saved = self.client.put(f"/api/plan/{payload['plan_id']}", json={"plan": plan})
        self.assertEqual(saved.status_code, 200)
        saved_payload = saved.get_json()
        self.assertTrue(saved_payload["ok"])
        self.assertEqual(saved_payload["plan"]["nodes"][0]["name"], "通过 API 修改的任务")
        self.assertTrue(saved_payload["plan"]["meta"]["edited"])

        fetched = self.client.get(f"/api/plan/{payload['plan_id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.get_json()["plan"]["nodes"][0]["name"], "通过 API 修改的任务")

    def test_save_rejects_invalid_plan(self) -> None:
        created = self.client.post("/api/analyze", json={"requirement": "我要做微信"}).get_json()
        invalid = self.client.put(
            f"/api/plan/{created['plan_id']}", json={"plan": {"nodes": [], "edges": []}}
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("error", invalid.get_json())

    def test_unknown_plan_and_api_404(self) -> None:
        self.assertEqual(self.client.get("/result/not-found").status_code, 404)
        self.assertEqual(
            self.client.put("/api/plan/not-found", json={"plan": {}}).status_code, 404
        )
        api_404 = self.client.get("/api/does-not-exist")
        self.assertEqual(api_404.status_code, 404)
        self.assertEqual(api_404.get_json()["error"], "接口不存在")

    def test_empty_requirement(self) -> None:
        self.assertEqual(self.client.post("/api/analyze", json={}).status_code, 400)
        self.assertEqual(self.client.post("/analyze", data={"requirement": "  "}).status_code, 400)

    def test_health_and_settings_api(self) -> None:
        health = self.client.get("/api/health").get_json()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["mode"], "mock")
        public = self.client.get("/api/settings").get_json()
        self.assertNotIn("api_key", public)
        self.assertFalse(public["configured"])

    def test_llm_test_without_key(self) -> None:
        response = self.client.post("/api/llm/test")
        self.assertEqual(response.status_code, 400)
        self.assertIn("LLM_API_KEY", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
