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
    # check_same_thread=False：LLM 循环、wait-mode 等待等多线程共享 engine。
    # timeout=30：多线程并发写入时等待而非立即报 "database is locked"。
    connect_args={"check_same_thread": False, "timeout": 30},
)


# 事务以 BEGIN IMMEDIATE 开始（而非默认的 DEFERRED）：先拿 RESERVED 写锁。
# 关键原因：SQLite 的 SHARED→RESERVED 锁升级不吃 busy 超时（防死锁设计），
# 先 SELECT 再 UPDATE 的并发写会立即报 database is locked（500）而不是干净等待；
# IMMEDIATE 让锁在事务开始时一次拿到位，升级问题消失。
# 实现用 SQLAlchemy 官方 pysqlite 配方：DBAPI 进 autocommit，由 begin 事件
# 发出自己的 BEGIN IMMEDIATE。
from sqlalchemy import event as _sa_event  # noqa: E402


@_sa_event.listens_for(engine, "connect")
def _sqlite_begin_immediate_connect(dbapi_connection, _connection_record):
    dbapi_connection.isolation_level = None  # pysqlite autocommit，接管事务语句


@_sa_event.listens_for(engine, "begin")
def _sqlite_begin_immediate(conn):
    conn.exec_driver_sql("BEGIN IMMEDIATE")
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

    # 新鲜 clone 没有 backend/data/ 目录时，sqlite 会报
    # "unable to open database file"；这里保证父目录存在。
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    # 轻量迁移：老库的 actions 表补 origin 列
    # 注意：inspect 必须用同一个 conn（inspect(conn)），不能 inspect(engine)——
    # 后者会从池里拿第二个连接发 BEGIN IMMEDIATE，而外层事务正持有 RESERVED 锁，
    # 单线程自死锁。
    with engine.begin() as conn:
        cols = [c["name"] for c in inspect(conn).get_columns("actions")]
        if "origin" not in cols:
            conn.execute(text("ALTER TABLE actions ADD COLUMN origin VARCHAR(16) DEFAULT 'web'"))
        # 轻量迁移：老库补 pending 审批单部分唯一索引
        idx = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name='uq_approval_pending_per_action'")
        ).first()
        if idx is None:
            conn.execute(
                text("CREATE UNIQUE INDEX uq_approval_pending_per_action "
                     "ON approvals (action_id) WHERE status = 'pending'")
            )
        # 轻量迁移：老库补审计 prev_hash 唯一索引（哈希链防分叉）
        # 若老库已有分叉链，建索引会失败：跳过（保持旧行为），不阻断启动
        try:
            conn.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_prev_hash "
                     "ON audit_events (prev_hash)")
            )
        except Exception:
            pass
    session = SessionLocal()
    try:
        seed_customers(session)  # 内部幂等：已有客户则跳过
        if session.get(SystemState, "emergency_stop") is None:
            session.add(SystemState(key="emergency_stop", value="0"))
        session.commit()
    finally:
        session.close()
