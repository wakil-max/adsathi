"""
Ad image generation (provider-agnostic).

Two ways to generate:
  - WITH a prompt: the user describes the image.
  - WITHOUT a prompt ("auto"): AdSathi writes the image prompt from the business profile
    (via Claude if a key is present, else a smart template), so the user doesn't have to.

Provider: set IMAGE_PROVIDER=openai + IMAGE_API_KEY to use the real API (gpt-image-1 or
dall-e-3). This is decoupled from DRY_RUN, so you can switch ONLY images to real without
turning on everything else. With no key it returns a self-contained SVG mockup so the flow
stays demoable.

Production pipeline: generate a clean background with the image API, then composite the
Bangla headline as a real text layer (Pillow) — diffusion models render Bengali poorly.
"""
from __future__ import annotations
import base64
import io
import random
from typing import Optional
from ..config import get_settings
from ..schemas import AdImage
from .. import llm

_PALETTE = ["#0F766E", "#7C3AED", "#B91C1C", "#1D4ED8", "#C2410C"]
_STYLES = [
    "clean studio product shot, soft shadows, seamless background",
    "lifestyle scene, natural daylight, real Bangladeshi setting",
    "flat-lay top view, neat props, pastel background",
    "dramatic spotlight on the product, dark moody background",
    "outdoor street-style shot, vibrant city backdrop",
]

_PROMPT_SYSTEM = (
    "You write concise text-to-image prompts for product ads. Given a business profile, "
    "output ONE vivid prompt (max 40 words) for a high-converting ad photo of their product. "
    "No text in the image, leave space at the bottom for an overlay. Output only the prompt."
)


def _use_real() -> bool:
    s = get_settings()
    return s.IMAGE_PROVIDER == "openai" and bool(s.IMAGE_API_KEY)


def auto_prompt(profile: dict) -> str:
    """Build an image prompt from the business profile (no user input needed)."""
    s = get_settings()
    product = (profile or {}).get("products") or "the product"
    industry = (profile or {}).get("industry") or ""
    if not s.DRY_RUN and s.ANTHROPIC_API_KEY:
        import json
        try:
            p = llm.complete(_PROMPT_SYSTEM, json.dumps(profile, ensure_ascii=False), max_tokens=120)
            if p and "[dry-run" not in p:
                return p.strip()
        except Exception:
            pass
    style = random.choice(_STYLES)
    extra = f" for a {industry} brand" if industry else ""
    return (f"High-quality advertising photo of {product}{extra}, {style}, vibrant, "
            f"e-commerce hero shot, empty space at the bottom for a text overlay, no text in image")


def _svg_mockup(headline_bn: str, headline_en: str, product: str, seed: int) -> str:
    c1 = _PALETTE[seed % len(_PALETTE)]
    c2 = _PALETTE[(seed + 2) % len(_PALETTE)]
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='1080' height='1080'>
  <defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
    <stop offset='0%' stop-color='{c1}'/><stop offset='100%' stop-color='{c2}'/></linearGradient></defs>
  <rect width='1080' height='1080' fill='url(#g)'/>
  <circle cx='820' cy='300' r='220' fill='#ffffff' opacity='0.10'/>
  <rect x='60' y='720' width='960' height='300' rx='28' fill='#000000' opacity='0.32'/>
  <text x='90' y='815' font-family='Noto Sans Bengali, sans-serif' font-size='62' font-weight='700' fill='#ffffff'>{headline_bn}</text>
  <text x='90' y='890' font-family='Arial, sans-serif' font-size='40' fill='#FDE68A'>{headline_en}</text>
  <text x='90' y='965' font-family='Arial, sans-serif' font-size='30' fill='#ffffff' opacity='0.85'>AdSathi - {product}</text>
  <text x='90' y='130' font-family='Arial, sans-serif' font-size='26' fill='#ffffff' opacity='0.7'>[demo mockup - add IMAGE_API_KEY for real photos]</text>
</svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _composite_headline(png_bytes: bytes, headline_bn: str) -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return png_bytes
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")
        w, h = img.size
        draw.rectangle([(0, int(h * 0.72)), (w, h)], fill=(0, 0, 0, 110))
        try:
            font = ImageFont.truetype("NotoSansBengali-Bold.ttf", int(h * 0.06))
        except Exception:
            font = ImageFont.load_default()
        draw.text((int(w * 0.06), int(h * 0.78)), headline_bn, font=font, fill=(255, 255, 255))
        out = io.BytesIO(); img.save(out, format="PNG"); return out.getvalue()
    except Exception:
        return png_bytes


def _openai_image(prompt: str) -> bytes:
    from openai import OpenAI
    s = get_settings()
    client = OpenAI(api_key=s.IMAGE_API_KEY)
    kwargs = {"model": s.IMAGE_MODEL, "prompt": prompt, "size": "1024x1024"}
    if s.IMAGE_MODEL.startswith("dall-e"):
        kwargs["response_format"] = "b64_json"   # gpt-image-1 returns b64 by default
    res = client.images.generate(**kwargs)
    return base64.b64decode(res.data[0].b64_json)


def _pollinations_url(prompt: str) -> str:
    """Free, key-less image generation (pollinations.ai). Returns a direct image URL."""
    import urllib.parse, random
    q = urllib.parse.quote((prompt or "product photo")[:300])
    seed = random.randint(1, 1_000_000)
    return (f"https://image.pollinations.ai/prompt/{q}"
            f"?width=1024&height=1024&nologo=true&model=flux&seed={seed}")


def generate(profile: dict, prompt: str, headline_bn: str = "বিশেষ অফার!",
             headline_en: str = "Special Offer!", n: int = 1) -> list[AdImage]:
    s = get_settings()
    product = (profile or {}).get("products") or "Product"

    # Free, no-key provider — works immediately, renders client-side from a URL.
    if s.IMAGE_PROVIDER == "pollinations":
        return [AdImage(url=_pollinations_url(prompt), prompt=prompt,
                        headline_bn=headline_bn[:30], headline_en=headline_en)
                for _ in range(n)]

    # Paid provider (OpenAI) — adds a real Bangla headline text layer.
    if s.IMAGE_PROVIDER == "openai" and s.IMAGE_API_KEY:
        out = []
        for _ in range(n):
            raw = _openai_image(prompt)
            composed = _composite_headline(raw, headline_bn[:30])
            b64 = base64.b64encode(composed).decode("ascii")
            out.append(AdImage(url=f"data:image/png;base64,{b64}", prompt=prompt,
                               headline_bn=headline_bn[:30], headline_en=headline_en, png_b64=b64))
        return out

    # Fallback: self-contained SVG mockup.
    return [AdImage(url=_svg_mockup(headline_bn[:30], headline_en, product, random.randint(0, 9)),
                    prompt=prompt, headline_bn=headline_bn[:30], headline_en=headline_en)
            for _ in range(n)]


# Back-compat helper used by the router.
def generate_for(profile: dict, prompt: str, n: int = 1):
    return generate(profile, prompt, n=n)


def bytes_for(image: AdImage) -> Optional[bytes]:
    if image.png_b64:
        return base64.b64decode(image.png_b64)
    return None
