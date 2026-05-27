---
phase: 10-splitgate-ergonomics
plan: "01"
subsystem: infra
tags: [bash, python, routing, vpn, path-migration, splitgate, iptables, systemd, networkmanager]

# Dependency graph
requires:
  - phase: 10-00
    provides: src/ directory restructure — all scripts moved to src/scripts/, src/systemd/

provides:
  - All 7 RPi-side scripts/units migrated from /etc/ flat namespace to /etc/splitgate/ namespace
  - vpn-rollback.sh extended with D-18 teardown (removes /usr/local/bin/splitgate + /etc/splitgate/ tree)
  - README.md and README.ru.md updated with new /etc/splitgate/ paths throughout

affects:
  - 10-02 (deploy.sh remote variable updates reference new /etc/splitgate/ paths)
  - 10-03 (dispatcher + logrotate config deployment to new paths)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "All RPi app scripts, data files, and env sourced from /etc/splitgate/ namespace"
    - "vpn-rollback.sh D-18 teardown: rm -f /usr/local/bin/splitgate then rm -rf /etc/splitgate after route restoration (Pitfall 5 ordering)"

key-files:
  created: []
  modified:
    - src/scripts/routing.sh
    - src/scripts/vpn-status.sh
    - src/scripts/update-vpn-routes
    - src/scripts/watch-routes.py
    - src/scripts/vpn-rollback.sh
    - src/scripts/10-vpn-routes
    - src/systemd/vpn-routing.service
    - README.md
    - docs/README.ru.md

key-decisions:
  - "D-12 honored: /etc/iptables/rules.v4 left unchanged (iptables-persistent path stays)"
  - "D-06 honored: /etc/cron.d/vpn-routes cleanup reference left unchanged"
  - "D-18 implemented: vpn-rollback.sh Step 7b removes /usr/local/bin/splitgate then /etc/splitgate/ as LAST filesystem operations before summary banner"
  - "Step 4c removed from vpn-rollback.sh: rm -f /etc/white-list-extended.txt is now redundant — D-18 removes entire /etc/splitgate/ tree"

patterns-established:
  - "Pattern: /etc/splitgate/ is the canonical RPi namespace for all app scripts, configs, and data files"

requirements-completed: []

# Metrics
duration: 23min
completed: "2026-05-27"
---

# Phase 10 Plan 01: Splitgate Path Migration Summary

**All internal /etc/ path references in 7 RPi scripts and the systemd unit migrated to /etc/splitgate/ namespace; vpn-rollback.sh extended with D-18 teardown (rm -f /usr/local/bin/splitgate + rm -rf /etc/splitgate/)**

## Performance

- **Duration:** 23 min
- **Started:** 2026-05-27T17:51:07Z
- **Completed:** 2026-05-27T18:14:00Z
- **Tasks:** 2
- **Files modified:** 9 (7 scripts/units + 2 READMEs)

## Accomplishments

- Migrated all /etc/ internal cross-references to /etc/splitgate/ across 7 files (routing.sh, vpn-status.sh, update-vpn-routes, watch-routes.py, vpn-rollback.sh, 10-vpn-routes, vpn-routing.service)
- Extended vpn-rollback.sh with D-18 teardown step (Step 7b: removes /usr/local/bin/splitgate and /etc/splitgate/ tree after route restoration, per Pitfall 5 ordering)
- Updated both README.md and README.ru.md to reflect new /etc/splitgate/ paths in all CLI examples, stage descriptions, and troubleshooting entries

## Task Commits

1. **Task 1: Migrate /etc/ paths in routing.sh, vpn-status.sh, update-vpn-routes, watch-routes.py** - `bfdaf05` (feat)
2. **Task 2: Migrate /etc/ paths in vpn-rollback.sh, 10-vpn-routes, vpn-routing.service; add D-18 teardown** - `ab29625` (feat)
3. **README update (CLAUDE.md convention)** - `3f07d63` (docs)

## Files Created/Modified

