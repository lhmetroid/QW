# -*- coding: utf-8 -*-
"""邮件新功能特性开关。

原则:
- **默认全关**。凡是会"真发邮件 / 覆盖发件人 / 取消或替换客户后续排期"的动作, 不打开就不跑。
- 涉及实际配置项的(如自检收件人、公共邮箱池), **人工没配好就跳过**, 返回明确的 skipped 原因, 不报错、不误动。
- 只读的统计/展示(每日迭代分析、回信分层统计)不设开关: 它们不产生外部动作。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


# key -> 元数据。default 一律 False(危险动作默认关)。
FEATURES: dict[str, dict[str, Any]] = {
    "public_mailbox_send": {
        "label": "公共邮箱池真发覆盖 (4.1)",
        "desc": "转入CRM(同步保存ERP)时, 用排期竞争分配到的公共邮箱覆盖发件人。关闭=始终用该联系人在职销售的个人企业邮箱。签名任何情况下都按在职销售赋值。",
        "default": False,
        "requires": ["公共邮箱池里至少 1 个启用邮箱", "自动发送规则的 mailbox_mode 非 personal_only"],
        "config_keys": [],
    },
    "self_check_send": {
        "label": "发件通道自检真发 (4.2)",
        "desc": "允许自检邮件真写入 CRM 待发队列。关闭=只允许 dry_run 构造校验, 不真发。",
        "default": False,
        "requires": ["配置 self_check_recipient(自检收件邮箱)"],
        "config_keys": ["self_check_recipient"],
    },
    "self_check_daily": {
        "label": "每天自动自检 (4.2)",
        "desc": "每天定时给自检收件人各发一封自检邮件。关闭=只能人工点 发送自检 按钮。",
        "default": False,
        "requires": ["self_check_send 已开启", "配置 self_check_recipient"],
        "config_keys": [],
    },
    "bounce_capture": {
        "label": "退信捕获与无效地址鉴定 (5.1)",
        "desc": "从 CRM 收信里按退信特征(MAILER-DAEMON/postmaster/Undeliverable 等)捞退信, 提取失效收件地址并登记。关闭=不扫描, 不鉴定。",
        "default": False,
        "requires": [],
        "config_keys": [],
    },
    "bounce_auto_link": {
        "label": "退信联动取消/替换后续排期 (5.2)",
        "desc": "鉴定出失效地址后, 自动取消或用该联系人其他有效地址替换其后续未发排期。关闭=只登记无效地址, 不动任何排期。",
        "default": False,
        "requires": ["bounce_capture 已开启"],
        "config_keys": [],
    },
}


def ensure_tables(db: Session) -> None:
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS mail_feature_switch ("
        "key VARCHAR(64) PRIMARY KEY,"
        "enabled BOOLEAN NOT NULL DEFAULT FALSE,"
        "config JSONB NOT NULL DEFAULT '{}'::jsonb,"
        "updated_at TIMESTAMP DEFAULT now()"
        ")"
    ))
    db.commit()


def _row(db: Session, key: str) -> dict | None:
    r = db.execute(text("SELECT key, enabled, config FROM mail_feature_switch WHERE key=:k"), {"k": key}).fetchone()
    return dict(r._mapping) if r else None


def is_enabled(db: Session, key: str) -> bool:
    """开关是否打开。表不存在/无记录 -> 用 FEATURES 默认值(全 False)。"""
    if key not in FEATURES:
        raise ValueError(f"unknown feature: {key}")
    try:
        ensure_tables(db)
        r = _row(db, key)
    except Exception:
        return bool(FEATURES[key]["default"])
    if not r:
        return bool(FEATURES[key]["default"])
    return bool(r.get("enabled"))


def get_config(db: Session, key: str) -> dict:
    if key not in FEATURES:
        raise ValueError(f"unknown feature: {key}")
    try:
        ensure_tables(db)
        r = _row(db, key)
    except Exception:
        return {}
    if not r:
        return {}
    cfg = r.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except Exception:
            cfg = {}
    return cfg if isinstance(cfg, dict) else {}


def set_switch(db: Session, key: str, *, enabled: bool | None = None, config: dict | None = None) -> dict:
    """打开/关闭开关或更新其配置。enabled/config 为 None 表示本次不改该维度。"""
    if key not in FEATURES:
        raise ValueError(f"unknown feature: {key}")
    ensure_tables(db)
    cur = _row(db, key) or {}
    cur_cfg = get_config(db, key)
    new_enabled = bool(cur.get("enabled", FEATURES[key]["default"])) if enabled is None else bool(enabled)
    new_cfg = cur_cfg if config is None else {**cur_cfg, **(config or {})}
    db.execute(text(
        "INSERT INTO mail_feature_switch (key, enabled, config, updated_at) VALUES (:k,:e,CAST(:c AS jsonb), now()) "
        "ON CONFLICT (key) DO UPDATE SET enabled=EXCLUDED.enabled, config=EXCLUDED.config, updated_at=now()"
    ), {"k": key, "e": new_enabled, "c": json.dumps(new_cfg, ensure_ascii=False)})
    db.commit()
    return {"key": key, "enabled": new_enabled, "config": new_cfg}


def check(db: Session, key: str, *, required_config: list[str] | None = None) -> dict:
    """统一的"能不能跑"判定。返回 {ok, reason, config}。

    ok=False 时调用方应**跳过**(不报错、不误动), 并把 reason 透出给页面。
    """
    if key not in FEATURES:
        return {"ok": False, "reason": f"未知开关: {key}", "config": {}}
    meta = FEATURES[key]
    if not is_enabled(db, key):
        return {"ok": False, "reason": f"开关未打开({meta['label']}), 已跳过", "config": {}}
    cfg = get_config(db, key)
    need = list(required_config if required_config is not None else meta.get("config_keys") or [])
    missing = [k for k in need if not str(cfg.get(k) or "").strip()]
    if missing:
        return {"ok": False, "reason": f"缺少人工配置: {', '.join(missing)}, 已跳过", "config": cfg}
    return {"ok": True, "reason": "", "config": cfg}


def list_all(db: Session) -> list[dict]:
    ensure_tables(db)
    out = []
    for key, meta in FEATURES.items():
        r = _row(db, key)
        out.append({
            "key": key,
            "label": meta["label"],
            "desc": meta["desc"],
            "requires": meta.get("requires") or [],
            "config_keys": meta.get("config_keys") or [],
            "default": bool(meta["default"]),
            "enabled": bool(r.get("enabled")) if r else bool(meta["default"]),
            "config": get_config(db, key),
        })
    return out
