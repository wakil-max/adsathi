"""
Framework-agnostic request router.

dispatch() returns (status:int, headers:list[(k,v)], body:bytes) and contains ALL the
app's HTTP logic. Both the stdlib server (app/main.py) and the Vercel WSGI entry
(api/index.py) call it.

Scope (current): accounts, business-profile onboarding, and credit-charged generation of
shooting scripts + images. Facebook connect / ad launch are intentionally not wired here
yet (planned for later).
"""
from __future__ import annotations
import json
import os
from typing import Optional

from .config import get_settings
from . import db, security, billing
from .schemas import jsonable
from .services import scripts as script_svc
from .services import images as image_svc

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
_inited = False


def _ensure_db():
    global _inited
    if not _inited:
        db.init_db()
        _inited = True


def _json(status, obj, extra_headers=None):
    body = json.dumps(jsonable(obj), ensure_ascii=False).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8")]
    if extra_headers:
        headers += extra_headers
    return status, headers, body


def _err(status, detail):
    return _json(status, {"detail": detail})


def _session_cookie(token):
    return ("Set-Cookie", f"sid={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={60*60*24*30}")


def _clear_cookie():
    return ("Set-Cookie", "sid=; HttpOnly; Path=/; Max-Age=0")


def _user_from(cookies, headers):
    token = cookies.get("sid")
    if not token:
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    return db.user_for_token(token) if token else None


def _public_user(u: dict) -> dict:
    prof = db.get_profile(u["id"])
    return {"id": u["id"], "email": u["email"], "name": u["name"], "credits": u["credits"],
            "has_profile": bool(prof),
            "business_name": prof["business_name"] if prof else None}


def _serve_index():
    path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return 200, [("Content-Type", "text/html; charset=utf-8")], fh.read()
    return 200, [("Content-Type", "text/html")], b"<h1>AdSathi</h1>"


def dispatch(method, path, query, cookies, headers, body):
    _ensure_db()
    s = get_settings()

    def jbody() -> dict:
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return {}

    # ---- public ----
    if method == "GET" and path == "/":
        return _serve_index()

    if method == "GET" and path == "/api/health":
        return _json(200, {"ok": True, "dry_run": s.DRY_RUN, "image_provider": s.IMAGE_PROVIDER,
                           "costs": {"script": s.CREDITS_PER_SCRIPT,
                                     "image": s.CREDITS_PER_IMAGE}})

    # ---- auth ----
    if method == "POST" and path == "/auth/signup":
        b = jbody()
        email, pw = (b.get("email") or "").strip(), b.get("password") or ""
        if not email or "@" not in email:
            return _err(400, "invalid_email")
        if db.get_user_by_email(email):
            return _err(400, "email_exists")
        if len(pw) < 6:
            return _err(400, "password_too_short")
        uid = db.create_user(email, b.get("name") or email.split("@")[0],
                             security.hash_password(pw), s.SIGNUP_FREE_CREDITS)
        token = security.new_token(); db.create_session(token, uid)
        return _json(200, {"user": _public_user(db.get_user(uid))}, [_session_cookie(token)])

    if method == "POST" and path == "/auth/login":
        b = jbody()
        user = db.get_user_by_email(b.get("email") or "")
        if not user or not security.verify_password(b.get("password") or "", user["password_hash"]):
            return _err(401, "invalid_credentials")
        token = security.new_token(); db.create_session(token, user["id"])
        return _json(200, {"user": _public_user(user)}, [_session_cookie(token)])

    if method == "POST" and path == "/auth/logout":
        if cookies.get("sid"):
            db.delete_session(cookies["sid"])
        return _json(200, {"ok": True}, [_clear_cookie()])

    # ---- everything below needs auth ----
    user = _user_from(cookies, headers)
    if not user:
        return _err(401, "not_authenticated")

    if method == "GET" and path == "/api/me":
        return _json(200, _public_user(db.get_user(user["id"])))

    # ---- onboarding / business profile ----
    if path == "/api/profile":
        if method == "GET":
            prof = db.get_profile(user["id"])
            if prof:
                prof.pop("user_id", None)
            return _json(200, {"profile": prof})
        if method == "POST":
            b = jbody()
            if not (b.get("business_name") or "").strip():
                return _err(400, "business_name_required")
            db.save_profile(user["id"], {
                "business_name": b.get("business_name", ""), "industry": b.get("industry", ""),
                "products": b.get("products", ""), "audience": b.get("audience", ""),
                "tone": b.get("tone", ""), "language": b.get("language", "bilingual"),
                "city": b.get("city", ""), "notes": b.get("notes", "")})
            return _json(200, {"ok": True, "user": _public_user(db.get_user(user["id"]))})

    # ---- generation (needs a profile) ----
    if method == "POST" and path in ("/api/generate/script", "/api/generate/image"):
        prof = db.get_profile(user["id"])
        if not prof:
            return _err(400, "no_profile")
        topic = (jbody().get("topic") or "").strip()
        if not topic:
            return _err(400, "topic_required")

        if path == "/api/generate/script":
            cost = s.CREDITS_PER_SCRIPT
            try:
                billing.charge(user["id"], cost, "script")
            except ValueError:
                return _err(402, "insufficient_credits")
            out = script_svc.generate(prof, topic)
            gid = db.save_generation(user["id"], "script", out.get("title", topic), topic, out)
            return _json(200, {"id": gid, "kind": "script", "output": out,
                               "credits": db.get_user(user["id"])["credits"]})
        else:
            cost = s.CREDITS_PER_IMAGE
            try:
                billing.charge(user["id"], cost, "image")
            except ValueError:
                return _err(402, "insufficient_credits")
            imgs = image_svc.generate_for(prof, topic, n=1)
            out = {"images": [jsonable(i) for i in imgs]}
            gid = db.save_generation(user["id"], "image", topic, topic, out)
            return _json(200, {"id": gid, "kind": "image", "output": out,
                               "credits": db.get_user(user["id"])["credits"]})

    if method == "GET" and path == "/api/history":
        rows = db.list_generations(user["id"])
        for r in rows:
            r.pop("user_id", None)
            try:
                r["output"] = json.loads(r.pop("output_json") or "{}")
            except Exception:
                r["output"] = {}
        return _json(200, {"generations": rows})

    # ---- billing ----
    if method == "GET" and path == "/api/billing/balance":
        u = db.get_user(user["id"])
        return _json(200, {"credits": u["credits"], "bdt_per_credit": s.BDT_PER_CREDIT,
                           "ledger": db.ledger(user["id"], 20)})

    if method == "POST" and path == "/api/billing/topup":
        credits = int(jbody().get("credits", 0) or 0)
        if credits < 1:
            return _err(400, "invalid_amount")
        return _json(200, billing.init_topup(user["id"], credits))

    if method == "GET" and path == "/billing/dryrun-pay":
        billing.confirm_topup(user["id"], int(query.get("credits", 0) or 0), query.get("tran_id", ""))
        return 302, [("Location", "/?pay=success")], b""

    if method == "GET" and path == "/billing/callback":
        status = query.get("status", "fail")
        if status == "success" and billing.validate_sslcommerz(query.get("val_id", "")):
            billing.confirm_topup(user["id"], int(query.get("credits", 0) or 0), query.get("val_id", ""))
            return 302, [("Location", "/?pay=success")], b""
        return 302, [("Location", f"/?pay={status}")], b""

    return _err(404, "not_found")
