"""引擎与接口的冒烟测试：保证任意输入都能产出结构完整、可序列化的 DAG 方案。

运行：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from engine import analyze  # noqa: E402


class AnalyzeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.xhs = analyze("我要做一个小红书")
        cls.wechat = analyze("我要做微信")
        cls.spec = analyze(
            "为连锁健身房做一套会员运营 App（iOS / Android）：\n"
            "- 支持会员注册、扫码入场、课表预约与取消\n"
            "- 支持私教课时购买、支付、退款与发票\n"
            "- 教练端可查看排课、会员训练记录并布置训练计划\n"
            "- 支持多门店与多租户隔离，总部可配置各门店权限\n"
            "- 后台需要营收报表、会员分层与营销触达\n"
            "- 要求弱网可用、数据合规，可支撑千万级会员"
        )
        cls.small = analyze("做一个简单的待办清单小工具，先出 MVP。")

    def test_domain_detection(self) -> None:
        self.assertEqual(self.xhs["profile"]["domain"]["id"], "content")
        self.assertEqual(self.wechat["profile"]["domain"]["id"], "social")
        self.assertIn("messaging", [module["key"] for module in self.wechat["modules"]])
        self.assertEqual(self.spec["profile"]["scale"]["code"], "L")

    def test_tree_is_three_layers(self) -> None:
        tree = self.xhs["tree"]
        self.assertGreater(len(tree), 5)
        for module in tree:
            self.assertEqual(module["type"], "module")
            for subtask in module["children"]:
                self.assertEqual(subtask["type"], "subtask")
                self.assertGreater(len(subtask["children"]), 0)
                for task in subtask["children"]:
                    self.assertEqual(task["id"][0], "T")
                    self.assertIn(task["priority"], {"P0", "P1", "P2"})
                    self.assertTrue(task["acceptance"])
                    self.assertGreater(task["effort"], 0)

    def test_dag_is_consistent(self) -> None:
        plan = self.wechat
        ids = {task["id"] for task in plan["tasks"]}
        edge_pairs = set()
        for edge in plan["edges"]:
            self.assertIn(edge["from"], ids)
            self.assertIn(edge["to"], ids)
            self.assertNotEqual(edge["from"], edge["to"])
            edge_pairs.add((edge["from"], edge["to"]))

        for task in plan["tasks"]:
            for dependency in task["depends_on"]:
                self.assertIn((dependency, task["id"]), edge_pairs)

        critical = plan["orchestration"]["critical_path"]
        self.assertGreater(len(critical), 1)
        critical_ids = {task["id"] for task in plan["tasks"] if task["critical"]}
        self.assertTrue(set(critical).issubset(critical_ids))
        self.assertTrue(critical_ids)

    def test_waves_cover_all_tasks(self) -> None:
        plan = self.xhs
        wave_ids = [task_id for wave in plan["orchestration"]["waves"] for task_id in wave["tasks"]]
        self.assertEqual(sorted(wave_ids), sorted(task["id"] for task in plan["tasks"]))
        self.assertEqual(plan["orchestration"]["waves"][0]["index"], 0)

    def test_agents_cover_all_tasks(self) -> None:
        plan = self.spec
        assigned = {task_id for agent in plan["orchestration"]["agents"] for task_id in agent["task_ids"]}
        self.assertEqual(assigned, {task["id"] for task in plan["tasks"]})
        load = sum(agent["effort"] for agent in plan["orchestration"]["agents"])
        self.assertAlmostEqual(load, plan["stats"]["total_effort"], places=1)

    def test_scale_changes_project_size(self) -> None:
        self.assertLess(len(self.small["tasks"]), len(self.wechat["tasks"]))

    def test_spec_has_custom_modules(self) -> None:
        custom = [module for module in self.spec["modules"] if module["custom"]]
        self.assertGreaterEqual(len(custom), 1)

    def test_plan_is_json_serializable(self) -> None:
        payload = json.dumps(self.xhs, ensure_ascii=False)
        self.assertGreater(len(payload), 2000)
        self.assertIn("critical_path", payload)


class RoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_index(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SE Workflow", response.get_data(as_text=True))

    def test_analyze_redirect_and_result_page(self) -> None:
        response = self.client.post("/analyze", data={"requirement": "我要做微信"})
        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        page = self.client.get(location)
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="plan-data"', page.get_data(as_text=True))

    def test_api_analyze(self) -> None:
        response = self.client.post("/api/analyze", json={"requirement": "我要做一个小红书"})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["profile"]["domain"]["id"], "content")
        self.assertGreater(payload["stats"]["tasks"], 0)

    def test_empty_requirement(self) -> None:
        self.assertEqual(self.client.post("/api/analyze", json={}).status_code, 400)
        self.assertEqual(self.client.post("/analyze", data={"requirement": "  "}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
