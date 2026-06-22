"""
Meta Marketing API client.

Builds the Campaign -> Ad Set -> Ad Creative -> Ad hierarchy and reads insights.
Accepts per-client credentials (token / ad account / page) and falls back to your
agency account when a client hasn't connected their own.

DRY_RUN returns realistic mock data so the launch + insights flow is fully testable
with no token. With real credentials (DRY_RUN=false) the same methods call the Graph API.

Safety: ads are created PAUSED by default; activation is a separate explicit step.
"""
from __future__ import annotations
import json
import time
import uuid
from typing import Any, Optional
from ..config import get_settings
from ..schemas import CampaignPlan, Caption, AdImage, LaunchResult

OBJECTIVE_MAP = {
    "traffic": "OUTCOME_TRAFFIC",
    "sales": "OUTCOME_SALES",
    "engagement": "OUTCOME_ENGAGEMENT",
    "leads": "OUTCOME_LEADS",
    "awareness": "OUTCOME_AWARENESS",
}

# Agency ad accounts funded via BDT remittance are typically USD-denominated; convert
# the user's BDT budget to USD minor units (cents) for the API. Rate is configurable.
BDT_PER_USD = 118.0


def _bdt_daily_to_minor(bdt: int) -> int:
    return max(100, round((bdt / BDT_PER_USD) * 100))  # Meta minimum ~ $1/day


class MetaError(RuntimeError):
    pass


