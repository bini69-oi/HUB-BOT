"""Crash-telemetry settings (docs/TELEMETRY.md).

Unhandled errors are reported to an ingest server so bugs in the wild get fixed.
No user data travels — see the reporter's module docstring for the exact payload.
No URL ships by default: telemetry stays off until ``TELEMETRY__URL`` points at an
ingest server (deploy one from ``telemetry-server/``). ``TELEMETRY__ENABLED=false``
also opts out explicitly.
"""

from __future__ import annotations

from pydantic import BaseModel


class TelemetrySettings(BaseModel):
    enabled: bool = True
    url: str = ""  # ingest endpoint; empty -> telemetry is a no-op
    token: str = ""  # optional shared secret, sent as X-Telemetry-Token
