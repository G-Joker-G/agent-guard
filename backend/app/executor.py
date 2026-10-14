"""受控执行器：执行前必须自己复查，绝不信任调用方的"已审批"断言。

复查顺序：
  1. 急停标志（system_state.emergency_stop）
  2. 策略复评（policy.evaluate）：deny 直接拒绝
  3. 审批绑定（needs_approval 时）：审批存在、已批准、未使用、未过期、
     scope_hash == sha256(tool + canonical_json(params))
通过后按 tool 真实执行：
  crm.read       查库返回客户
  crm.update     写库更新客户字段
  mail.send      写 outbox 表（模拟发送，不发真实邮件）
  crm.export_all / 未知 tool  直接拒绝
审批一次一用：执行前原子认领（UPDATE ... WHERE used=0），并发下只认领成功者执行。
输入类型校验：params/updates 非 dict 时返回 invalid_params/invalid_updates，
绝不抛未捕获异常（LLM 输出不可控）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from . import policy
from .models import Approval, Customer, Outbox, SystemState

from sqlalchemy import update as sa_update

# 允许 crm.update 修改的字段白名单
UPDATE_FIELDS = {"name", "company", "email", "phone", "notes"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_stopped(session) -> bool:
    row = session.get(SystemState, "emergency_stop")
    return row is not None and row.value == "1"


def _claim_approval(session, approval: Approval) -> bool:
    """原子认领审批（一次一用）：UPDATE ... WHERE used=0，rowcount 决定成败。

    查与置必须是一条原子语句，否则两个并发 /execute（或 wait-mode 等待线程 +
    REST execute）可同时通过 used=0 检查，各执行一次敏感动作。
    调用方负责 commit。
    """
    rowcount = session.execute(
        sa_update(Approval)
        .where(Approval.id == approval.id, Approval.used == 0)
        .values(used=1)
    ).rowcount
    session.flush()
    return rowcount == 1


def _find_valid_approval(session, action) -> Tuple[Optional[Approval], str]:
    """查找与当前 action 参数绑定的有效审批。返回 (approval, err_code)。"""
    params = json.loads(action.params or "{}")
    expected = policy.request_hash(action.tool, params)
    appr = (
        session.query(Approval)
        .filter(Approval.action_id == action.id, Approval.status == "approved")
        .order_by(Approval.id.desc())
        .first()
    )
    if appr is None:
        return None, "approval_missing"
    if appr.used:
        return None, "approval_already_used"
    if appr.expires_at and appr.expires_at < _utcnow():
        return None, "approval_expired"
    if appr.scope_hash != expected:
        return None, "approval_scope_mismatch"
    return appr, ""


def execute(session, action) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """执行单个动作。返回 (ok, result, reason)。

    reason 为空表示成功；失败时为机器可读的错误码。
    调用方负责 commit。
    """
    params = json.loads(action.params or "{}")

    # 0. 输入类型校验（LLM 输出不可控；非法输入必须返回错误码，不能抛 500）
    # 注意：updates 的校验必须在审批认领之前——非法输入不能消耗一次性的审批。
    if not isinstance(params, dict):
        return False, None, "invalid_params"
    if action.tool == "crm.update":
        updates = params.get("updates")
        if updates is not None and not isinstance(updates, dict):
            return False, None, "invalid_updates"

    # 1. 急停复查
    if _is_stopped(session):
        return False, None, "emergency_stop"

    # 2. 策略复评（不信任调用方）
    decision, p_reason, _risk = policy.evaluate(action.tool, params)
    if decision == "deny":
        return False, None, f"policy_deny: {p_reason}"

    # 3. 审批绑定复查
    approval = None
    if decision == "needs_approval":
        approval, err = _find_valid_approval(session, action)
        if approval is None:
            return False, None, err
        # 审批一次一用：先原子认领再执行（认领失败说明被并发认领，直接拒绝）
        if not _claim_approval(session, approval):
            return False, None, "approval_already_used"

    # 4. 按 tool 真实执行
    if action.tool == "crm.read":
        customer = session.get(Customer, params.get("customer_id"))
        if customer is None:
            return False, None, "customer_not_found"
        result = {
            "id": customer.id,
            "name": customer.name,
            "company": customer.company,
            "email": customer.email,
            "phone": customer.phone,
            "notes": customer.notes,
        }

    elif action.tool == "crm.update":
        customer = session.get(Customer, params.get("customer_id"))
        if customer is None:
            return False, None, "customer_not_found"
        updates = params.get("updates") or {}
        changed = {}
        for k, v in updates.items():
            if k in UPDATE_FIELDS:
                setattr(customer, k, v)
                changed[k] = v
        if not changed:
            return False, None, "no_valid_updates"
        result = {"id": customer.id, "updated": changed}

    elif action.tool == "mail.send":
        to_email = params.get("to")
        if not to_email and params.get("customer_id"):
            customer = session.get(Customer, params.get("customer_id"))
            if customer is None:
                return False, None, "customer_not_found"
            to_email = customer.email
        if not to_email:
            return False, None, "missing_recipient"
        row = Outbox(
            to_email=to_email,
            subject=params.get("subject", ""),
            body=params.get("body", ""),
            task_id=action.task_id,
            action_id=action.id,
            created_at=_utcnow(),
        )
        session.add(row)
        session.flush()
        result = {"outbox_id": row.id, "to": to_email, "subject": row.subject}

    else:
        # crm.export_all 与未知 tool：直接拒绝（策略已 deny，这里是纵深防御）
        return False, None, f"tool_refused: {action.tool}"

    return True, result, ""
