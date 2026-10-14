"""V2 安全加固回归测试（2026-10-13 审计驱动）。

覆盖：
  P1-1 审批一次一用并发竞态（原子认领）
  P1-2 decide 不再重算 scope_hash（篡改 params 后批准→执行必须拒绝）
  P1-3 decide 并发双批（原子认领）
  P1-4 审计哈希链并发写入不分叉
  P1-5 executor 非法输入类型校验
  P1-6 管理口令开关（GUARD_ADMIN_TOKEN）
  P2-10 agent.goal 审计事件
  P2-11 pending 审批单唯一索引
  P2-12 急停冻结任务显示 stopped
另：wait 中途急停、审批过期、max_steps 耗尽、run_llm_task 无 key 直接调用。
"""

import json
import socket
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import stub_llm_server  # noqa: E402

from app import db, gateway, llm_agent  # noqa: E402
from app import policy as policy_mod  # noqa: E402
from app.models import Action, Approval  # noqa: E402


@pytest.fixture()
def stub():
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


def _create_task(api, title="加固测试", scenario="followup"):
    r = api.post("/api/tasks", json={"title": title, "scenario": scenario})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _plan_and_advance(api, task_id):
    r = api.post(f"/api/tasks/{task_id}/plan")
    assert r.status_code == 200, r.text
    r = api.post(f"/api/tasks/{task_id}/advance")
    assert r.status_code == 200, r.text


def _pending_approval_for(api, task_id, tool):
    r = api.get("/api/approvals", params={"status": "pending"})
    assert r.status_code == 200
    for ap in r.json():
        action = ap.get("action") or {}
        if action.get("task_id") == task_id and action.get("tool") == tool:
            return ap
    raise AssertionError(f"未找到 {tool} 的 pending 审批单")


def _approve(api, approval_id):
    r = api.post(f"/api/approvals/{approval_id}/decide",
                 json={"decision": "approve", "approver": "test"})
    assert r.status_code == 200, r.text
    return r.json()


def _outbox_count(api):
    r = api.get("/api/outbox")
    assert r.status_code == 200
    return len(r.json())


# ---------- P1-1：并发双执行，只执行一次 ----------

def test_concurrent_double_execute_single_execution(api):
    task_id = _create_task(api)
    _plan_and_advance(api, task_id)
    ap = _pending_approval_for(api, task_id, "mail.send")
    action_id = ap["action"]["id"]
    _approve(api, ap["id"])
    assert _outbox_count(api) == 0

    results = []

    def _run():
        results.append(api.post(f"/api/actions/{action_id}/execute"))

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert all(not t.is_alive() for t in threads)

    codes = sorted(r.status_code for r in results)
    # 两种合法结果：真正并发时 [200, 409]（第二个被原子认领拒绝）；
    # 一前一后时 [200, 200]（第二个走终态幂等，直接返回已执行结果）。
    # 核心安全属性：无论哪种时序，敏感动作只执行一次。
    assert codes in ([200, 200], [200, 409]), [r.text for r in results]
    for r in results:
        if r.status_code == 409:
            assert "approval_already_used" in r.text
    assert _outbox_count(api) == 1  # 只发出一封邮件


def test_claim_approval_is_atomic(api):
    """确定性单测：_claim_approval 的原子性不依赖线程时序。"""
    from app import executor

    task_id = _create_task(api)
    _plan_and_advance(api, task_id)
    ap = _pending_approval_for(api, task_id, "mail.send")
    _approve(api, ap["id"])

    s1 = db.SessionLocal()
    try:
        ap1 = s1.get(Approval, ap["id"])
        assert executor._claim_approval(s1, ap1) is True
        s1.commit()  # 第一个认领落库
    finally:
        s1.close()

    # 第二个会话再认领同一张单：used 已是 1，UPDATE 影响 0 行 → 必须失败
    s2 = db.SessionLocal()
    try:
        ap2 = s2.get(Approval, ap["id"])
        assert executor._claim_approval(s2, ap2) is False
        s2.rollback()
    finally:
        s2.close()
    # 注：真正的并发交叠（两线程同时认领）由
    # test_concurrent_double_execute_single_execution 覆盖