class MetaAdsClient:
    def __init__(self, token: Optional[str] = None, ad_account_id: Optional[str] = None,
                 page_id: Optional[str] = None):
        self.s = get_settings()
        self.token = token or self.s.META_AGENCY_TOKEN
        self.ad_account_id = ad_account_id or self.s.META_AGENCY_AD_ACCOUNT_ID
        self.page_id = page_id or self.s.META_AGENCY_PAGE_ID
        self.base = f"https://graph.facebook.com/{self.s.META_API_VERSION}"

    @property
    def is_live(self) -> bool:
        return not self.s.DRY_RUN and bool(self.token) and bool(self.ad_account_id)

    # ---- low level ----
    def _post(self, path: str, data: dict[str, Any]) -> dict:
        import httpx
        data = {**data, "access_token": self.token}
        r = httpx.post(f"{self.base}/{path}", data=data, timeout=60)
        body = r.json()
        if r.status_code >= 400 or "error" in body:
            raise MetaError(json.dumps(body.get("error", body)))
        return body

    def _get(self, path: str, params: dict[str, Any]) -> dict:
        import httpx
        params = {**params, "access_token": self.token}
        r = httpx.get(f"{self.base}/{path}", params=params, timeout=60)
        body = r.json()
        if r.status_code >= 400 or "error" in body:
            raise MetaError(json.dumps(body.get("error", body)))
        return body

    # ---- hierarchy ----
    def upload_image(self, image_bytes: bytes, filename: str = "ad.png") -> str:
        """Upload creative image, return image_hash."""
        import httpx
        files = {"filename": (filename, image_bytes)}
        r = httpx.post(
            f"{self.base}/{self.ad_account_id}/adimages",
            data={"access_token": self.token},
            files=files,
            timeout=120,
        )
        body = r.json()
        if "error" in body:
            raise MetaError(json.dumps(body["error"]))
        return list(body["images"].values())[0]["hash"]

    def create_campaign(self, name: str, objective: str) -> str:
        res = self._post(
            f"{self.ad_account_id}/campaigns",
            {
                "name": name,
                "objective": OBJECTIVE_MAP.get(objective, "OUTCOME_TRAFFIC"),
                "status": "PAUSED",
                "special_ad_categories": json.dumps([]),
            },
        )
        return res["id"]

    def create_ad_set(self, campaign_id: str, plan: CampaignPlan, name: str) -> str:
        aud = plan.audience or {}
        targeting = {
            "geo_locations": {"countries": ["BD"]},
            "age_min": aud.get("age_min", 18),
            "age_max": aud.get("age_max", 45),
            "publisher_platforms": ["facebook", "instagram"],
        }
        optimization = "OFFSITE_CONVERSIONS" if plan.objective == "sales" else "LINK_CLICKS"
        res = self._post(
            f"{self.ad_account_id}/adsets",
            {
                "name": name,
                "campaign_id": campaign_id,
                "daily_budget": _bdt_daily_to_minor(plan.daily_budget_bdt),
                "billing_event": "IMPRESSIONS",
                "optimization_goal": optimization if plan.objective != "sales" else "LINK_CLICKS",
                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                "targeting": json.dumps(targeting),
                "status": "PAUSED",
            },
        )
        return res["id"]

    def create_creative(self, caption: Caption, image_hash: Optional[str], name: str,
                        link: str) -> str:
        link_data: dict[str, Any] = {
            "message": f"{caption.bn}\n\n{caption.en}",
            "link": link,
        }
        if image_hash:
            link_data["image_hash"] = image_hash
        story = {"page_id": self.page_id, "link_data": link_data}
        res = self._post(
            f"{self.ad_account_id}/adcreatives",
            {"name": name, "object_story_spec": json.dumps(story)},
        )
        return res["id"]

    def create_ad(self, ad_set_id: str, creative_id: str, name: str) -> str:
        res = self._post(
            f"{self.ad_account_id}/ads",
            {
                "name": name,
                "adset_id": ad_set_id,
                "creative": json.dumps({"creative_id": creative_id}),
                "status": "PAUSED",
            },
        )
        return res["id"]

    def set_status(self, obj_id: str, status: str) -> None:
        self._post(obj_id, {"status": status})

    def insights(self, ad_id: str) -> dict:
        if not self.is_live:
            return {"impressions": 0, "reach": 0, "spend": "0", "clicks": 0,
                    "note": "dry-run: connect a real account to see live metrics"}
        data = self._get(
            f"{ad_id}/insights",
            {"fields": "impressions,reach,spend,clicks,cpc,ctr"},
        )
        rows = data.get("data", [])
        return rows[0] if rows else {"impressions": 0, "reach": 0, "spend": "0"}

    # ---- orchestrated launch ----
    def launch(self, plan: CampaignPlan, caption: Caption, image: AdImage,
               image_bytes: Optional[bytes] = None, link: str = "https://example.com",
               activate: bool = False) -> LaunchResult:
        name = f"AdSathi {time.strftime('%Y-%m-%d %H:%M')}"

        if not self.is_live:
            tag = uuid.uuid4().hex[:8]
            return LaunchResult(
                dry_run=True,
                status="ACTIVE" if activate else "PAUSED",
                campaign_id=f"dryrun_camp_{tag}",
                ad_set_id=f"dryrun_adset_{tag}",
                creative_id=f"dryrun_creative_{tag}",
                ad_id=f"dryrun_ad_{tag}",
                review_status="PENDING_REVIEW",
                notes=[
                    "DRY RUN: no Meta API call was made.",
                    f"Objective -> {OBJECTIVE_MAP.get(plan.objective, 'OUTCOME_TRAFFIC')}",
                    f"Daily budget {plan.daily_budget_bdt} BDT "
                    f"(~{_bdt_daily_to_minor(plan.daily_budget_bdt)/100:.2f} USD).",
                    "Set DRY_RUN=false + connect a real ad account to launch for real.",
                ],
            )

        image_hash = self.upload_image(image_bytes) if image_bytes else None
        camp = self.create_campaign(name, plan.objective)
        adset = self.create_ad_set(camp, plan, name)
        creative = self.create_creative(caption, image_hash, name, link)
        ad = self.create_ad(adset, creative, name)
        if activate:
            self.set_status(adset, "ACTIVE")
            self.set_status(ad, "ACTIVE")
        return LaunchResult(
            dry_run=False,
            status="ACTIVE" if activate else "PAUSED",
            campaign_id=camp, ad_set_id=adset, creative_id=creative, ad_id=ad,
            review_status="PENDING_REVIEW",
            notes=["Created via Meta Marketing API."],
        )
