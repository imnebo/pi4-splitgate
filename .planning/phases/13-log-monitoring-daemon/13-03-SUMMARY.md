---
plan: "13-03"
phase: "13-log-monitoring-daemon"
status: complete
completed: "2026-05-29"
self_check: PASSED
---

# Summary: Plan 13-03 — watch-routes.py Daemon + Systemd Service

## What Was Built

Extended `watch-routes.py` with daemon mode, connection status checking, and daily log rotation. Created `splitgate-watch.service` for systemd. Updated `deploy.sh` and `vpn-rollback.sh`.

## Key Files

### Created
- `src/systemd/splitgate-watch.service` — systemd unit: `ExecStart=watch-routes.py --daemon`, Restart=on-failure, StandardError→watch-error.log

### Modified
- `src/scripts/watch-routes.py` — daemon mode, conntrack status, dedup, dated logs
- `src/deploy.sh` — WATCH_SERVICE_* vars, TOTAL_STAGES=28, Stage 28 (service deploy + enable)
- `src/scripts/vpn-rollback.sh` — Step 1a: stop/disable splitgate-watch.service

## Implementation Details

**watch-routes.py additions:**
- `STATUS_DELAY = 3` — seconds to wait before conntrack check (fits in BUFFER_TIMEOUT=6s window)
- `DEDUP_TTL = 30` — seconds before same (src, dst, dport) logged again
- `LOG_DIR = "/etc/splitgate/logs"` — base for dated log files
- `_check_conntrack(src, dst, dpt)` — reads `/proc/net/nf_conntrack`, returns `✓`/`✗`/`""` (empty if file absent)
- `_open_log_file()` — opens `watch-YYYY-MM-DD.log` in append mode; creates LOG_DIR if absent
- `_write_daemon_line(line)` — acquires `_daemon_write_lock`, checks date rotation, writes + flushes
- `--daemon` flag — write to dated log instead of stdout
- Dedup: skip (src, dst, dport) tuples seen within DEDUP_TTL seconds
- Status injected after [VPN]/[ISP] tag: `[ISP] ✓` or `[ISP] ✗`
- `--no-asn` mode unchanged (no dedup, no status, no delay)

**Output format:**
```
2026-05-29T10:14:00 [ISP] ✓ 192.168.1.237 → yandex.ru TCP:443 | TELETECH, RU
2026-05-29T10:14:05 [ISP] ✗ 192.168.1.237 → github.com TCP:443 | FASTLY, US
```

## Commits
- `a3879b4`: feat(13-03): add daemon mode, conntrack status, systemd service, and deploy stage

## Self-Check: PASSED

- python3 syntax check: OK
- STATUS_DELAY, DEDUP_TTL, LOG_DIR, _check_conntrack, _open_log_file, _write_daemon_line present
- splitgate-watch.service exists with correct ExecStart
- deploy.sh: TOTAL_STAGES=28, Stage 28 present, WATCH_SERVICE_* vars
- vpn-rollback.sh: Step 1a stops splitgate-watch.service