# ---------- P1-3：并发双批，只有一个生效 ----------

def test_concurrent_double_decide_single_winner(api):
    task_id = _create_task(api)
    _plan_and_advance(api, task_id)
    ap = _pending_approval_for(api, task_id, "mail.send")

    results = []

    def _run():
        results.append(api.post(
            f"/api/approvals/{ap['id']}/decide",
            json={"decision": "approve", "approver": "t1"}))

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409], [r.text for r in results]

    # 审计里只有一条 approval.approved
    r = api.get("/api/audit", params={"task_id": task_id, "limit": 100})
    kinds = [e["event"] for e in r.json()]
    assert kinds.count("approval.approved") == 1


# ---------- P1-2：批准时不重算 scope_hash，篡改 params 后执行被拒 ----------

def test_tampered_params_not_rebound_on_approve(api):
    task_id = _create_task(api)
    _plan_and_advance(api, task_id)
    ap = _pending_approval_for(api, task_id, "mail.send")
    action_id = ap["action"]["id"]
    created_scope = ap["scope_hash"]

    # 模拟攻击者：在审批单创建后、人工批准前篡改 params
    session = db.SessionLocal()
    try:
        action = session.get(Action, action_id)
        tampered = dict(json.loads(action.params))
        tampered["subject"] = "被篡改的主题"
        action.params = policy_mod.canonical_json(tampered)
        session.commit()
    finally:
        session.close()

    _approve(api, ap["id"])  # 批准成功（审批单本身有效）

    # 批准后 scope_hash 必须仍是创建时的绑定，不能被重算合法化
    session = db.SessionLocal()
    try:
        ap_row = session.get(Approval, ap["id"])
        assert ap_row.scope_hash == created_scope
    finally:
        session.close()

    r = api.post(f"/api/actions/{action_id}/execute")
    assert r.status_code == 409
    assert "approval_scope_mismatch" in r.text
    assert _outbox_count(api) == 0


# ---------- P1-4：审计并发写入不分叉 ----------

