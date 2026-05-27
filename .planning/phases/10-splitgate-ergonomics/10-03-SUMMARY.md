---
phase: 10-splitgate-ergonomics
plan: "03"
subsystem: infra
tags: [bash, splitgate, dispatcher, logrotate, docs, readme]
dependency_graph:
  requires:
    - 10-01 (internal /etc/splitgate/ path migration in all 7 scripts)
    - 10-02 (deploy.sh preflight checks for scripts/splitgate and configs/logrotate-vpn-gateway)
  provides:
    - src/scripts/splitgate — bash dispatcher CLI deployed to /usr/local/bin/splitgate
    - src/configs/logrotate-vpn-gateway — logrotate stanza targeting /etc/splitgate/logs/vpn-gateway.log
    - README.md and docs/README.ru.md updated with splitgate CLI, filesystem layout, D-18 rollback behavior
  affects:
    - Phase 10 deploy is now fully unblocked (preflight checks pass)
    - Phase 9 — logrotate config exists with correct path
tech_stack:
  added: []
  patterns:
    - "exec-based bash dispatcher: exec replaces shell process so target's exit code propagates without wrapper overhead"
    - "logrotate stanza with dateext + compress + 0640 permissions for secure log rotation"
requirements-completed: []
key-files:
  created:
    - src/scripts/splitgate
    - src/configs/logrotate-vpn-gateway
    - .planning/phases/10-splitgate-ergonomics/10-03-SUMMARY.md
  modified:
    - README.md
    - docs/README.ru.md
key-decisions:
  - "splitgate dispatcher uses exec for all 5 subcommands — replaces shell process; target exit code propagates cleanly (no double-process overhead)"
  - "watch subcommand uses exec sudo python3 (not exec sudo) because watch-routes.py lacks a shebang that lets the OS invoke it as root directly"
  - "No set -euo pipefail in dispatcher — exec replaces the shell; defensive flags unnecessary and could interfere with target exit code semantics"
  - "logrotate stanza references /etc/splitgate/logs/vpn-gateway.log (Phase 10 path, not Phase 9 D-01 /var/log/vpn-gateway.log which was superseded by D-19)"
  - "README docs added splitgate CLI section, filesystem layout tree, and explicit D-18 rollback behavior (white-list.txt included in /etc/splitgate/ tree removal)"
duration: 5min
completed: 2026-05-27
---

# Phase 10 Plan 03: Splitgate Dispatcher + Logrotate Config + README Docs Summary

