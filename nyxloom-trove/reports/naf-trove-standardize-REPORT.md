# naf trove standardization report

## 1. Standards refresh

- Replaced `STANDARD.md` verbatim with the canonical 150-line standard.
- Replaced `AUTHORING.md` verbatim with the canonical guide; there was no naf-specific
  guidance to retain as local notes.
- Replaced `tooling/test-runner/schemas/handoff-frontmatter.schema.json` verbatim with the
  canonical schema.
- Updated the sole remaining open handoff, P06, to validate against that schema.

## 2. Spine adoption

Created the managed spine:

- `1-north-star.md`
- `2-product-definition.md`
- `3-roadmap.md`
- `4-backlog.md`

Created product features: F001, F002, F003, F004, F005, F006, F007, F008, F009, F010,
F011, F012, F013, F014, F015, F016, F017, F018, F019, F020, F021, F022, F023, F024,
F025, F026.

Preserved roadmap milestones: M1, M2, M3, M4, M5, M6, M7.

Created backlog items: B001, B002, B003, B004, B005, B006, B007, B008, B009, B010,
B011, B012, B013, B014, B015, B016, B017, B018, B019, B020, B021, B022, B023, B024,
B025, B026, B027, B028, B029, B030, B031, B032, B033, B034, B035, B036, B037, B038.

`nyxloom.toml` now names the north-star and product-definition paths and repoints roadmap and
backlog to the numeric spine. The old unprefixed roadmap and backlog were removed after their
content was converted.

C6 self-validation output:

```
S1 1-north-star.md: PASS
S1 2-product-definition.md: PASS
S1 3-roadmap.md: PASS
S1 4-backlog.md: PASS
S2 roadmap feature references: PASS (26 product features; 26 references)
S2 product acceptance: PASS (26/26 features have >=1 acceptance)
S2 backlog folds_into references: PASS (38/38 resolve)
S5 unique product feature ids: PASS (26 unique)
S5 unique roadmap milestone ids: PASS (7 unique)
S5 unique backlog item ids: PASS (38 unique)
```

The handoff lint also passed:

```
trove OK — 1 handoff(s) valid against the frontmatter schema (gates declared: e2e, trove, unit)
```

## 3. Cleanup

Archived as superseded, each with the required 2026-07-21 note:

- `CMRU-RELEASE-PLAN-2026-07-21.md`
- `INFRA-PLAN-2026-07-20.md`
- `INFRA-PLAN-B-2026-07-20.md`

STATE.md confirms all three plans' recorded work is merged.

## 4. Handoff state-match

- P05 is closed and archived with its paired report: O1 merged; O2 is superseded by naf-I04;
  there is no residual work.
- P06 remains open. Its status now says O1 part-1 is merged and must not be reimplemented;
  active work is O2 and O3 plus any O1 part-2 work named by STATE.md. Its frontmatter
  `input_revision` is `a5a9397`.

## 5. Decisions and operator items

No new D-### decision was needed: the direction calls used here are already resolved by
STATE.md and decisions.md. D-002 (live realm backend execution) and D-003 (greenfield versus
data-preserving upgrades) remain the existing product work recorded in the spine; neither was
silently resolved by this documentation package.
