# Phase 9: Operational Logging - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-23
**Phase:** 9-operational-logging
**Areas discussed:** Log interface, routing.sh gap, Log content depth, Rotation mechanism

---

## Log interface

| Option | Description | Selected |
|--------|-------------|----------|
| journald only | All scripts use logger -t tag → journald. Read with journalctl. | |
| Dedicated file | /var/log/vpn-gateway.log — single file, tail/cat/grep friendly. | ✓ |
| Both | logger → journald AND tee to file. Maximum coverage. Extra complexity. | |

**User's choice:** Dedicated file `/var/log/vpn-gateway.log`

| Option | Description | Selected |
|--------|-------------|----------|
| Single /var/log/vpn-gateway.log | All scripts append to one file. Chronological. | ✓ |
| Per-component files | /var/log/vpn-gateway/routing.log, etc. | |

**User's choice:** Single file

| Option | Description | Selected |
|--------|-------------|----------|
| Shared log() → append to file | Each script inlines timestamped append. No daemon. | ✓ |
| logger + rsyslog/syslog-ng rule | Keep logger calls, add syslog routing to file. | |
| Both logger and direct append | Dual output. Overkill for home gateway. | |

**User's choice:** Shared log() function with direct file append

| Option | Description | Selected |
|--------|-------------|----------|
| Replace logger with file-only | One destination. Drop existing logger calls. | ✓ |
| Keep logger, add file writes | Both journald and file populated. | |

**User's choice:** Replace logger calls with file-append in all scripts

---

## routing.sh gap

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — upgrade log() to append to file | Replace echo with timestamped file-append. | ✓ |
| No — leave echo-only | Systemd captures stdout to journald; gaps only for cron. | |

**User's choice:** Upgrade routing.sh log() to write to /var/log/vpn-gateway.log

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — errors to same file with ERROR prefix | Single file shows full context around failures. | ✓ |
| Errors to separate /var/log/vpn-gateway-errors.log | More complex, overkill. | |

**User's choice:** err() writes to same file with ERROR: prefix

---

## Log content depth

| Option | Description | Selected |
|--------|-------------|----------|
| Keep verbose — all stages logged | routing.sh logs every stage. Context for debugging. | ✓ |
| Errors and key events only | Cleaner log, fewer context clues. | |
| Add explicit levels (INFO/WARN/ERROR) | grep 'ERROR' filtering. Adds complexity. | |

**User's choice:** Keep current verbosity in routing.sh (all stages logged)

| Option | Description | Selected |
|--------|-------------|----------|
| No — interactive tools stay silent | vpn-status.sh, watch-routes.py, asn-lookup.py — no log writes. | ✓ |
| Yes — log all invocations | Noise: every query run adds log entries. | |

**User's choice:** Only daemon/cron scripts write to the log

---

## Rotation mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| logrotate config | /etc/logrotate.d/vpn-gateway. Standard Debian tool. deploy.sh installs it. | ✓ |
| Manual cron + find | find /var/log/vpn-gateway*.log -mtime +14 -delete. Reinvents logrotate. | |

**User's choice:** logrotate config

| Option | Description | Selected |
|--------|-------------|----------|
| dateext + daily | Files named vpn-gateway.log-YYYYMMDD.gz. Date-correlation friendly. | ✓ |
| Numbered + daily | vpn-gateway.log.1.gz, .2.gz. Harder to match to incident dates. | |

**User's choice:** dateext + daily rotation

| Option | Description | Selected |
|--------|-------------|----------|
| Deploy yes, rollback yes | deploy.sh installs config; vpn-rollback.sh removes config + logs. | ✓ |
| Deploy yes, rollback no | Leaves dangling logrotate config after rollback. | |

**User's choice:** Deploy and rollback both handle the logrotate config

---

## Claude's Discretion

- Whether to pre-create `/var/log/vpn-gateway.log` in deploy.sh or rely on first-write creation
- Exact placement of logrotate deploy stage number in deploy.sh
- Whether `LOG_FILE` constant lives in `/etc/vpn-gateway.env` or is hardcoded in each log() function

## Deferred Ideas

None — discussion stayed within phase scope.
