# Telegram Bot Setup for Netcup API Filter

Date: 2026-01-16

This document explains how to configure an existing Telegram bot to work with Netcup API Filter (NAF).

NAF does **not** host the bot process itself. The bot must run as a separate service that:
- receives Telegram updates (webhook)
- calls back into NAF to confirm account linking

## 1) Bot prerequisites

- A Telegram bot created via `@BotFather`
- Bot token available (keep secret)
- Bot username (without `@`)

## 2) Configure NAF

Set these environment variables (see `.env.defaults` for the catalog):

- `TELEGRAM_BOT_USERNAME` — bot username used for deep-links in the UI
- `TELEGRAM_LINK_CALLBACK_SECRET` — shared secret required for bot → NAF callback
- `TELEGRAM_NOTIFICATIONS_ENABLED=true` — enables sending messages
- `TELEGRAM_BOT_TOKEN` — required for sending messages

Optional:
- `TELEGRAM_API_BASE_URL` — defaults to `https://api.telegram.org`
- `TELEGRAM_REQUEST_TIMEOUT_SECONDS`
- `TELEGRAM_LINK_TOKEN_TTL_SECONDS`

Note: `.env.defaults` includes placeholder values for local testing. Production
deployments must override `TELEGRAM_BOT_USERNAME` and `TELEGRAM_LINK_CALLBACK_SECRET`.

## 3) Configure the bot service

### Receiving updates

Telegram provides updates to your bot via webhook.
Your bot service should:

1. Parse updates for messages like:
   - `/start link_<TOKEN>`

2. Extract:
   - `chat_id` (where to send messages)
   - `token` (the raw link token)

3. Call the NAF callback endpoint:

- `POST https://<naf-host>/api/telegram/link`
- Header: `X-NAF-TELEGRAM-SECRET: <TELEGRAM_LINK_CALLBACK_SECRET>`
- Body:
  ```json
  {"token": "<TOKEN>", "chat_id": "<CHAT_ID>"}
  ```

If NAF returns `200`, send a user-facing confirmation message in Telegram.

### Minimal bot behavior

- Always require the `link_` prefix in `/start` payload to avoid accidentally consuming other start parameters.
- Do not log the raw token.
- If NAF returns `410` (expired) or `404` (unknown), tell the user to refresh the NAF linking page to generate a new token.

## 4) Testing bot integration

- Fast local test (no Telegram): simulate bot callback as described in [docs/TELEGRAM_LINKING.md](docs/TELEGRAM_LINKING.md).
- Full end-to-end test requires:
  - public HTTPS URL reachable by Telegram
  - bot webhook configured
  - NAF running with the callback secret + bot token

## 5) Security checklist

- `TELEGRAM_LINK_CALLBACK_SECRET` must be random and kept secret.
- Do not accept link callbacks without the secret header.
- Keep link tokens short-lived (`TELEGRAM_LINK_TOKEN_TTL_SECONDS`).
- Never store raw link tokens in the database.
