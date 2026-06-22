"""
Ad image generation (provider-agnostic).

Production pipeline (see PLAN.md): generate a clean background/product image with an AI
image API, THEN composite the Bangla headline as a real text layer (Pillow + a Bengali
font) because diffusion models render Bengali script poorly.

DRY_RUN / stub: produce a self-contained SVG mockup (already shows the AI-background +
real-text-layer composite) so the chat flow is testable with no keys.
provider=openai: call OpenAI Images, get a PNG, optionally composite the headline.
"""
from __future__ import annotations
import base64
import io
from typing import Optional
from ..config import get_settings
from ..schemas import AdImage

_PALETTE = ["#0F766E", "#7C3AED", "#B91C1C", "#1D4ED8", "#C2410C"]


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
  <text x='90' y='130' font-family='Arial, sans-serif' font-size='28' fill='#ffffff' opacity='0.7'>[AI-generated background mockup]</text>
</svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _composite_headline(png_bytes: bytes, headline_bn: str) -> bytes:
    """Overlay a Bangla headline as a real text layer. No-op if Pillow/font missing."""
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
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return png_bytes


def _openai_image(prompt: str) -> bytes:
    from openai import OpenAI
    s = get_settings()
    client = OpenAI(api_key=s.IMAGE_API_KEY)
    res = client.images.generate(model=s.IMAGE_MODEL, prompt=prompt, size="1024x1024")
    return base64.b64decode(res.data[0].b64_json)


def generate(brief: dict, n: int = 1) -> list[AdImage]:
    s = get_settings()
    product = brief.get("product", "Product")
    headline_bn = (brief.get("offer") or "বিশেষ অফার!")[:30]
    headline_en = "Special Offer!"
    base_prompt = (
        f"High-quality advertising photo of {product}, clean studio lighting, vibrant, "
        f"e-commerce hero shot, empty space at the bottom for a text overlay, no text in image"
    )

    if s.DRY_RUN or s.IMAGE_PROVIDER == "stub" or not s.IMAGE_API_KEY:
        return [
            AdImage(url=_svg_mockup(headline_bn, headline_en, product, i), prompt=base_prompt,
                    headline_bn=headline_bn, headline_en=headline_en)
            for i in range(n)
        ]

    if s.IMAGE_PROVIDER == "openai":
        out = []
        for _ in range(n):
            raw = _openai_image(base_prompt)
            composed = _composite_headline(raw, headline_bn)
            b64 = base64.b64encode(composed).decode("ascii")
            out.append(AdImage(
                url=f"data:image/png;base64,{b64}", prompt=base_prompt,
                headline_bn=headline_bn, headline_en=headline_en, png_b64=b64,
            ))
        return out

    raise NotImplementedError(f"Image provider '{s.IMAGE_PROVIDER}' not wired up.")


def bytes_for(image: AdImage) -> Optional[bytes]:
    """Return raster bytes suitable for Meta upload, or None (e.g. SVG dry-run mockup)."""
    if image.png_b64:
        return base64.b64decode(image.png_b64)
    return None


def generate_for(profile: dict, prompt: str, n: int = 1):
    """Generate ad image(s) from the business profile + a free-form description."""
    product = (profile or {}).get("products") or prompt or "Product"
    brief = {"product": product, "offer": (prompt or "")[:30]}
    return generate(brief, n)
