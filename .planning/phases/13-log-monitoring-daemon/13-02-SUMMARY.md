---
phase: "13-log-monitoring-daemon"
plan: "02"
subsystem: "scripts, configs"
tags: [rename, logging, file-rename, install-log, exclude-filter]
dependency_graph:
  requires: []
  provides:
    - "routing.sh writes to /etc/splitgate/logs/install.log (was vpn-gateway.log)"
    - "routing.sh reads /etc/splitgate/ru-list-exclude.txt (was ru-exclude.txt)"
    - "update-vpn-routes writes to install.log; logs source domain, excluded CIDRs, route count"
    - "vpn-rollback.sh writes to install.log; Step 8 summary lists ru-list-exclude.txt"
    - "logrotate-vpn-gateway targets install.log; postrotate cleans watch-*.log files older than 14 days"
    - "ru-list-exclude.txt.example replaces ru-exclude.txt.example (git mv)"
  affects:
    - "src/deploy.sh (Plan 03 handles deploy.sh ru-exclude.txt → ru-list-exclude.txt rename)"
    - "docs/ (Plan 04 handles README.md, docs/README.ru.md, docs/REFERENCE.md updates)"
tech_stack:
  added: []
  patterns:
    - "exclude_list variable accumulates CIDRs during loop for verbose log output"
    - "logrotate postrotate with find -delete for dated watch-*.log cleanup"
key_files:
  created: []
  modified:
    - src/scripts/routing.sh
    - src/scripts/update-vpn-routes
    - src/scripts/vpn-rollback.sh
    - src/configs/logrotate-vpn-gateway
    - src/configs/ru-list-exclude.txt.example
decisions:
  - "D-07: vpn-gateway.log renamed to install.log across all scripts and logrotate config"
  - "D-08: ru-exclude.txt renamed to ru-list-exclude.txt in scripts; example file renamed via git mv with full internal content update"
  - "D-09: update-vpn-routes now logs source domain (russia.iplist.opencck.org), actual excluded CIDRs (not just count), and downloaded route count"
  - "D-09: routing.sh Stage 1 exclude log now lists all CIDRs explicitly"
  - "D-06: logrotate postrotate block added to clean watch-*.log files older than 14 days"
metrics:
  duration: "~15 minutes"
  completed: "2026-05-29T09:56:17Z"
  tasks_completed: 2
  files_modified: 5
---

# Phase 13 Plan 02: Log and File Rename + Install Log Verbosity Summary

**One-liner:** vpn-gateway.log renamed to install.log and ru-exclude.txt to ru-list-exclude.txt across five files; install log verbosity improved with source domain, explicit CIDR list, and route count.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rename log and exclude file refs in routing.sh and update-vpn-routes | 1883de6 | src/scripts/routing.sh, src/scripts/update-vpn-routes |
| 2 | Update vpn-rollback.sh, logrotate config, and rename example file | 9115126 | src/scripts/vpn-rollback.sh, src/configs/logrotate-vpn-gateway, src/configs/ru-list-exclude.txt.example |

## What Was Done

### Task 1: routing.sh and update-vpn-routes

**D-07 (vpn-gateway.log → install.log):**
- `routing.sh` L46: `LOG_FILE` updated to `/etc/splitgate/logs/install.log`
- `update-vpn-routes`: `log()` function hardcode updated to `/etc/splitgate/logs/install.log`; header comment updated

**D-08 (ru-exclude.txt → ru-list-exclude.txt):**
- `routing.sh` L92: `EXCLUDE_FILE` updated to `/etc/splitgate/ru-list-exclude.txt`
- `routing.sh` L89, L159: comments updated from `ru-exclude.txt` to `ru-list-exclude.txt`
- `update-vpn-routes` L41: `EXCLUDE_FILE` updated to `/etc/splitgate/ru-list-exclude.txt`
- `update-vpn-routes` L38: comment updated

