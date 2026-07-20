# Roadmap — netcup-api-filter

Milestones, in dependency order. Sourced from the deep review
(`docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md`) and the operator's stated priorities: **portal &
notifications, UI usability + correctness, testing framework, interesting features.**

Handoffs reference these via `advances:`; the reviewer verifies the ratchet at merge.

---

## Landed status (updated 2026-07-20)

- **M1 — authorization boundary:** M1.1 (naf-P01, REST delete/update scope) ✅ and M1.2
  (naf-P02, portal create/edit/delete scope) ✅ merged. M1.3 (read-scope leak) still open
  in backlog B-UI. The boundary is closed on the *mutation* paths.
- **M2 — audit trail:** ✅ done (naf-P03, merged 2026-07-16).
- **M3 — production-shaped config:** M3.1 + M3.2 (naf-P04, settings encoding + SMTP key) ✅
  merged. M3.3 (naf-P05, devcontainer FQDN) still open (deferred this session — infra/shell,
  needs a post-create run).
- **M4 — honest suite:** M4.1 (route discovery fails loudly + route floor) ✅ merged as
  naf-P06 part 1. M4.2 (kill can't-fail tests) is naf-P06 part 2, open (needs the e2e gate).

All merged work validated on BOTH Passenger interpreters (3.11 + 3.9) via the gate.

---

## M1 — Close the authorization boundary (ship-blocker)

The product is a *scoped, audited* DNS authorization layer. Today that claim is false on
several paths, so this precedes everything.

- **M1.1** REST DNS API enforces record-level scope on delete + update-by-id → `naf-P01`
- **M1.2** Account portal enforces realm hostname scope on create/edit/delete → `naf-P02`
- **M1.3** Read scope is filtered by hostname, not type alone → backlog B-UI
- **Done when:** no path mutates or reads a record outside a realm's hostname scope, and
  each is covered by a backend-truth test (not a status-code test).

## M2 — The audit trail actually exists

Auditing is the other half of the product claim, and it is currently crashing.

- **M2.1** Portal DNS UI writes audit rows instead of raising `TypeError` → `naf-P03`
- **M2.2** Admin revokes write an audit row instead of `NameError` → `naf-P03`
- **Done when:** every sensitive action (grants, revokes, DNS mutations, auth failures)
  leaves a row with real columns, and a revoke cannot commit without one.

## M3 — Production-shaped config works

Bugs that are invisible locally and fire only on a real deployment.

- **M3.1** Settings round-trip as the type they were written → `naf-P04`
- **M3.2** Invite/verification email reads the key production writes → `naf-P04`
- **M3.3** The devcontainer rebuild does not break every script → `naf-P05`
- **Done when:** a fresh deploy from TOML serves DNS and sends invite mail with no
  admin re-save, and a fresh devcontainer rebuild runs `deploy.sh --help` successfully.

## M4 — The suite is honest

Gates the credibility of every milestone above.

- **M4.1** Route discovery fails loudly; smoke has a route floor → `naf-P06`
- **M4.2** No test converts its failure condition into a skip → `naf-P06`
- **M4.3** Documented counts match reality (unit is **373**, not 355) → backlog B-DOCS
- **M4.4** `pytest.ini` stops hiding failures behind `-x` → backlog B-TESTS
- **Done when:** the reported coverage equals the real coverage, and the gate
  (`tooling/test-runner`, python 3.11) is the only accepted signal.

## M5 — Portal & notifications (the operator's headline priority)

- **M5.1** Notification preferences are honored → backlog B-PORTAL *(carve first: the
  rest sit on it)*
- **M5.2** Token usage analytics in the portal → depends on M2.1 (the crashing
  `realm_detail` query is the seed; the data is already in `ActivityLog`)
- **M5.3** Webhook channel → depends on M5.1
- **M5.4** Self-service 2FA-lockout unlock + status view
- **M5.5** Background dispatch for the remaining `notify_*` paths (kills the 30s
  request-thread SMTP hang)

## M6 — One DNS stack

- **M6.1** Delete `filter_proxy.py` (and the `GET /api/ddns/...` 500 it causes in prod)
- **M6.2** Delete `netcup_client_mock.py` + the dead `MOCK_NETCUP_API` exports
- **M6.3** Resolve **D-002**: wire `get_backend_for_realm()` into the live paths, or mark
  BYOD/PowerDNS not-yet-live and guard realm creation
- **Unlocks:** Cloudflare / Route53 become contained changes. Blocked on D-002.

## M7 — Data can survive an upgrade

- **M7.1** FK enforcement on; the audit-wipe cascade fixed → backlog B-DATA
- **M7.2** No plaintext credentials in logs → backlog B-DATA
- **M7.3** Resolve **D-003**: Alembic, or formally keep greenfield and document it
- **M7.4** Encryption at rest for TOTP seeds (`totp_secret` is plaintext `String(32)`)
- **Done when:** a deploy can preserve production data without hand-holding — or the
  product says, in writing, that it does not.
