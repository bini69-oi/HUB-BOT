"""VPN-client connection deep links (shared by the mini-app cabinet API and the bot)."""

from __future__ import annotations

# Import schemes for the popular clients. Keys are stable identifiers used by both surfaces.
CLIENT_LABELS: dict[str, str] = {
    "happ": "Happ",
    "v2raytun": "v2RayTun",
    "hiddify": "Hiddify",
    "streisand": "Streisand",
}


def build_deep_links(subscription_url: str, crypto_link: str | None = None) -> dict[str, str]:
    """One-tap import links per client from a Remnawave subscription URL.

    Happ prefers the panel-provided crypto (happ) link when present.
    """
    return {
        "happ": crypto_link or f"happ://add/{subscription_url}",
        "v2raytun": f"v2raytun://import/{subscription_url}",
        "hiddify": f"hiddify://import/{subscription_url}",
        "streisand": f"streisand://import/{subscription_url}",
    }
