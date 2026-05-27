---
phase: 10-splitgate-ergonomics
plan: "02"
subsystem: infra
tags: [bash, deploy, splitgate, path-migration, staging, logrotate, dispatcher]
dependency_graph:
  requires:
    - 10-00 (src/ restructure — deploy.sh in src/, *_LOCAL paths relative to src/)
    - 10-01 (internal /etc/ paths in 7 scripts migrated to /etc/splitgate/)
  provides:
    - deploy.sh with all *_REMOTE vars pointing under /etc/splitgate/
    - deploy.sh with 3 new stages: Stage 5 (mkdir), Stage 26 (dispatcher), Stage 27 (logrotate)
    - deploy.sh TOTAL_STAGES=27 with correct renumbering of all existing stages
    - preflight checks for scripts/splitgate and configs/logrotate-vpn-gateway
  affects:
    - 10-03 (creates scripts/splitgate and configs/logrotate-vpn-gateway that preflight checks expect)
tech_stack:
  added: []
  patterns:
    - "deploy.sh variable-driven stages: updating *_REMOTE variable propagates to all stage bodies automatically"
    - "Stage insert-and-renumber: new Stage 5 inserted, stages 5..24 shifted to 6..25"
    - "Stage 21b (Pitfall 6) corrected to [22b/${TOTAL_STAGES}] header"
key_files:
  created: []
  modified:
    - src/deploy.sh
    - README.md
    - docs/README.ru.md
decisions:
  - "Stage insert at position 5 (after AmneziaWG install, before awg0.conf render) guarantees /etc/splitgate/ exists before any sudo mv into that namespace (RESEARCH.md Pitfall 4)"
  - "Dispatcher (Stage 26) and logrotate (Stage 27) placed AFTER routing.sh activation (Stage 25) — routing activation remains the last runtime activation stage (Phase 7 D-10)"
  - "Stage 21b header bug from Pitfall 6 corrected: [21/${TOTAL_STAGES}] -> [22b/${TOTAL_STAGES}]"
  - "Final summary hardcoded /etc/(routing.sh|vpn-status.sh|vpn-rollback.sh|update-vpn-routes|white-list-extended.txt) replaced with /etc/splitgate/... literals"
requirements: []
metrics:
  duration: "789s (13 min)"
  completed_date: "2026-05-27"
  tasks_completed: 2
  files_changed: 3
---

# Phase 10 Plan 02: deploy.sh Remote Path Update Summary

**deploy.sh fully migrated: 9 `*_REMOTE` variables updated to `/etc/splitgate/`, 8 new SPLITGATE/LOGROTATE variables declared, 3 new stages added (mkdir namespace, dispatcher deploy, logrotate deploy), TOTAL_STAGES bumped to 27, existing stages 5-24 renumbered to 6-25, Stage 21b header bug fixed.**

## Performance

- **Duration:** 789s (~13 min)
- **Started:** 2026-05-27T14:38:09Z
- **Completed:** 2026-05-27T14:51:18Z
- **Tasks:** 2 (+ 1 README update per CLAUDE.md convention)
- **Files modified:** 3 (src/deploy.sh, README.md, docs/README.ru.md)

## Accomplishments

### Task 1: Variable updates + preflight checks + header fixes
- Updated 9 `*_REMOTE` variables to point under `/etc/splitgate/` (`ENV_REMOTE`, `ROUTING_SH_REMOTE`, `UPDATE_VPN_ROUTES_REMOTE`, `VPN_ROLLBACK_REMOTE`, `VPN_STATUS_REMOTE`, `WATCH_ROUTES_REMOTE`, `ASN_LOOKUP_REMOTE`, `WHITE_LIST_EXT_REMOTE`, `EXCLUDE_LIST_REMOTE`)
- Added 8 new variables: `SPLITGATE_DIR_REMOTE`, `SPLITGATE_LOGS_REMOTE`, `SPLITGATE_DISPATCHER_LOCAL/REMOTE/TMP`, `LOGROTATE_CONF_LOCAL/REMOTE/TMP`
- Bumped `TOTAL_STAGES=24` → `TOTAL_STAGES=27`
- Added two new preflight existence checks (for `scripts/splitgate` and `configs/logrotate-vpn-gateway`)
- Updated file header comment to reflect `/etc/splitgate/` namespace and new artifacts
- Fixed all hardcoded old paths in final summary block (`/etc/routing.sh`, `/etc/vpn-status.sh`, `/etc/vpn-rollback.sh`, `/etc/update-vpn-routes`, `/etc/white-list-extended.txt`) → `/etc/splitgate/...` literals

