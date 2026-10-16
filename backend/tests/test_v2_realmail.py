"""真实邮件发送能力测试（2026-10-16）。

全程 mock smtplib.SMTP_SSL，无真实网络调用。
覆盖：
  1. 默认关闭：走模拟，outbox real_sent=0，不触网
  2. 开启但缺 SMTP 配置：拒绝 real_mail_config_missing，记 blocked 记录
  3. 开启+配置齐+收件人不在白名单：拒绝 real_mail_not_allowlisted，记 blocked 记录
  4. 开启+白名单内+mock 发送成功：real_sent=1，审计有 mail.real_sent 事件
  5. mock 发送抛异常：real_mail_send_failed，不抛 500
  6. 白名单大小写/空格宽容
"""

import smtplib
from unittest import mock

import pytest

from app import db, gateway, realmail  # noqa: F401  (realmail 确保模块可导入)
from app.models import Action, AuditEvent, Outbox

MAIL_ENV_KEYS = [
    "REAL_MAIL_ENABLED",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASS",
    "SMTP_FROM",
    "REAL_MAIL_ALLOWLIST",
]


@pytest.fixture(autouse=True)
def _clean_mail_env(monkeypatch):
    for k in MAIL_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture()
def _no_smtp():
    """拦截所有 SMTP_SSL 实例化，断言无真实网络调用。"""
    with mock.patch("smtplib.SMTP_SSL") as m:
        yield m


def _set_full_config(monkeypatch, allowlist="boss@example.com"):
    monkeypatch.setenv("REAL_MAIL_ENABLED", "1")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASS", "s3cr3t")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setenv("REAL_MAIL_ALLOWLIST", allowlist)


def _make_and_approve_mail(api, to="boss@example.com"):
    r = api.post("/api/tasks", json={"title": "mail test", "scenario": "followup"})
    assert r.status_code == 200, r.text
    task_id = r.json()["id"]
    session = db.SessionLocal()
    try:
        action = gateway.propose_action(
            session, task_id=task_id, tool="mail.send",
            params={"to": to, "subject": "验收测试", "body": "hello"},
        )
        action_id = action.id
        # 走一次裁决（advance 模式）：mail.send -> needs_approval，并建 pending 审批单
        gateway.adjudicate(session, action, mode="advance")
        ap = gateway.ensure_pending_approval(session, action)
        ap_id = ap.id
        session.commit()
    finally:
        session.close()
    r = api.post(f"/api/approvals/{ap_id}/decide",
                 json={"decision": "approve", "approver": "test"})
    assert r.status_code == 200, r.text
    return task_id, action_id


def _outbox_rows():
    session = db.SessionLocal()
    try:
        return session.query(Outbox).order_by(Outbox.id).all()
    finally:
        session.close()


def _audit_events(name):
    session = db.SessionLocal()
    try:
        return session.query(AuditEvent).filter(AuditEvent.event == name).all()
    finally:
        session.close()


def test_default_disabled_simulated(api, _no_smtp):
    """默认关闭：走模拟写 outbox，不触网。"""
    _, action_id = _make_and_approve_mail(api)
    r = api.post(f"/api/actions/{action_id}/execute")
    assert r.status_code == 200, r.text
    assert r.json()["result"]["real_sent"] is False
    _no_smtp.assert_not_called()
    rows = _outbox_rows()
    assert len(rows) == 1
    assert rows[0].real_sent == 0
    assert rows[0].blocked_reason is None
    assert _audit_events("mail.real_sent") == []


def test_enabled_missing_config_refused(api, _no_smtp, monkeypatch):
    """开启但缺 SMTP 配置：拒绝，记 blocked 记录，不抛 500。"""
    monkeypatch.setenv("REAL_MAIL_ENABLED", "1")
    _, action_id = _make_and_approve_mail(api)
    r = api.post(f"/api/actions/{action_id}/execute")
    assert r.status_code == 409, r.text
    assert "real_mail_config_missing" in r.text
    _no_smtp.assert_not_called()
    rows = _outbox_rows()
    assert len(rows) == 1
    assert rows[0].real_sent == 0
    assert rows[0].blocked_reason.startswith("config_missing:")


def test_enabled_not_allowlisted_refused(api, _no_smtp, monkeypatch):
    """收件人不在白名单：拒绝，记 blocked 记录。"""
    _set_full_config(monkeypatch, allowlist="boss@example.com")
    _, action_id = _make_and_approve_mail(api, to="stranger@evil.com")
    r = api.post(f"/api/actions/{action_id}/execute")
    assert r.status_code == 409, r.text
    assert "real_mail_not_allowlisted" in r.text
    _no_smtp.assert_not_called()
    rows = _outbox_rows()
    assert len(rows) == 1
    assert rows[0].real_sent == 0
    assert rows[0].blocked_reason == "not_allowlisted"


def test_enabled_allowlisted_sends_and_audits(api, _no_smtp, monkeypatch):
    """白名单内 + mock 发送成功：real_sent=1，审计记 mail.real_sent。"""
    _set_full_config(monkeypatch, allowlist="boss@example.com")
    _, action_id = _make_and_approve_mail(api, to="boss@example.com")
    r = api.post(f"/api/actions/{action_id}/execute")
    assert r.status_code == 200, r.text
    assert r.json()["result"]["real_sent"] is True
    _no_smtp.assert_called_once()
    rows = _outbox_rows()
    assert len(rows) == 1
    assert rows[0].real_sent == 1
    assert rows[0].blocked_reason is None
    evs = _audit_events("mail.real_sent")
    assert len(evs) == 1
    import json as _json
    detail = _json.loads(evs[0].detail)
    assert detail["to"] == "boss@example.com"
    assert detail["subject"] == "验收测试"
    assert "body" not in detail  # 正文敏感信息不进审计，只记摘要
    assert detail["body_len"] == len("hello")


def test_enabled_smtp_failure_no_500(api, _no_smtp, monkeypatch):
    """SMTP 发送抛异常：返回 real_mail_send_failed，不抛 500。"""
    _set_full_config(monkeypatch, allowlist="boss@example.com")
    _no_smtp.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
    _, action_id = _make_and_approve_mail(api, to="boss@example.com")
    r = api.post(f"/api/actions/{action_id}/execute")
    assert r.status_code == 409, r.text
    assert "real_mail_send_failed" in r.text
    rows = _outbox_rows()
    assert len(rows) == 1
    assert rows[0].real_sent == 0
    assert rows[0].blocked_reason == "send_failed"


def test_allowlist_case_insensitive(api, _no_smtp, monkeypatch):
    """白名单大小写/空格宽容。"""
    _set_full_config(monkeypatch, allowlist="  Boss@Example.COM ")
    _, action_id = _make_and_approve_mail(api, to="boss@example.com")
    r = api.post(f"/api/actions/{action_id}/execute")
    assert r.status_code == 200, r.text
    assert r.json()["result"]["real_sent"] is True
