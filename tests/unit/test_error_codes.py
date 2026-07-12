"""E-коды: классификация исключений и формат error_id."""

from __future__ import annotations

from src.core.error_codes import UNCLASSIFIED, all_codes, classify, format_error_id
from src.core.exceptions import (
    GatewayNotConfigured,
    PurchaseError,
    RemnawaveTransientError,
    TrialNotAvailable,
    WebhookVerificationError,
)


def test_domain_subclass_wins_over_base() -> None:
    assert classify(TrialNotAvailable("no")).code == 3002
    assert classify(PurchaseError("generic")).code == 3001
    assert classify(WebhookVerificationError("sig")).code == 4003
    assert classify(GatewayNotConfigured("off")).code == 4002
    assert classify(RemnawaveTransientError("503")).code == 5003


def test_unknown_exception_is_unclassified() -> None:
    assert classify(RuntimeError("boom")) is UNCLASSIFIED
    assert classify(ValueError("bad")) is UNCLASSIFIED


def test_builtin_timeouts_and_connections() -> None:
    assert classify(TimeoutError("slow")).code == 1402
    assert classify(ConnectionResetError("rst")).code == 1401


def test_external_matched_by_module_without_import() -> None:
    exc_type = type("OperationalError", (Exception,), {"__module__": "sqlalchemy.exc"})
    assert classify(exc_type("db down")).code == 1201
    retry = type("TelegramRetryAfter", (Exception,), {"__module__": "aiogram.exceptions"})
    assert classify(retry("429")).code == 6002
    other_tg = type("TelegramServerError", (Exception,), {"__module__": "aiogram.exceptions"})
    assert classify(other_tg("502")).code == 6001


def test_httpx_timeout_subclass_beats_module_catchall() -> None:
    # httpx на практике бросает подклассы (ReadTimeout и т.п.), не сам TimeoutException —
    # специфичное правило 1402 обязано выиграть у catch-all 1401 того же модуля.
    base = type("TimeoutException", (Exception,), {"__module__": "httpx"})
    read_timeout = type("ReadTimeout", (base,), {"__module__": "httpx"})
    assert classify(read_timeout("slow read")).code == 1402
    transport_err = type("ConnectError", (Exception,), {"__module__": "httpx"})
    assert classify(transport_err("refused")).code == 1401


def test_format_error_id() -> None:
    assert format_error_id(RuntimeError("x"), "1a2b3c4d") == "E9001-1a2b3c4d"
    assert format_error_id(TrialNotAvailable("x"), "deadbeef") == "E3002-deadbeef"


def test_registry_has_no_conflicting_codes() -> None:
    # Инвариант реестра (all_codes() дедупит, поэтому проверяем сырые структуры):
    # один номер не может описывать две разные ошибки.
    from src.core import error_codes as ec

    mapping: dict[int, object] = {}
    for c in (
        *ec._SYSTEM,
        *ec._DOMAIN_CODES.values(),
        *(code for *_, code in ec._EXTERNAL_CODES),
        ec.UNCLASSIFIED,
    ):
        assert mapping.setdefault(c.code, c) is c, f"код {c.code} назначен двум разным ошибкам"
    # каждый код полностью расписан для справочника
    for c in all_codes():
        assert c.title and c.meaning and c.action