### Task 2: Stage insertion, renumbering, new stages 26-27
- Inserted **Stage 5** (Creating splitgate namespace): `sudo mkdir -p /etc/splitgate/logs && sudo chmod 755 /etc/splitgate` — runs before awg0.conf render, guaranteeing `/etc/splitgate/` exists before any file is deployed there (Pitfall 4)
- Renumbered old stages 5-24 → new 6-25 (shift +1)
- Fixed Stage 21b header bug (was `[21/${TOTAL_STAGES}]`, now `[22b/${TOTAL_STAGES}]`) — Pitfall 6 correction
- Added **Stage 26** (Deploying splitgate dispatcher): scp `scripts/splitgate` → `/tmp/splitgate.tmp` → `sudo mv + chmod +x + chown root:root` to `/usr/local/bin/splitgate`
- Added **Stage 27** (Deploying logrotate config): scp `configs/logrotate-vpn-gateway` → `/tmp/logrotate-vpn-gateway.tmp` → `sudo mv + chmod 644 + chown root:root` to `/etc/logrotate.d/vpn-gateway`
- Updated Final Summary banner: "Phase 1 + 2 + 3 + Phase 10 (splitgate ergonomics) deploy successful."
- Added two PHASE 10 bullets in Deployed section
- Added Phase 10 verification block with 6 check commands

## Task Commits

1. **Task 1: Update *_REMOTE vars + add SPLITGATE/LOGROTATE vars + preflight + header** - `abecc2c` (feat)
2. **Task 2: Add stages 5/26/27, renumber 5-24 to 6-25, fix Stage 21b, update summary** - `a409d74` (feat)
3. **README update (CLAUDE.md convention)** - `8e3f3e1` (docs)

## Files Created/Modified

- `src/deploy.sh` — 9 migrated REMOTE vars + 8 new SPLITGATE/LOGROTATE vars; TOTAL_STAGES=27; 3 new stages (5, 26, 27); renumbered stages 6-25; Stage 22b fixed; final summary updated
- `README.md` — Stage table updated: 23→27 stages, groups corrected, CLI reference stage count updated; stage references in deployment sections updated
- `docs/README.ru.md` — Same updates in Russian: stage table, stage count, inline step references

## Deviations from Plan

### Auto-added (CLAUDE.md requirement)

**README.md + docs/README.ru.md update (CLAUDE.md: keep both READMEs in sync)**

- **Found during:** Post-task review
- **Issue:** CLAUDE.md mandates: "After completing any task, review README.md and docs/README.ru.md. If the work touched areas covered by either file — update them before closing the task." Both READMEs contained the old stage count (23/24) and old stage group table (groups 5-9, 10-11, ..., 21-22, 23, 24). The deploy section also had inline stage number references (Stage 21, Stage 22, Stage 23) that now correspond to different stages.
- **Fix:** Updated stage count (23→27), stage group table with new Stage 5 group and Stages 26-27 group, renumbered inline stage references (21→22, 22→23, Stage 21b→22b, 17/18→18/19), updated CLI reference (24→27 stages).
- **Files modified:** README.md, docs/README.ru.md
- **Commit:** 8e3f3e1

## Known Stubs

**Preflight check for `scripts/splitgate` and `configs/logrotate-vpn-gateway`** — These two files do NOT yet exist in the repo. The preflight check (added in Task 1) will cause `deploy.sh` to exit 1 at Stage 1 if invoked before Plan 10-03 creates them. This is intentional by design (per plan objective: "Plan 03 must complete before any actual deploy invocation"). The stub is tracked here so the verifier knows an actual `bash src/deploy.sh` invocation will fail until Plan 10-03 is complete.

## Threat Flags

No new security surface introduced. All new stages follow the existing scp→`/tmp/foo.tmp`→`sudo mv ${TMP} ${REMOTE}` pattern (T-10-04 mitigated per plan threat model). `chmod +x /usr/local/bin/splitgate` has same trust model as existing `chmod +x` stages (T-10-05 accepted per plan). TOTAL_STAGES=27 matches actual stage count (T-10-06 mitigated — grep-verified in done criteria).

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| src/deploy.sh exists | FOUND |
| 10-02-SUMMARY.md exists | FOUND |
| Commit abecc2c (Task 1) | FOUND |
| Commit a409d74 (Task 2) | FOUND |
| Commit 8e3f3e1 (README) | FOUND |
| bash -n src/deploy.sh exits 0 | PASSED |
| TOTAL_STAGES=27 (exactly 1) | PASSED |
| SPLITGATE_DIR_REMOTE="/etc/splitgate" | PASSED |
| Stage headers count = 27 | PASSED |
| No stale /etc/(routing.sh|vpn-status.sh|vpn-rollback.sh|update-vpn-routes) | PASSED (0 matches) |
