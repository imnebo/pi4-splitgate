---
phase: 08-ru-ip-list-exclusion-filter
plan: "01"
subsystem: infra
tags: [bash, curl, routing, ru-ip-list, exclusion-filter]

# Dependency graph
requires:
  - phase: 07-update-vpn-routes
    provides: update-vpn-routes script with RU_SUBNET_URL and Stage 1 curl download
provides:
  - EFFECTIVE_URL construction block in update-vpn-routes that reads /etc/ru-exclude.txt
  - Per-CIDR exclusion appended as &exclude[cidr4]=LINE query params to download URL
affects:
  - 08-02-deploy-exclude-file
  - 08-03-verify-exclusion-filter

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "EFFECTIVE_URL pattern: initialize from base URL var, conditionally extend via file-driven loop"
    - "Bash arithmetic guard: (( count++ )) || true to avoid set -e triggering on zero result"
    - "Comment/blank-line skip: [[ line =~ ^# || -z line ]] && continue"

key-files:
  created: []
  modified:
    - scripts/update-vpn-routes

key-decisions:
  - "EFFECTIVE_URL initialized to RU_SUBNET_URL and extended only when /etc/ru-exclude.txt has non-comment, non-blank lines"
  - "Used (( exclude_count++ )) || true to prevent set -e from aborting on first increment (when count transitions from 0)"
  - "Exclusion file absence is a no-op: if -f guard ensures unchanged behavior when /etc/ru-exclude.txt does not exist"

patterns-established:
  - "File-driven URL parameter injection: read operator-controlled file, append query params, pass EFFECTIVE_URL to network call"

requirements-completed: []

# Metrics
duration: 1 min
completed: 2026-05-27
---

# Phase 8 Plan 01: RU IP Exclusion Filter — EFFECTIVE_URL Construction Summary

**Bash loop in update-vpn-routes reads /etc/ru-exclude.txt and builds EFFECTIVE_URL by appending &exclude[cidr4]=CIDR query parameters before the Stage 1 curl download**

## Performance

- **Duration:** 1 min
- **Started:** 2026-05-27T12:34:11Z
- **Completed:** 2026-05-27T12:35:56Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Inserted EFFECTIVE_URL construction block between `source /etc/vpn-gateway.env` and Stage 1 in `scripts/update-vpn-routes`
- When `/etc/ru-exclude.txt` is absent or empty, `EFFECTIVE_URL` equals `RU_SUBNET_URL` — behavior identical to before
- When exclude file has valid CIDR entries, each non-comment non-blank line is appended as `&exclude[cidr4]=LINE`
- Excluded CIDR count is logged via `logger -t vpn-routes` for operator visibility
- The Stage 1 curl call now uses `${EFFECTIVE_URL}` instead of `${RU_SUBNET_URL}` directly

## Task Commits

Each task was committed atomically:

1. **Task 1: Insert EFFECTIVE_URL construction block into update-vpn-routes** - `e2f4ac6` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `scripts/update-vpn-routes` - Added 19 lines: EFFECTIVE_URL block + curl call updated

## Decisions Made
- Used `(( exclude_count++ )) || true` to prevent `set -e` from triggering when the counter increments from 0 (arithmetic expansion returns exit code 1 when result is 0)
- Guard with `[[ -f "${EXCLUDE_FILE}" ]]` ensures absent file is a zero-cost no-op
- Comment and blank line skipping follows the same pattern used elsewhere in the project

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `scripts/update-vpn-routes` is ready with EFFECTIVE_URL logic
- Next: Plan 08-02 — deploy `/etc/ru-exclude.txt` to the RPi and deploy updated script
- No blockers

## Self-Check: PASSED

Verified checks:
- `[ -f scripts/update-vpn-routes ]` → FOUND
- `bash -n scripts/update-vpn-routes` → PASSED
- `grep EFFECTIVE_URL scripts/update-vpn-routes` → 3 lines (lines 40, 47, 58)
- `grep ru-exclude.txt scripts/update-vpn-routes` → 2 lines (lines 38, 41)
- `grep 'curl.*EFFECTIVE_URL' scripts/update-vpn-routes` → 1 line (line 58)
- `grep 'curl.*RU_SUBNET_URL' scripts/update-vpn-routes` → 0 lines
- Commit `e2f4ac6` exists: `feat(08-01): add EFFECTIVE_URL exclusion filter to update-vpn-routes`

---
*Phase: 08-ru-ip-list-exclusion-filter*
*Completed: 2026-05-27*
