"""Central configuration, loaded from environment (.env)."""
import os
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # When True, no external API is called; realistic mock data is returned so the
    # whole product is demoable with zero keys. Flip to false in production.
    DRY_RUN: bool = _bool("DRY_RUN", True)

    APP_NAME: str = os.getenv("APP_NAME", "AdSathi")
    BASE_URL: str = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    DB_PATH: str = os.getenv("DB_PATH", "adsathi.db")

    # New users get this many free credits to try the product.
    SIGNUP_FREE_CREDITS: int = int(os.getenv("SIGNUP_FREE_CREDITS", "20"))
    # Credits charged per action.
    CREDITS_PER_IMAGE: int = int(os.getenv("CREDITS_PER_IMAGE", "2"))
    CREDITS_PER_CAPTION_SET: int = int(os.getenv("CREDITS_PER_CAPTION_SET", "1"))
    CREDITS_PER_SCRIPT: int = int(os.getenv("CREDITS_PER_SCRIPT", "2"))
    CREDITS_PER_LAUNCH: int = int(os.getenv("CREDITS_PER_LAUNCH", "5"))
    # BDT price per credit when topping up.
    BDT_PER_CREDIT: int = int(os.getenv("BDT_PER_CREDIT", "10"))

    # LLM
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

    # Images
    IMAGE_PROVIDER: str = os.getenv("IMAGE_PROVIDER", "pollinations")  # pollinations (free) | openai | stub
    IMAGE_API_KEY: str = os.getenv("IMAGE_API_KEY", "")
    IMAGE_MODEL: str = os.getenv("IMAGE_MODEL", "gpt-image-1")

    # Meta / Facebook
    META_APP_ID: str = os.getenv("META_APP_ID", "")
    META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
    META_API_VERSION: str = os.getenv("META_API_VERSION", "v21.0")
    META_OAUTH_REDIRECT: str = os.getenv(
        "META_OAUTH_REDIRECT", "http://127.0.0.1:8000/connect/facebook/callback"
    )
    # Agency-model fallback: a system-user token + ad account you own, used when a
    # client hasn't connected their own account.
    META_AGENCY_TOKEN: str = os.getenv("META_AGENCY_TOKEN", "")
    META_AGENCY_AD_ACCOUNT_ID: str = os.getenv("META_AGENCY_AD_ACCOUNT_ID", "")
    META_AGENCY_PAGE_ID: str = os.getenv("META_AGENCY_PAGE_ID", "")

    # Payments (SSLCommerz: supports bKash, Nagad, cards in Bangladesh)
    PAYMENT_PROVIDER: str = os.getenv("PAYMENT_PROVIDER", "sslcommerz")
    SSLCZ_STORE_ID: str = os.getenv("SSLCZ_STORE_ID", "")
    SSLCZ_STORE_PASS: str = os.getenv("SSLCZ_STORE_PASS", "")
    SSLCZ_SANDBOX: bool = _bool("SSLCZ_SANDBOX", True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
