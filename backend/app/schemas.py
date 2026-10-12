"""Pydantic 请求/响应模型（API 契约 v1）。"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Scenario = Literal["followup", "export_attack", "batch"]


# ---------- 任务 ----------

class TaskCreate(BaseModel):
    title: str
    scenario: Scenario


class TaskOut(BaseModel):
    id: int
    title: str
    scenario: str
    status: str
    created_at: str


class ActionOut(BaseModel):
    id: int
    task_id: int
    seq: int
    tool: str
    params: Dict[str, Any]
    status: str
    request_hash: str
    decision: str
    decision_reason: str
    risk: str
    result: Optional[Dict[str, Any]]
    origin: str = "web"
    created_at: str


class TaskDetailOut(TaskOut):
    actions: List[ActionOut] = []


# ---------- 审批 ----------

class ApprovalCreate(BaseModel):
    action_id: int


class ApprovalOut(BaseModel):
    id: int
    action_id: int
    scope_hash: str
    status: str
    approver: str
    note: str
    expires_at: str
    used: int
    decided_at: str
    created_at: str


class ApprovalWithActionOut(ApprovalOut):
    action: Optional[ActionOut] = None


class DecideIn(BaseModel):
    decision: Literal["approve", "reject"]
    approver: str = "admin"
    note: str = ""


# ---------- 管理 ----------

class AdminIn(BaseModel):
    by: str = "admin"


class HealthOut(BaseModel):
    ok: bool = True
    simulation_mode: bool = True
    version: str = "0.2.0"


class StopStatusOut(BaseModel):
    emergency_stop: bool


class StopResultOut(BaseModel):
    emergency_stop: bool
    affected: int = 0


# ---------- 模拟数据 ----------

class CustomerOut(BaseModel):
    id: int
    name: str
    company: str
    email: str
    phone: str
    notes: str


class OutboxOut(BaseModel):
    id: int
    to_email: str
    subject: str
    body: str
    task_id: Optional[int]
    action_id: Optional[int]
    created_at: str


# ---------- 审计 ----------

class AuditEventOut(BaseModel):
    id: int
    ts: str
    task_id: Optional[int]
    action_id: Optional[int]
    event: str
    actor: str
    detail: str
    prev_hash: str
    hash: str


class VerifyOut(BaseModel):
    ok: bool
    checked: int
