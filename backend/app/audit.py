"""审计事件写入 + 哈希链。

链式规则：hash = sha256(prev_hash | ts | event | detail)
detail 按 canonical JSON 序列化，保证 verify() 可重算。
对外口径为"可检测篡改"，不宣称防篡改。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict

from .models import AuditEvent


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _serialize(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    return json.dumps(detail, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def chain_hash(prev_hash: str, ts: str, event: str, detail: str) -> str:
    return hashlib.sha256(f"{prev_hash}|{ts}|{event}|{detail}".encode("utf-8")).hexdigest()


def append_event(session, *, task_id=None, action_id=None, event: str,
                 actor: str = "", detail: Any = "") -> AuditEvent:
    """追加一条审计事件并维护哈希链。调用方负责 commit。"""
    last = session.query(AuditEvent).order_by(AuditEvent.id.desc()).first()
    prev = last.hash if last else "GENESIS"
    ts = utcnow()
    detail_s = _serialize(detail)
    ev = AuditEvent(
        ts=ts,
        task_id=task_id,
        action_id=action_id,
        event=event,
        actor=actor,
        detail=detail_s,
        prev_hash=prev,
        hash=chain_hash(prev, ts, event, detail_s),
    )
    session.add(ev)
    session.flush()
    return ev


def verify(session) -> Dict[str, Any]:
    """重算整条哈希链。返回 {"ok": bool, "checked": N}。"""
    events = session.query(AuditEvent).order_by(AuditEvent.id.asc()).all()
    prev = "GENESIS"
    for ev in events:
        if ev.prev_hash != prev:
            return {"ok": False, "checked": len(events)}
        if ev.hash != chain_hash(ev.prev_hash, ev.ts, ev.event, ev.detail):
            return {"ok": False, "checked": len(events)}
        prev = ev.hash
    return {"ok": True, "checked": len(events)}
