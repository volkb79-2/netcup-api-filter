#!/usr/bin/env bash
# =============================================================================
# tooling/mutation/run.sh  —  Toggleable LOCAL-ONLY mutation-testing runner
# =============================================================================
# Usage:
#   ./tooling/mutation/run.sh run                     # full 5-module run
#   ./tooling/mutation/run.sh run src/netcup_api_filter/recovery_codes.py
#                                                     # single-module run (fast)
#   ./tooling/mutation/run.sh results                 # print survivor summary
#   ./tooling/mutation/run.sh show                    # same as results
#
# This script is the ONLY way to trigger mutation testing.
# It is NOT referenced from CI or pytest.ini — it must be invoked explicitly.
# See tooling/mutation/README.md for full documentation.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Locate project root (two levels up from tooling/mutation/)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_ROOT}"

# ---------------------------------------------------------------------------
# Activate .venv if present
# ---------------------------------------------------------------------------
if [[ -f "${PROJECT_ROOT}/.venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.venv/bin/activate"
    echo "[mutation] Using venv: ${PROJECT_ROOT}/.venv"
else
    echo "[mutation] WARNING: No .venv found — using system Python: $(which python3)"
fi

# ---------------------------------------------------------------------------
# Verify mutmut is available
# ---------------------------------------------------------------------------
if ! command -v mutmut &>/dev/null; then
    echo "[mutation] ERROR: mutmut not found. Install dev deps:"
    echo "           pip install -r requirements-dev.txt"
    exit 1
fi

MUTMUT_VERSION="$(mutmut --version 2>&1 | head -1)"
echo "[mutation] ${MUTMUT_VERSION}"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ORIG_SETUP_CFG="${PROJECT_ROOT}/setup.cfg"
BACKUP_SETUP_CFG="${PROJECT_ROOT}/.setup.cfg.mutation-backup"

# The test selection used per-mutant (fast unit subset, no coverage overhead)
PER_MUTANT_TESTS="
    tests/test_token_auth_unit.py
    tests/test_realm_matching_unit.py
    tests/test_validators_unit.py
    tests/test_ddns_parsing_unit.py
    tests/test_recovery_codes_unit.py
    tests/test_password_policy_unit.py
    tests/test_token_model_property.py
    tests/test_ddns_property.py
    tests/test_validators_property.py"

# ---------------------------------------------------------------------------
# Helper: print survivor summary from mutmut results
# ---------------------------------------------------------------------------
print_summary() {
    echo ""
    echo "=== Mutation summary ============================================="
    local total killed survived timed_out not_checked suspicious
    total=$(mutmut results 2>&1 | wc -l)
    killed=$(mutmut results 2>&1 | grep -c ": killed" || true)
    survived=$(mutmut results 2>&1 | grep -c ": survived" || true)
    timed_out=$(mutmut results 2>&1 | grep -c ": timeout" || true)
    not_checked=$(mutmut results 2>&1 | grep -c ": not checked" || true)
    suspicious=$(mutmut results 2>&1 | grep -c ": suspicious" || true)

    echo "  Total mutants  : ${total}"
    echo "  Killed         : ${killed}  (tests detected the mutation)"
    echo "  Survived       : ${survived}  <-- examine these"
    echo "  Timed out      : ${timed_out}"
    echo "  Suspicious     : ${suspicious}"
    echo "  Not checked    : ${not_checked}"
    echo ""
    if [[ "${survived}" -gt 0 ]]; then
        echo "Surviving mutants (tests did NOT detect these changes):"
        mutmut results 2>&1 | grep ": survived" | sed 's/^[[:space:]]*/  /'
        echo ""
        echo "To inspect a survivor: mutmut show <mutant-name>"
        echo "Full detail guide:     tooling/mutation/README.md"
    else
        echo "No survivors — all checked mutants were killed by the test suite."
    fi
    echo "=================================================================="
}

# ---------------------------------------------------------------------------
# Helper: restore setup.cfg from backup (used as trap handler)
# ---------------------------------------------------------------------------
cleanup_temp_cfg() {
    if [[ -f "${BACKUP_SETUP_CFG}" ]]; then
        mv "${BACKUP_SETUP_CFG}" "${ORIG_SETUP_CFG}"
        echo "[mutation] Restored original setup.cfg"
    fi
}

# ---------------------------------------------------------------------------
# Helper: write a single-module setup.cfg override, run mutmut, restore
# ---------------------------------------------------------------------------
run_single_module() {
    local module_path="$1"
    local rel_path="${module_path#./}"   # strip leading ./

    if [[ ! -f "${PROJECT_ROOT}/${rel_path}" ]]; then
        echo "[mutation] ERROR: module not found: ${module_path}"
        echo "           Expected a path like: src/netcup_api_filter/recovery_codes.py"
        exit 1
    fi

    echo "[mutation] Single-module run: ${rel_path}"

    # Backup and replace setup.cfg; restore on exit/interrupt
    cp "${ORIG_SETUP_CFG}" "${BACKUP_SETUP_CFG}"
    trap cleanup_temp_cfg EXIT INT TERM

    # Write single-module config
    cat > "${ORIG_SETUP_CFG}" <<CFGEOF
# Temporary single-module mutation config — restored by run.sh after the run
[mutmut]
source_paths =
    ${rel_path}

also_copy =
    src/
    pytest.ini
    requirements-dev.txt

# Neutralise repo addopts (--cov / -x / --tb=short) per-mutant
pytest_add_cli_args =
    -o
    addopts=

pytest_add_cli_args_test_selection =${PER_MUTANT_TESTS}
CFGEOF

    # Fresh sandbox for this single-module run
    rm -rf "${PROJECT_ROOT}/mutants"

    local start_ts end_ts elapsed
    start_ts=$(date +%s)

    mutmut run

    end_ts=$(date +%s)
    elapsed=$(( end_ts - start_ts ))
    echo "[mutation] Completed in ${elapsed}s"

    print_summary

    # Explicit restore (trap is a safety net)
    cleanup_temp_cfg
    trap - EXIT INT TERM
}

# ---------------------------------------------------------------------------
# Helper: full 5-module run
# ---------------------------------------------------------------------------
run_full() {
    echo "[mutation] Full 5-module run — this is slow (see tooling/mutation/README.md for estimates)"
    echo "[mutation] Config: ${ORIG_SETUP_CFG}"
    rm -rf "${PROJECT_ROOT}/mutants"

    local start_ts end_ts elapsed
    start_ts=$(date +%s)

    mutmut run

    end_ts=$(date +%s)
    elapsed=$(( end_ts - start_ts ))
    echo "[mutation] Completed in ${elapsed}s"

    print_summary
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
CMD="${1:-help}"
shift || true

case "${CMD}" in
    run)
        MODULE="${1:-}"
        if [[ -n "${MODULE}" ]]; then
            run_single_module "${MODULE}"
        else
            run_full
        fi
        ;;
    results|show)
        print_summary
        ;;
    *)
        cat <<'USAGE'
Usage:
  ./tooling/mutation/run.sh run
      Full 5-module mutation run (slow — allocate 15-30 min).

  ./tooling/mutation/run.sh run src/netcup_api_filter/recovery_codes.py
      Single-module run (fast smoke check, ~2-5 min).

  ./tooling/mutation/run.sh results
  ./tooling/mutation/run.sh show
      Print surviving-mutant summary from the last run.

See tooling/mutation/README.md for full documentation.
USAGE
        exit 0
        ;;
esac
