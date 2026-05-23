---
plan: "07-02"
phase: "07-asn-enrichment-traffic-attribution"
status: complete
completed_at: "2026-05-23T10:12:36Z"
commits:
  - "1aaa249: test(07-02): add failing tests for ORG column and --summary flag"
  - "16e58fd: feat(07-02): extend vpn-status.sh with ORG column and --summary aggregate view"
subsystem: vpn-status
tags: [asn-enrichment, bash, iptables-log, org-lookup, summary-view]
dependency_graph:
  requires: ["07-01 (scripts/asn-lookup.py)"]
  provides: ["ORG-enriched connection table", "--summary aggregate mode"]
  affects: ["scripts/vpn-status.sh"]
tech_stack:
  added: []
  patterns: ["bash associative arrays (declare -A)", "inline python3 JSON parse", "single subprocess ASN lookup"]
key_files:
  created: ["tests/test_vpn_status_phase7.sh"]
  modified: ["scripts/vpn-status.sh"]
decisions:
  - "ORG column placed after DOMAIN and before PATH per D-06"
  - "Docker image switched from debian:bookworm-slim to python:3.11-slim-bookworm for test re-exec (slim image lacked python3 needed by vpn-status.sh logic under test)"
metrics:
  duration_seconds: 502
  tasks_completed: 1
  files_changed: 2
---

# Phase 7 Plan 02: vpn-status.sh ORG column + --summary Summary

## What was built

Extended `scripts/vpn-status.sh` with ASN/org enrichment and an aggregate summary mode:

**ORG column** — added after DOMAIN in the regular connection table. Format: `{org} (AS{asn})` (e.g., `GOOGLE, US (AS15169)`) or `-` when the IP is unknown or lookup is unavailable.

**ASN enrichment block** — inserted between the entries loop and the output block. Collects all unique DST IPs from the full `entries[]` array before any output-time filter (Pitfall 6), makes a single `python3 /etc/asn-lookup.py` subprocess call, parses the returned JSON via inline `python3 -c`, and populates `declare -A org_map`.

**`--summary` flag** — new boolean flag (default `false`). When active, prints an `ORG | VPN_COUNT | ISP_COUNT | TOTAL` aggregate table (top 20 by TOTAL desc) using inline Python sort, then exits 0. Composes with `--filter`, `--device`, and `--via` filters. Does not print the per-connection table.

**Graceful degradation** — if `/etc/asn-lookup.py` is absent, `python3` is unavailable, or the lookup returns empty JSON, `org_map` stays empty and all ORG cells render as `-`. Script always exits 0.

## Verification

All automated checks passed:

- `bash -n scripts/vpn-status.sh` — syntax valid
- `grep -q "SUMMARY=false"` — default present
- `grep -q -- "--summary"` — flag implemented
- `grep -q "declare -A org_map"` — Pitfall 5 (associative array declared before write)
- `grep -q "asn-lookup.py"` — subprocess call wired
- `grep -q "ORG"`, `grep -q "VPN_COUNT"`, `grep -q "ISP_COUNT"`, `grep -q "TOTAL"` — all present
- `bash tests/test_vpn_status_phase7.sh` — 17/17 tests pass (via Docker re-exec on macOS)

## Test coverage (tests/test_vpn_status_phase7.sh)

8 test groups, 17 assertions:
1. `--summary` parses without error, exits 0 with no entries
2. ORG column header present in regular output (alongside TIMESTAMP, DOMAIN, PATH)
3. ORG cell populated from stub asn-lookup JSON — `GOOGLE, US (AS15169)`
4. ORG cell is `-` when stub returns `{}`
5. `--summary` header contains ORG, VPN_COUNT, ISP_COUNT, TOTAL
6. Regular per-row table (SRC-IP, DST-IP) not printed in `--summary` mode
7. Existing `--last=abc` validation exits 1 (preserved)
8. Pitfall 6: stub captures stdin of asn-lookup — both 8.8.8.8 (VPN entry) and 1.1.1.1 (ISP entry) present despite `--via=vpn` filter

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Docker image updated from debian:bookworm-slim to python:3.11-slim-bookworm**
- **Found during:** GREEN phase (Test 3 failed — ORG cell showed `-` despite stub)
- **Issue:** `debian:bookworm-slim` does not include `python3`. The `vpn-status.sh` ASN enrichment block checks `command -v python3` and skips the lookup when python3 is unavailable. The test therefore never exercised the enrichment path.
- **Fix:** Changed Docker image in the macOS re-exec guard to `python:3.11-slim-bookworm` (bash 5.2, GNU grep with -P, python3 3.11 — all requirements met).
- **Files modified:** `tests/test_vpn_status_phase7.sh`
- **Impact:** No functional change to `vpn-status.sh`; test infrastructure improvement only.

## Known Stubs

None. All ORG data is live from `/etc/asn-lookup.py` at runtime.

## Threat Flags

No new network endpoints, auth paths, or schema changes introduced. Changes are confined to local script output formatting and a single subprocess call to an already-deployed local file (`/etc/asn-lookup.py`). Threats T-07-06 and T-07-07 mitigated as designed (see PLAN.md threat model).

## Self-Check

- `scripts/vpn-status.sh` exists: FOUND
- `tests/test_vpn_status_phase7.sh` exists: FOUND
- commit 1aaa249 exists: FOUND
- commit 16e58fd exists: FOUND

## Self-Check: PASSED
