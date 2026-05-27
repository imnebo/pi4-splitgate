---
phase: 10-splitgate-ergonomics
plan: "00"
subsystem: repo-structure
tags: [restructure, git-mv, src-layout, deploy]
dependency_graph:
  requires: []
  provides: [src/scripts, src/configs, src/systemd, src/tests, src/deploy.sh]
  affects: [10-01, 10-02, 10-03]
tech_stack:
  added: []
  patterns: [cd-$(dirname-BASH_SOURCE) for portable script invocation]
key_files:
  created:
    - src/deploy.sh
    - src/scripts/routing.sh
    - src/scripts/vpn-status.sh
    - src/scripts/vpn-rollback.sh
    - src/scripts/update-vpn-routes
    - src/scripts/watch-routes.py
    - src/scripts/10-vpn-routes
    - src/scripts/asn-lookup.py
    - src/scripts/install-awg.sh
    - src/configs/dnsmasq.conf
    - src/configs/amnezia.key.template.txt
    - src/systemd/vpn-routing.service
    - src/tests/test_asn_lookup.py
    - src/tests/test_vpn_status_phase7.sh
    - src/tests/test_watch_routes_asn.py
  modified:
    - .gitignore
    - README.md
    - docs/README.ru.md
decisions:
  - "D-10-00-01: cd '$(dirname BASH_SOURCE[0])' inserted immediately after set -euo pipefail in src/deploy.sh — all *_LOCAL relative paths (scripts/, configs/, systemd/) resolve to src/ subdirectories without modification"
  - "D-10-00-02: .env and .env.secrets accessed via ../ prefix from src/deploy.sh after cd; repo-level .gitignore gains src/configs/ prefix on previously bare configs/ entries"
metrics:
  duration: "644s (10 min)"
  completed_date: "2026-05-27"
  tasks_completed: 3
  files_changed: 18
---

# Phase 10 Plan 00: src/ Directory Restructure Summary

Pure structural reorganization — all source code, scripts, configs, and deploy tooling moved into `src/` using git mv (history preserved); deploy.sh patched to auto-navigate to its own directory at startup.

## What Was Built

All source directories and the deploy orchestrator moved from repo root into `src/`:

| Old path | New path |
|----------|----------|
| `scripts/` | `src/scripts/` |
| `configs/` | `src/configs/` |
| `systemd/` | `src/systemd/` |
| `tests/` | `src/tests/` |
| `deploy.sh` | `src/deploy.sh` |
| `amnezia.key.template.txt` | `src/configs/amnezia.key.template.txt` |

`src/deploy.sh` gains `cd "$(dirname "${BASH_SOURCE[0]}")"` immediately after `set -euo pipefail`, making it invocable as `bash src/deploy.sh` from the repo root. All `*_LOCAL` relative path variables (e.g. `ROUTING_SH_LOCAL="scripts/routing.sh"`) continue to resolve correctly — now relative to `src/`.

`.env` and `.env.secrets` remain at repo root and are accessed via `../` prefix. `TEMPLATE` updated from `amnezia.key.template.txt` to `configs/amnezia.key.template.txt`.

`.gitignore` updated to use `src/configs/` prefix for both `white-list-extended.txt` and `ru-exclude.txt`. README.md and docs/README.ru.md updated to reflect new invocation (`bash src/deploy.sh`) and new file paths.

## Commits

| Task | Description | Hash |
|------|-------------|------|
| 1 | git mv all source directories into src/ | 7830898 |
| 2 | Update src/deploy.sh for src/ relocation | 43a9a65 |
| 3 | Update .gitignore for src/ path prefix | 6605307 |
| docs | Update README.md and README.ru.md | ad409fc |

## Deviations from Plan

### Auto-added (CLAUDE.md requirement)

**README.md + docs/README.ru.md update (CLAUDE.md: keep both READMEs in sync)**

- **Found during:** Post-task review
- **Issue:** CLAUDE.md mandates: "After completing any task, review README.md and docs/README.ru.md. If the work touched areas covered by either file — update them before closing the task." Both READMEs reference `./deploy.sh`, `scripts/`, and `configs/` paths that no longer exist at repo root.
- **Fix:** Updated all invocation commands (`./deploy.sh` → `bash src/deploy.sh`), script section headings (`scripts/routing.sh` → `src/scripts/routing.sh`), and config file copy commands (`configs/white-list-extended.txt` → `src/configs/white-list-extended.txt`) in both README.md and docs/README.ru.md.
- **Files modified:** README.md, docs/README.ru.md
- **Commit:** ad409fc

### Observation: src/configs/.gitignore lifecycle

During `git mv configs src/configs`, git moved an untracked-but-present `configs/.gitignore` (containing the full old root-level gitignore content, not the per-directory rules). This file was committed in Task 2 as `src/configs/.gitignore` (wrong content), then deleted in the docs commit. The correct gitignore rules for `src/configs/` are now in the root `.gitignore` with the `src/configs/` prefix, which is the right approach for a root-anchored gitignore.

## Known Stubs

None — this is a pure structural move with no logic changes.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. File moves only.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| src/scripts exists | FOUND |
| src/configs exists | FOUND |
| src/systemd exists | FOUND |
| src/tests exists | FOUND |
| src/deploy.sh exists | FOUND |
| src/configs/amnezia.key.template.txt exists | FOUND |
| SUMMARY.md exists | FOUND |
| Commit 7830898 (Task 1) | FOUND |
| Commit 43a9a65 (Task 2) | FOUND |
| Commit 6605307 (Task 3) | FOUND |
| Commit ad409fc (docs) | FOUND |
