"""SQLAlchemy 数据模型。所有数据均为虚构演示数据，无真实个人信息。"""

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Customer(Base):
    """虚构客户（种子数据，中文姓名/公司，example.com 邮箱）。"""

    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    company = Column(String(128), nullable=False)
    email = Column(String(128), nullable=False)
    phone = Column(String(32), nullable=False)
    notes = Column(Text, nullable=False, default="")


class Task(Base):
    """用户任务。"""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    scenario = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="created")
    created_at = Column(String(32), nullable=False)


class Action(Base):
    """结构化动作请求。status 取值见 PLAN.md 契约。"""

    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    tool = Column(String(64), nullable=False)
    params = Column(Text, nullable=False, default="{}")  # canonical JSON
    status = Column(String(32), nullable=False, default="proposed")
    request_hash = Column(String(64), nullable=False, default="")
    decision = Column(String(32), nullable=False, default="")
    decision_reason = Column(Text, nullable=False, default="")
    risk = Column(String(16), nullable=False, default="")
    result = Column(Text, nullable=True)  # JSON（执行结果）或 None
    origin = Column(String(16), nullable=False, default="web", server_default="web")  # web|demo|mcp|llm
    created_at = Column(String(32), nullable=False)


class Approval(Base):
    """人工审批单：绑定 action + scope_hash，一次一用，有有效期。"""

    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = Column(Integer, ForeignKey("actions.id"), nullable=False, index=True)
    scope_hash = Column(String(64), nullable=False, default="")
    status = Column(String(16), nullable=False, default="pending")  # pending|approved|rejected
    approver = Column(String(64), nullable=False, default="")
    note = Column(Text, nullable=False, default="")
    expires_at = Column(String(32), nullable=False, default="")
    used = Column(Integer, nullable=False, default=0)  # 0/1
    decided_at = Column(String(32), nullable=False, default="")
    created_at = Column(String(32), nullable=False)


class AuditEvent(Base):
    """审计事件：哈希链 hash=sha256(prev_hash|ts|event|detail)。"""

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(String(32), nullable=False)
    task_id = Column(Integer, nullable=True, index=True)
    action_id = Column(Integer, nullable=True, index=True)
    event = Column(String(64), nullable=False)
    actor = Column(String(64), nullable=False, default="")
    detail = Column(Text, nullable=False, default="")
    prev_hash = Column(String(64), nullable=False)
    hash = Column(String(64), nullable=False)


class Outbox(Base):
    """模拟发件箱：mail.send 的真实写入记录（不发送真实邮件）。"""

    __tablename__ = "outbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    to_email = Column(String(128), nullable=False)
    subject = Column(String(256), nullable=False)
    body = Column(Text, nullable=False, default="")
    task_id = Column(Integer, nullable=True)
    action_id = Column(Integer, nullable=True)
    created_at = Column(String(32), nullable=False)


class SystemState(Base):
    """系统状态键值：emergency_stop 等。"""

    __tablename__ = "system_state"

    key = Column(String(64), primary_key=True)
    value = Column(String(64), nullable=False)
