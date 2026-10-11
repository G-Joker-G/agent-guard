"""Agent Guard 后端测试（对应 PLAN.md 测试清单 9 条）。

1. 未定义 tool 默认拒绝；拒绝后 execute 不执行
2. crm.update 未审批时 execute 被拒绝（无审批=不执行）
3. 审批与请求绑定：篡改 params 后原审批失效
4. 审批一次一用：重复 execute 不重复执行
5. 急停：stop 后新动作 blocked_by_stop；已 approved 未执行的 execute 被阻止
6. 恢复必须显式：无 auto-resume
7. 审计完整性：路径 A 关键事件齐全且哈希链 verify 通过
8. 架构隔离：demo_agent.py 源码不含 executor/sqlite3/import db
9. E2E：三条路径（A/B/C）跑通，断言 DB 真实变更
"""

import json
from pathlib import Path

from app import db
from app.models import Action, Customer, Outbox


# ---------- 辅助 ----------

def create_task(api, scenario="followup", title="测试任务"):
    r = api.post("/api/tasks", json={"title": title, "scenario": scenario})
    assert r.status_code == 200, r.text
    return r.json()


def plan(api, task_id):
    r = api.post(f"/api/tasks/{task_id}/plan")
    assert r.status_code == 200, r.text
    return r.json()


def advance(api, task_id):
    r = api.post(f"/api/tasks/{task_id}/advance")
    assert r.status_code == 200, r.text
    return r.json()


def action_by_tool(actions, tool, idx=0):
    matched = [a for a in actions if a["tool"] == tool]
    return matched[idx]


def approve_action(api, action):
    """为 needs_approval 的 action 走完“创建审批单→批准”全流程。"""
    r = api.post("/api/approvals", json={"action_id": action["id"]})
    assert r.status_code == 200, r.text
    ap = r.json()
    r = api.post(f"/api/approvals/{ap['id']}/decide",
                 json={"decision": "approve", "approver": "admin"})
    assert r.status_code == 200, r.text
    return r.json()


def customer_notes(customer_id):
    s = db.SessionLocal()
    try:
        return s.get(Customer, customer_id).notes
    finally:
        s.close()


def outbox_count():
    s = db.SessionLocal()
    try:
        return s.query(Outbox).count()
    finally:
        s.close()


def set_action_tool(action_id, tool):
    """白盒：直接改库，把 action 的 tool 换成未定义值。"""
    s = db.SessionLocal()
    try:
        a = s.get(Action, action_id)
        a.tool = tool
        s.commit()
    finally:
        s.close()


