---
kind: product-definition
schema_version: 1
product_version: 1
features:
  - id: F001
    title: REST DNS mutations respect record-level realm scope
    acceptance:
      - When a token attempts an update or delete outside its realm hostname scope, the REST API rejects the request and does not mutate the record.
    status: shipped
    milestone: M1
  - id: F002
    title: Portal DNS management respects realm hostname scope
    acceptance:
      - When an account user creates, edits, or deletes a portal DNS record outside the selected realm scope, the portal rejects the operation.
    status: shipped
    milestone: M1
  - id: F003
    title: DNS record reads respect realm hostname scope
    acceptance:
      - When a host or subdomain-only token lists records, the API returns only hostnames matched by that token's realm.
    status: planned
    milestone: M1
  - id: F026
    title: Account authentication resists known lockout, IP, and password-policy bypasses
    acceptance:
      - When a user retries TOTP, presents spoofed forwarding headers, or resets or accepts an invite with a weak password, the account flow enforces the corresponding lockout, trusted client-IP, and shared password-policy controls.
    status: shipped
    milestone: M1
  - id: F027
    title: Machine clients can authenticate DNS API requests with HTTP SCRAM-SHA-256
    acceptance:
      - When a client with provisioned realm-scoped credentials completes the RFC 7804 SCRAM-SHA-256 HTTP exchange, the API verifies the client and server proofs without sending the reusable password.
      - When the exchange succeeds, requests use the provisioned realm scope and existing record-level authorization; failed or replayed exchanges are rate-limited and audited.
    status: planned
    milestone: M8
  - id: F004
    title: Sensitive DNS and revoke actions leave usable audit records
    acceptance:
      - When a portal DNS mutation or an admin revoke succeeds, an ActivityLog row is written with valid action metadata.
    status: shipped
    milestone: M2
  - id: F005
    title: Settings preserve their configured type and SMTP key
    acceptance:
      - When a setting is saved and read through the production configuration path, its value type is preserved and invite or verification mail uses the configured SMTP key.
    status: shipped
    milestone: M3
  - id: F006
    title: Development configuration does not fail on an absent public FQDN
    acceptance:
      - When .env.services is sourced with unset PUBLIC_* variables, it completes without an unbound-variable failure.
    status: shipped
    milestone: M3
  - id: F007
    title: Release artifacts and deployment follow production-parity infrastructure
    acceptance:
      - When a release is published, it includes the OCI image and ABI-matched Passenger variants and a selected variant can be activated by ciu.
    status: shipped
    milestone: M3
  - id: F008
    title: Route discovery failures cannot silently shrink smoke coverage
    acceptance:
      - When application route discovery fails, route-smoke collection fails loudly; when it succeeds, the discovered route floor is asserted.
    status: building
    milestone: M4
  - id: F009
    title: Tests enforce their named failure conditions
    acceptance:
      - When a touched nonfunctional or registration condition is violated, its test fails rather than unconditionally skipping itself.
    status: planned
    milestone: M4
  - id: F010
    title: Test counts and failure policy are honest
    acceptance:
      - When test-suite documentation reports counts or invocation policy, it matches collected tests and does not conceal later failures through global first-failure behavior.
    status: planned
    milestone: M4
  - id: F011
    title: Known portal and admin routes are reliable
    acceptance:
      - When a user opens /account/docs or an admin opens /admin/app-logs, the route renders without a server error or traceback.
    status: planned
    milestone: M4
  - id: F012
    title: Notification preferences control notification delivery
    acceptance:
      - When an account disables a notification type or supplies a notification email, notification delivery honors that preference and address.
    status: planned
    milestone: M5
  - id: F013
    title: Portal exposes token usage analytics
    acceptance:
      - When an account views a realm, it can see each token's last use, call and denial counts, and observed source IPs from ActivityLog data.
    status: planned
    milestone: M5
  - id: F014
    title: Webhook notification delivery is available
    acceptance:
      - When an account enables a configured webhook notification, naf delivers the event through the webhook channel subject to notification preferences.
    status: planned
    milestone: M5
  - id: F015
    title: Users can view and resolve their 2FA lockout
    acceptance:
      - When an account is 2FA-locked, its owner can view the lockout state and use the supported self-service unlock flow.
    status: planned
    milestone: M5
  - id: F016
    title: Request paths do not synchronously wait on SMTP delivery
    acceptance:
      - When verification, 2FA, or reset notification work is queued, the request returns without waiting for synchronous SMTP delivery.
    status: planned
    milestone: M5
  - id: F017
    title: Security events notify affected users
    acceptance:
      - When a documented brute-force, IP-denied, or revoked-token security event occurs, naf sends the corresponding security alert or documents it as unavailable.
    status: planned
    milestone: M5
  - id: F018
    title: Only the supported DNS API stack serves requests
    acceptance:
      - When a DDNS request reaches the application, it is handled by the supported DNS API path and no registered legacy filter proxy can return a shadowed-route error.
    status: planned
    milestone: M6
  - id: F019
    title: Dead Netcup mock paths are removed
    acceptance:
      - When a deployment selects its DNS endpoint, it uses the configured API URL and no unused mock client or MOCK_NETCUP_API switch can imply a different backend.
    status: planned
    milestone: M6
  - id: F020
    title: Realm-selected backends execute live DNS operations
    acceptance:
      - When a realm is bound to a supported BYOD or PowerDNS backend, DNS and DDNS operations use that backend and preserve deletion, priority, hostname, and RRset semantics.
    status: planned
    milestone: M6
  - id: F021
    title: Audit history survives token deletion and foreign keys are enforced
    acceptance:
      - When a token is deleted, its audit rows remain with a null token reference, and SQLite enforces declared foreign-key behavior.
    status: planned
    milestone: M7
  - id: F022
    title: Credentials are never written to application logs
    acceptance:
      - When bootstrap or demo credentials are generated, logs contain no password or full token and any required recovery state is stored outside the log with restricted access.
    status: planned
    milestone: M7
  - id: F023
    title: Upgrade data posture is explicit and safe
    acceptance:
      - When naf deploys with existing production data, it follows the decided migration posture or explicitly documents its greenfield-only limitation.
    status: planned
    milestone: M7
  - id: F024
    title: TOTP secrets are protected at rest
    acceptance:
      - When a TOTP seed is persisted, it is protected at rest rather than stored as plaintext application data.
    status: planned
    milestone: M7
  - id: F025
    title: Lightweight migrations preserve declared schema invariants
    acceptance:
      - When a lightweight migration adds a scalar-default non-null column, the upgraded schema enforces the declared non-null invariant.
    status: planned
    milestone: M7
non_goals:
  - Replacing the additive lightweight migration path with Alembic before D-003 decides the product's data-survival posture.
  - Treating configured BYOD or PowerDNS backends as live DNS execution before F020 is delivered.
  - Preserving webhosting database state across releases while the current greenfield deployment posture remains in force.
---

# Product definition v1

This definition records the shipped authorization, audit, configuration, security-hardening,
and release foundations alongside the remaining product work. Status is derived from
STATE.md: merged work is shipped, P06's delivered route-discovery slice is building, and
un-carved/open work is planned.

The data-survival choice remains D-003. The backend execution choice is settled by D-002:
wire live paths through the realm-selected backend; F020 is the resulting implementation
target, not a claim that BYOD is already live.
