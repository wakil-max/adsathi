"""
Credits + payments.

Users spend credits to generate images/captions and to launch ads. They top up credits
by paying in BDT through SSLCommerz (supports bKash, Nagad, Rocket, cards) — the most
common Bangladeshi payment gateway.

DRY_RUN: payment init returns a fake redirect URL and top-ups can be confirmed locally so
the flow is testable. With real SSLCommerz store credentials it creates a real session and
validates the IPN/callback.
"""
from __future__ import annotations
import uuid
from .config import get_settings
from . import db


def credits_to_bdt(credits: int) -> int:
    return credits * get_settings().BDT_PER_CREDIT


def charge(user_id: int, credits: int, reason: str, ref: str = "") -> int:
    """Deduct credits (raises ValueError('insufficient_credits') if not enough)."""
    return db.adjust_credits(user_id, -abs(credits), reason, ref)


def grant(user_id: int, credits: int, reason: str, ref: str = "") -> int:
    return db.adjust_credits(user_id, abs(credits), reason, ref)


def init_topup(user_id: int, credits: int) -> dict:
    """Start a payment for `credits`. Returns {gateway_url, tran_id, amount_bdt}."""
    s = get_settings()
    amount = credits_to_bdt(credits)
    tran_id = f"adsathi_{user_id}_{uuid.uuid4().hex[:10]}"

    if s.DRY_RUN or not s.SSLCZ_STORE_ID:
        # Local sandbox: caller can immediately confirm via confirm_topup().
        return {
            "gateway_url": f"{s.BASE_URL}/billing/dryrun-pay?tran_id={tran_id}&credits={credits}",
            "tran_id": tran_id,
            "amount_bdt": amount,
            "dry_run": True,
        }
    import httpx

    host = "sandbox.sslcommerz.com" if s.SSLCZ_SANDBOX else "securepay.sslcommerz.com"
    payload = {
        "store_id": s.SSLCZ_STORE_ID,
        "store_passwd": s.SSLCZ_STORE_PASS,
        "total_amount": amount,
        "currency": "BDT",
        "tran_id": tran_id,
        "success_url": f"{s.BASE_URL}/billing/callback?status=success&credits={credits}",
        "fail_url": f"{s.BASE_URL}/billing/callback?status=fail",
        "cancel_url": f"{s.BASE_URL}/billing/callback?status=cancel",
        "ipn_url": f"{s.BASE_URL}/billing/ipn",
        "product_name": f"{credits} AdSathi credits",
        "product_category": "digital",
        "product_profile": "general",
        "cus_name": "Customer",
        "cus_email": "customer@example.com",
        "cus_phone": "01700000000",
    }
    r = httpx.post(f"https://{host}/gwprocess/v4/api.php", data=payload, timeout=30)
    data = r.json()
    if data.get("status") != "SUCCESS":
        raise RuntimeError(f"SSLCommerz init failed: {data.get('failedreason', data)}")
    return {
        "gateway_url": data["GatewayPageURL"],
        "tran_id": tran_id,
        "amount_bdt": amount,
        "dry_run": False,
    }


def confirm_topup(user_id: int, credits: int, tran_id: str) -> int:
    """Credit the user after a verified successful payment. Returns new balance."""
    return grant(user_id, credits, "topup", tran_id)


def validate_sslcommerz(val_id: str) -> bool:
    """Server-side validation of a payment via SSLCommerz validator API."""
    s = get_settings()
    if s.DRY_RUN or not s.SSLCZ_STORE_ID:
        return True
    import httpx
    host = "sandbox.sslcommerz.com" if s.SSLCZ_SANDBOX else "securepay.sslcommerz.com"
    r = httpx.get(
        f"https://{host}/validator/api/validationserverAPI.php",
        params={"val_id": val_id, "store_id": s.SSLCZ_STORE_ID,
                "store_passwd": s.SSLCZ_STORE_PASS, "format": "json"},
        timeout=30,
    )
    return r.json().get("status") in ("VALID", "VALIDATED")
