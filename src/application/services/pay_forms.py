"""Per-form payment routing — one gateway, several provider-side methods.

Some providers (Platega) can charge through more than one distinct method (СБП QR vs
card acquiring vs crypto). Instead of a single fixed method per gateway, the owner
enables the forms they want and each becomes its own payment button; the chosen form
travels to the gateway in ``PaymentContext.metadata['form']`` and the gateway maps it
to its provider method id.

The user-facing method code for such a button is ``"<gateway>@<form>"`` (e.g.
``platega@sbp``) — the ``@`` never collides with the ``:``-separated callback data.
"""

from __future__ import annotations

from src.core.enums import PaymentGatewayType

# Gateways whose enabled forms should surface as SEPARATE payment buttons, with the
# human label shown to the buyer. A gateway not listed here opens one payment as before.
FORM_ROUTABLE: dict[PaymentGatewayType, dict[str, str]] = {
    PaymentGatewayType.PLATEGA: {"sbp": "СБП", "card": "Карта", "crypto": "Крипта"},
}


def gateway_form_options(gtype: PaymentGatewayType, enabled_forms: object) -> list[tuple[str, str]]:
    """``[(form, label)]`` the buyer may pick for this gateway, or ``[]`` when it opens a
    single payment (not form-routable, or only one form is enabled)."""
    routable = FORM_ROUTABLE.get(gtype)
    if not routable:
        return []
    forms = [f for f in enabled_forms if f in routable] if isinstance(enabled_forms, list) else []
    if len(forms) <= 1:
        return []  # a single method needs no choice — keep the plain gateway button
    return [(f, routable[f]) for f in forms]


def split_method(method: str) -> tuple[str, str | None]:
    """``"platega@sbp"`` -> ``("platega", "sbp")``; plain ``"platega"`` -> ``("platega", None)``."""
    gateway, sep, form = method.partition("@")
    return gateway, (form if sep else None)
