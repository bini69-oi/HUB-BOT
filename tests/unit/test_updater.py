"""Update checker: compares our build SHA to GitHub's latest commit. Fail-soft everywhere."""

from __future__ import annotations

import httpx
import respx

from src.infrastructure.services.updater import check_for_update

_URL = "https://api.github.com/repos/acme/bot/commits/main"


def _commit(sha: str, msg: str = "feat: thing\n\nbody") -> dict[str, object]:
    return {"sha": sha, "commit": {"message": msg}}


@respx.mock
async def test_update_available_when_sha_differs() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json=_commit("b" * 40)))
    info = await check_for_update("acme/bot", "main", "a" * 12)
    assert info.available is True
    assert info.latest == "b" * 12
    assert info.current == "a" * 12
    assert info.message == "feat: thing"
    assert "compare" in info.url


@respx.mock
async def test_no_update_when_sha_matches() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json=_commit("a" * 40)))
    info = await check_for_update("acme/bot", "main", "a" * 12)
    assert info.available is False
    assert info.latest == "a" * 12


@respx.mock
async def test_unknown_local_sha_surfaces_update() -> None:
    # An image built without the build-arg (build_sha="") should still surface an update.
    respx.get(_URL).mock(return_value=httpx.Response(200, json=_commit("c" * 40)))
    info = await check_for_update("acme/bot", "main", "")
    assert info.available is True
    assert "commit/" in info.url  # no compare base → link the commit


@respx.mock
async def test_network_error_is_soft() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("down"))
    info = await check_for_update("acme/bot", "main", "a" * 12)
    assert info.available is False and info.latest == ""


@respx.mock
async def test_non_200_is_soft() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(404))
    info = await check_for_update("acme/bot", "main", "a" * 12)
    assert info.available is False


async def test_bad_repo_is_soft() -> None:
    info = await check_for_update("", "main", "a" * 12)
    assert info.available is False and info.latest == ""