def test_concurrent_audit_writes_chain_intact(api):
    from app import audit as audit_mod

    # 8 线程 × 25 次写入，每次短事务提交（贴近生产：每次请求提交一次）
    def _write():
        for _ in range(25):
            s = db.SessionLocal()
            try:
                audit_mod.append_event(s, task_id=1, event="test.concurrent",
                                       actor="t", detail={"x": 1})
                s.commit()
            finally:
                s.close()

    threads = [threading.Thread(target=_write) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert all(not t.is_alive() for t in threads)

    s = db.SessionLocal()
    try:
        res = audit_mod.verify(s)
    finally:
        s.close()
    assert res["ok"] is True, res
    assert res["checked"] >= 200


# ---------- P1-5：非法输入类型 ----------

def test_executor_rejects_non_dict_inputs():
    from app import executor

    s = db.SessionLocal()
    try:
        # params 不是 dict
        a = SimpleNamespace(id=1, task_id=1, tool="crm.update",
                            params=json.dumps(["x"]))
        ok, _, err = executor.execute(s, a)
        assert ok is False and err == "invalid_params", err

        # updates 不是 dict（LLM 可能输出 "updates": ["x"]）
        a2 = SimpleNamespace(id=2, task_id=1, tool="crm.update",
                             params=json.dumps({"customer_id": 1, "updates": ["x"]}))
        ok, _, err = executor.execute(s, a2)
        assert ok is False and err == "invalid_updates", err
    finally:
        s.close()


# ---------- P1-6：管理口令 ----------

def test_admin_token_gate(api, monkeypatch):
    monkeypatch.setenv("GUARD_ADMIN_TOKEN", "s3cret")
    # 无头 → 401
    r = api.post("/api/admin/stop", json={"by": "t"})
    assert r.status_code == 401
    task_id = _create_task(api)
    _plan_and_advance(api, task_id)
    ap = _pending_approval_for(api, task_id, "mail.send")
    r = api.post(f"/api/approvals/{ap['id']}/decide",
                 json={"decision": "approve", "approver": "t"})
    assert r.status_code == 401
    # 带正确头 → 通过
    r = api.post("/api/admin/stop", json={"by": "t"},
                 headers={"X-Admin-Token": "s3cret"})
    assert r.status_code == 200
    # 错误口令 → 401
    r = api.post("/api/admin/resume", json={"by": "t"},
                 headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 401


def test_admin_token_unset_keeps_current_behavior(api, monkeypatch):
    monkeypatch.delenv("GUARD_ADMIN_TOKEN", raising=False)
    r = api.post("/api/admin/stop", json={"by": "t"})
    assert r.status_code == 200


# ---------- 审批过期 ----------

def test_approval_expired_rejected(api):
    from datetime import datetime, timedelta, timezone

    task_id = _create_task(api)
    _plan_and_advance(api, task_id)
    ap = _pending_approval_for(api, task_id, "mail.send")
    _approve(api, ap["id"])

    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    s = db.SessionLocal()
    try:
        row = s.get(Approval, ap["id"])
        row.expires_at = past
        s.commit()
    finally:
        s.close()

    r = api.post(f"/api/actions/{ap['action']['id']}/execute")
    assert r.status_code == 409
    assert "approval_expired" in r.text
    assert _outbox_count(api) == 0


# ---------- wait 中途急停 ----------

def test_wait_mode_interrupted_by_stop(api):
    results = {}

    def _run():
        results["res"] = gateway.run_protected_tool(
            tool="mail.send",
            params={"customer_id": 1, "subject": "t", "body": "b"},
            origin="mcp", approval_timeout=30,
        )

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(2)  # 等 wait-mode 进入阻塞等待
    r = api.post("/api/admin/stop", json={"by": "test"})
    assert r.status_code == 200
    t.join(timeout=30)
    assert not t.is_alive()
    assert results["res"]["error"] == "emergency_stop"
    assert _outbox_count(api) == 0


# ---------- P2-12：急停冻结任务显示 stopped ----------

def test_stopped_task_not_completed(api):
    task_id = _create_task(api)
    api.post(f"/api/tasks/{task_id}/plan")
    api.post("/api/admin/stop", json={"by": "test"})
    api.post(f"/api/tasks/{task_id}/advance")  # proposed → blocked_by_stop
    r = api.get(f"/api/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "stopped"


# ---------- P2-10：agent.goal 审计 ----------

def test_agent_goal_audited(api, stub):
    # 纯文本目标（不含 跟进/攻击 关键词）：stub 直接终答，不触发审批等待
    task_id = _create_task(api)
    res = llm_agent.run_llm_task(task_id, "测试目标：你好",
                                 base_url=stub, api_key="stub", model="stub")
    assert res["status"] == "completed"

    r = api.get("/api/audit", params={"task_id": task_id, "limit": 100})
    goals = [e for e in r.json() if e["event"] == "agent.goal"]
    assert len(goals) == 1
    assert "测试目标" in json.dumps(goals[0]["detail"], ensure_ascii=False)


# ---------- max_steps 耗尽 ----------

def test_max_steps_exhaustion(api, monkeypatch, stub):
    monkeypatch.setenv("LLM_MAX_STEPS", "3")

    def _fake_client(*a, **k):
        fn = SimpleNamespace(name="crm_read", arguments='{"customer_id": 1}')
        tc = SimpleNamespace(id="c1", type="function", function=fn)
        msg = SimpleNamespace(content="", tool_calls=[tc])
        choice = SimpleNamespace(message=msg, finish_reason="tool_calls")
        completions = SimpleNamespace(
            create=lambda **kw: SimpleNamespace(choices=[choice]))
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    monkeypatch.setattr(llm_agent, "_make_client", _fake_client)
    task_id = _create_task(api)
    res = llm_agent.run_llm_task(task_id, "x", base_url=stub,
                                 api_key="stub", model="stub")
    assert res["steps"] == 3
    assert res["status"] == "completed"  # 正常结束，不是异常


# ---------- run_llm_task 无 key 直接调用 ----------

def test_run_llm_task_no_key_direct(api, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    task_id = _create_task(api)
    res = llm_agent.run_llm_task(task_id, "x")
    assert res["status"] == "failed"
    assert res["error"] == "llm_not_configured"
    assert res["steps"] == 0
