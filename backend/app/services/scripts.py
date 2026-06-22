"""
Video-ad shooting-script generator (bilingual).

Produces a structured script the user can film themselves: a hook, a shot list (each shot
has what to film, on-screen text, and bilingual voiceover), and a call to action — grounded
in the user's saved business profile.

DRY_RUN: deterministic template built from the profile + topic (works with no keys).
Real mode: Claude, prompted with the profile and topic.
"""
from __future__ import annotations
import json
from ..config import get_settings
from .. import llm

SYSTEM = (
    "You are a Bangladeshi short-form video ad director. Given a business profile and an ad "
    "topic, write a concise, shoot-ready script for a 20-30s vertical video ad. Be culturally "
    "native. Return strict JSON with keys: title, duration_seconds, hook_bn, hook_en, "
    "shots (list of {scene, on_screen_text, voiceover_bn, voiceover_en, seconds}), "
    "cta_bn, cta_en, music."
)


def _template(profile: dict, topic: str) -> dict:
    biz = (profile or {}).get("business_name") or "আপনার ব্র্যান্ড"
    product = (profile or {}).get("products") or topic or "পণ্য"
    city = (profile or {}).get("city") or "বাংলাদেশ"
    return {
        "title": f"{topic or product} — video ad",
        "duration_seconds": 25,
        "hook_bn": f"এই {product} না দেখলে মিস করবেন! 😮",
        "hook_en": f"You don't want to miss this {product}!",
        "shots": [
            {
                "scene": f"Close-up of the {product}, slow rotation, bright natural light.",
                "on_screen_text": f"{biz}",
                "voiceover_bn": f"{biz} নিয়ে এলো দারুণ {product}।",
                "voiceover_en": f"{biz} brings you amazing {product}.",
                "seconds": 5,
            },
            {
                "scene": "A happy customer using/wearing the product, smiling at camera.",
                "on_screen_text": "১০০% কোয়ালিটি গ্যারান্টি",
                "voiceover_bn": "গুণগত মানে সেরা, দামেও সাশ্রয়ী।",
                "voiceover_en": "Top quality, and easy on the pocket.",
                "seconds": 8,
            },
            {
                "scene": f"Phone screen showing an order being placed; delivery box with {city} backdrop.",
                "on_screen_text": "সারা দেশে ডেলিভারি",
                "voiceover_bn": f"{city} সহ সারা দেশে দ্রুত হোম ডেলিভারি।",
                "voiceover_en": f"Fast home delivery across {city} and beyond.",
                "seconds": 7,
            },
            {
                "scene": "Logo + offer card, bold text, upbeat ending.",
                "on_screen_text": "এখনই অর্ডার করুন",
                "voiceover_bn": "আজই অর্ডার করুন, লিমিটেড স্টক!",
                "voiceover_en": "Order today — limited stock!",
                "seconds": 5,
            },
        ],
        "cta_bn": "📲 অর্ডার করতে ইনবক্স করুন বা কল করুন।",
        "cta_en": "📲 DM us or call to order now.",
        "music": "Upbeat, modern Bangladeshi pop / trending reel audio.",
    }


def generate(profile: dict, topic: str) -> dict:
    s = get_settings()
    if s.DRY_RUN or not s.ANTHROPIC_API_KEY:
        return _template(profile, topic)
    prompt = (
        f"Business profile (JSON):\n{json.dumps(profile, ensure_ascii=False)}\n\n"
        f"Ad topic / idea: {topic}\n\nWrite the shooting script now."
    )
    raw = llm.complete(SYSTEM, prompt, max_tokens=1200)
    try:
        return json.loads(raw)
    except Exception:
        return _template(profile, topic)
