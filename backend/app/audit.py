"""审计事件写入 + 哈希链。

链式规则：hash = sha256(prev_hash | ts | event | detail)
detail 按 canonical JSON 序列化，保证 verify() 可重算。
对外口径为"可检测篡改"，不宣称防篡改。
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.exc import IntegrityError

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
    """追加一条审计事件并维护哈希链。调用方负责 commit。

    并发写入用乐观并发控制：prev_hash 有唯一约束（uq_audit_prev_hash），
    两个并发写入读到同一个 last 时只有一个能插入成功；失败者在 savepoint 内
    回滚后重读 last 再试（最多 6 次，指数退避 + 抖动，避免重试风暴下饿死）。
    不引入进程锁——进程锁曾与 SQLite 写锁形成锁序死锁
    （execute 路径：DB 写→审计锁；append 路径：审计锁→DB 写）。
    """
    for attempt in range(6):
        in_tx = session.in_transaction()
        sp = session.begin_nested() if in_tx else None
        try:
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
            if sp is not None:
                sp.commit()  # 只释放 savepoint；外层提交仍由调用方负责
            return ev
        except IntegrityError as exc:
            if sp is not None:
                sp.rollback()
            else:
                session.rollback()
            # 只有"我们的"唯一约束冲突才重试：SQLite 报错形如
            # "UNIQUE constraint failed: audit_events.prev_hash"。
            # 其他完整性错误直接抛出；第 6 次（attempt==5）不再重试。
            # 指数退避 + 抖动：高争用下立即重试会反复撞车导致饿死。
            if "audit_events.prev_hash" not in str(exc.orig) or attempt == 5:
                raise
            time.sleep(min(0.05 * (2 ** attempt), 0.5) + random.uniform(0, 0.01))
            continue
    raise AssertionError("unreachable")  # pragma: no cover


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
