"""Bilingual (Bangla + English) ad caption generation."""
from __future__ import annotations
import json
from ..config import get_settings
from ..schemas import Caption
from .. import llm

SYSTEM = (
    "You are a Bangladeshi performance-marketing copywriter. Write Meta (Facebook/Instagram) "
    "ad captions that are punchy, culturally native, and conversion-focused. For each variant "
    "return BOTH a natural Bangla version and an English version with the same meaning. "
    "Return strict JSON: a list of objects with keys bn, en, tone."
)

# Tone presets used for the dry-run templates and to guide the real model.
_TONES = ["urgency", "friendly", "premium"]


def _template(brief: dict, tone: str) -> Caption:
    product = brief.get("product", "আপনার পণ্য / your product")
    budget = brief.get("daily_budget_bdt")
    city = (brief.get("audience") or {}).get("location", "বাংলাদেশ")
    offer = brief.get("offer", "")
    if tone == "urgency":
        bn = f"🔥 সীমিত সময়ের অফার! {product} এখনই অর্ডার করুন। {offer} সারা {city} জুড়ে দ্রুত ডেলিভারি।"
        en = f"🔥 Limited-time offer! Order {product} now. {offer} Fast delivery across {city}."
    elif tone == "friendly":
        bn = f"আপনি কি {product} খুঁজছেন? 😍 আজই অর্ডার করুন, ঘরে বসেই পেয়ে যান। {offer}"
        en = f"Looking for {product}? 😍 Order today and get it delivered to your door. {offer}"
    else:  # premium
        bn = f"গুণগত মানে সেরা {product}। আপনি ডিজার্ভ করেন সেরাটাই। {offer} এখনই অর্ডার করুন।"
        en = f"Premium-quality {product}. You deserve the best. {offer} Order now."
    return Caption(bn=bn.strip(), en=en.strip(), tone=tone)


def generate(brief: dict, n: int = 3) -> list[Caption]:
    settings = get_settings()
    if settings.DRY_RUN or not settings.ANTHROPIC_API_KEY:
        return [_template(brief, _TONES[i % len(_TONES)]) for i in range(n)]

    prompt = (
        f"Brief (JSON):\n{json.dumps(brief, ensure_ascii=False)}\n\n"
        f"Write {n} caption variants with different tones."
    )
    raw = llm.complete(SYSTEM, prompt, max_tokens=900)
    try:
        data = json.loads(raw)
        return [Caption(**c) for c in data][:n]
    except Exception:
        # If the model didn't return clean JSON, fall back to templates.
        return [_template(brief, _TONES[i % len(_TONES)]) for i in range(n)]
