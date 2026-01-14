
# Configuration Seeding (First Start)

This project supports **one-time seeding** of initial configuration via `app-config.toml`.
On first application start:

- The file is read once.
- Values are written to the database (Settings + seeded rows like Accounts/Backends).
- The file is deleted after a successful import.

After that, **the database becomes the source of truth** (managed via the admin UI).

## Avoiding “Too Many Places”

Use this mental model:

1. **`app-config.toml`**: initial seeding only (first start)
2. **DB (admin UI)**: runtime configuration and subsequent changes
3. **`.env.defaults` + env vars**: runtime process settings (cookie flags, ports, log level, test harness knobs)
4. **UI test state**: `deployment_state_local.json` / `deployment_state_webhosting.json` track *what tests changed* (passwords, and now admin email)

If you need deterministic prod-parity credentials for UI tests, prefer:

- putting them in `app-config.toml` for the *deployment bundle*, and
- persisting any test-driven changes in the deployment state JSON.

## Admin Seeding

Seed the initial admin via `[[users]]` with `is_admin = true` in `app-config.toml`.
The precise key names are validated by the importer; use [app-config.example.toml](../app-config.example.toml) as the
canonical template for what’s supported.

Important: **email-based 2FA is sent to the account’s email**.

- Recipient: `admin_email` (for admin) or `[[users]].email` (for normal users)
- Sender identity: `[smtp].from_email`

So it’s valid (and sometimes desirable) that these differ.

## User Preseeding

You can pre-create users at first start using `[[users]]` entries in `app-config.toml`.

```toml
[[users]]
username = "naf-user"
email = "naf-user@vxxu.de"
password = "generate" # or explicit strong password
is_approved = true
must_change_password = false
```

This is supported by the importer and is useful for user-owned backends and for
repeatable end-to-end tests.

## Testing With IMAP Aliases (Prod-Parity)

For webhosting/live UI tests, IMAP polling reads from the mailbox configured by `IMAP_USER`.
It’s OK if your seeded `admin_email` / `[[users]].email` values are **aliases** that
deliver into that same mailbox. This keeps “send-to” semantics correct while still
allowing a single IMAP inbox to collect the test emails.

