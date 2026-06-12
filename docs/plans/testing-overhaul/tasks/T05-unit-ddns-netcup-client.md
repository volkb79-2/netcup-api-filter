# T05 — Unit tests: DDNS protocol parsing + netcup response envelopes (~42 cases)

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high | T02 | M |

## Objective

Unit-test the DDNS request-parsing layer (hostname splitting, client-IP detection,
auto-IP keywords) and the netcup response-envelope helpers. These currently have only
coarse E2E coverage; parsing bugs here cause silent wrong-record updates.

## Context — read first

- `src/netcup_api_filter/api/ddns_protocols.py` — verified targets: `get_auto_ip_keywords`
  (46), `get_client_ip` (62), `should_auto_detect_ip` (81), `validate_ip_address` (99),
  `parse_hostname` (118), `validate_hostname_format` (157). **Read each first** — in
  particular check whether `parse_hostname` needs DB/app context (managed domain roots);
  if it does, use the T02 `app` fixture and seed what it needs via factories.
- `src/netcup_api_filter/netcup_client.py` — `extract_dns_records` (22), `mutation_failed`
  (36), `mutation_message` (49). Pure functions over response dicts.
- `docs/DDNS_PROTOCOLS.md` — the documented protocol contract.
- T02 fixtures (`app`, factories) for anything needing request/app context.

## Spec

### `tests/test_ddns_parsing_unit.py` (~29)

- `parse_hostname` (~8): plain `host.example.com` → expected (domain, host) split per the
  implementation's strategy; multi-label host (`a.b.example.com`); apex (`example.com`);
  trailing dot; uppercase normalization; single label (invalid?); empty; a case exercising
  how the zone boundary is decided (read the code — if it consults known roots, seed one).
- `validate_hostname_format` (~5): valid FQDN, invalid chars, overlong label, leading hyphen,
  empty.
- `validate_ip_address` (~6): valid v4, valid v6, v4-mapped v6 (per impl), octet overflow,
  garbage, empty.
- `should_auto_detect_ip` (~6): empty/None → auto (per impl); each default keyword from
  `get_auto_ip_keywords()`; keyword case-insensitivity; explicit IP → not auto; custom
  `DDNS_AUTO_IP_KEYWORDS` env via `monkeypatch` changes the set.
- `get_client_ip` (~4): use `app.test_request_context(...)` — no header → `remote_addr`;
  single `X-Forwarded-For`; multi-hop `X-Forwarded-For: client, proxy1, proxy2` (assert which
  element the implementation picks and leave a comment that this is the trust contract);
  malformed header.

### `tests/test_netcup_client_unit.py` (~13, pure)

- `extract_dns_records` (~5): well-formed envelope `{"responsedata": {"dnsrecords": [...]}}`
  → list; missing `responsedata`; `dnsrecords` missing; non-dict input; empty list.
- `mutation_failed` (~5): success envelope → False; explicit failure status → True;
  missing status fields; None; string input.
- `mutation_message` (~3): message present → extracted; absent → provided default;
  weird shape → default.

(Confirm the exact envelope key names from the implementation and from
`ui_tests/mock_netcup_api.py` — assert real shapes, not guessed ones.)

## Acceptance criteria

- [ ] Both files green; `python -m pytest tests/ -q` green overall; no skips.
- [ ] The X-Forwarded-For trust behavior is pinned by an exact assertion + comment.
- [ ] Suspected real bugs → `xfail(strict=True)` + named in summary, not blessed.

## Verify

```bash
cd /workspaces/netcup-api-filter
python -m pytest tests/test_ddns_parsing_unit.py tests/test_netcup_client_unit.py -v
python -m pytest tests/ -q
```

## Guardrails (non-negotiable)

- No `pytest.skip` to go green, no assertions inside `if found:` blocks, no `or`-chained assertions.
- Never hardcode credentials. Run pytest from the repo root.
- Don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`. Don't modify `src/` to make tests pass.
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T05 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.
