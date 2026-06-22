"""Framework-agnostic request router.

dispatch() returns (status:int, headers:list[(k,v)], body:bytes) and contains ALL the
app's HTTP logic. Both the stdlib server (app/main.py) and the Vercel WSGI entry
(api/index.py) call it, so behaviour is identical everywhere.
"""
from __future__ import annotations
import json
import os
from typing import Optional

from .config import get_settings
from . import db, security, billing, meta_oauth, orchestrator
from .schemas import ChatRequest, LaunchResult, jsonable, caption_from, image_from, plan_from
from .services.meta_ads import MetaAdsClient, MetaError
from .services import images as image_svc

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
_inited = False


def _ensure_db():
    global _inited
    if not _inited:
        db.init_db()
        _inited = True


# ---------- response helpers ----------
def _json(status: int, obj, extra_headers=None):
    body = json.dumps(jsonable(obj), ensure_ascii=False).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8")]
    if extra_headers:
        headers += extra_headers
    return status, headers, body


def _err(status: int, detail: str):
    return _json(status, {"detail": detail})


def _redirect(location: str, extra_headers=None):
    headers = [("Location", location)]
    if extra_headers:
        headers += extra_headers
    return 302, headers, b""


def _session_cookie(token: str) -> tuple:
    return ("Set-Cookie",
            f"sid={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={60*60*24*30}")


def _clear_cookie() -> tuple:
    return ("Set-Cookie", "sid=; HttpOnly; Path=/; Max-Age=0")


def _user_from(cookies: dict, headers: dict) -> Optional[dict]:
    token = cookies.get("sid")
    if not token:
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    return db.user_for_token(token) if token else None


def _public_user(u: dict) -> dict:
    acct = db.get_fb_account(u["id"])
    return {"id": u["id"], "email": u["email"], "name": u["name"], "credits": u["credits"],
            "connected": bool(acct), "account_label": acct["label"] if acct else None}


def _serve_index():
    path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return 200, [("Content-Type", "text/html; charset=utf-8")], fh.read()
    return 200, [("Content-Type", "text/html")], b"<h1>AdSathi</h1>"


