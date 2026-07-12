# Добавить платёжного провайдера

Дизайн платежей — single ABC / single route / DB-config (ADR-0004, см. [Архитектуру](/dev/architecture)). Добавление провайдера = **один файл + один enum + одна регистрация + seed-row**. Роут и пайплайн обработки платежа не трогаются.

## Шаги

1. **Enum.** Добавьте значение в `PaymentGatewayType` — `src/core/enums.py`.

2. **Класс шлюза.** Новый файл `src/infrastructure/payments/gateways/<name>.py`, наследуйте `BasePaymentGateway` (`src/infrastructure/payments/base.py`). Реализуйте:
   - `gateway_type` = новое значение enum;
   - `capabilities` → `GatewayCapabilities` (валюты, `needs_http_webhook`, refund/recurrent/saved);
   - `create_payment(ctx) -> PaymentResult` — hosted `REDIRECT` URL или `IN_BOT` payload;
   - `handle_webhook(request) -> WebhookResult` — верифицируйте и верните `(payment_id | external_id, status)`. Используйте шаред-хелперы базы: `verify_hmac`, `check_ip_allowlist`, `client_ip`, `parse_json`. Кидайте `WebhookVerificationError` (→ 403) при провале подписи/IP, `NotFound` (→ 404) при неизвестном платеже.

3. **Регистрация.** Впишите класс в `_REGISTRY` в `src/infrastructure/payments/factory.py`.

4. **Seed-row.** Настройки провайдера — строка таблицы `payment_gateways` (`settings` JSONB, секреты Fernet-шифруются через `SecretBox`). `is_active=true` включает шлюз.

5. **Тест.** `tests/unit/test_<name>_gateway.py` по образцу `test_manual_gateway.py`: успешный вебхук → `WebhookResult`, плохая подпись/IP → `WebhookVerificationError`.

## Инварианты — не нарушать

- Никогда не фулфиллить в вебхуке — только verify → 200; фулфилмент делает воркер (идемпотентный CAS). Шлюзы ретраят на не-200, тяжёлая работа в вебхуке недопустима.
- Деньги — целые minor-units; `Decimal` — только на границе шлюза; для крипты/Stars — толеранс сверки сумм.
- Тело вебхука парсить с fallback-реселиализацией: прокси переписывают тело и ломают HMAC.

## Проверка

```bash
make check   # ruff + mypy + pytest
```

Роут `POST /api/v1/payments/{gateway_type}` заработает автоматически — отдельно регистрировать не нужно. После включения провайдера в кабинете кнопки оплаты сами появляются в боте и мини-аппе ([как настраиваются кассы](/payments/settings)).

::: tip Смотрите на соседей
21 живой провайдер уже лежит в `src/infrastructure/payments/gateways/` — hosted-редиректы, крипта, HMAC- и IP-верификация. Почти наверняка ваш новый провайдер похож на одного из них: начните с копии ближайшего.
:::
