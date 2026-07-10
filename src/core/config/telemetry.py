"""Crash-telemetry settings (docs/TELEMETRY.md).

Unhandled errors are reported to the vendor ingest server so bugs in the wild
get fixed. No user data travels — see the reporter's module docstring for the
exact payload. ``TELEMETRY__ENABLED=false`` opts the installation out.
"""

from __future__ import annotations

from pydantic import BaseModel


class TelemetrySettings(BaseModel):
    enabled: bool = True
    url: str = "https://errors.manual32.online/ingest"
    token: str = ""  # optional shared secret, sent as X-Telemetry-Token
