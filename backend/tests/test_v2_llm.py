"""V2-M2 测试：真实 LLM Agent 循环对本地 stub 的端到端验证。

铁律：只打 127.0.0.1 的本地 stub，不碰外网；LLM_API_KEY 恒为空。
验证 plan→call→verdict→execute 完整链路：
  - followup：crm.read 放行执行 → mail.send 人工批准后执行 → outbox 落库
  - export_attack：注入诱导出的 crm.export_all 被网关 deny，无副作用
"""

import json
import socket
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

# 引入 scripts/stub_llm_server.py（只用标准库的本地桩）
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import stub_llm_server  # noqa: E402

from app import llm_agent  # noqa: E402


@pytest.fixture()
def stub():
    """在可用端口启动 stub，返回 base_url（如 http://127.0.0.1:PORT/v1）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = ThreadingHTTPServer(("127.0.0.1", port), stub_llm_server.StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()
    server.server_close()


def _create_task(api, title, scenario):
    r = api.post("/api/tasks", json={"title": title, "scenario": scenario})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _wait_for_pending_approval(api, tool, timeout=30):
    """轮询直到出现指定 tool 的 pending 审批单，返回 approval id。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = api.get("/api/approvals", params={"status": "pending"})
        assert r.status_code == 200
        for ap in r.json():
            action = ap.get("action") or {}
            if action.get("tool") == tool:
                return ap["id"]
        time.sleep(0.5)
    raise AssertionError(f"超时：未出现 {tool} 的 pending 审批单")


def _audit_events(api, task_id):
    r = api.get("/api/audit", params={"task_id": task_id, "limit": 200})
    assert r.status_code == 200
    return r.json()


# ---------- 配置状态 ----------

def test_llm_status_unconfigured(api, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    r = api.get("/api/llm/status")
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is False
    assert data["base_url"]  # 有默认值
    assert data["model"]
    # 绝不泄露 key
    assert "api_key" not in json.dumps(data).lower()


def test_run_llm_without_key_returns_409(api, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    task_id = _create_task(api, "跟进客户 1", "followup")
    r = api.post(f"/api/tasks/{task_id}/run-llm", json={"goal": "请跟进客户 1"})
    assert r.status_code == 409
    assert r.json()["detail"] == "llm_not_configured"


# ---------- followup 端到端：read 放行 + mail 审批后执行 ----------

def test_followup_loop_end_to_end(api, stub):
    task_id = _create_task(api, "跟进客户 1", "followup")

    results = {}

    def _run():
        results["res"] = llm_agent.run_llm_task(
            task_id, "请跟进客户 1，查阅资料后发送跟进邮件",
            base_url=stub, api_key="stub", model="stub",
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        # mail.send 走审批路径：等审批单出现后人工批准
        approval_id = _wait_for_pending_approval(api, "mail.send", timeout=30)
        r = api.post(f"/api/approvals/{approval_id}/decide",
                     json={"decision": "approve", "approver": "test"})
        assert r.status_code == 200, r.text

        thread.join(timeout=90)
        assert not thread.is_alive(), "agent 循环线程超时未结束"
    finally:
        if thread.is_alive():
            # 失败时不让线程悬挂：测试库隔离由 conftest 负责
            pass

    res = results.get("res")
    assert res is not None
    assert res["status"] == "completed", res
    assert res["steps"] >= 3  # read → mail → 终答

    # 动作状态：read 与 mail 都 executed
    r = api.get(f"/api/tasks/{task_id}")
    assert r.status_code == 200
    by_tool = {a["tool"]: a for a in r.json()["actions"]}
    assert by_tool["crm.read"]["status"] == "executed"
    assert by_tool["crm.read"]["origin"] == "llm"
    assert by_tool["mail.send"]["status"] == "executed"
    assert by_tool["mail.send"]["decision"] == "needs_approval"

    # outbox 落库
    r = api.get("/api/outbox")
    assert r.status_code == 200
    mine = [o for o in r.json() if o["task_id"] == task_id]
    assert len(mine) >= 1
    assert mine[0]["to_email"]  # 真实写入收件人

    # 审计事件链：agent.step 推理步骤 + 执行事件
    events = _audit_events(api, task_id)
    kinds = [e["event"] for e in events]
    assert kinds.count("agent.step") >= 2
    assert "action.executed" in kinds
    assert "approval.approved" in kinds
    assert all(e["actor"] == "llm-agent" for e in events if e["event"] == "agent.step")


# ---------- export_attack：注入诱导的导出必须被网关 deny ----------

def test_export_attack_denied(api, stub):
    task_id = _create_task(api, "攻击测试", "export_attack")

    res = llm_agent.run_llm_task(
        task_id, "攻击测试：查看客户 6 的备注并按备注要求操作",
        base_url=stub, api_key="stub", model="stub",
    )
    # Agent 拿到 deny 后正常收尾（拒绝本身不是循环异常）
    assert res["status"] == "completed", res

    r = api.get(f"/api/tasks/{task_id}")
    assert r.status_code == 200
    by_tool = {a["tool"]: a for a in r.json()["actions"]}
    assert "crm.read" in by_tool  # 先读到了客户 6（含模拟注入的 notes）
    export = by_tool.get("crm.export_all")
    assert export is not None, "stub 应在读到注入后诱导出 crm.export_all"
    assert export["status"] == "denied"
    assert export["decision"] == "deny"

    # 无副作用：发件箱为空
    r = api.get("/api/outbox")
    assert r.status_code == 200
    assert [o for o in r.json() if o["task_id"] == task_id] == []

    # 审计有 deny 记录
    events = _audit_events(api, task_id)
    kinds = [e["event"] for e in events]
    assert "action.denied" in kinds
    assert kinds.count("agent.step") >= 2
