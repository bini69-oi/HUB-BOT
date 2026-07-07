"""Heleket — crypto checkout, an API-compatible Cryptomus fork (same md5(base64+key) scheme)."""

from __future__ import annotations

from typing import ClassVar

from src.core.enums import PaymentGatewayType
from src.infrastructure.payments.gateways.cryptomus import CryptomusGateway


class HeleketGateway(CryptomusGateway):
    gateway_type = PaymentGatewayType.HELEKET
    api_base: ClassVar[str] = "https://api.heleket.com/v1"
    title: ClassVar[str] = "Heleket"
