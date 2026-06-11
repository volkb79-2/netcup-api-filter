# Telegram Linking (Option A) — Deep Link + Automatic Confirmation

Date: 2026-01-16

This document describes how Netcup API Filter (NAF) links a user’s Telegram chat to their account using the **recommended Option A** flow:

- UI shows a Telegram deep-link containing a **one-time link token**
- User presses **Start** in Telegram
- A separately-hosted bot service receives the update and calls back into NAF
- NAF stores the user’s `telegram_chat_id` and marks Telegram as linked

## Why this exists

Telegram bots **cannot initiate** messages to a user until the user has started a chat with the bot.
This flow ensures users don’t need to know their Telegram user ID or chat ID.

## Data model

The account record stores:
- `telegram_chat_id` + `telegram_enabled`
- `telegram_link_token_hash` (sha256 hex; raw token is never stored)
- `telegram_link_token_expires_at`
- `telegram_linked_at`

## Runtime configuration

All values are config-driven via environment variables (see `.env.defaults`):

- `TELEGRAM_BOT_USERNAME` — used to generate the deep-link
- `TELEGRAM_LINK_CALLBACK_SECRET` — shared secret required for bot → app callback
- `TELEGRAM_LINK_TOKEN_TTL_SECONDS` — how long a link token stays valid
- `TELEGRAM_NOTIFICATIONS_ENABLED` — whether sending Telegram messages is enabled
- `TELEGRAM_BOT_TOKEN` — required for sending messages
- `TELEGRAM_API_BASE_URL` — overrideable for tests/mocks

### Local testing defaults

For local development/test runs, `.env.defaults` ships placeholder values for
`TELEGRAM_BOT_USERNAME` and `TELEGRAM_LINK_CALLBACK_SECRET` so the UI and test
suite can exercise the linking flow without extra manual setup.

Production deployments MUST override these values (do not rely on placeholders).

### Placeholder secret rejection on non-local deployments

The placeholder value shipped in `.env.defaults` for `TELEGRAM_LINK_CALLBACK_SECRET`
(`local-test-telegram-callback-secret-change-me`) is **rejected at runtime** on any
deployment where `DEPLOYMENT_TARGET` is not `local`. When that value is detected on a
non-local target the app logs an error and returns `503` to the bot, silently
disabling Telegram linking. This prevents a public, repo-committed secret from ever
authorizing the callback endpoint in production.

To enable linking in production set a strong, unique value for
`TELEGRAM_LINK_CALLBACK_SECRET` in your deployment environment.

## User flow (UI)

1. User goes to Account → Settings → Security → Telegram → Link
2. NAF generates a one-time token and renders a button like:

   `https://t.me/<BOT_USERNAME>?start=link_<TOKEN>`

3. User presses **Start** in Telegram
4. UI polls `/account/settings/telegram/status` and auto-refreshes when linked

**Token stability across page refreshes:** the raw link token is cached in the user's browser
session so that reloading the linking page (or opening it in a second tab) reuses the same
deep-link while the token is still valid. A new token is only issued when the cached one has
expired or is absent. This means opening the Telegram app and pressing **Start** will still work
even if the user refreshed the page after seeing the deep-link.

## Telegram as a 2FA method

Linking a Telegram chat enables Telegram as an additional 2FA option at login — but only when
the server can actually deliver a code. Telegram is offered as a 2FA method only when **both**
conditions are true at login time:

- `TELEGRAM_NOTIFICATIONS_ENABLED=true`
- `TELEGRAM_BOT_TOKEN` is set

If the account has Telegram linked but the server has notifications disabled (or the bot token
is missing), Telegram will **not appear** in the 2FA method list. Email, TOTP, and recovery codes
continue to work normally. No action is needed from the user — Telegram will reappear
automatically once the server-side configuration is restored.

## Bot → App callback (API contract)

Endpoint:
- `POST /api/telegram/link`

Auth:
- Header `X-NAF-TELEGRAM-SECRET: <secret>` must match `TELEGRAM_LINK_CALLBACK_SECRET`

Body (JSON):
```json
{
  "token": "<raw_link_token>",
  "chat_id": "<digits>"
}
```

Responses:
- `200 {"status":"linked"}`
- `401` unauthorized (wrong/missing secret)
- `404` token unknown
- `409` token not in pending state, or `chat_id` already linked to a different account
- `410` token expired
- `503` linking not configured (including when the placeholder secret is active on a non-local deployment)

On success, NAF consumes the token (clears token hash + expiry) and stores the `chat_id`.

**Security properties of the callback endpoint:**

- The `X-NAF-TELEGRAM-SECRET` value is compared in **constant time** (`hmac.compare_digest`) to
  prevent timing-based secret discovery.
- The entire `/api/telegram` blueprint is **rate-limited** (default: 60 requests per minute,
  configurable via `api_rate_limit`).
- A `chat_id` can only be linked to **one account**. Attempting to link a chat already bound to
  another account returns HTTP 409. This prevents a single Telegram chat from receiving 2FA codes
  or security alerts for multiple accounts.
- Every successful link operation is written to the **audit log** (`telegram_linked` action,
  severity `medium`).

## Manual testing (without real Telegram)

You can simulate the bot confirmation call directly:

1. Ensure the backend has linking configured:
   - set `TELEGRAM_BOT_USERNAME`
   - set `TELEGRAM_LINK_CALLBACK_SECRET`

2. Open the link page for an account:
   - `/account/settings/telegram/link`

3. Copy the displayed token and call `POST /api/telegram/link` with the secret header.

4. Return to the UI; it should show “Telegram Linked”.

## Automated testing

- Backend callback contract tests: `tests/test_telegram_linking.py`
- UI tests (Playwright): update/extend the Telegram 2FA tests under `ui_tests/tests/` to:
  - visit the link page
  - parse the token from the page
  - call the callback endpoint (simulating the bot)
  - assert the UI shows “Linked"

## Implementation files

- Telegram HTTP sender: `src/netcup_api_filter/telegram_service.py`
- Bot callback endpoint: `src/netcup_api_filter/api/telegram.py`
- Account linking page route + polling endpoint:
  - `src/netcup_api_filter/api/account.py`
  - `src/netcup_api_filter/templates/account/link_telegram.html`
