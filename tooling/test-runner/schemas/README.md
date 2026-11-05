# Vendored schemas

`handoff-frontmatter.schema.json` is a **copy** of the canonical nyxloom schema:

    nyxloom/schemas/handoff-frontmatter.schema.json   (vbpub repo)

Vendored at vbpub commit `d7e553a` (2026-07-16).

## Why vendored

The gate container mounts only this repo, so it cannot read the nyxloom checkout.
`tooling/test-runner/lint_trove.py` needs the schema to validate our handoffs before
the nyxloomd daemon is able to reach this project at all (it currently mounts only
vbpub + dstdns — see nyxloom-trove/decisions.md D-001).

## Refreshing

Deliberate, not automatic — a schema bump can invalidate existing handoffs:

    cp /workspaces/vbpub/nyxloom/schemas/handoff-frontmatter.schema.json \
       tooling/test-runner/schemas/
    run-gate trove --worktree "$PWD"

Once nyxloomd mounts this repo, `nyxloom lint` becomes authoritative and this copy is
only a pre-flight convenience.
