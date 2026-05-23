---
plan: "07-03"
phase: "07-asn-enrichment-traffic-attribution"
subsystem: "watch-routes.py + deploy.sh"
status: complete
completed_at: "2026-05-23T10:40:00Z"
commits:
  - "219a00c: feat(07-03): add ASN background-thread enrichment to watch-routes.py"
  - "e104afd: feat(07-03): extend deploy.sh with Stage 23 asn-lookup.py deploy and bump TOTAL_STAGES to 24"
tags:
  - asn
  - watch-routes
  - deploy
  - threading
dependency_graph:
  requires:
    - "07-01: scripts/asn-lookup.py"
    - "07-02: vpn-status.sh ORG column (parallel, same wave)"
  provides:
    - "scripts/watch-routes.py with inline ' | {org}' suffix via background thread"
    - "deploy.sh Stage 23 deploys asn-lookup.py to /etc/asn-lookup.py on RPi"
  affects:
    - "scripts/watch-routes.py"
    - "deploy.sh"
    - "tests/test_watch_routes_asn.py (created)"
tech_stack:
  added:
    - "threading.Thread (daemon=True) for non-blocking ASN lookups"
    - "subprocess.run with timeout=5.0 to invoke /etc/asn-lookup.py"
    - "threading.Lock for _asn_cache concurrent access"
  patterns:
    - "Sentinel-based in-flight dedup (_asn_cache[ip]=None prevents duplicate threads)"
    - "SCP → sudo mv → chmod +x → chown root:root deploy pattern (mirrors Stage 19/20)"
key_files:
  created:
    - "tests/test_watch_routes_asn.py"
  modified:
    - "scripts/watch-routes.py"
    - "deploy.sh"
decisions:
  - "enable_asn implemented as keyword-only parameter with default True — backward compatible with all existing positional callers"
  - "Subprocess target path hardcoded to /etc/asn-lookup.py (ASN_LOOKUP_PATH) — matches deploy destination"
  - "Daemon threads (daemon=True) ensure no hang on Ctrl-C even if lookup is mid-flight"
  - "Three-state cache sentinel: None=in-flight, {}=completed-no-result, dict=resolved — prevents re-querying"
  - "TOTAL_STAGES bumped 23→24 before adding Stage 23 to keep [N/TOTAL] display correct"
  - "New Stage 23 inserted BEFORE routing activation so routing.sh remains last runtime stage"
metrics:
  duration: "~30 minutes"
  completed_date: "2026-05-23"
  tasks_completed: 2
  files_changed: 3
---

# Phase 7 Plan 03: ASN Background-Thread Enrichment + deploy.sh Stage 24 Summary

## What was built

Two tightly-coupled deliverables shipped together in plan 07-03:

### 1. scripts/watch-routes.py — background-thread ASN enrichment

Extended the real-time iptables log enricher with non-blocking ASN org attribution via daemon background threads invoking `/etc/asn-lookup.py` as a subprocess.

Key additions:
- `_asn_cache: dict` + `_asn_lock = threading.Lock()` as module globals — thread-safe shared cache
- `_do_lookup(ip)` — daemon background worker: calls `python3 /etc/asn-lookup.py` with `input=ip+"\n"`, 5s timeout; stores parsed dict or `{}` on any error
- `lookup_async(ip)` — idempotent async trigger: uses `None` sentinel to prevent duplicate threads per IP
- `format_line()` extended with `enable_asn: bool = True` keyword-only param: checks cache, appends ` | {org}` when resolved, triggers `lookup_async` on miss — never blocks the journalctl stream
- `--no-asn` CLI flag to opt out of enrichment entirely
- Updated module docstring to document the subprocess dependency and new flag

### 2. deploy.sh — Stage 23 (asn-lookup.py deploy) + TOTAL_STAGES bump

Extended the deploy orchestrator to ship `scripts/asn-lookup.py` to the RPi as `/etc/asn-lookup.py`.

Key changes:
- Added `ASN_LOOKUP_LOCAL`, `ASN_LOOKUP_REMOTE`, `ASN_LOOKUP_TMP` path variables (after WATCH_ROUTES_* block)
- Bumped `TOTAL_STAGES=23` → `TOTAL_STAGES=24`
- Added preflight check for `$ASN_LOOKUP_LOCAL` existence
- Inserted Stage 23 (new): `scp` → `sudo mv` → `chmod +x` → `chown root:root` pattern mirroring Stages 19/20
- Renumbered prior Stage 23 (routing activation) to Stage 24 — routing.sh remains the last runtime stage
- Added `PHASE 7:` line to final summary block

### 3. tests/test_watch_routes_asn.py (created)

10 pytest tests covering all ASN enrichment behavior — imported via `importlib.util.spec_from_file_location` due to hyphen in filename:
- Tests 1–3: Three cache states (resolved org / in-flight None / empty dict)
- Test 4: Cache miss triggers `lookup_async` exactly once for same IP
- Tests 5–6: `_do_lookup` with mocked subprocess (valid JSON / TimeoutExpired)
- Test 7: Concurrent `lookup_async` calls → single subprocess invocation
- Test 8: `enable_asn=False` → no suffix even with pre-populated cache
- Test 9 (help): `--help` exits 0 and contains `--no-asn`
- Test 9 (compat): Existing positional `format_line(...)` call still works

## Verification

All automated checks pass:

```
python3 -c "import ast; ast.parse(open('scripts/watch-routes.py').read())"  # OK
python3 -m pytest tests/test_watch_routes_asn.py -x -v                      # 10 passed
bash -n deploy.sh                                                             # OK
grep -q "^TOTAL_STAGES=24$" deploy.sh                                        # OK
grep -q "[23/${TOTAL_STAGES}] Deploying asn-lookup.py" deploy.sh             # OK
grep -q "[24/${TOTAL_STAGES}] Activating routes via routing.sh" deploy.sh    # OK
grep -c '\[[0-9]*/\${TOTAL_STAGES}\]' deploy.sh                              # 25 (24 stages + 1 --no-run duplicate)
```

## Deviations from Plan

None — plan executed exactly as written. `enable_asn` was implemented as a keyword-only parameter (`*,`) to maintain backward compatibility with existing positional callers in `main()`.

## Known Stubs

None — all functionality fully wired.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes beyond those covered in the plan's threat model (T-07-10 through T-07-14).

## Self-Check: PASSED

- `scripts/watch-routes.py` exists and passes `ast.parse`
- `tests/test_watch_routes_asn.py` exists and all 10 tests pass
- `deploy.sh` passes `bash -n`
- Commits 219a00c and e104afd exist in git log
