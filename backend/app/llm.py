"""Thin LLM wrapper. Falls back to deterministic templates in DRY_RUN."""
from __future__ import annotations
from .config import get_settings


def complete(system: str, prompt: str, max_tokens: int = 800) -> str:
    """Return model text. In DRY_RUN this is never called for real."""
    settings = get_settings()
    if settings.DRY_RUN or not settings.ANTHROPIC_API_KEY:
        return "[dry-run: LLM disabled]"
    # Real provider (only runs when keys present and DRY_RUN=false).
    if settings.LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    raise NotImplementedError(f"LLM provider {settings.LLM_PROVIDER} not wired up")
