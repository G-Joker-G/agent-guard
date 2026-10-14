"""单一网关：所有受保护工具调用的唯一入口。

V2 重构：Web REST / MCP / LLM Agent 循环全部经由本模块 adjudicate()，
保证外部 Agent 无法绕过"策略 → 审批 → 执行器"路径。

安全语义（与 V1 一致，测试锁定）：
  - 审批绑定 scope_hash = sha256(tool + canonical_json(params))，一次一用，30 分钟 TTL
  - 急停：blocked_by_stop 终态；仅显式 resume 恢复；每次执行前复查
  - 审计哈希链只宣称"可检测篡改"
  - 所有状态变迁写审计事件

三种裁决模式：
  mode="advance"  Web 网关推进（V1 _advance_task 语义）：allow 失败记 failed；
                  needs_approval 只标记+建审批单，不执行
  mode="execute"  单动作执行（V1 /execute 语义）：直接调执行器，无有效审批则 409
  mode="wait"     MCP / LLM 调用：建审批单后阻塞等待人工决策（可配置超时）
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError

from . import audit as audit_mod
from . import db, executor, policy
from .models import Action, Approval, SystemState, Task

TERMINAL_STATUSES = {"executed", "failed", "denied", "rejected", "blocked_by_stop"}
APPROVAL_TTL = timedelta(minutes=30)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_stopped(session) -> bool:
    row = session.get(SystemState, "emergency_stop")
    return row is not None and row.value == "1"


def _approval_timeout() -> int:
    try:
        return int(os.environ.get("GUARD_APPROVAL_TIMEOUT", "300"))
    except ValueError:
        return 300


def _result(action: Action, **extra) -> Dict[str, Any]:
    out = {
        "action_id": action.id,
        "task_id": action.task_id,
        "tool": action.tool,
        "params": json.loads(action.params or "{}"),
        "decision": action.decision,
        "decision_reason": action.decision_reason,
        "risk": action.risk,
        "status": action.status,
        "result": json.loads(action.result) if action.result else None,
        "error": None,
        "approval_id": None,
    }
    out.update(extra)
    return out


def _log(session, task_id, action_id, event, actor="", detail=""):
    audit_mod.append_event(
        session, task_id=task_id, action_id=action_id, event=event, actor=actor, detail=detail
    )


def propose_action(session, *, task_id: int, tool: str, params: Dict[str, Any],
                   origin: str = "web", actor: str = "agent") -> Action:
    """提议一个结构化动作（只建 proposed 记录，不裁决）。调用方负责 commit。"""
    params = params or {}
    seq = session.query(Action).filter(Action.task_id == task_id).count()
    stopped = _is_stopped(session)
    action = Action(
        task_id=task_id,
        seq=seq,
        tool=tool,
        params=policy.canonical_json(params),
        status="blocked_by_stop" if stopped else "proposed",
        request_hash=policy.request_hash(tool, params),
        created_at=_utcnow(),
        origin=origin,
    )
    if stopped:
        action.decision = "blocked_by_stop"
        action.decision_reason = "急停生效中，新动作被阻止"
    session.add(action)
    session.flush()
    _log(session, task_id, action.id,
         "action.blocked_stop" if stopped else "action.proposed",
         "gateway" if stopped else actor,
         {"tool": tool, "params": params, "origin": origin})
    return action


def ensure_pending_approval(session, action: Action) -> Approval:
    """为 needs_approval 的 action 确保有一张 pending 审批单（幂等）。调用方负责 commit。

    并发下两个调用可能同时通过"无 pending"检查：部分唯一索引
    uq_approval_pending_per_action 会拒绝第二个 INSERT，此时回滚本函数未提交的
    写入并重查，返回已存在的那张（幂等语义不变）。
    """
    existing = (
        session.query(Approval)
        .filter(Approval.action_id == action.id, Approval.status == "pending")
        .first()
    )
    if existing:
        return existing
    params = json.loads(action.params or "{}")
    ap = Approval(
        action_id=action.id,
        scope_hash=policy.request_hash(action.tool, params),
        status="pending",
        created_at=_utcnow(),
    )
    session.add(ap)
    try:
        session.flush()
    except IntegrityError:
        # 并发插入冲突：只回滚本函数的写入（调用方此前的提交不受影响），重查返回
        session.rollback()
        existing = (
            session.query(Approval)
            .filter(Approval.action_id == action.id, Approval.status == "pending")
            .first()
        )
        if existing is not None:
            return existing
        raise
    _log(session, action.task_id, action.id, "approval.created", "gateway",
         {"tool": action.tool, "risk": action.risk, "reason": action.decision_reason,
          "origin": getattr(action, "origin", "web")})
    return ap


def _run_executor(session, action: Action, *, fail_mode: str) -> Dict[str, Any]:
    """调执行器。fail_mode="failed"（advance 语义：失败记终态）或 "keep"（execute 语义：状态不变）。"""
    ok, result, err = executor.execute(session, action)
    if ok:
        action.status = "executed"
        action.result = json.dumps(result, ensure_ascii=False)
        _log(session, action.task_id, action.id, "action.executed", "gateway",
             {"tool": action.tool, "result": result})
        return _result(action, result=result)
    if err == "emergency_stop":
        # 状态保持不变（恢复后可继续），仅审计被阻止的尝试
        _log(session, action.task_id, action.id, "action.blocked_stop", "gateway",
             {"tool": action.tool})
        return _result(action, error="emergency_stop")
    if fail_mode == "failed":
        action.status = "failed"
        action.result = json.dumps({"error": err}, ensure_ascii=False)
        _log(session, action.task_id, action.id, "action.failed", "gateway",
             {"tool": action.tool, "error": err})
    else:
        _log(session, action.task_id, action.id, "action.execute_rejected", "gateway",
             {"tool": action.tool, "error": err})
    return _result(action, error=err)


def _wait_for_decision(approval_id: int, timeout: int) -> str:
    """阻塞轮询审批单决策。返回 approved | rejected | stopped | timeout。

    用全新 session 轮询，避免调用方 session 的 identity map 缓存看不到其他请求提交的决策。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = db.SessionLocal()
        try:
            ap = s.get(Approval, approval_id)
            status = ap.status if ap is not None else None
            stopped = _is_stopped(s)
        finally:
            s.close()
        if stopped:
            return "stopped"
        if status == "approved":
            return "approved"
        if status == "rejected":
            return "rejected"
        if status is None:
            return "timeout"  # 审批单消失（如被重置）视为超时
        time.sleep(1)
    return "timeout"


