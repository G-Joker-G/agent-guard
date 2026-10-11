"""外置权限策略引擎：纯函数，无副作用。

按 PLAN.md 规则表：
  crm.read       -> allow
  crm.update     -> needs_approval
  mail.send      -> needs_approval（batch=true 时高风险标注）
  crm.export_all -> deny
  未定义 tool    -> deny（默认拒绝）
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Tuple


def canonical_json(params: Dict[str, Any]) -> str:
    """确定性序列化：排序键 + 紧凑分隔符，用于哈希绑定。"""
    return json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(tool: str, params: Dict[str, Any]) -> str:
    """动作请求的绑定哈希：sha256(tool + canonical_json(params))。"""
    return hashlib.sha256(f"{tool}|{canonical_json(params)}".encode("utf-8")).hexdigest()


def evaluate(tool: str, params: Dict[str, Any]) -> Tuple[str, str, str]:
    """评估动作请求。返回 (decision, reason, risk)。

    decision: "allow" | "needs_approval" | "deny"
    risk:     "low" | "medium" | "high" | "critical"
    """
    params = params or {}

    if tool == "crm.read":
        return ("allow", "只读客户信息，低风险", "low")

    if tool == "crm.update":
        return ("needs_approval", "修改客户资料，需人工确认变更内容", "medium")

    if tool == "mail.send":
        if params.get("batch") is True:
            return ("needs_approval", "对外发送，内容需审核；批量发送标记为高风险", "high")
        return ("needs_approval", "对外发送，内容需审核", "medium")

    if tool == "crm.export_all":
        return ("deny", "批量导出全部客户资料，禁止", "critical")

    return ("deny", f"未知动作 {tool}，默认拒绝", "critical")
