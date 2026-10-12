"""真实 LLM Agent 循环（V2-M2）。

安全声明（必读）：
  LLM 永远拿不到执行权：它只产出 tool_calls，所有放行判定都在网关
  （gateway.adjudicate，mode="wait"）；审批只能由控制台人工完成。
  系统提示词里不放任何授权语义。

开发铁律：
  开发与测试全程零真实外部 LLM 调用——Agent 循环只允许打本地 stub
  （scripts/stub_llm_server.py）。LLM_API_KEY 默认为空；代码、日志、
  文档、测试中绝不出现真实 key。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import audit as audit_mod
from . import db, gateway
from .models import Task

# ---- 配置（与 .env.example 一致；真实 key 只由用户在 Mac 验收时填入 .env）----

DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Flash"

SYSTEM_PROMPT = (
    "你是 CRM 客户跟进助手。你只能通过调用工具来行动，不能直接读写任何数据。\n"
    "敏感操作（如发送邮件、修改客户资料）需要人工审批，请耐心等待审批结果返回，"
    "不要重复提交同一个请求。\n"
    "绝不声称已执行任何未经网关放行的操作；一切执行状态以工具返回的结果为准。"
)

# ---- 工具名映射 ----
# 网关内部统一用点分名（crm.read）；但部分 LLM 厂商（如 DeepSeek API）要求
# function name 符合 ^[a-zA-Z0-9_-]+$（不允许点），否则直接 400。
# 因此发给 LLM 的 schema 用下划线名，模型返回 tool_call 后再映射回点分名交网关。
LLM_TOOL_NAME_MAP = {
    "crm.read": "crm_read",
    "crm.update": "crm_update",
    "mail.send": "mail_send",
    "crm.export_all": "crm_export_all",
}
LLM_TOOL_NAME_REVERSE = {v: k for k, v in LLM_TOOL_NAME_MAP.items()}


def llm_tool_name(gateway_name: str) -> str:
    """网关点分名 → LLM 侧合法名（未知名原样返回）。"""
    return LLM_TOOL_NAME_MAP.get(gateway_name, gateway_name)


def gateway_tool_name(llm_name: str) -> str:
    """LLM 侧名字 → 网关点分名（未知名原样返回，兼容旧 stub 的点分名）。"""
    return LLM_TOOL_NAME_REVERSE.get(llm_name, llm_name)


def _make_client(base_url: str, api_key: str):
    """建 OpenAI 客户端。base_url 为本机回环地址时绕过环境代理变量
    （trust_env=False），保证测试只打 127.0.0.1 的 stub、不受代理干扰；
    真实远端地址保持默认行为（尊重系统代理设置）。"""
    from urllib.parse import urlparse

    from openai import OpenAI

    host = (urlparse(base_url).hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        import httpx

        http_client = httpx.Client(trust_env=False, timeout=60.0)
        return OpenAI(base_url=base_url, api_key=api_key, http_client=http_client)
    return OpenAI(base_url=base_url, api_key=api_key)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def llm_configured() -> bool:
    """LLM_API_KEY 非空即视为已配置。"""
    return bool(os.environ.get("LLM_API_KEY", "").strip())


def llm_status() -> Dict[str, Any]:
    """返回 LLM 配置状态。绝不返回 key。"""
    return {
        "configured": llm_configured(),
        "base_url": os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL),
        "model": os.environ.get("LLM_MODEL", DEFAULT_MODEL),
    }


def build_tools() -> List[Dict[str, Any]]:
    """OpenAI function tools schema（中文 description），与网关工具一一对应。"""
    return [
        {
            "type": "function",
            "function": {
                "name": llm_tool_name("crm.read"),
                "description": "读取指定客户的资料（只读操作，低风险，网关直接放行）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "integer", "description": "客户 ID"},
                    },
                    "required": ["customer_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": llm_tool_name("crm.update"),
                "description": "修改客户资料字段（敏感操作，需要人工审批）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "integer", "description": "客户 ID"},
                        "updates": {
                            "type": "object",
                            "description": "要修改的字段（name/company/email/phone/notes）",
                        },
                    },
                    "required": ["customer_id", "updates"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": llm_tool_name("mail.send"),
                "description": "向客户发送邮件（敏感操作，需要人工审批；批量发送会被标记为高风险）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "integer", "description": "收件客户 ID（与 to 二选一）"},
                        "to": {"type": "string", "description": "收件邮箱（与 customer_id 二选一）"},
                        "subject": {"type": "string", "description": "邮件主题"},
                        "body": {"type": "string", "description": "邮件正文"},
                        "batch": {"type": "boolean", "description": "是否为批量发送"},
                    },
                    "required": ["subject", "body"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": llm_tool_name("crm.export_all"),
                "description": "导出全部客户资料（高危操作，网关策略默认拒绝）。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
    ]


def _set_task_status(task_id: int, status: str) -> None:
    """用全新 session 更新任务状态并 commit。"""
    session = db.SessionLocal()
    try:
        task = session.get(Task, task_id)
        if task is not None:
            task.status = status
        session.commit()
    finally:
        session.close()


def _audit_agent_event(task_id: int, event: str, detail: Dict[str, Any]) -> None:
    """用全新 session 写一条 agent 审计事件并 commit（前端 SSE 可实时看到）。"""
    session = db.SessionLocal()
    try:
        audit_mod.append_event(
            session, task_id=task_id, event=event, actor="llm-agent", detail=detail
        )
        session.commit()
    finally:
        session.close()


def _assistant_dict(msg) -> Dict[str, Any]:
    """把 OpenAI 返回的 assistant message 转成可继续发送的 dict。"""
    out: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
            for tc in msg.tool_calls
        ]
    return out


def run_llm_task(task_id: int, goal: str, *, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, model: Optional[str] = None,
                 max_steps: int = 12) -> Dict[str, Any]:
    """真实 LLM Agent 循环（同步函数，由调用方放到后台线程执行）。

    循环：chat.completions.create(tools) → tool_calls →
    每个 call 经网关 propose + adjudicate(mode="wait")（全新 session）→
    网关返回（含 decision/error/result）作为 tool message 回填 →
    继续，直到 finish_reason == "stop" 或达到 max_steps。

    参数缺省时读环境变量 LLM_BASE_URL / LLM_MODEL / LLM_API_KEY。
    开发期只能打本地 stub（base_url 指向 127.0.0.1 的桩服务）。
    """
    # openai 包在 _make_client 内延迟导入：缺包时 /api/llm/status 仍可用
    base_url = base_url or os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    if api_key is None:
        api_key = os.environ.get("LLM_API_KEY", "")
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)

    started_at = _utcnow()
    if not api_key:
        _audit_agent_event(task_id, "agent.error", {"error": "llm_not_configured", "at": started_at})
        _set_task_status(task_id, "failed")
        return {"task_id": task_id, "status": "failed", "steps": 0, "error": "llm_not_configured"}

    client = _make_client(base_url, api_key)
    tools = build_tools()
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": goal},
    ]

    steps = 0
    final_text = ""
    error: Optional[str] = None
    try:
        _set_task_status(task_id, "in_progress")
        for step in range(1, max_steps + 1):
            resp = client.chat.completions.create(model=model, messages=messages, tools=tools)
            choice = resp.choices[0]
            msg = choice.message
            finish_reason = choice.finish_reason
            calls = list(msg.tool_calls or [])
            steps = step

            # 每次 LLM 决策记审计（推理步骤摘要，不dump 工具返回全文）
            _audit_agent_event(task_id, "agent.step", {
                "step": step,
                "finish_reason": finish_reason,
                "tool_calls": [
                    {"id": tc.id, "tool": gateway_tool_name(tc.function.name),
                     "params": (tc.function.arguments or "{}")[:500]}
                    for tc in calls
                ],
                "text": (msg.content or "")[:200],
            })

            messages.append(_assistant_dict(msg))

            if calls:
                for tc in calls:
                    tool_name = gateway_tool_name(tc.function.name)
                    try:
                        params = json.loads(tc.function.arguments or "{}")
                    except (json.JSONDecodeError, TypeError):
                        params = {}
                    if not isinstance(params, dict):
                        params = {}
                    # 每个 tool_call 走网关：全新 session → propose → commit →
                    # adjudicate(mode="wait") 阻塞等人工审批 → commit
                    session = db.SessionLocal()
                    try:
                        if session.get(Task, task_id) is None:
                            res: Dict[str, Any] = {
                                "tool": tool_name, "error": "task_not_found", "status": "failed",
                            }
                        else:
                            action = gateway.propose_action(
                                session, task_id=task_id, tool=tool_name,
                                params=params, origin="llm", actor="llm-agent",
                            )
                            session.commit()
                            res = gateway.adjudicate(session, action, mode="wait")
                            session.commit()
                    finally:
                        session.close()
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(res, ensure_ascii=False),
                    })
            else:
                # finish_reason == "stop"：LLM 给出终答，结束循环
                final_text = msg.content or ""
                break
    except Exception as exc:  # API 错误、网络错误等：记审计，任务置 failed
        error = f"{type(exc).__name__}: {exc}"
        _audit_agent_event(task_id, "agent.error", {"error": error[:1000], "at": _utcnow()})

    status = "failed" if error else "completed"
    _set_task_status(task_id, status)
    out: Dict[str, Any] = {"task_id": task_id, "status": status, "steps": steps,
                           "final_text": final_text[:500]}
    if error:
        out["error"] = error[:1000]
    return out
