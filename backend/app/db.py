"""SQLite 连接、建表、seed 入口。

数据库文件：backend/data/agent_guard.db（gitignore，不提交）。
测试可通过环境变量 AGENT_GUARD_DB_PATH 指向独立测试库。
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base, SystemState

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "agent_guard.db"

DB_PATH = os.environ.get("AGENT_GUARD_DB_PATH", str(DEFAULT_DB_PATH))

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    """FastAPI 依赖：按请求提供会话。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """建表 + 种子客户 + 急停标志初始化（幂等）。"""
    from .models import Customer  # noqa: F401  (建表需要模型注册)
    from .seed import seed_customers
    from sqlalchemy import inspect, text

    Base.metadata.create_all(engine)
    # 轻量迁移：老库的 actions 表补 origin 列
    with engine.begin() as conn:
        cols = [c["name"] for c in inspect(engine).get_columns("actions")]
        if "origin" not in cols:
            conn.execute(text("ALTER TABLE actions ADD COLUMN origin VARCHAR(16) DEFAULT 'web'"))
    session = SessionLocal()
    try:
        seed_customers(session)  # 内部幂等：已有客户则跳过
        if session.get(SystemState, "emergency_stop") is None:
            session.add(SystemState(key="emergency_stop", value="0"))
        session.commit()
    finally:
        session.close()
