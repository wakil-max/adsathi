"""Data models — pure stdlib dataclasses (no pydantic, no install required)."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict, is_dataclass
from typing import Any, Optional


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatRequest:
    message: str
    history: list = field(default_factory=list)
    brief: dict = field(default_factory=dict)


@dataclass
class Caption:
    bn: str
    en: str
    tone: str


@dataclass
class AdImage:
    url: str
    prompt: str
    headline_bn: Optional[str] = None
    headline_en: Optional[str] = None
    # Raster bytes (base64 PNG) for uploading to Meta. None for the SVG dry-run mockup.
    png_b64: Optional[str] = None


@dataclass
class CampaignPlan:
    objective: str
    audience: dict
    placements: list
    daily_budget_bdt: int
    schedule_days: int
    page_id: Optional[str] = None


@dataclass
class ChatResponse:
    reply: str
    brief: dict
    captions: list = field(default_factory=list)
    images: list = field(default_factory=list)
    campaign_plan: Optional[CampaignPlan] = None
    ready_to_launch: bool = False


@dataclass
class LaunchResult:
    dry_run: bool
    status: str
    campaign_id: str
    ad_set_id: str
    creative_id: str
    ad_id: str
    review_status: str
    notes: list = field(default_factory=list)


# ---------- helpers ----------
def jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses/lists/dicts into JSON-serialisable structures."""
    if is_dataclass(obj):
        return {k: jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    return obj


def caption_from(d: dict) -> Caption:
    return Caption(bn=d.get("bn", ""), en=d.get("en", ""), tone=d.get("tone", ""))


def image_from(d: dict) -> AdImage:
    return AdImage(
        url=d.get("url", ""), prompt=d.get("prompt", ""),
        headline_bn=d.get("headline_bn"), headline_en=d.get("headline_en"),
        png_b64=d.get("png_b64"),
    )


def plan_from(d: dict) -> CampaignPlan:
    return CampaignPlan(
        objective=d.get("objective", "traffic"),
        audience=d.get("audience", {}) or {},
        placements=d.get("placements", []) or [],
        daily_budget_bdt=int(d.get("daily_budget_bdt", 0) or 0),
        schedule_days=int(d.get("schedule_days", 7) or 7),
        page_id=d.get("page_id"),
    )
