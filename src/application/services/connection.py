"""VPN-client connection deep links (shared by the mini-app cabinet API and the bot)."""

from __future__ import annotations

from typing import Any

# Import schemes for the popular clients. Keys are stable identifiers used by both surfaces.
CLIENT_LABELS: dict[str, str] = {
    "happ": "Happ",
    "v2raytun": "v2RayTun",
    "hiddify": "Hiddify",
    "streisand": "Streisand",
}

# Official per-platform download pages for each client. The Connect tab's "download the
# app" button uses these for the OWNER'S configured client (not a hardcoded one), so the
# store link always matches the app the owner set up. ``default`` is the fallback for a
# platform without a dedicated entry. Platform keys: ios / android / macos / windows / linux.
CLIENT_STORES: dict[str, dict[str, str]] = {
    "happ": {
        "ios": "https://apps.apple.com/app/happ-proxy-utility/id6504287215",
        "macos": "https://apps.apple.com/app/happ-proxy-utility/id6504287215",
        "android": "https://play.google.com/store/apps/details?id=com.happproxy",
        "windows": "https://github.com/Happ-proxy/happ-desktop/releases/latest",
        "linux": "https://github.com/Happ-proxy/happ-desktop/releases/latest",
        "default": "https://happ.su/",
    },
    "v2raytun": {
        "ios": "https://apps.apple.com/app/v2raytun/id6476628951",
        "macos": "https://apps.apple.com/app/v2raytun/id6476628951",
        "android": "https://play.google.com/store/apps/details?id=com.v2raytun.android",
        "default": "https://v2raytun.com/",
    },
    "hiddify": {
        "default": "https://github.com/hiddify/hiddify-app/releases/latest",
    },
    "streisand": {
        "ios": "https://apps.apple.com/app/streisand/id6450534064",
        "macos": "https://apps.apple.com/app/streisand/id6450534064",
        "default": "https://apps.apple.com/app/streisand/id6450534064",
    },
}


def store_links(client: str) -> dict[str, str]:
    """Per-platform download links for a client key (empty dict for an unknown key)."""
    return CLIENT_STORES.get(client, {})


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


def parse_enabled_apps(raw: str | None) -> list[str]:
    """Owner setting CONNECTION_APPS ('happ,hiddify') -> ordered list of known client keys.

    Unknown/empty entries are dropped; an empty result falls back to all clients so the
    Connect tab is never left with nothing to import into.
    """
    keys = [k.strip().lower() for k in (raw or "").split(",") if k.strip()]
    enabled = [k for k in keys if k in CLIENT_LABELS]
    return enabled or list(CLIENT_LABELS)


def connection_apps(
    subscription_url: str, crypto_link: str | None, enabled: list[str]
) -> list[dict[str, Any]]:
    """Per-app entries (key, label, deep_link, stores) for enabled clients, in owner order."""
    links = build_deep_links(subscription_url, crypto_link)
    return [
        {
            "key": k,
            "label": CLIENT_LABELS[k],
            "deep_link": links[k],
            "stores": CLIENT_STORES.get(k, {}),
        }
        for k in enabled
        if k in links
    ]
