"""Agent Guard 后端网关（FastAPI）。

安全语义：
  POST /api/tasks/{id}/advance   对 proposed action 调 policy.evaluate；
                                 allow→直接执行；needs_approval→建审批单并停下；
                                 deny→标记并继续；幂等。
  POST /api/actions/{id}/execute 复查急停→复查策略/审批→执行器→审计；幂等。
  急停期间新 action 直接 blocked_by_stop；resume 只能走 POST /api/admin/resume。
  所有状态变迁写审计事件。
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import update as sa_update

from . import audit as audit_mod
from . import db, demo_agent, executor, gateway, policy
from .models import Action, Approval, AuditEvent, Customer, Outbox, SystemState, Task
from .schemas import (
    ActionOut,
    AdminIn,
    ApprovalCreate,
    ApprovalOut,
    ApprovalWithActionOut,
    AuditEventOut,
    CustomerOut,
    DecideIn,
    HealthOut,
    OutboxOut,
    StopResultOut,
    StopStatusOut,
    TaskCreate,
    TaskDetailOut,
    TaskOut,
    VerifyOut,
)

TERMINAL_STATUSES = gateway.TERMINAL_STATUSES
APPROVAL_TTL = gateway.APPROVAL_TTL


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_stopped(session) -> bool:
    row = session.get(SystemState, "emergency_stop")
    return row is not None and row.value == "1"


def _action_out(a: Action) -> ActionOut:
    return ActionOut(
        id=a.id,
        task_id=a.task_id,
        seq=a.seq,
        tool=a.tool,
        params=json.loads(a.params or "{}"),
        status=a.status,
        request_hash=a.request_hash,
        decision=a.decision,
        decision_reason=a.decision_reason,
        risk=a.risk,
        result=json.loads(a.result) if a.result else None,
        origin=getattr(a, "origin", "web") or "web",
        created_at=a.created_at,
    )


def _approval_out(ap: Approval, action: Optional[Action] = None) -> ApprovalWithActionOut:
    return ApprovalWithActionOut(
        id=ap.id,
        action_id=ap.action_id,
        scope_hash=ap.scope_hash,
        status=ap.status,
        approver=ap.approver,
        note=ap.note,
        expires_at=ap.expires_at,
        used=ap.used,
        decided_at=ap.decided_at,
        created_at=ap.created_at,
        action=_action_out(action) if action else None,
    )


def _log(session, task_id, action_id, event, actor="", detail=""):
    audit_mod.append_event(
        session, task_id=task_id, action_id=action_id, event=event, actor=actor, detail=detail
    )


def _require_admin_token(request: Request) -> None:
    """管理口令校验（可选开关）。

    只有当环境变量 GUARD_ADMIN_TOKEN 非空时才强制：管理接口
    （/api/admin/stop|resume|reset）与审批决议（/api/approvals/{id}/decide）
    要求请求头 X-Admin-Token 匹配，否则 401。
    未设置时保持现状——本机演示零负担（口径见 README 已知限制）。
    """
    expected = os.environ.get("GUARD_ADMIN_TOKEN", "").strip()
    if not expected:
        return
    if request.headers.get("X-Admin-Token", "") != expected:
        raise HTTPException(status_code=401, detail="admin_token_required")


def _recompute_task_status(session, task: Task) -> None:
    statuses = {a.status for a in session.query(Action).filter(Action.task_id == task.id)}
    if not statuses:
        return
    pending_approvals = (
        session.query(Approval)
        .join(Action, Approval.action_id == Action.id)
        .filter(Action.task_id == task.id, Approval.status == "pending")
        .count()
    )
    if statuses & {"needs_approval"} or pending_approvals:
        task.status = "pending_approval"
    elif statuses & {"proposed", "approved"}:
        task.status = "in_progress"
    elif statuses <= TERMINAL_STATUSES:
        # blocked_by_stop 是终态但不是"完成"：急停冻结的任务显示"已急停"，
        # 避免看板上把被冻结的任务误标为已完成
        task.status = "stopped" if "blocked_by_stop" in statuses else "completed"


def _advance_task(session, task: Task) -> None:
    """网关推进：处理 task 下所有 proposed action。幂等。
    approved 的 action 由 POST /api/actions/{id}/execute 显式执行。
    统一走 gateway.adjudicate(mode="advance")，与 MCP/LLM 同一裁决路径。"""
    actions = (
        session.query(Action)
        .filter(Action.task_id == task.id, Action.status == "proposed")
        .order_by(Action.seq.asc())
        .all()
    )
    for action in actions:
        res = gateway.adjudicate(session, action, mode="advance")
        if res["decision"] == "needs_approval":
            break  # 遇到待审批即停下，等待人工
    _recompute_task_status(session, task)
    session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Agent Guard", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MCP 服务器挂载（/mcp/sse + /mcp/messages/）：工具处理器走同一网关裁决路径。
# mcp_server.py 由 V2-M1 交付；缺失时静默跳过，不影响 REST 功能。
try:
    from .mcp_server import build_mcp_app
    app.mount("/mcp", build_mcp_app())
except ImportError:
    pass

# 真实 LLM Agent 路由（/api/tasks/{id}/run-llm 等）：llm_routes.py 由 V2-M2 交付。
try:
    from .llm_routes import router as llm_router
    app.include_router(llm_router)
except ImportError:
    pass


# ---------- 基础 ----------

@app.get("/api/health", response_model=HealthOut)
def health():
    return HealthOut()


@app.get("/api/admin/status", response_model=StopStatusOut)
def admin_status(session=Depends(db.get_session)):
    return StopStatusOut(emergency_stop=_is_stopped(session))


# ---------- 任务 ----------

@app.post("/api/tasks", response_model=TaskOut)
def create_task(body: TaskCreate, session=Depends(db.get_session)):
    task = Task(title=body.title, scenario=body.scenario, status="created", created_at=_utcnow())
    session.add(task)
    session.flush()
    _log(session, task.id, None, "task.created", "user",
         {"title": body.title, "scenario": body.scenario})
    session.commit()
    return TaskOut(id=task.id, title=task.title, scenario=task.scenario,
                   status=task.status, created_at=task.created_at)


@app.get("/api/tasks", response_model=List[TaskOut])
def list_tasks(session=Depends(db.get_session)):
    tasks = session.query(Task).order_by(Task.id.desc()).all()
    return [TaskOut(id=t.id, title=t.title, scenario=t.scenario,
                    status=t.status, created_at=t.created_at) for t in tasks]


@app.get("/api/tasks/{task_id}", response_model=TaskDetailOut)
def get_task(task_id: int, session=Depends(db.get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "task not found")
    actions = (
        session.query(Action).filter(Action.task_id == task.id).order_by(Action.seq.asc()).all()
    )
    return TaskDetailOut(
        id=task.id, title=task.title, scenario=task.scenario,
        status=task.status, created_at=task.created_at,
        actions=[_action_out(a) for a in actions],
    )


@app.post("/api/tasks/{task_id}/plan", response_model=List[ActionOut])
def plan_task(task_id: int, session=Depends(db.get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "task not found")
    existing = (
        session.query(Action).filter(Action.task_id == task.id).order_by(Action.seq.asc()).all()
    )
    if existing:
        return [_action_out(a) for a in existing]  # 幂等：已有规划直接返回

    stopped = _is_stopped(session)
    created: List[Action] = []
    for req in demo_agent.plan(task.scenario):
        created.append(gateway.propose_action(
            session, task_id=task.id, tool=req["tool"], params=req.get("params") or {},
            origin="demo", actor="agent"))
    task.status = "planned"
    session.commit()
    return [_action_out(a) for a in created]


@app.post("/api/tasks/{task_id}/advance", response_model=TaskDetailOut)
def advance_task(task_id: int, session=Depends(db.get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "task not found")
    _advance_task(session, task)
    actions = (
        session.query(Action).filter(Action.task_id == task.id).order_by(Action.seq.asc()).all()
    )
    return TaskDetailOut(
        id=task.id, title=task.title, scenario=task.scenario,
        status=task.status, created_at=task.created_at,
        actions=[_action_out(a) for a in actions],
    )


# ---------- 动作 ----------

@app.post("/api/actions/{action_id}/execute", response_model=ActionOut)
def execute_action(action_id: int, session=Depends(db.get_session)):
    action = session.get(Action, action_id)
    if not action:
        raise HTTPException(404, "action not found")
    # 统一走网关裁决（mode="execute" 保持 V1 语义：直接调执行器，无有效审批则 409）
    res = gateway.adjudicate(session, action, mode="execute")
    session.commit()
    if res.get("idempotent") or res["status"] == "executed":
        return _action_out(action)
    raise HTTPException(status_code=409, detail=res["error"] or res["decision"])


# ---------- 审批 ----------

@app.get("/api/approvals", response_model=List[ApprovalWithActionOut])
def list_approvals(status: Optional[str] = Query(default=None),
                   session=Depends(db.get_session)):
    q = session.query(Approval).order_by(Approval.id.desc())
    if status:
        q = q.filter(Approval.status == status)
    out = []
    for ap in q.all():
        out.append(_approval_out(ap, session.get(Action, ap.action_id)))
    return out


@app.post("/api/approvals", response_model=ApprovalOut)
def create_approval(body: ApprovalCreate, session=Depends(db.get_session)):
    action = session.get(Action, body.action_id)
    if not action:
        raise HTTPException(404, "action not found")
    existing = (
        session.query(Approval)
        .filter(Approval.action_id == action.id, Approval.status == "pending")
        .first()
    )
    if existing:
        return _approval_out(existing)  # 幂等
    if action.status != "needs_approval":
        raise HTTPException(409, "action is not awaiting approval")
    ap = gateway.ensure_pending_approval(session, action)
    session.commit()
    return _approval_out(ap)


@app.post("/api/approvals/{approval_id}/decide", response_model=ApprovalOut)
def decide_approval(approval_id: int, body: DecideIn, request: Request,
                    session=Depends(db.get_session)):
    _require_admin_token(request)
    # 并发双批防护：先原子认领 pending 审批单（UPDATE ... WHERE status='pending'）。
    # 两个同时的批准请求只有一个能认领成功，另一个得 409；否则 last-write-wins
    # 会产生多条 approval.approved 审计事件并可能覆盖 approver/note。
    claimed = session.execute(
        sa_update(Approval)
        .where(Approval.id == approval_id, Approval.status == "pending")
        .values(status="__claimed__")
    ).rowcount
    session.flush()
    if not claimed:
        ap = session.get(Approval, approval_id)
        if ap is None:
            raise HTTPException(404, "approval not found")
        raise HTTPException(409, "approval already decided")
    ap = session.get(Approval, approval_id)
    action = session.get(Action, ap.action_id)
    if not action or action.status != "needs_approval":
        # 回滚认领：动作已不在待审批态，本次决议无效
        ap.status = "pending"
        session.commit()
        raise HTTPException(409, "action is not awaiting approval")

    if body.decision == "approve":
        ap.status = "approved"
        ap.approver = body.approver
        ap.note = body.note
        # 审批绑定沿用创建时的 scope_hash（ensure_pending_approval 按当时 params 算好）。
        # 批准时不再重算：重算会把"创建后、批准前被篡改过的 params"重新合法化，
        # 架空网关的 scope 校验。篡改过的 params 会在执行器复查时被拒绝
        # （approval_scope_mismatch）。
        ap.expires_at = (datetime.now(timezone.utc) + APPROVAL_TTL).isoformat(timespec="seconds")
        ap.decided_at = _utcnow()
        action.status = "approved"
        _log(session, action.task_id, action.id, "approval.approved", body.approver,
             {"scope_hash": ap.scope_hash, "expires_at": ap.expires_at})
    else:
        ap.status = "rejected"
        ap.approver = body.approver
        ap.note = body.note
        ap.decided_at = _utcnow()
        action.status = "rejected"
        _log(session, action.task_id, action.id, "approval.rejected", body.approver,
             {"note": body.note})
    session.commit()
    return _approval_out(ap)


# ---------- 急停 ----------

@app.post("/api/admin/stop", response_model=StopResultOut)
def admin_stop(body: AdminIn, request: Request, session=Depends(db.get_session)):
    _require_admin_token(request)
    row = session.get(SystemState, "emergency_stop")
    if row is None:
        row = SystemState(key="emergency_stop", value="0")
        session.add(row)
    row.value = "1"
    affected = (
        session.query(Action)
        .filter(Action.status.in_(["proposed", "allowed", "approved", "needs_approval"]))
        .count()
    )
    _log(session, None, None, "stop.engaged", body.by, {"affected": affected})
    session.commit()
    return StopResultOut(emergency_stop=True, affected=affected)


@app.post("/api/admin/resume", response_model=StopStatusOut)
def admin_resume(body: AdminIn, request: Request, session=Depends(db.get_session)):
    _require_admin_token(request)
    row = session.get(SystemState, "emergency_stop")
    if row is None:
        row = SystemState(key="emergency_stop", value="0")
        session.add(row)
    row.value = "0"
    _log(session, None, None, "stop.released", body.by, {})
    session.commit()
    return StopStatusOut(emergency_stop=False)


@app.post("/api/admin/reset")
def admin_reset(request: Request, session=Depends(db.get_session)):
    _require_admin_token(request)
    # 子表先删（外键顺序）
    session.query(AuditEvent).delete()
    session.query(Approval).delete()
    session.query(Action).delete()
    session.query(Task).delete()
    session.query(Outbox).delete()
    session.query(Customer).delete()
    row = session.get(SystemState, "emergency_stop")
    if row is None:
        session.add(SystemState(key="emergency_stop", value="0"))
    else:
        row.value = "0"
    session.flush()
    from .seed import seed_customers
    seed_customers(session)
    session.commit()
    _log(session, None, None, "data.reset", "admin", {})
    session.commit()
    return {"ok": True}


# ---------- 模拟数据 ----------

@app.get("/api/customers", response_model=List[CustomerOut])
def list_customers(session=Depends(db.get_session)):
    customers = session.query(Customer).order_by(Customer.id.asc()).all()
    return [CustomerOut(id=c.id, name=c.name, company=c.company, email=c.email,
                        phone=c.phone, notes=c.notes) for c in customers]


@app.get("/api/outbox", response_model=List[OutboxOut])
def list_outbox(session=Depends(db.get_session)):
    rows = session.query(Outbox).order_by(Outbox.id.desc()).all()
    return [OutboxOut(id=r.id, to_email=r.to_email, subject=r.subject, body=r.body,
                      task_id=r.task_id, action_id=r.action_id, created_at=r.created_at)
            for r in rows]


# ---------- 审计 ----------

@app.get("/api/audit", response_model=List[AuditEventOut])
def list_audit(task_id: Optional[int] = Query(default=None),
               limit: int = Query(default=200, le=1000),
               session=Depends(db.get_session)):
    q = session.query(AuditEvent).order_by(AuditEvent.id.desc())
    if task_id is not None:
        q = q.filter(AuditEvent.task_id == task_id)
    events = q.limit(limit).all()
    return [AuditEventOut(id=e.id, ts=e.ts, task_id=e.task_id, action_id=e.action_id,
                          event=e.event, actor=e.actor, detail=e.detail,
                          prev_hash=e.prev_hash, hash=e.hash) for e in events]


@app.get("/api/audit/verify", response_model=VerifyOut)
def verify_audit(session=Depends(db.get_session)):
    result = audit_mod.verify(session)
    return VerifyOut(ok=result["ok"], checked=result["checked"])


# ---------- 实时事件（SSE，事件源 = 审计表，唯一真相源） ----------

def _safe_detail(s: str):
    try:
        return json.loads(s)
    except Exception:
        return s


@app.get("/api/events")
async def events(since: int = Query(default=0)):
    """Server-Sent Events：增量推送审计事件（含 agent.step 推理步骤）。
    前端用 EventSource 订阅，实现实时运行视图。"""
    async def gen():
        last = since
        hb = 0
        while True:
            session = db.SessionLocal()
            try:
                rows = (
                    session.query(AuditEvent)
                    .filter(AuditEvent.id > last)
                    .order_by(AuditEvent.id.asc())
                    .limit(200)
                    .all()
                )
                payload = [
                    {
                        "id": e.id, "ts": e.ts, "task_id": e.task_id,
                        "action_id": e.action_id, "event": e.event,
                        "actor": e.actor, "detail": _safe_detail(e.detail or ""),
                    }
                    for e in rows
                ]
                if rows:
                    last = rows[-1].id
            finally:
                session.close()
            for p in payload:
                yield f"data: {json.dumps(p, ensure_ascii=False)}\n\n"
            hb += 1
            if hb % 30 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")
