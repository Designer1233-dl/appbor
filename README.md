# BOR Fullstack Mini App

Полноценный локальный прототип Telegram Mini App с:

- фронтендом в тёмно-зелёном стиле;
- backend API на Python;
- SQLite базой;
- админкой только для админов;
- интеграцией `CryptoBot` через инвойсы, webhook и резервную синхронизацию оплат.

## Запуск

Запусти:

```bat
start.bat
```

Потом открой:

```text
http://127.0.0.1:8080
```

## Переменные окружения

На хостинге заполняй переменные окружения из шаблона:

```text
.env.example
```

Основные:

- `BOR_HOST` — адрес сервера, для хостинга обычно `0.0.0.0`
- `BOR_PORT` — порт приложения
- `BOR_DB_PATH` — путь к SQLite базе
- `BOR_APP_TITLE` — название мини‑аппа
- `BOR_APP_MODE` — подпись режима
- `BOR_DEFAULT_ADMIN_ID` — id первого админа
- `BOR_DEFAULT_ADMIN_USERNAME` — username первого админа
- `BOR_DEFAULT_ADMIN_DISPLAY_NAME` — имя первого админа
- `BOR_SESSION_SECRET` — секрет сессии
- `BOR_TELEGRAM_BOT_TOKEN` — токен Telegram бота
- `WEBAPP_URL` — публичный URL мини‑аппа
- `WEBHOOK_BASE_URL` — базовый публичный URL для webhook'ов
- `BOR_CRYPTOBOT_ENABLED` — включен ли реальный CryptoBot режим
- `BOR_CRYPTOBOT_BOT_USERNAME` — username бота для ссылок оплаты
- `BOR_CRYPTOBOT_API_TOKEN` — токен API CryptoBot
- `BOR_CRYPTOBOT_WEBHOOK_SECRET` — секрет webhook CryptoBot
- `BOR_CRYPTOBOT_ASSET` — валюта инвойсов, например `USDT`
- `BOR_CRYPTOBOT_TESTNET` — `true`, если используешь тестнет `CryptoTestnetBot`
- `BOR_CRYPTOBOT_INVOICE_EXPIRES_IN` — время жизни счета в секундах
- `BOR_AUTO_DEPOSIT_DEFAULT` — автопополнение по умолчанию
- `BOR_AUTO_WITHDRAW_DEFAULT` — автовывод по умолчанию
- `BOR_AUTO_WITHDRAW_LIMIT` — лимит суммы для автоодобрения вывода
- `BOR_RISK_ALERTS_DEFAULT` — стартовое число риск‑алертов
- `BOR_VIP_SILVER_DEFAULT` — показатель для Silver
- `BOR_VIP_GOLD_DEFAULT` — показатель для Gold
- `BOR_FREEZE_QUEUE_DEFAULT` — стартовое значение очереди фриза

Сейчас сервер читает переменные напрямую из окружения хостинга. Файл `.env.example` нужен как шпаргалка, какие ключи создать.

Для удобства добавлены короткие ключи `WEBAPP_URL` и `WEBHOOK_BASE_URL`. Старый ключ `BOR_TELEGRAM_WEBAPP_URL` тоже можно оставить, но приоритет теперь у `WEBAPP_URL`.

## Что есть

- Главный экран `x50`
- Лобби с карточками игр
- Профиль, баланс, пополнение, вывод
- Промокоды
- Денежное колесо с участием по ссылке
- Админка:
  - история действий пользователей
  - заявки на вывод
  - переключение автовыводов
  - создание и удаление промокодов
  - создание колеса
  - дополнительный блок `Risk Center`

## Важно

Сервер теперь умеет:

- создавать реальные инвойсы через `createInvoice`;
- сохранять каждый счёт в `SQLite`;
- принимать webhook `invoice_paid`;
- проверять подпись `crypto-pay-api-signature`;
- зачислять баланс идемпотентно, без повторного начисления;
- резервно синхронизировать оплаченные счета через `getInvoices`.

Если `BOR_CRYPTOBOT_ENABLED=false` или не задан `BOR_CRYPTOBOT_API_TOKEN`, приложение автоматически уходит в mock‑режим без падения.
