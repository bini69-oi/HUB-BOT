"""Crash telemetry: ship unhandled errors to the vendor ingest server.

Fire-and-forget by design: :meth:`TelemetryReporter.report` only enqueues (it
never blocks, never raises, never touches the DB) and a background task batches
and sends. What travels: exception class, message, a path-relativized traceback,
a small caller-supplied context dict, the app version and an anonymous install
id (a hash of the bot token) — no user data, no secrets, everything size-capped.
``TELEMETRY__ENABLED=false`` turns it into a no-op; :meth:`report` still returns
an error id so user-facing "код ошибки" messages keep working.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import re
import traceback
from contextlib import suppress
from typing import Any

import httpx

from src.core.logging import get_logger

log = get_logger(__name__)

_FLUSH_INTERVAL = 30.0
_MAX_PENDING_FINGERPRINTS = 50
_MAX_TRACEBACK = 8_000
_MAX_MESSAGE = 500
_MAX_CONTEXT_KEYS = 10
_MAX_BACKOFF = 600.0
_SEND_TIMEOUT = 5.0

# `File "/abs/path/to/src/foo.py"` -> `File "src/foo.py"` (same for site-packages).
_PATH_RE = re.compile(r'File "([^"]+)"')

# --- PII/secret scrubbing (defense in depth) -------------------------------
# str(exc) and tracebacks can carry user data and secrets (SQLAlchemy appends bound
# parameters, error messages quote emails/ids/tokens). These strip the worst offenders
# before anything leaves the process. The panel also runs with hide_parameters=True.
_SQLA_TAIL_RE = re.compile(r"\n?\[(?:SQL|parameters|cached since)[^\]]*\][^\n]*", re.IGNORECASE)
_ABS_PATH_RE = re.compile(r"(?:/(?:Users|home|root)/[^\s'\"]+|[A-Za-z]:\\\\[^\s'\"]+)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")  # telegram bot token shape
_LONG_DIGITS_RE = re.compile(r"\b\d{6,}\b")  # telegram ids, payment ids, card-ish runs


def _rel_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    for marker in ("/src/", "/site-packages/"):
        if marker in normalized:
            return marker.lstrip("/") + normalized.rsplit(marker, 1)[1]
    return normalized.rsplit("/", 1)[-1]


def _scrub(text: str) -> str:
    """Redact secrets/PII from free-form error text before it leaves the box."""
    text = _SQLA_TAIL_RE.sub("", text)  # drop SQLAlchemy '[SQL: ...] [parameters: ...]'
    text = _TOKEN_RE.sub("<token>", text)
    text = _EMAIL_RE.sub("<email>", text)
    text = _ABS_PATH_RE.sub(lambda m: _rel_path(m.group(0)), text)
    text = _LONG_DIGITS_RE.sub("<id>", text)
    return text


def fingerprint(exc: BaseException) -> str:
    """Stable issue key: exception type + our frames (file:func, no line numbers)."""
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in frames if "/src/" in f.filename.replace("\\", "/")] or frames
    parts = [f"{_rel_path(f.filename)}:{f.name}" for f in ours[-5:]]
    raw = type(exc).__name__ + "|" + "|".join(parts)
    return hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:16]


def _format_traceback(exc: BaseException) -> str:
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    text = _PATH_RE.sub(lambda m: f'File "{_rel_path(m.group(1))}"', text)
    return _scrub(text)[-_MAX_TRACEBACK:]


def install_id_from_token(bot_token: str) -> str:
    """Anonymous, stable per-installation id (not reversible, same in all processes)."""
    raw = f"hubbot:{bot_token or 'tokenless'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class TelemetryReporter:
    def __init__(
        self,
        *,
        enabled: bool,
        url: str,
        app_version: str,
        install_id: str,
        token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._enabled = enabled and bool(url)
        self._url = url
        self._token = token
        self._version = app_version
        self._install_id = install_id
        self._transport = transport
        self._http: httpx.AsyncClient | None = None
        self._pending: dict[str, dict[str, Any]] = {}  # fingerprint -> event (count merges)
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._closing = False
        self._backoff = _FLUSH_INTERVAL

    # -- public ------------------------------------------------------------
    def report(
        self, exc: BaseException, *, source: str, context: dict[str, Any] | None = None
    ) -> str:
        """Queue one error, return a short id the user can quote to support.

        The id is deterministic per bug (``E<fingerprint>``): every occurrence shows
        the same id, and it maps to the issue on the dashboard even though repeat
        occurrences merge into a count client-side rather than being sent again.
        """
        fp = fingerprint(exc)
        error_id = f"E{fp[:8]}"
        if not self._enabled or self._closing:
            return error_id
        try:
            pending = self._pending.get(fp)
            if pending is not None:
                pending["count"] += 1
            elif len(self._pending) < _MAX_PENDING_FINGERPRINTS:
                self._pending[fp] = {
                    "error_id": error_id,
                    "fingerprint": fp,
                    "source": source,
                    "exc_type": type(exc).__name__,
                    "message": _scrub(str(exc))[:_MAX_MESSAGE],
                    "traceback": _format_traceback(exc),
                    "context": {
                        str(k)[:64]: _scrub(str(v))[:200]
                        for k, v in list((context or {}).items())[:_MAX_CONTEXT_KEYS]
                    },
                    "count": 1,
                    "ts": dt.datetime.now(dt.UTC).isoformat(),
                }
            self._ensure_task()
        except Exception:
            log.debug("telemetry enqueue failed", exc_info=True)
        return error_id

    async def flush(self) -> None:
        """Send whatever is queued right now (used by tests and aclose)."""
        if not self._pending:
            return
        events = list(self._pending.values())
        self._pending = {}
        payload = {"install_id": self._install_id, "version": self._version, "events": events}
        headers = {"X-Telemetry-Token": self._token} if self._token else {}
        try:
            if self._http is None:
                self._http = httpx.AsyncClient(timeout=_SEND_TIMEOUT, transport=self._transport)
            resp = await self._http.post(self._url, json=payload, headers=headers)
            resp.raise_for_status()
            self._backoff = _FLUSH_INTERVAL
        except Exception as exc:
            # Put events back (merged) and retry later with backoff.
            for event in events:
                kept = self._pending.get(event["fingerprint"])
                if kept is not None:
                    kept["count"] += int(event["count"])
                elif len(self._pending) < _MAX_PENDING_FINGERPRINTS:
                    self._pending[event["fingerprint"]] = event
            self._backoff = min(self._backoff * 2, _MAX_BACKOFF)
            log.debug("telemetry send failed", error=str(exc))

    async def aclose(self) -> None:
        self._closing = True
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._task
        with suppress(Exception):
            await asyncio.wait_for(self.flush(), timeout=_SEND_TIMEOUT)
        if self._http is not None:
            await self._http.aclose()

    # -- internals -----------------------------------------------------------
    def _ensure_task(self) -> None:
        if self._task is None or self._task.done():
            loop = asyncio.get_running_loop()  # raises outside a loop -> caught by report()
            self._task = loop.create_task(self._run(), name="telemetry-sender")
        self._wake.set()

    async def _run(self) -> None:
        # Wake early on new reports, otherwise poll every backoff interval;
        # flush() is a no-op when the queue is empty.
        while not self._closing:
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=self._backoff)
            self._wake.clear()
            if self._closing:
                return
            if self._pending:
                # Settle delay: an error storm merges into per-fingerprint counts
                # instead of one HTTP call per occurrence.
                await asyncio.sleep(3.0)
                await self.flush()
