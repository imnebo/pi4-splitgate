---
phase: 08-ru-ip-list-exclusion-filter
plan: "02"
subsystem: infra
tags: [deploy, scp, bash, split-tunnel, ru-exclude]

# Dependency graph
requires:
  - phase: 07-asn-lookup
    provides: deploy.sh with TOTAL_STAGES=24 and Stage 21 white-list-extended.txt pattern
provides:
  - EXCLUDE_LIST_LOCAL/REMOTE/TMP path variables in deploy.sh
  - Stage 21b conditional SCP block deploying configs/ru-exclude.txt to /etc/ru-exclude.txt
  - PHASE 8 summary line in deploy.sh Final Summary
affects:
  - 08-03-PLAN — README/docs updates for Phase 8 feature

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sub-stage pattern: Stage 21b uses same number as Stage 21 (no TOTAL_STAGES bump for optional adjacent deploy)"
    - "Conditional file deploy: [[ -f local ]] guard + scp + sudo mv + chmod 644 + chown root:root"

key-files:
  created: []
  modified:
    - deploy.sh

key-decisions:
  - "Stage 21b reuses stage number 21 rather than incrementing TOTAL_STAGES — optional adjacent deploy does not count as a new stage"
  - "EXCLUDE_LIST variable naming follows WHITE_LIST_EXT pattern for consistency (LOCAL/REMOTE/TMP suffix)"

patterns-established:
  - "Sub-stage pattern: conditional optional deploys adjacent to their parent stage share the parent stage number"

requirements-completed: []

# Metrics
duration: 5min
completed: 2026-05-27
---

# Phase 8 Plan 02: Stage 21b EXCLUDE_LIST Deploy Summary

**deploy.sh extended with EXCLUDE_LIST_* path vars, conditional Stage 21b SCP block for ru-exclude.txt, and PHASE 8 Final Summary line — TOTAL_STAGES unchanged at 24**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-27T12:35:00Z
- **Completed:** 2026-05-27T12:40:48Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Added three EXCLUDE_LIST_* path variable declarations in the deploy.sh path variable block (after WHITE_LIST_EXT_TMP, before NM_DISPATCHER_LOCAL)
- Added Stage 21b conditional SCP block: deploys configs/ru-exclude.txt to /etc/ru-exclude.txt (mode 644, root:root) when local file exists, skips silently otherwise
- Added PHASE 8 echo line to Final Summary section after PHASE 7 line
- TOTAL_STAGES remains 24 — Stage 21b is a sub-stage adjacent to Stage 21, not a new numbered stage

## Task Commits

Each task was committed atomically:

1. **Task 1: Add path variable declarations** + **Task 2: Add Stage 21b block and PHASE 8 summary** - `9b40841` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified

- `deploy.sh` - Added EXCLUDE_LIST_LOCAL/REMOTE/TMP vars, Stage 21b conditional SCP block, PHASE 8 Final Summary echo

## Decisions Made

- Stage 21b echoes `[21/${TOTAL_STAGES}]` (same number as Stage 21) because it is an optional adjacent sub-deploy, not a new mandatory pipeline stage — no TOTAL_STAGES bump
- Variable naming (`EXCLUDE_LIST_LOCAL`, `EXCLUDE_LIST_REMOTE`, `EXCLUDE_LIST_TMP`) mirrors the WHITE_LIST_EXT pattern for readability and consistency

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Stage 21b is live in deploy.sh; operators who create `configs/ru-exclude.txt` will have it deployed automatically on next `./deploy.sh` run
- Plan 08-03 (README/docs updates) can proceed

## Self-Check

- [x] `bash -n deploy.sh` passes (no syntax errors)
- [x] `grep "Stage 21b" deploy.sh` returns 1 line
- [x] `grep "PHASE 8" deploy.sh` returns 1 line in Final Summary
- [x] `grep -c "TOTAL_STAGES=24" deploy.sh` returns 1
- [x] `grep -c "TOTAL_STAGES=25" deploy.sh` returns 0
- [x] EXCLUDE_LIST_LOCAL grep returns 7 lines (>= 4 required)
- [x] Commit 9b40841 exists

## Self-Check: PASSED

---
*Phase: 08-ru-ip-list-exclusion-filter*
*Completed: 2026-05-27*
