---
phase: 9
plan: "09-01"
status: complete
completed: "2026-05-28"
---

# Summary: Plan 09-01 — Operational Logging

## What Was Done

Unified centralized logging across all daemon/cron scripts to
`/etc/splitgate/logs/vpn-gateway.log`.

### routing.sh
- `log()`: upgraded from `echo "[routing] $*"` to timestamped file-append
- `err()`: now `tee -a LOG_FILE >&2` — both file and stderr
- `LOG_FILE` constant defined at top of logging block

### update-vpn-routes
- `log()`: replaced `logger -t "vpn-routes"` with timestamped file-append
- Header comment D-09 reference updated

### vpn-rollback.sh
- `log()`: replaced `logger -t "vpn-rollback"` with `tee -a` (stdout + file)
- Step 7b: added `rm -f /etc/logrotate.d/vpn-gateway` before `/etc/splitgate/` removal
- Summary echo updated to mention `/etc/logrotate.d/vpn-gateway` and `logs/`

### vpn-status.sh
- `log()`: replaced `logger -t "vpn-status"` with plain `echo "[vpn-status] $*"`
- No file write (D-08: interactive tool)

## Already Done by Phase 10 (not repeated)
- `src/configs/logrotate-vpn-gateway` — targets `/etc/splitgate/logs/vpn-gateway.log`
- `deploy.sh` Stage 27 — deploys logrotate config to RPi
- `deploy.sh` Stage 5 — `mkdir /etc/splitgate/logs` (creates log directory on RPi)

## Log Format

```
[2026-05-28 10:30:00] [routing] Stage 3: Flushing existing VPN routes
[2026-05-28 10:30:00] [routing] ERROR: awg0 interface not found
[2026-05-28 10:30:00] [vpn-routes] Checksum match — no rebuild needed
[2026-05-28 10:30:00] [vpn-rollback] Starting VPN gateway rollback...
```
