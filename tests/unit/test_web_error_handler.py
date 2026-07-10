"""Web last-resort handler: clean JSON 500 with error id, reported to telemetry."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from fastapi import Request

from src.web.app import unhandled_error_handler


class _RecordingTelemetry:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def report(
        self, exc: BaseException, *, source: str, context: dict[str, Any] | None = None
    ) -> str:
        self.calls.append({"exc": exc, "source": source, "context": context})
        return "Eabc123-dead"


def _request(app: Any) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/cabinet/purchase",
        "headers": [],
        "query_string": b"",
        "app": app,
    }
    return Request(scope)


async def test_returns_json_500_with_error_id_and_reports() -> None:
    telemetry = _RecordingTelemetry()
    app = SimpleNamespace(state=SimpleNamespace(container=SimpleNamespace(telemetry=telemetry)))
    exc = RuntimeError("boom")

    response = await unhandled_error_handler(_request(app), exc)

    assert response.status_code == 500
    body = json.loads(bytes(response.body))
    assert body["ok"] is False
    assert body["error_id"] == "Eabc123-dead"
    assert "boom" not in json.dumps(body)  # no stack/exception details leak to the client
    call = telemetry.calls[0]
    assert call["source"] == "web"
    # The route template, not the concrete path (no ids leak); scope has no matched route here.
    assert call["context"] == {"endpoint": "unmatched", "method": "POST"}


async def test_survives_missing_container() -> None:
    app = SimpleNamespace(state=SimpleNamespace())  # lifespan not started yet
    response = await unhandled_error_handler(_request(app), RuntimeError("boom"))
    assert response.status_code == 500
    assert json.loads(bytes(response.body))["error_id"] == ""
