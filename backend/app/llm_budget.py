"""真实 LLM 成本熔断（预算守卫）。

用户明确要求：在没有限额机制之前，不给真实 API Key。
本模块在 Agent 循环之外、之内加三道保险：

  1. LLM_KILL_SWITCH=1 → /run-llm 直接 409，不启动任何线程（紧急停止开关）；
  2. LLM_DAILY_MAX_CALLS → 每天**真实** API 调用上限，超限后拒绝启动、
     循环中每一步调用前复查（超限即终止，任务 failed 并记审计）；
  3. LLM_MAX_STEPS → 单轮最大步数（每步 = 1 次 API 调用），限制单次运行的上限。

"真实调用"的定义：base_url 主机非回环地址（127.0.0.1 / localhost / ::1）。
开发期本地 stub（scripts/stub_llm_server.py）不计费、不计入额度——
但同样受 LLM_MAX_STEPS 约束，防止无限循环。

额度持久化在 SQLite system_state（key = llm_calls_YYYY-MM-DD），
后端重启不丢失；并发读写用模块级 threading.Lock 保护。

注意：本熔断是"费用保险丝"，不是精确计费——按调用次数限额，
不按 token/金额换算。金额级限额请在模型服务商控制台设置。
"""

from __future__ import annotations

import os
import threading
from datetime import date
from typing import Tuple
from urllib.parse import urlparse

from . import db
from .models import SystemState

_LOCK = threading.Lock()

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _int_env(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
        return v if v > 0 else default
    except (ValueError, TypeError):
        return default


def max_steps() -> int:
    """单轮最大步数（默认 12，可配 LLM_MAX_STEPS）。"""
    return _int_env("LLM_MAX_STEPS", 12)


def daily_limit() -> int:
    """每天真实 API 调用上限（默认 50，可配 LLM_DAILY_MAX_CALLS）。"""
    return _int_env("LLM_DAILY_MAX_CALLS", 50)


def kill_switch_on() -> bool:
    """紧急停止开关（LLM_KILL_SWITCH=1/true/yes/on）。"""
    return os.environ.get("LLM_KILL_SWITCH", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def is_real_call(base_url: str) -> bool:
    """回环地址 = 本地 stub（不计费）；其他 = 真实调用。"""
    host = (urlparse(base_url or "").hostname or "").lower()
    return host not in LOOPBACK_HOSTS


def _today_key() -> str:
    return f"llm_calls_{date.today().isoformat()}"


def daily_used() -> int:
    """今天已用的真实调用次数。"""
    key = _today_key()
    with _LOCK:
        session = db.SessionLocal()
        try:
            row = session.get(SystemState, key)
            return int(row.value) if row is not None and row.value.isdigit() else 0
        finally:
            session.close()


def budget_ok() -> Tuple[bool, int, int]:
    """是否还有额度。返回 (ok, 已用, 上限)。"""
    used = daily_used()
    limit = daily_limit()
    return used < limit, used, limit


def record_call() -> int:
    """真实调用计数 +1。返回当日累计。调用方负责只对真实调用计数。"""
    key = _today_key()
    with _LOCK:
        session = db.SessionLocal()
        try:
            row = session.get(SystemState, key)
            if row is None:
                row = SystemState(key=key, value="0")
                session.add(row)
            used = int(row.value) if row.value.isdigit() else 0
            row.value = str(used + 1)
            session.commit()
            return used + 1
        finally:
            session.close()
