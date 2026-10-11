"""Agent Guard MCP 服务器（V2-M1）。

安全注释（必读）：
  - 本文件所有工具处理器**没有任何直达执行器的路径**。每个 MCP 工具调用都会
    经过 `gateway.run_protected_tool()`，与 Web REST / LLM Agent 走完全相同的
    "策略评估 → 审批 → 执行器"裁决路径，外部 Agent 无法绕过网关。
  - 处理器是 async def，内部用 `asyncio.to_thread` 调用同步网关，保证
    Starlette 事件循环不被阻塞。
  - 审批等待默认 300 秒（环境变量 GUARD_APPROVAL_TIMEOUT 可配）；超时只返回
    错误，审批单保持 pending，客户端可用 `guard_check_status` 继续查询。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer

from . import db, gateway
from .models import Action, Approval

# MCP 工具名（snake_case）→ 网关工具名（点分风格）的映射。
_TOOL_MAP = {
    "crm_read": "crm.read",
    "crm_update": "crm.update",
    "mail_send": "mail.send",
    "crm_export_all": "crm.export_all",
}


def mcp_call_tool(tool_name: str, params: Dict[str, Any],
                  timeout: Optional[int] = None) -> Dict[str, Any]:
    """MCP 工具调用的同步核心逻辑（供测试直接调用，不起 MCP 协议）。

    经过 gateway.run_protected_tool 的完整"建任务 → 提议 → 裁决"路径，
    与 Web / LLM 调用方共享同一网关语义。mode="wait"：审批路径阻塞等待
    人工决策（timeout 为 None 时读 GUARD_APPROVAL_TIMEOUT，默认 300 秒）。
    """
    gateway_tool = _TOOL_MAP.get(tool_name, tool_name)
    return gateway.run_protected_tool(
        tool=gateway_tool,
        params=params or {},
        origin="mcp",
        task_title=f"MCP 调用: {tool_name}",
        actor="mcp-client",
        approval_timeout=timeout,
    )


def mcp_check_status(action_id: int) -> str:
    """查询动作状态/裁决/审批单/结果，返回 JSON 字符串（供客户端超时后轮询）。"""
    session = db.SessionLocal()
    try:
        action = session.get(Action, action_id)
        if action is None:
            return json.dumps({"error": "action_not_found", "action_id": action_id},
                              ensure_ascii=False)
        approvals = (
            session.query(Approval)
            .filter(Approval.action_id == action.id)
            .order_by(Approval.id)
            .all()
        )
        return json.dumps(
            {
                "action_id": action.id,
                "task_id": action.task_id,
                "tool": action.tool,
                "params": json.loads(action.params or "{}"),
                "decision": action.decision,
                "decision_reason": action.decision_reason,
                "risk": action.risk,
                "status": action.status,
                "result": json.loads(action.result) if action.result else None,
                "approvals": [
                    {
                        "id": ap.id,
                        "status": ap.status,
                        "approver": ap.approver,
                        "created_at": ap.created_at,
                        "decided_at": ap.decided_at,
                    }
                    for ap in approvals
                ],
            },
            ensure_ascii=False,
        )
    finally:
        session.close()


server = MCPServer("agent-guard")


@server.tool()
async def crm_read(customer_id: int) -> str:
    """读取客户信息（只读查询，策略自动放行执行）"""
    result = await asyncio.to_thread(
        mcp_call_tool, "crm_read", {"customer_id": customer_id})
    return json.dumps(result, ensure_ascii=False)


@server.tool()
async def crm_update(customer_id: int, updates: dict) -> str:
    """更新客户字段（写操作，需要人工审批，调用将阻塞等待批准或拒绝）"""
    result = await asyncio.to_thread(
        mcp_call_tool, "crm_update", {"customer_id": customer_id, "updates": updates})
    return json.dumps(result, ensure_ascii=False)


@server.tool()
async def mail_send(customer_id: int | None = None, to: str | None = None,
                    subject: str = "", body: str = "", batch: bool = False) -> str:
    """发送邮件（需要人工审批；batch=true 批量发送会被标注高风险）"""
    result = await asyncio.to_thread(
        mcp_call_tool, "mail_send",
        {"customer_id": customer_id, "to": to, "subject": subject,
         "body": body, "batch": batch})
    return json.dumps(result, ensure_ascii=False)


@server.tool()
async def crm_export_all() -> str:
    """导出全部客户数据（策略拒绝：该工具永远不被允许执行）"""
    result = await asyncio.to_thread(mcp_call_tool, "crm_export_all", {})
    return json.dumps(result, ensure_ascii=False)


@server.tool()
async def guard_check_status(action_id: int) -> str:
    """查询动作的当前状态、策略裁决、审批单与执行结果（供审批超时后轮询）"""
    return mcp_check_status(action_id)


def build_mcp_app():
    """返回挂载用的 Starlette 应用（路由 /sse 与 /messages/）。"""
    return server.sse_app()
