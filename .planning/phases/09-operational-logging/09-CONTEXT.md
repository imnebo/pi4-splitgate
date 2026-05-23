# Phase 9: Operational Logging - Context

**Gathered:** 2026-05-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Centralized, human-readable operational log at `/var/log/vpn-gateway.log` that aggregates events from all daemon/cron scripts. When any component fails or misbehaves, the operator opens this file and immediately understands what happened and when.

**In scope:**
- Unified `log()` helper (timestamp + component tag + message → append to `/var/log/vpn-gateway.log`)
- Update `routing.sh` `log()` and `err()` to write to the file (currently echo-only)
- Update `update-vpn-routes`, `vpn-rollback.sh` `log()` to replace `logger` with file append
- `vpn-status.sh` `log()` updated to write to file (was `logger -t vpn-status`)
- `configs/logrotate-vpn-gateway` — logrotate config, deployed to `/etc/logrotate.d/vpn-gateway`
- `deploy.sh` extended to install logrotate config on RPi
- `vpn-rollback.sh` teardown removes `/etc/logrotate.d/vpn-gateway` and `/var/log/vpn-gateway*.log`

**Out of scope:**
- Per-connection traffic logging (already handled by iptables LOG rules in Phase 4)
- Interactive tools: `vpn-status.sh` query runs, `watch-routes.py`, `asn-lookup.py` — no log writes
- JSON structured logging or log aggregation daemons
- journald / syslog configuration changes

</domain>

<decisions>
## Implementation Decisions

### Log Destination
- **D-01:** Single file: `/var/log/vpn-gateway.log`. One file for all components — chronological, grep-friendly. No per-component splitting.
- **D-02:** Scripts write by appending directly to the file — no syslog/rsyslog/journald intermediary.

### Log Function Pattern
- **D-03:** Each script gets a `log()` function: `echo "[$(date '+%F %T')] [component] $*" >> /var/log/vpn-gateway.log`. Component tags: `routing`, `update-vpn-routes`, `vpn-rollback`, `vpn-status`.
- **D-04:** `err()` writes to both the file (with `ERROR:` prefix) and stderr. Pattern: `echo "[$(date '+%F %T')] [component] ERROR: $*" | tee -a /var/log/vpn-gateway.log >&2`.
- **D-05:** Replace existing `logger -t tag` calls in `update-vpn-routes`, `vpn-rollback.sh`, `vpn-status.sh` with the new file-append `log()`. No `logger` calls remain after this phase.

### routing.sh Upgrade
- **D-06:** `routing.sh` `log()` upgraded from `echo "[routing] $*"` to `echo "[$(date '+%F %T')] [routing] $*" >> /var/log/vpn-gateway.log`. Same for `err()`.
- **D-07:** Keep current verbosity level in routing.sh (all stages logged). When something breaks, stage context before the failure is essential.

### Log Content Scope
- **D-08:** Only daemon/cron scripts write to the log: `routing.sh`, `update-vpn-routes`, `vpn-rollback.sh`. Interactive query tools (`vpn-status.sh` user-facing output, `watch-routes.py`, `asn-lookup.py`) do NOT write to `/var/log/vpn-gateway.log`.

### Rotation
- **D-09:** logrotate config at `configs/logrotate-vpn-gateway`, deployed to `/etc/logrotate.d/vpn-gateway` on RPi via deploy.sh.
- **D-10:** Rotation settings: `daily`, `rotate 14` (14-day retention), `compress`, `dateext` (files named `vpn-gateway.log-YYYYMMDD.gz`), `missingok`, `notifempty`, `create 0640 root root`.
- **D-11:** `vpn-rollback.sh` removes `/etc/logrotate.d/vpn-gateway` and `/var/log/vpn-gateway*.log` during rollback teardown.

### Claude's Discretion
- Whether to create `/var/log/vpn-gateway.log` with correct permissions on first write (e.g., touch + chmod in deploy.sh or lazily via `>> file` which creates it on first write)
- Exact placement of the logrotate deploy stage in deploy.sh (new stage number after current TOTAL_STAGES=24)
- Whether to add a `create_log_dir` step in deploy.sh (probably not needed since `/var/log` always exists on Debian)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scripts to Modify
- `scripts/routing.sh` — FULL FILE; specifically `log()` at line 44 and `err()` at line 48; replace echo with timestamped file-append
- `scripts/update-vpn-routes` — FULL FILE; `log()` at line 25: replace `logger -t "vpn-routes"` with file-append
- `scripts/vpn-rollback.sh` — FULL FILE; `log()` at line 34: replace `logger -t "vpn-rollback"` with file-append; add teardown of `/etc/logrotate.d/vpn-gateway` and log files
- `scripts/vpn-status.sh` — FULL FILE; `log()` at line 35: replace `logger -t "vpn-status"` with file-append
- `deploy.sh` — FULL FILE; add new stage to SCP `configs/logrotate-vpn-gateway` to `/etc/logrotate.d/vpn-gateway` on RPi; bump TOTAL_STAGES

### New Config File
- `configs/logrotate-vpn-gateway` — new file; standard logrotate config for `/var/log/vpn-gateway.log`

### Prior Phase Context
- `.planning/phases/08-ru-ip-list-exclusion-filter/08-CONTEXT.md` — D-07/D-08: conditional deploy pattern (mirror for logrotate config deploy)
- `.planning/phases/05-custom-route-exceptions-ip/05-CONTEXT.md` — D-12/D-13: established SCP deploy + stage pattern

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/update-vpn-routes` line 25: `log() { logger -t "vpn-routes" "$*"; }` — exact pattern to change; replace body only, keep the function signature
- `scripts/vpn-rollback.sh` line 34: `log() { logger -t "vpn-rollback" "$*"; echo "[rollback] $*"; }` — similar; drop `logger`, keep echo-to-stdout behavior for operator visibility, add file-append
- deploy.sh Stage 21 conditional SCP block — template for logrotate config deploy stage (unconditional SCP since logrotate config is always needed)

### Established Patterns
- All scripts source `/etc/vpn-gateway.env` — `LOG_FILE=/var/log/vpn-gateway.log` can be added here as a shared constant, or hardcoded in each log() function (simpler, avoid env dependency)
- File deploy: SCP to `/tmp/` staging then `sudo mv + chmod` (Phase 1 pattern)
- Stage bumping: TOTAL_STAGES incremented per new deploy stage

### Integration Points
- `vpn-rollback.sh` teardown section: add two cleanup lines after existing cleanup — `sudo rm -f /etc/logrotate.d/vpn-gateway` and `sudo rm -f /var/log/vpn-gateway*.log`
- `deploy.sh` new stage: `sudo cp /tmp/logrotate-vpn-gateway /etc/logrotate.d/vpn-gateway && sudo chmod 644 /etc/logrotate.d/vpn-gateway`

</code_context>

<specifics>
## Specific Ideas

- Log entry format: `[2026-05-23 10:30:00] [routing] Stage 3: Flushing existing VPN routes`
- Error entry format: `[2026-05-23 10:30:00] [routing] ERROR: awg0 interface not found`
- The `dateext` rotation produces files like `vpn-gateway.log-20260523.gz` — easy to correlate with incidents

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 9-operational-logging*
*Context gathered: 2026-05-23*