**bash exec-dispatcher at /usr/local/bin/splitgate (5 subcommands → /etc/splitgate/* targets) + logrotate stanza for /etc/splitgate/logs/vpn-gateway.log + README docs for splitgate CLI, filesystem layout, and D-18 rollback behavior**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-27T14:55:00Z
- **Completed:** 2026-05-27T14:58:38Z
- **Tasks:** 3
- **Files modified:** 4 (src/scripts/splitgate, src/configs/logrotate-vpn-gateway, README.md, docs/README.ru.md)

## Accomplishments

### Task 1: Create src/scripts/splitgate dispatcher
- Created `src/scripts/splitgate` (22 lines, bash, executable mode 0755)
- Implements all 5 subcommands (status, watch, rollback, routing, update) dispatching to `/etc/splitgate/` targets via `exec sudo`
- `watch` uses `exec sudo python3` per D-14 (watch-routes.py lacks direct executable invocation as root)
- Default `*)` branch prints exact `Usage: splitgate {status|watch|rollback|routing|update} [args...]` and exits 1 per D-16
- Header comment block lists decisions D-13 through D-18

### Task 2: Create src/configs/logrotate-vpn-gateway
- Created `src/configs/logrotate-vpn-gateway` (10 lines, logrotate stanza)
- Targets `/etc/splitgate/logs/vpn-gateway.log` (Phase 10 path per D-19 — NOT Phase 9 D-01 `/var/log/vpn-gateway.log`)
- All 7 required directives: daily, rotate 14, compress, dateext, missingok, notifempty, create 0640 root root
- Single-line header comment referencing D-11 and D-19

### Task 3: Update README.md + docs/README.ru.md
- Added "splitgate CLI" section with 5-row dispatch table and Usage string note
- Added "Filesystem Layout on the RPi" section with `/etc/splitgate/` tree + system-location files list
- Updated Rollback section: explicitly states `/etc/splitgate/` tree (including `white-list.txt`) is removed by D-18
- Added Phase 10 entry in Development Phases table
- Both READMEs verified free of stale `sudo /etc/{routing.sh,vpn-status.sh,vpn-rollback.sh,...}` invocations
- Both files kept in sync (Russian file translated equivalently)

## Task Commits

1. **Task 1: Create src/scripts/splitgate ergonomic dispatcher CLI** - `087ef1f` (feat)
2. **Task 2: Create src/configs/logrotate-vpn-gateway stanza** - `b481f7d` (feat)
3. **Task 3: Update README docs for splitgate CLI + filesystem layout + rollback** - `dff43be` (docs)

## Files Created/Modified

- `src/scripts/splitgate` — bash exec-dispatcher; deployed to `/usr/local/bin/splitgate` by Stage 26; 5 subcommands + Usage default branch
- `src/configs/logrotate-vpn-gateway` — logrotate stanza targeting `/etc/splitgate/logs/vpn-gateway.log`; deployed to `/etc/logrotate.d/vpn-gateway` by Stage 27
- `README.md` — added splitgate CLI section, filesystem layout tree, D-18 rollback behavior, Phase 10 changelog entry
- `docs/README.ru.md` — same additions in Russian; all terminology consistent with existing Russian text

## Decisions Made

- `exec` used in all 5 case branches — replaces the dispatcher shell process with the target, so the target's exit code is the dispatcher's exit code; no wrapper process overhead
- `exec sudo python3` for `watch` branch — `watch-routes.py` is not deployed with a shebang that the OS can invoke as root directly; `exec sudo python3 path` is the correct invocation
- No `set -euo pipefail` — after `exec`, no more shell code runs; the flag would be misleading and could interfere with target exit code in edge cases
- Logrotate stanza uses only 7 canonical directives (no postrotate, sharedscripts, delaycompress, etc.) — minimal stanza matching Phase 9 intent

## Deviations from Plan

None — plan executed exactly as written. All three tasks completed per specification.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. The two new files enable `deploy.sh` preflight to pass; actual deploy to RPi is the next manual step.

## Next Phase Readiness

Phase 10 is now fully complete (all 4 plans done):
- 10-00: src/ restructure
- 10-01: internal path migration to /etc/splitgate/
- 10-02: deploy.sh remote vars + 3 new stages (5/26/27)
- 10-03: dispatcher + logrotate config + README docs

`bash src/deploy.sh` preflight will now pass for both `scripts/splitgate` and `configs/logrotate-vpn-gateway`. The full 27-stage deploy is ready for execution on the RPi.

Phase 9 (Operational Logging) is the remaining unexecuted phase — when executed, it should write log output to `/etc/splitgate/logs/vpn-gateway.log` (the path already referenced by the logrotate config created in this plan).

---
*Phase: 10-splitgate-ergonomics*
*Completed: 2026-05-27*

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| src/scripts/splitgate exists | FOUND |
| src/configs/logrotate-vpn-gateway exists | FOUND |
| 10-03-SUMMARY.md exists | FOUND |
| bash -n src/scripts/splitgate exits 0 | PASSED |
| splitgate is executable | PASSED |
| Usage string correct | PASSED |
| Exit code 1 on no args | PASSED |
| SPLITGATE_DIR="/etc/splitgate" (exactly 1) | PASSED |
| 5 case branches | PASSED (5) |
| exec sudo count ≥ 4 | PASSED (5) |
| exec sudo python3 count = 1 | PASSED |
| Line count ≤ 30 | PASSED (22) |
| logrotate path /etc/splitgate/logs/vpn-gateway.log | PASSED |
| All 7 directives present | PASSED |
| No /var/log/vpn-gateway.log | PASSED (0 matches) |
| No unexpected directives | PASSED (0) |
| splitgate status in README | PASSED |
| splitgate watch in README | PASSED |
| /etc/splitgate/ in README | PASSED |
| Usage string in README | PASSED (1 match) |
| /usr/local/bin/splitgate in README | PASSED |
| No stale /etc/routing.sh invocations in README | PASSED |
| Same checks on docs/README.ru.md | PASSED |
| Commit 087ef1f (Task 1) | FOUND |
| Commit b481f7d (Task 2) | FOUND |
| Commit dff43be (Task 3) | FOUND |