- `src/scripts/routing.sh` - WHITE_LIST_FILE, EXCEPTIONS_FILE, vpn-gateway.env guard+source+log → /etc/splitgate/; header comments updated
- `src/scripts/vpn-status.sh` - vpn-gateway.env guard+source → /etc/splitgate/; asn-lookup.py detection+invocation → /etc/splitgate/; header comments updated
- `src/scripts/update-vpn-routes` - SUBNET_FILE, EXCLUDE_FILE → /etc/splitgate/; vpn-gateway.env guard+source → /etc/splitgate/; routing.sh --no-update calls → /etc/splitgate/; header comments updated
- `src/scripts/watch-routes.py` - ASN_LOOKUP_PATH → /etc/splitgate/asn-lookup.py; module docstring updated
- `src/scripts/vpn-rollback.sh` - vpn-gateway.env guard+source → /etc/splitgate/; Step 4c removed; Step 7b added (D-18 teardown); Step 8 summary updated; header comments updated
- `src/scripts/10-vpn-routes` - /etc/routing.sh --no-update → /etc/splitgate/routing.sh --no-update
- `src/systemd/vpn-routing.service` - ExecStart=/etc/routing.sh → ExecStart=/etc/splitgate/routing.sh; D-01 comment updated
- `README.md` - All /etc/ script/data paths updated to /etc/splitgate/; rollback section updated with D-18 behavior
- `docs/README.ru.md` - All /etc/ script/data paths updated to /etc/splitgate/; rollback section updated with D-18 behavior

## Decisions Made

- Kept `/etc/iptables/rules.v4` unchanged per D-12 (iptables-persistent requires exact path)
- Kept `/etc/cron.d/vpn-routes` removal in vpn-rollback.sh unchanged per D-06
- Removed Step 4c entirely (rm /etc/white-list-extended.txt) — D-18 removes the whole /etc/splitgate/ tree making individual file removals redundant
- D-18 teardown steps ordered: rm /usr/local/bin/splitgate THEN rm -rf /etc/splitgate, AFTER ip route add default (per Pitfall 5: teardown after route restoration)
- watch-routes.py in READMEs now documented as `sudo python3 /etc/splitgate/watch-routes.py` (not `sudo /etc/watch-routes.py`) — Python scripts require explicit interpreter

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Updated header comments alongside code paths**
- **Found during:** Task 1 and Task 2
- **Issue:** Plan action explicitly required updating header comments (e.g., "Deployed to /etc/routing.sh" → "Deployed to /etc/splitgate/routing.sh"). The verify grep filter `grep -v '^[^:]*:[[:space:]]*#'` in the done criteria was designed for a single-colon format but grep output uses `filename:linenum:content` format — the pattern did not exclude comment lines as intended.
- **Fix:** Updated all comment lines referencing old paths per task action instructions. The comment-line matches in the done criteria count (3 instead of 2 for `routing.sh --no-update`) represent correct behavior (2 executable + 1 comment updated per instructions).
- **Files modified:** All 4 Task 1 files, all 3 Task 2 files
- **Committed in:** bfdaf05, ab29625 (within task commits)

---

**Total deviations:** 1 documentation-only clarification (no behavior changes)
**Impact on plan:** Zero — pure comment update per plan action instructions; all executable path changes verified correct.

## Issues Encountered

None - plan executed exactly as specified.

## Known Stubs

None - this is a pure path migration with no data-flow or UI components.

## Threat Flags

No new security surface introduced. T-10-01, T-10-02, T-10-03 all mitigated as specified in the plan threat model. The `rm -rf /etc/splitgate` literal (no variable expansion) satisfies T-10-01. ExecStart updated satisfies T-10-02 readiness. Error messages referencing the new env path satisfy T-10-03 (env file contains no secrets).

## Next Phase Readiness

- Plan 10-02 (deploy.sh remote variable updates) is now unblocked — scripts contain correct target paths
- Plan 10-03 (dispatcher + logrotate) is unblocked
- After Plans 02 + 03 deploy, the RPi will use /etc/splitgate/ for all scripts and data files

## Self-Check: PASSED

- FOUND: src/scripts/routing.sh
- FOUND: src/scripts/vpn-status.sh
- FOUND: src/scripts/update-vpn-routes
- FOUND: src/scripts/watch-routes.py
- FOUND: src/scripts/vpn-rollback.sh
- FOUND: src/scripts/10-vpn-routes
- FOUND: src/systemd/vpn-routing.service
- FOUND: .planning/phases/10-splitgate-ergonomics/10-01-SUMMARY.md
- FOUND: commit bfdaf05 (Task 1)
- FOUND: commit ab29625 (Task 2)
- FOUND: commit 3f07d63 (README update)

---
*Phase: 10-splitgate-ergonomics*
*Completed: 2026-05-27*
