"""真实邮件发送（显式开关，默认关闭）。

设计原则：
  1. 默认关闭：REAL_MAIL_ENABLED != "1" 时，mail.send 行为与之前完全一致
     （只写 outbox 模拟表，不触网）。
  2. 白名单强制：启用后只允许 REAL_MAIL_ALLOWLIST 中的收件地址，
     其他地址一律拒绝（fail-closed）。
  3. 密钥零落盘：SMTP_PASS 只从环境变量读取，不写日志、不进审计、不进返回值。
  4. 异常不抛 500：smtplib 所有异常统一收敛为 (False, err) 返回。
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Dict, List, Optional, Tuple

DEFAULT_SMTP_PORT = 465
SMTP_TIMEOUT = 30


def is_enabled() -> bool:
    """真实发送总开关。"""
    return os.environ.get("REAL_MAIL_ENABLED", "0").strip() == "1"


def get_config() -> Tuple[Optional[Dict], List[str]]:
    """读取 SMTP 配置。返回 (config, missing)。

    config 为 None 表示配置缺失，missing 列出缺失项名称；
    否则 config 含 host/port/user/from/allowlist（allowlist 为小写集合）。
    注意：密码只做"是否提供"检查，绝不返回明文以外的任何形式。
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "")
    from_addr = os.environ.get("SMTP_FROM", "").strip() or user
    raw_port = os.environ.get("SMTP_PORT", "").strip()
    try:
        port = int(raw_port) if raw_port else DEFAULT_SMTP_PORT
    except ValueError:
        port = DEFAULT_SMTP_PORT
    allowlist = {
        a.strip().lower()
        for a in os.environ.get("REAL_MAIL_ALLOWLIST", "").split(",")
        if a.strip()
    }

    missing = []
    if not host:
        missing.append("SMTP_HOST")
    if not user:
        missing.append("SMTP_USER")
    if not password.strip():
        missing.append("SMTP_PASS")
    if not allowlist:
        missing.append("REAL_MAIL_ALLOWLIST")

    if missing:
        return None, missing
    return {
        "host": host,
        "port": port,
        "user": user,
        "from_addr": from_addr,
        "allowlist": allowlist,
    }, []


def is_allowlisted(to_email: str, allowlist) -> bool:
    return (to_email or "").strip().lower() in allowlist


def send_real_mail(to_email: str, subject: str, body: str) -> Tuple[bool, str]:
    """用 SMTP_SSL 发一封真实邮件。返回 (ok, err)。

    err 为空表示成功；失败时为异常摘要（不含密码等敏感信息）。
    调用前必须已完成 is_enabled/get_config/is_allowlisted 检查。
    """
    config, missing = get_config()
    if config is None:
        return False, "config_missing:" + ",".join(missing)
    password = os.environ.get("SMTP_PASS", "")
    try:
        msg = EmailMessage()
        msg["From"] = config["from_addr"]
        msg["To"] = to_email
        msg["Subject"] = subject or ""
        msg.set_content(body or "")
        with smtplib.SMTP_SSL(config["host"], config["port"],
                               timeout=SMTP_TIMEOUT) as smtp:
            smtp.login(config["user"], password)
            smtp.send_message(msg)
        return True, ""
    except Exception as e:  # noqa: BLE001 — 全部收敛为错误码，不抛 500
        return False, f"{type(e).__name__}: {str(e)[:200]}"