def adjudicate(session, action: Action, *, mode: str = "execute",
               approval_timeout: Optional[int] = None) -> Dict[str, Any]:
    """单动作裁决。调用方负责 commit（wait 模式内部会在等待前 commit）。

    返回 _result() 结构化 dict；error 非空表示未执行及原因。
    """
    if action.status in TERMINAL_STATUSES:
        return _result(action, idempotent=True)

    # 急停复查（每次执行前）
    if _is_stopped(session):
        if mode == "advance" and action.status == "proposed":
            action.status = "blocked_by_stop"
            action.decision = "blocked_by_stop"
            action.decision_reason = "急停生效中，新动作被阻止"
            _log(session, action.task_id, action.id, "action.blocked_stop", "gateway",
                 {"tool": action.tool})
            return _result(action)
        _log(session, action.task_id, action.id, "action.blocked_stop", "gateway",
             {"tool": action.tool})
        return _result(action, error="emergency_stop")

    # 策略评估（不信任调用方，每次重评）
    params = json.loads(action.params or "{}")
    decision, reason, risk = policy.evaluate(action.tool, params)
    action.decision = decision
    action.decision_reason = reason
    action.risk = risk
    _log(session, action.task_id, action.id, "action.policy", "gateway",
         {"tool": action.tool, "decision": decision, "reason": reason, "risk": risk,
          "origin": getattr(action, "origin", "web")})

    if decision == "allow":
        return _run_executor(session, action, fail_mode="failed" if mode == "advance" else "keep")

    if decision == "deny":
        action.status = "denied"
        _log(session, action.task_id, action.id, "action.denied", "gateway",
             {"tool": action.tool, "reason": reason})
        return _result(action, error=f"policy_deny: {reason}")

    # needs_approval
    if mode == "advance":
        action.status = "needs_approval"
        ensure_pending_approval(session, action)
        return _result(action)

    if mode == "execute":
        # V1 /execute 语义：直接调执行器，由审批绑定复查决定 409 或执行
        return _run_executor(session, action, fail_mode="keep")

    # mode == "wait"：MCP / LLM 调用，阻塞等待人工审批
    action.status = "needs_approval"
    approval = ensure_pending_approval(session, action)
    session.commit()  # 审批单必须先落库，控制台与轮询才能看到
    timeout = approval_timeout if approval_timeout is not None else _approval_timeout()
    verdict = _wait_for_decision(approval.id, timeout)

    if verdict == "approved":
        session.refresh(action)
        if _is_stopped(session):
            _log(session, action.task_id, action.id, "action.blocked_stop", "gateway",
                 {"tool": action.tool})
            return _result(action, error="emergency_stop", approval_id=approval.id)
        res = _run_executor(session, action, fail_mode="keep")
        res["approval_id"] = approval.id  # 关联"哪张审批单放行了这次执行"
        return res

    if verdict == "rejected":
        session.refresh(action)  # decide 接口已置 rejected
        return _result(action, error="approval_rejected", approval_id=approval.id)

    if verdict == "stopped":
        return _result(action, error="emergency_stop", approval_id=approval.id)

    # timeout：审批单保持 pending（人工稍后仍可决策），只审计 + 返回超时错误
    _log(session, action.task_id, action.id, "approval.timeout", "gateway",
         {"approval_id": approval.id, "timeout": timeout})
    session.commit()
    return _result(action, error="approval_timeout", approval_id=approval.id)


def run_protected_tool(*, tool: str, params: Dict[str, Any], origin: str,
                       task_title: Optional[str] = None, actor: str = "agent",
                       approval_timeout: Optional[int] = None) -> Dict[str, Any]:
    """一站式受保护工具调用（供 MCP / LLM 调用方使用）：建任务 → 提议 → 裁决。

    内部管理自己的 session；wait 模式会阻塞直到人工决策/超时/急停。
    返回 adjudicate 结果 dict（附加 task_id）。
    """
    session = db.SessionLocal()
    try:
        task = Task(
            title=task_title or f"{origin} 调用: {tool}",
            scenario=origin,
            status="created",
            created_at=_utcnow(),
        )
        session.add(task)
        session.flush()
        _log(session, task.id, None, "task.created", actor,
             {"title": task.title, "scenario": origin, "origin": origin})
        action = propose_action(session, task_id=task.id, tool=tool, params=params,
                                origin=origin, actor=actor)
        session.commit()
        res = adjudicate(session, action, mode="wait", approval_timeout=approval_timeout)
        session.commit()
        res["task_id"] = task.id
        # MCP/LLM 创建的任务此前永远停在 created：按动作终态同步任务状态，
        # 与 REST 路径的看板语义一致
        session.refresh(action)
        if action.status == "executed":
            task.status = "completed"
        elif action.status in TERMINAL_STATUSES:
            task.status = "failed"
        session.commit()
        return res
    finally:
        session.close()
