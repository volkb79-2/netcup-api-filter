# KSM opt-in shim (vendored)

`ksm-optin.so` is a tiny `LD_PRELOAD` library whose constructor calls
`prctl(PR_SET_MEMORY_MERGE, 1)`, marking the process's (and its children's) anonymous
memory as **KSM-mergeable** — equivalent to `MADV_MERGEABLE` on every mapping. Identical
pages across our many long-lived containers (mocks, PowerDNS, the app, pwmcp) then dedupe
system-wide, cutting RSS. Needs kernel ≥ 6.4, `CONFIG_KSM`, and the host running KSM
(`/sys/kernel/mm/ksm/run = 1`).

**Vendored from `dstdns/tools/ksm-optin/`** (`ksm-optin.c` kept for reproducibility — rebuild
with `cc -shared -fPIC -O2 -o ksm-optin.so ksm-optin.c`). naf is self-contained: it does not
reach into a sibling repo for this.

**Wiring:** ciu governance injects it, not the compose files. `ciu.global.defaults.toml.j2`
sets `[governance] ksm_optin = "tooling/ksm-optin/ksm-optin.so"`, and ciu adds
`LD_PRELOAD=/opt/ksm/ksm-optin.so` + a read-only bind of this `.so` into every **non-exempt**
governed service. Confirm at `ciu up` time — the `[GOVERNANCE]` line prints `ksm_optin=…`.

pwmcp opts in at the **image** level instead (its supervisord `prctl`s at startup), so every
pwmcp instance across every repo dedupes regardless of who deploys it.
