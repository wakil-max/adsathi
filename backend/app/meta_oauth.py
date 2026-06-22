"""Facebook Login (OAuth) for connecting a client's ad account + page.

Flow:
  1. login_url()  -> redirect the user to Facebook to grant permissions.
  2. Facebook redirects back to META_OAUTH_REDIRECT with ?code=...
  3. exchange_code(code) -> short-lived token -> long-lived token.
  4. list_ad_accounts(token) / list_pages(token) -> let the user pick.

In DRY_RUN these return mock data so the connect flow is demoable without a Meta app.
"""
from __future__ import annotations
import urllib.parse
from .config import get_settings

SCOPES = [
    "ads_management",
    "ads_read",
    "business_management",
    "pages_show_list",
    "pages_read_engagement",
]


def login_url(state: str) -> str:
    s = get_settings()
    params = {
        "client_id": s.META_APP_ID,
        "redirect_uri": s.META_OAUTH_REDIRECT,
        "state": state,
        "scope": ",".join(SCOPES),
        "response_type": "code",
    }
    return f"https://www.facebook.com/{s.META_API_VERSION}/dialog/oauth?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> str:
    """Return a long-lived user access token."""
    s = get_settings()
    if s.DRY_RUN or not s.META_APP_ID:
        return "DRYRUN_USER_TOKEN"
    import httpx
    base = f"https://graph.facebook.com/{s.META_API_VERSION}"
    short = httpx.get(
        f"{base}/oauth/access_token",
        params={
            "client_id": s.META_APP_ID,
            "client_secret": s.META_APP_SECRET,
            "redirect_uri": s.META_OAUTH_REDIRECT,
            "code": code,
        },
        timeout=30,
    ).json()["access_token"]
    long = httpx.get(
        f"{base}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": s.META_APP_ID,
            "client_secret": s.META_APP_SECRET,
            "fb_exchange_token": short,
        },
        timeout=30,
    ).json()["access_token"]
    return long


def list_ad_accounts(token: str) -> list[dict]:
    s = get_settings()
    if s.DRY_RUN or token == "DRYRUN_USER_TOKEN":
        return [{"id": "act_1234567890", "name": "Demo Ad Account (BDT)"}]
    import httpx
    base = f"https://graph.facebook.com/{s.META_API_VERSION}"
    data = httpx.get(
        f"{base}/me/adaccounts",
        params={"fields": "name,account_status", "access_token": token},
        timeout=30,
    ).json()
    return [{"id": a["id"], "name": a.get("name", a["id"])} for a in data.get("data", [])]


def list_pages(token: str) -> list[dict]:
    s = get_settings()
    if s.DRY_RUN or token == "DRYRUN_USER_TOKEN":
        return [{"id": "100000000000000", "name": "Demo Page"}]
    import httpx
    base = f"https://graph.facebook.com/{s.META_API_VERSION}"
    data = httpx.get(
        f"{base}/me/accounts",
        params={"fields": "name", "access_token": token},
        timeout=30,
    ).json()
    return [{"id": p["id"], "name": p.get("name", p["id"])} for p in data.get("data", [])]
