"""Data layer. Works on SQLite (local/Docker) or Postgres (Vercel/Neon).

Backend is chosen by env: if DATABASE_URL starts with 'postgres', Postgres is used
(requires `psycopg`); otherwise SQLite at DB_PATH. The same functions serve both.
"""
from __future__ import annotations
import os
import sqlite3
import time
import json
from contextlib import contextmanager
from typing import Any, Optional
from .config import get_settings

DATABASE_URL = os.getenv("DATABASE_URL", "")
IS_PG = DATABASE_URL.startswith("postgres")

_PK = "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"

TABLES = [
    f"""CREATE TABLE IF NOT EXISTS users (
        id {_PK}, email TEXT UNIQUE NOT NULL, name TEXT, password_hash TEXT NOT NULL,
        credits INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at INTEGER NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS fb_accounts (
        id {_PK}, user_id INTEGER NOT NULL, access_token TEXT NOT NULL, ad_account_id TEXT,
        page_id TEXT, label TEXT, created_at INTEGER NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS campaigns (
        id {_PK}, user_id INTEGER NOT NULL, name TEXT, status TEXT, meta_campaign_id TEXT,
        meta_ad_id TEXT, plan_json TEXT, caption_json TEXT, image_url TEXT,
        dry_run INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS credit_ledger (
        id {_PK}, user_id INTEGER NOT NULL, delta INTEGER NOT NULL, reason TEXT, ref TEXT,
        created_at INTEGER NOT NULL)""",
]


def _q(sql: str) -> str:
    """Translate '?' placeholders to '%s' for Postgres."""
    return sql.replace("?", "%s") if IS_PG else sql


@contextmanager
def conn():
    if IS_PG:
        import psycopg
        from psycopg.rows import dict_row
        c = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    else:
        c = sqlite3.connect(get_settings().DB_PATH)
        c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _insert(c, sql: str, params: tuple) -> int:
    """Run an INSERT and return the new row id, on either backend."""
    if IS_PG:
        cur = c.execute(_q(sql) + " RETURNING id", params)
        return cur.fetchone()["id"]
    cur = c.execute(sql, params)
    return cur.lastrowid


def _one(c, sql: str, params: tuple = ()) -> Optional[dict]:
    r = c.execute(_q(sql), params).fetchone()
    return dict(r) if r else None


def _all(c, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in c.execute(_q(sql), params).fetchall()]


def init_db() -> None:
    with conn() as c:
        for stmt in TABLES:
            c.execute(stmt)


# ---------- users ----------
def create_user(email: str, name: str, password_hash: str, credits: int) -> int:
    with conn() as c:
        uid = _insert(
            c, "INSERT INTO users(email,name,password_hash,credits,created_at) VALUES(?,?,?,?,?)",
            (email.lower().strip(), name, password_hash, credits, int(time.time())),
        )
        _insert(c, "INSERT INTO credit_ledger(user_id,delta,reason,ref,created_at) VALUES(?,?,?,?,?)",
                (uid, credits, "signup_bonus", "", int(time.time())))
        return uid


def get_user_by_email(email: str) -> Optional[dict]:
    with conn() as c:
        return _one(c, "SELECT * FROM users WHERE email=?", (email.lower().strip(),))


def get_user(uid: int) -> Optional[dict]:
    with conn() as c:
        return _one(c, "SELECT * FROM users WHERE id=?", (uid,))


# ---------- sessions ----------
def create_session(token: str, user_id: int) -> None:
    with conn() as c:
        c.execute(_q("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)"),
                  (token, user_id, int(time.time())))


def user_for_token(token: str) -> Optional[dict]:
    with conn() as c:
        return _one(c, "SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=?",
                    (token,))


def delete_session(token: str) -> None:
    with conn() as c:
        c.execute(_q("DELETE FROM sessions WHERE token=?"), (token,))


# ---------- credits ----------
def adjust_credits(user_id: int, delta: int, reason: str, ref: str = "") -> int:
    with conn() as c:
        row = _one(c, "SELECT credits FROM users WHERE id=?", (user_id,))
        if row is None:
            raise ValueError("user not found")
        new_balance = row["credits"] + delta
        if new_balance < 0:
            raise ValueError("insufficient_credits")
        c.execute(_q("UPDATE users SET credits=? WHERE id=?"), (new_balance, user_id))
        c.execute(_q("INSERT INTO credit_ledger(user_id,delta,reason,ref,created_at) VALUES(?,?,?,?,?)"),
                  (user_id, delta, reason, ref, int(time.time())))
        return new_balance


def ledger(user_id: int, limit: int = 50) -> list[dict]:
    with conn() as c:
        return _all(c, "SELECT * FROM credit_ledger WHERE user_id=? ORDER BY id DESC LIMIT ?",
                    (user_id, limit))


# ---------- fb accounts ----------
def save_fb_account(user_id: int, access_token: str, ad_account_id: str,
                    page_id: str, label: str) -> int:
    with conn() as c:
        return _insert(
            c, "INSERT INTO fb_accounts(user_id,access_token,ad_account_id,page_id,label,created_at)"
               " VALUES(?,?,?,?,?,?)",
            (user_id, access_token, ad_account_id, page_id, label, int(time.time())))


def get_fb_account(user_id: int) -> Optional[dict]:
    with conn() as c:
        return _one(c, "SELECT * FROM fb_accounts WHERE user_id=? ORDER BY id DESC LIMIT 1",
                    (user_id,))


# ---------- campaigns ----------
def save_campaign(user_id: int, data: dict[str, Any]) -> int:
    with conn() as c:
        return _insert(
            c, "INSERT INTO campaigns(user_id,name,status,meta_campaign_id,meta_ad_id,"
               "plan_json,caption_json,image_url,dry_run,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (user_id, data.get("name"), data.get("status"), data.get("meta_campaign_id"),
             data.get("meta_ad_id"), json.dumps(data.get("plan"), ensure_ascii=False),
             json.dumps(data.get("caption"), ensure_ascii=False), data.get("image_url"),
             1 if data.get("dry_run") else 0, int(time.time())))


def list_campaigns(user_id: int, limit: int = 50) -> list[dict]:
    with conn() as c:
        return _all(c, "SELECT * FROM campaigns WHERE user_id=? ORDER BY id DESC LIMIT ?",
                    (user_id, limit))