def set_action_params(action_id, params):
    s = db.SessionLocal()
    try:
        a = s.get(Action, action_id)
        a.params = json.dumps(params, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"))
        s.commit()
    finally:
        s.close()


# ---------- 1. 未定义 tool 默认拒绝 ----------

def test_1_undefined_tool_denied_and_not_executed(api):
    task = create_task(api)
    actions = plan(api, task["id"])
    set_action_tool(actions[0]["id"], "shell.exec")  # 未定义 tool

    detail = advance(api, task["id"])
    a = action_by_tool(detail["actions"], "shell.exec")
    assert a["status"] == "denied"
    assert a["decision"] == "deny"

    # 拒绝后 execute 不执行（终态幂等返回）
    r = api.post(f"/api/actions/{a['id']}/execute")
    assert r.status_code == 200
    assert r.json()["status"] == "denied"
    assert outbox_count() == 0


# ---------- 2. crm.update 未审批时 execute 被拒绝 ----------

def test_2_update_without_approval_rejected(api):
    task = create_task(api, scenario="batch", title="批量任务")
    plan(api, task["id"])
    detail = advance(api, task["id"])  # crm.read 执行；mail.send 待审批停下
    update_action = action_by_tool(detail["actions"], "crm.update")
    assert update_action["status"] == "proposed"

    before = customer_notes(2)
    r = api.post(f"/api/actions/{update_action['id']}/execute")
    assert r.status_code == 409, r.text
    assert "approval" in r.json()["detail"]
    assert customer_notes(2) == before  # 无审批=不执行，DB 未变更


# ---------- 3. 篡改 params 后原审批失效 ----------

def test_3_tampered_params_invalidate_approval(api):
    task = create_task(api, scenario="batch", title="批量任务")
    plan(api, task["id"])
    detail = advance(api, task["id"])
    mail_action = action_by_tool(detail["actions"], "mail.send")
    approve_action(api, mail_action)

    # 批准后篡改参数（模拟攻击者改请求内容）
    set_action_params(mail_action["id"], {
        "customer_id": 2, "batch": True,
        "subject": "被篡改的主题", "body": "恶意内容",
    })

    r = api.post(f"/api/actions/{mail_action['id']}/execute")
    assert r.status_code == 409, r.text
    assert "scope_mismatch" in r.json()["detail"]
    assert outbox_count() == 0  # 未执行，无发件记录


# ---------- 4. 审批一次一用 ----------

def test_4_approval_single_use(api):
    task = create_task(api, scenario="batch", title="批量任务")
    plan(api, task["id"])
    detail = advance(api, task["id"])
    mail_action = action_by_tool(detail["actions"], "mail.send")
    approve_action(api, mail_action)

    r1 = api.post(f"/api/actions/{mail_action['id']}/execute")
    assert r1.status_code == 200
    assert r1.json()["status"] == "executed"
    assert outbox_count() == 1

    r2 = api.post(f"/api/actions/{mail_action['id']}/execute")
    assert r2.status_code == 200
    assert r2.json()["status"] == "executed"
    assert outbox_count() == 1  # 重复 execute 不重复执行


# ---------- 5. 急停 ----------

def test_5_emergency_stop(api):
    task = create_task(api, scenario="batch", title="批量任务")
    plan(api, task["id"])
    detail = advance(api, task["id"])
    mail_action = action_by_tool(detail["actions"], "mail.send")
    approve_action(api, mail_action)  # 已 approved，未执行

    r = api.post("/api/admin/stop", json={"by": "admin"})
    assert r.status_code == 200
    assert r.json()["emergency_stop"] is True
    assert r.json()["affected"] >= 1
    assert api.get("/api/admin/status").json()["emergency_stop"] is True

    # 5a. 急停后新动作 blocked_by_stop
    task2 = create_task(api, scenario="followup", title="急停后新任务")
    plan(api, task2["id"])
    detail2 = advance(api, task2["id"])
    for a in detail2["actions"]:
        assert a["status"] == "blocked_by_stop", a

    # 5b. 已 approved 未执行的 execute 被阻止（状态保持 approved，恢复后可继续）
    r = api.post(f"/api/actions/{mail_action['id']}/execute")
    assert r.status_code == 409
    assert r.json()["detail"] == "emergency_stop"
    assert outbox_count() == 0
    r = api.get(f"/api/tasks/{task['id']}")
    m = action_by_tool(r.json()["actions"], "mail.send")
    assert m["status"] == "approved"

    # 恢复后可继续执行
    api.post("/api/admin/resume", json={"by": "admin"})
    r = api.post(f"/api/actions/{mail_action['id']}/execute")
    assert r.json()["status"] == "executed"
    assert outbox_count() == 1

    events = api.get("/api/audit", params={"task_id": task["id"]}).json()
    assert any(e["event"] == "action.blocked_stop" for e in events)


# ---------- 6. 恢复必须显式（无 auto-resume） ----------

def test_6_no_auto_resume(api):
    api.post("/api/admin/stop", json={"by": "admin"})

    task = create_task(api, scenario="followup", title="急停期间任务")
    plan(api, task["id"])
    detail = advance(api, task["id"])
    assert all(a["status"] == "blocked_by_stop" for a in detail["actions"])
    assert outbox_count() == 0

    # 没有自动恢复：急停标志仍在
    assert api.get("/api/admin/status").json()["emergency_stop"] is True

    # 只有显式 resume 能恢复
    r = api.post("/api/admin/resume", json={"by": "admin"})
    assert r.json()["emergency_stop"] is False
    assert api.get("/api/admin/status").json()["emergency_stop"] is False


# ---------- 7. 审计完整性 ----------

def test_7_audit_integrity_path_a(api):
    task = create_task(api, scenario="followup", title="路径A")
    plan(api, task["id"])
    detail = advance(api, task["id"])
    mail_action = action_by_tool(detail["actions"], "mail.send")
    approve_action(api, mail_action)
    r = api.post(f"/api/actions/{mail_action['id']}/execute")
    assert r.json()["status"] == "executed"

    events = api.get("/api/audit", params={"task_id": task["id"]}).json()
    names = {e["event"] for e in events}
    for required in ("task.created", "action.proposed", "action.policy",
                     "approval.created", "approval.approved", "action.executed"):
        assert required in names, f"missing audit event: {required}"

    v = api.get("/api/audit/verify").json()
    assert v["ok"] is True and v["checked"] > 0


# ---------- 8. 架构隔离 ----------

def test_8_demo_agent_isolation():
    src = Path(__file__).resolve().parent.parent / "app" / "demo_agent.py"
    text = src.read_text(encoding="utf-8")
    assert "executor" not in text, "demo_agent.py 不得引用执行器"
    assert "sqlite3" not in text, "demo_agent.py 不得直连数据库"
    assert "import db" not in text, "demo_agent.py 不得 import db"


# ---------- 9. E2E 三条路径 ----------

def test_9_e2e_path_a_followup(api):
    task = create_task(api, scenario="followup", title="E2E-A 跟进")
    actions = plan(api, task["id"])
    assert [a["tool"] for a in actions] == ["crm.read", "mail.send"]

    detail = advance(api, task["id"])
    assert action_by_tool(detail["actions"], "crm.read")["status"] == "executed"
    mail_action = action_by_tool(detail["actions"], "mail.send")
    assert mail_action["status"] == "needs_approval"
    assert detail["status"] == "pending_approval"

    approve_action(api, mail_action)
    r = api.post(f"/api/actions/{mail_action['id']}/execute")
    assert r.json()["status"] == "executed"

    # DB 真实变更：发件箱多 1 条
    assert outbox_count() == 1
    s = db.SessionLocal()
    try:
        row = s.query(Outbox).first()
        assert row.to_email == "zhangwei@huanan-trade.example.com"
        assert "白皮书" in row.subject
    finally:
        s.close()


def test_9_e2e_path_b_export_attack(api):
    task = create_task(api, scenario="export_attack", title="E2E-B 注入攻击")
    actions = plan(api, task["id"])
    assert [a["tool"] for a in actions] == ["crm.read", "crm.export_all"]

    # 攻击客户 notes 确实内嵌中文恶意指令（种子数据）
    r = api.get("/api/customers")
    cust6 = [c for c in r.json() if c["id"] == 6][0]
    assert "系统指令" in cust6["notes"] and "导出" in cust6["notes"]

    detail = advance(api, task["id"])
    assert action_by_tool(detail["actions"], "crm.read")["status"] == "executed"
    export_action = action_by_tool(detail["actions"], "crm.export_all")
    assert export_action["status"] == "denied"
    assert export_action["decision"] == "deny"

    events = api.get("/api/audit", params={"task_id": task["id"]}).json()
    assert any(e["event"] == "action.denied" for e in events)


def test_9_e2e_path_c_batch_with_stop(api):
    task = create_task(api, scenario="batch", title="E2E-C 批量+急停")
    actions = plan(api, task["id"])
    assert [a["tool"] for a in actions] == ["crm.read", "mail.send", "mail.send",
                                            "mail.send", "crm.update"]

    detail = advance(api, task["id"])
    assert action_by_tool(detail["actions"], "crm.read")["status"] == "executed"
    mails = [a for a in detail["actions"] if a["tool"] == "mail.send"]
    # 网关遇到第一个 needs_approval 即停下：mail[0] 待审批，其余仍为 proposed
    assert mails[0]["status"] == "needs_approval"
    assert all(m["status"] == "proposed" for m in mails[1:])
    # batch=true 高风险标注
    assert mails[0]["risk"] == "high"

    # 急停：第一封已批准但尚未执行 → 被阻止（状态保持 approved）
    approve_action(api, mails[0])
    api.post("/api/admin/stop", json={"by": "admin"})
    r = api.post(f"/api/actions/{mails[0]['id']}/execute")
    assert r.status_code == 409
    assert r.json()["detail"] == "emergency_stop"
    assert outbox_count() == 0

    # 显式恢复后继续：三封邮件全部真实写入发件箱
    api.post("/api/admin/resume", json={"by": "admin"})
    r = api.post(f"/api/actions/{mails[0]['id']}/execute")
    assert r.json()["status"] == "executed", r.text
    # 逐个推进剩余邮件：每次 advance 只处理到下一个 needs_approval
    remaining = [a for a in api.get(f"/api/tasks/{task['id']}").json()["actions"]
                 if a["tool"] == "mail.send" and a["status"] != "executed"]
    for m in remaining:
        if m["status"] == "proposed":
            detail = advance(api, task["id"])
            m = [a for a in detail["actions"]
                 if a["tool"] == "mail.send" and a["status"] == "needs_approval"][0]
        approve_action(api, m)
        r = api.post(f"/api/actions/{m['id']}/execute")
        assert r.json()["status"] == "executed", r.text
    assert outbox_count() == 3

    # 继续推进：crm.update 走审批后真实写库
    detail = advance(api, task["id"])
    upd = action_by_tool(detail["actions"], "crm.update")
    assert upd["status"] == "needs_approval"
    approve_action(api, upd)
    r = api.post(f"/api/actions/{upd['id']}/execute")
    assert r.json()["status"] == "executed"
    assert "行业简报" in customer_notes(2)

    v = api.get("/api/audit/verify").json()
    assert v["ok"] is True