# ---------- main dispatch ----------
def dispatch(method: str, path: str, query: dict, cookies: dict, headers: dict,
             body: bytes) -> tuple:
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
                           "meta_app_configured": bool(s.META_APP_ID),
                           "payments_configured": bool(s.SSLCZ_STORE_ID)})

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
        return _json(200, {"token": token, "user": _public_user(db.get_user(uid))},
                     [_session_cookie(token)])

    if method == "POST" and path == "/auth/login":
        b = jbody()
        user = db.get_user_by_email(b.get("email") or "")
        if not user or not security.verify_password(b.get("password") or "", user["password_hash"]):
            return _err(401, "invalid_credentials")
        token = security.new_token(); db.create_session(token, user["id"])
        return _json(200, {"token": token, "user": _public_user(user)}, [_session_cookie(token)])

    if method == "POST" and path == "/auth/logout":
        if cookies.get("sid"):
            db.delete_session(cookies["sid"])
        return _json(200, {"ok": True}, [_clear_cookie()])

    # ---- everything below needs auth ----
    user = _user_from(cookies, headers)

    if method == "GET" and path == "/api/me":
        if not user:
            return _err(401, "not_authenticated")
        return _json(200, _public_user(db.get_user(user["id"])))

    if method == "GET" and path == "/connect/facebook/start":
        if not user:
            return _err(401, "not_authenticated")
        return _json(200, {"login_url": meta_oauth.login_url(state=cookies.get("sid", ""))})

    if method == "GET" and path == "/connect/facebook/callback":
        owner = db.user_for_token(query.get("state", ""))
        if not owner:
            return _redirect("/?connect=error")
        access = meta_oauth.exchange_code(query.get("code", ""))
        accounts = meta_oauth.list_ad_accounts(access)
        pages = meta_oauth.list_pages(access)
        db.save_fb_account(owner["id"], access,
                           accounts[0]["id"] if accounts else "",
                           pages[0]["id"] if pages else "",
                           accounts[0]["name"] if accounts else "Connected account")
        return _redirect("/?connect=success")

    if method == "POST" and path == "/api/chat":
        if not user:
            return _err(401, "not_authenticated")
        b = jbody()
        req = ChatRequest(message=b.get("message", ""), history=b.get("history", []),
                          brief=b.get("brief", {}))
        resp = orchestrator.handle(req)
        if resp.ready_to_launch:
            cost = s.CREDITS_PER_IMAGE * len(resp.images) + s.CREDITS_PER_CAPTION_SET
            try:
                billing.charge(user["id"], cost, "content_generation")
            except ValueError:
                return _err(402, "insufficient_credits")
        return _json(200, resp)

    if method == "POST" and path == "/api/launch":
        if not user:
            return _err(401, "not_authenticated")
        b = jbody()
        plan = plan_from(b.get("campaign_plan", {}))
        caption = caption_from(b.get("caption", {}))
        image = image_from(b.get("image", {}))
        try:
            billing.charge(user["id"], s.CREDITS_PER_LAUNCH, "launch")
        except ValueError:
            return _err(402, "insufficient_credits")
        acct = db.get_fb_account(user["id"])
        client = MetaAdsClient(
            token=acct["access_token"] if acct else None,
            ad_account_id=acct["ad_account_id"] if acct else None,
            page_id=acct["page_id"] if acct else None)
        try:
            result = client.launch(plan, caption, image,
                                   image_bytes=image_svc.bytes_for(image),
                                   activate=bool(b.get("activate")))
        except MetaError as e:
            billing.grant(user["id"], s.CREDITS_PER_LAUNCH, "launch_refund")
            return _err(502, f"meta_error: {e}")
        db.save_campaign(user["id"], {
            "name": result.campaign_id, "status": result.status,
            "meta_campaign_id": result.campaign_id, "meta_ad_id": result.ad_id,
            "plan": jsonable(plan), "caption": jsonable(caption),
            "image_url": image.url[:120], "dry_run": result.dry_run})
        return _json(200, result)

    if method == "GET" and path == "/api/campaigns":
        if not user:
            return _err(401, "not_authenticated")
        rows = db.list_campaigns(user["id"])
        for r in rows:
            r.pop("user_id", None)
        return _json(200, {"campaigns": rows})

    if method == "GET" and path.startswith("/api/insights/"):
        if not user:
            return _err(401, "not_authenticated")
        ad_id = path.rsplit("/", 1)[-1]
        acct = db.get_fb_account(user["id"])
        client = MetaAdsClient(token=acct["access_token"] if acct else None,
                               ad_account_id=acct["ad_account_id"] if acct else None)
        return _json(200, client.insights(ad_id))

    if method == "GET" and path == "/api/billing/balance":
        if not user:
            return _err(401, "not_authenticated")
        u = db.get_user(user["id"])
        return _json(200, {"credits": u["credits"], "bdt_per_credit": s.BDT_PER_CREDIT,
                           "ledger": db.ledger(user["id"], 20)})

    if method == "POST" and path == "/api/billing/topup":
        if not user:
            return _err(401, "not_authenticated")
        credits = int(jbody().get("credits", 0) or 0)
        if credits < 1:
            return _err(400, "invalid_amount")
        return _json(200, billing.init_topup(user["id"], credits))

    if method == "GET" and path == "/billing/dryrun-pay":
        if not user:
            return _redirect("/?pay=error")
        billing.confirm_topup(user["id"], int(query.get("credits", 0) or 0),
                              query.get("tran_id", ""))
        return _redirect("/?pay=success")

    if method == "GET" and path == "/billing/callback":
        status = query.get("status", "fail")
        if status == "success" and user and billing.validate_sslcommerz(query.get("val_id", "")):
            billing.confirm_topup(user["id"], int(query.get("credits", 0) or 0),
                                  query.get("val_id", ""))
            return _redirect("/?pay=success")
        return _redirect(f"/?pay={status}")

    return _err(404, "not_found")