**D-09 (install log verbosity):**
- `routing.sh`: Stage 1 exclude loop now builds `exclude_list` variable and logs "Stage 1: Applying N exclusion(s) from FILE: CIDR1 CIDR2 ..." instead of just the count
- `update-vpn-routes`: exclude loop builds `exclude_list` and logs "Excluding N CIDR(s) from RU subnet download: CIDR1 CIDR2 ..." instead of just the count
- `update-vpn-routes`: added `log "Source: russia.iplist.opencck.org"` before the curl call
- `update-vpn-routes`: added `route_count=$(grep -c . "${SUBNET_FILE}") && log "Downloaded ${route_count} routes"` after successful mv in Stage 3

### Task 2: vpn-rollback.sh, logrotate-vpn-gateway, ru-list-exclude.txt.example

**D-07 (vpn-gateway.log → install.log):**
- `vpn-rollback.sh` L34: `log()` updated to `/etc/splitgate/logs/install.log`
- `vpn-rollback.sh` L14: header comment updated from `vpn-gateway.log` to `install.log`
- `logrotate-vpn-gateway`: target path updated from `vpn-gateway.log` to `install.log`

**D-08 (ru-exclude.txt → ru-list-exclude.txt):**
- `vpn-rollback.sh` L155: Step 8 summary echo updated to list `ru-list-exclude.txt`
- `src/configs/ru-exclude.txt.example` renamed to `ru-list-exclude.txt.example` via `git mv`
- All internal content updated: header comment, RPi path (`/etc/splitgate/ru-list-exclude.txt`), copy instructions, step 5 stage reference (22b)

**D-06 (logrotate postrotate):**
- `logrotate-vpn-gateway`: added `sharedscripts` + `postrotate` block with `find /etc/splitgate/logs -name "watch-*.log" -mtime +14 -delete 2>/dev/null || true` + `endscript`

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

All automated checks passed:
- `grep 'vpn-gateway\.log' routing.sh update-vpn-routes vpn-rollback.sh logrotate-vpn-gateway` → no output
- `grep 'ru-exclude\.txt' routing.sh update-vpn-routes vpn-rollback.sh ru-list-exclude.txt.example` → no output
- `bash -n src/scripts/routing.sh && bash -n src/scripts/update-vpn-routes && bash -n src/scripts/vpn-rollback.sh` → all exit 0
- `grep -q 'postrotate' src/configs/logrotate-vpn-gateway` → exit 0
- `test -f src/configs/ru-list-exclude.txt.example && test ! -f src/configs/ru-exclude.txt.example` → exit 0
- `grep -q 'exclude_list' src/scripts/update-vpn-routes` → exit 0
- `grep -q 'Downloaded.*routes' src/scripts/update-vpn-routes` → exit 0
- `grep -q 'russia\.iplist\.opencck\.org' src/scripts/update-vpn-routes` → exit 0

## Scope Notes

Per plan design, these files are NOT modified in Plan 02:
- `src/deploy.sh` — handles `ru-exclude.txt` and `vpn-gateway.log` rename (Plan 03, Wave 2)
- `README.md`, `docs/README.ru.md`, `docs/REFERENCE.md` — docs update (Plan 04)

Stale references to `vpn-gateway.log` and `ru-exclude.txt` remain in `src/deploy.sh` and docs intentionally — those are Plan 03 and Plan 04 scope respectively.

## Known Stubs

None — all renames are complete in the files targeted by this plan.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries. The logrotate `find -delete` postrotate script is tightly scoped to `watch-*.log` in the root-owned `/etc/splitgate/logs/` directory (T-13-02-01: accept).

## Self-Check

- [x] src/scripts/routing.sh — exists, contains `install.log` and `ru-list-exclude.txt`
- [x] src/scripts/update-vpn-routes — exists, contains `install.log`, `ru-list-exclude.txt`, `russia.iplist.opencck.org`, `exclude_list`, `Downloaded`
- [x] src/scripts/vpn-rollback.sh — exists, contains `install.log`, `ru-list-exclude.txt`
- [x] src/configs/logrotate-vpn-gateway — exists, contains `install.log`, `postrotate`, `watch-*.log`
- [x] src/configs/ru-list-exclude.txt.example — exists, zero `ru-exclude.txt` references
- [x] Commit 1883de6 exists
- [x] Commit 9115126 exists

## Self-Check: PASSED
