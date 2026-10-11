"""V2-M1 MCP 接入测试。

直接调用 app.mcp_server 的同步核心逻辑（mcp_call_tool / mcp_check_status），
不起 MCP 协议；验证外部 Agent 经网关裁决的完整语义。
"""

import json
import threading
import time

import pytest

from app import mcp_server

MAIL_PARAMS = {
    "customer_id": 1,
    "to": "test@example.com",
    "subject": "MCP 测试邮件",
    "body": "审批流测试",
    "batch": False,
}


def _wait_pending_approval(api, tool, timeout=15):
    """轮询待审批单，返回首个匹配 tool 的审批单 id。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ap in api.get("/api/approvals", params={"status": "pending"}).json():
            if ap["action"] and ap["action"]["tool"] == tool:
                return ap["id"]
        time.sleep(0.3)
    raise TimeoutError(f"未出现 {tool} 的 pending 审批单")


def test_1_crm_read_allowed_and_executed(api):
    """crm_read 走 allow 路径：自动执行，返回真实客户数据。"""
    res = mcp_server.mcp_call_tool("crm_read", {"customer_id": 1})
    assert res["decision"] == "allow", res
    assert res["status"] == "executed", res
    assert res["error"] is None, res
    assert res["result"] and res["result"].get("id") == 1, res


def test_2_mail_send_approval_flow(api):
    """mail_send 走审批：建审批单 → 另一线程批准 → 执行成功 → outbox 落库。"""
    holder = {}
    t = threading.Thread(
        target=lambda: holder.update(res=mcp_server.mcp_call_tool("mail_send", dict(MAIL_PARAMS))),
        daemon=True,
    )
    t.start()
    try:
        approval_id = _wait_pending_approval(api, "mail.send")
        r = api.post(f"/api/approvals/{approval_id}/decide",
                     json={"decision": "approve", "approver": "admin"})
        assert r.status_code == 200, r.text
        t.join(timeout=30)
        assert not t.is_alive(), "网关 wait 未在批准后返回"
        res = holder["res"]
        assert res["status"] == "executed", res
        assert res["error"] is None, res
        outbox = api.get("/api/outbox").json()
        assert len(outbox) == 1, outbox
        assert outbox[0]["subject"] == "MCP 测试邮件", outbox
        assert outbox[0]["action_id"] == res["action_id"], outbox
    finally:
        t.join(timeout=30)


def test_3_crm_export_all_denied_no_side_effect(api):
    """crm_export_all 被策略拒绝，无任何副作用（outbox 为 0）。"""
    res = mcp_server.mcp_call_tool("crm_export_all", {})
    assert res["decision"] == "deny", res
    assert res["status"] == "denied", res
    assert res["error"] and res["error"].startswith("policy_deny"), res
    assert api.get("/api/outbox").json() == []


def test_4_stop_blocks_mcp_call(api):
    """急停后 MCP 调用 → blocked_by_stop，不执行。"""
    api.post("/api/admin/stop", json={"by": "admin"})
    res = mcp_server.mcp_call_tool("crm_read", {"customer_id": 1})
    assert res["status"] == "blocked_by_stop", res
    assert res["result"] is None, res
    events = api.get("/api/audit", params={"task_id": res["task_id"]}).json()
    assert any(e["event"] == "action.blocked_stop" for e in events), events


def test_5_approval_wait_timeout(api, monkeypatch):
    """审批等待超时：返回 approval_timeout 错误，审批单仍为 pending。"""
    monkeypatch.setenv("GUARD_APPROVAL_TIMEOUT", "2")
    started = time.time()
    res = mcp_server.mcp_call_tool("mail_send", dict(MAIL_PARAMS))
    elapsed = time.time() - started
    assert res["error"] == "approval_timeout", res
    assert res["status"] == "needs_approval", res
    assert res["approval_id"], res
    assert elapsed < 15, f"超时等待过长: {elapsed}s"
    # 审批单保持 pending：人工稍后仍可决策
    status = json.loads(mcp_server.mcp_check_status(res["action_id"]))
    assert status["approvals"][0]["status"] == "pending", status


def test_6_audit_chain_for_mcp_origin(api):
    """origin=mcp 的动作在 /api/audit 中有完整事件链。"""
    res = mcp_server.mcp_call_tool("crm_read", {"customer_id": 1})
    assert res["status"] == "executed", res
    events = api.get("/api/audit", params={"task_id": res["task_id"]}).json()
    kinds = [e["event"] for e in events]
    for required in ("task.created", "action.proposed", "action.policy", "action.executed"):
        assert required in kinds, f"缺失审计事件: {required}，实际: {kinds}"
    # 事件 detail 携带 origin=mcp
    proposed = next(e for e in events if e["event"] == "action.proposed")
    assert json.loads(proposed["detail"])["origin"] == "mcp", proposed


def test_7_guard_check_status_roundtrip(api):
    """guard_check_status 返回动作状态/裁决/审批单/结果 JSON。"""
    res = mcp_server.mcp_call_tool("crm_read", {"customer_id": 1})
    info = json.loads(mcp_server.mcp_check_status(res["action_id"]))
    assert info["action_id"] == res["action_id"], info
    assert info["status"] == "executed", info
    assert info["decision"] == "allow", info
    assert info["result"]["id"] == 1, info
    missing = json.loads(mcp_server.mcp_check_status(999999))
    assert missing["error"] == "action_not_found", missing


def test_8_tool_name_mapping(api):
    """MCP snake_case 工具名正确映射到网关点分工具名。"""
    res = mcp_server.mcp_call_tool(
        "crm_update", {"customer_id": 1, "updates": {"notes": "x"}}, timeout=3)
    assert res["tool"] == "crm.update", res  # 网关侧记录的是点分名
    assert res["decision"] == "needs_approval", res
    assert res["error"] == "approval_timeout", res
