"""Panel write-payload shaping (_spec_payload).

Guards the resync/migration outage bug: an empty internal-squad list must be OMITTED,
never sent as ``activeInternalSquads: []`` (which REPLACES the panel set with none and
disconnects the user from every server).
"""

from __future__ import annotations

import datetime as dt

from src.application.dto.panel import ProvisionSpec
from src.infrastructure.remnawave.client import _spec_payload


def _spec(**kw: object) -> ProvisionSpec:
    base: dict[str, object] = {
        "short_id": "abc123",
        "telegram_id": 42,
        "username": "sub_abc123",
        "expire_at": dt.datetime(2030, 1, 1, tzinfo=dt.UTC),
        "traffic_limit_bytes": 0,
        "device_limit": 3,
    }
    base.update(kw)
    return ProvisionSpec(**base)  # type: ignore[arg-type]


def test_empty_squads_are_omitted_not_wiped() -> None:
    payload = _spec_payload(_spec(internal_squads=()))
    assert "activeInternalSquads" not in payload  # empty ⇒ leave the panel set alone


def test_non_empty_squads_are_sent() -> None:
    payload = _spec_payload(_spec(internal_squads=("squad-a", "squad-b")))
    assert payload["activeInternalSquads"] == ["squad-a", "squad-b"]


def test_device_limit_and_external_squad_follow_omit_semantics() -> None:
    # None/falsy ⇒ omit (leave alone); concrete ⇒ send.
    p = _spec_payload(_spec(device_limit=None, external_squad=None))
    assert "hwidDeviceLimit" not in p
    assert "externalSquadUuid" not in p
    p2 = _spec_payload(_spec(device_limit=5, external_squad="ext-1"))
    assert p2["hwidDeviceLimit"] == 5
    assert p2["externalSquadUuid"] == "ext-1"
