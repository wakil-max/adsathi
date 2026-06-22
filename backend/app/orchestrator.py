"""
Conversation orchestrator.

Interprets the chat, accumulates a structured 'brief', figures out what's still missing,
and calls the caption + image services. When the brief is complete it builds a CampaignPlan
and flags ready_to_launch so the UI can show the Launch button.

In DRY_RUN this uses lightweight rule-based extraction (works for Bangla, English, and
Banglish). With an LLM key it can be upgraded to model-based slot filling.
"""
from __future__ import annotations
import re
from .schemas import ChatRequest, ChatResponse, CampaignPlan
from .services import captions as caption_svc
from .services import images as image_svc

# Bengali + Western digits
_DIGITS = {ord(b): str(i) for i, b in enumerate("০১২৩৪৫৬৭৮৯")}

_CITIES = {
    "dhaka": "Dhaka", "ঢাকা": "Dhaka", "chittagong": "Chattogram",
    "chattogram": "Chattogram", "চট্টগ্রাম": "Chattogram", "sylhet": "Sylhet",
    "সিলেট": "Sylhet", "khulna": "Khulna", "খুলনা": "Khulna", "rajshahi": "Rajshahi",
}

_OBJECTIVE_HINTS = {
    "sales": ["sale", "sell", "order", "buy", "বিক্রি", "অর্ডার"],
    "leads": ["lead", "signup", "register", "লিড"],
    "engagement": ["engage", "like", "follow", "লাইক", "ফলো"],
    "awareness": ["awareness", "brand", "ব্র্যান্ড", "পরিচিত"],
    "traffic": ["traffic", "visit", "website", "ওয়েবসাইট", "ভিজিট"],
}


def _norm_digits(text: str) -> str:
    return text.translate(_DIGITS)


def _extract_budget(text: str) -> int | None:
    t = _norm_digits(text.lower())
    # e.g. "500 taka", "৳500", "budget 1000", "1000 tk"
    m = re.search(r"(?:৳|tk|taka|টাকা|budget|বাজেট)\s*[:\-]?\s*(\d{2,7})", t)
    if not m:
        m = re.search(r"(\d{2,7})\s*(?:৳|tk|taka|টাকা)", t)
    return int(m.group(1)) if m else None


def _extract_age(text: str) -> tuple[int, int] | None:
    t = _norm_digits(text)
    m = re.search(r"(\d{1,2})\s*[-–to]+\s*(\d{1,2})", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _extract_city(text: str) -> str | None:
    t = text.lower()
    for key, name in _CITIES.items():
        if key in t:
            return name
    return None


def _extract_objective(text: str) -> str | None:
    t = text.lower()
    for obj, words in _OBJECTIVE_HINTS.items():
        if any(w in t for w in words):
            return obj
    return None


def _update_brief(brief: dict, message: str) -> dict:
    b = dict(brief)
    b.setdefault("audience", {})

    budget = _extract_budget(message)
    if budget:
        b["daily_budget_bdt"] = budget

    age = _extract_age(message)
    if age:
        b["audience"]["age_min"], b["audience"]["age_max"] = age

    city = _extract_city(message)
    if city:
        b["audience"]["location"] = city

    obj = _extract_objective(message)
    if obj:
        b["objective"] = obj

    # First substantive message with no product yet -> treat as the product/offer.
    # (Only skip if the message is *purely* a budget figure, e.g. "500 taka".)
    stripped = re.sub(r"[\u09e6-\u09ef\d]+|\u09f3|tk|taka|\u099f\u09be\u0995\u09be|budget|\u09ac\u09be\u099c\u09c7\u099f", "", message.lower()).strip()
    if "product" not in b and len(stripped) > 3:
        b["product"] = message.strip()[:80]
    return b


def _missing(brief: dict) -> list[str]:
    miss = []
    if not brief.get("product"):
        miss.append("product")
    if not brief.get("daily_budget_bdt"):
        miss.append("budget")
    if not (brief.get("audience") or {}).get("location"):
        miss.append("location")
    return miss


def _ask(miss: list[str]) -> str:
    q = {
        "product": "আপনি কী বিক্রি করছেন? / What product are you advertising?",
        "budget": "দৈনিক বাজেট কত টাকা? / What's your daily budget in BDT?",
        "location": "কোন এলাকায় অ্যাড দেখাতে চান? / Which area should the ad target?",
    }
    return q[miss[0]]


def handle(req: ChatRequest) -> ChatResponse:
    brief = _update_brief(req.brief, req.message)
    miss = _missing(brief)

    if miss:
        return ChatResponse(
            reply=_ask(miss),
            brief=brief,
        )

    # Brief complete -> generate creative + propose campaign.
    caps = caption_svc.generate(brief, n=3)
    imgs = image_svc.generate(brief, n=2)
    aud = brief.get("audience", {})
    plan = CampaignPlan(
        objective=brief.get("objective", "traffic"),
        audience={
            "location": aud.get("location", "Dhaka"),
            "age_min": aud.get("age_min", 18),
            "age_max": aud.get("age_max", 45),
        },
        placements=["facebook_feed", "instagram_feed", "facebook_stories"],
        daily_budget_bdt=brief["daily_budget_bdt"],
        schedule_days=brief.get("schedule_days", 7),
    )
    reply = (
        "✅ সব তথ্য পেয়েছি! নিচে ছবি ও ক্যাপশন তৈরি করেছি এবং একটি ক্যাম্পেইন প্ল্যান সাজিয়েছি। "
        "পছন্দ হলে Launch চাপুন।\n"
        "Got everything! I generated images + captions and drafted a campaign plan. "
        "Review and hit Launch when ready."
    )
    return ChatResponse(
        reply=reply,
        brief=brief,
        captions=caps,
        images=imgs,
        campaign_plan=plan,
        ready_to_launch=True,
    )
