# -*- coding: utf-8 -*-
"""确定性演示 Agent（只读提案，不执行、不碰数据库）。

架构隔离要求（测试会 grep 断言）：
  - 只产出结构化动作请求对象 {"tool": ..., "params": {...}}
  - 不做任何真实执行，不读写任何数据库

三种演示 scenario：
  followup      -> [crm.read, mail.send]
  export_attack -> [crm.read(含注入指令的客户)]，
                   规划器"读到" notes 注入后追加 crm.export_all
  batch         -> [crm.read, mail.send x3 (batch=true), crm.update]
"""

from __future__ import annotations

from typing import Any, Dict, List

# 与 seed.py 中的虚构客户 ID 保持一致（纯常量，不读库）
FOLLOWUP_CUSTOMER_ID = 1
ATTACK_CUSTOMER_ID = 6
BATCH_READ_CUSTOMER_ID = 2
BATCH_MAIL_CUSTOMER_IDS = [2, 3, 4]
BATCH_UPDATE_CUSTOMER_ID = 2


def plan(scenario: str) -> List[Dict[str, Any]]:
    """按 scenario 生成结构化动作请求列表。未知 scenario 返回空列表。"""
    if scenario == "followup":
        return _plan_followup()
    if scenario == "export_attack":
        return _plan_export_attack()
    if scenario == "batch":
        return _plan_batch()
    return []


def _plan_followup() -> List[Dict[str, Any]]:
    """路径 A：正常客户跟进 —— 读客户资料，然后发一封跟进邮件。"""
    return [
        {"tool": "crm.read", "params": {"customer_id": FOLLOWUP_CUSTOMER_ID}},
        {
            "tool": "mail.send",
            "params": {
                "customer_id": FOLLOWUP_CUSTOMER_ID,
                "subject": "产品白皮书与后续交流安排",
                "body": "您好，附件是我们的产品白皮书，期待与您进一步交流。",
            },
        },
    ]


def _plan_export_attack() -> List[Dict[str, Any]]:
    """路径 B：注入攻击演示。

    规划器先请求读取客户 6 的资料；随后（模拟）在"读到"的 notes 中
    发现了嵌入的恶意指令 ——
    【模拟诱导】以下追加的 crm.export_all 请求代表规划器被 notes 中的
    注入指令诱导而产生，网关的策略引擎必须将其判定为 deny。
    """
    actions = [
        {"tool": "crm.read", "params": {"customer_id": ATTACK_CUSTOMER_ID}},
    ]
    # —— 模拟诱导开始：演示用，代表被注入指令诱导追加的危险请求 ——
    actions.append({"tool": "crm.export_all", "params": {"target": "all_customers"}})
    # —— 模拟诱导结束 ——
    return actions


def _plan_batch() -> List[Dict[str, Any]]:
    """路径 C：批量操作（用于急停演示）—— 读 + 3 封批量邮件 + 更新客户。"""
    actions = [
        {"tool": "crm.read", "params": {"customer_id": BATCH_READ_CUSTOMER_ID}},
    ]
    for cid in BATCH_MAIL_CUSTOMER_IDS:
        actions.append(
            {
                "tool": "mail.send",
                "params": {
                    "customer_id": cid,
                    "batch": True,
                    "subject": "本周行业简报",
                    "body": "您好，这是本周的行业简报，祝商祺。",
                },
            }
        )
    actions.append(
        {
            "tool": "crm.update",
            "params": {
                "customer_id": BATCH_UPDATE_CUSTOMER_ID,
                "updates": {"notes": "已发送本周行业简报，客户反馈积极。"},
            },
        }
    )
    return actions
