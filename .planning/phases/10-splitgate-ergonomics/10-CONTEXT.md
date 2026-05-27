# Phase 10: Splitgate Ergonomics & Organization — Context

**Gathered:** 2026-05-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Ergonomics and organization phase. Two deliverables:
1. All RPi app files consolidated under `/etc/splitgate/` (branded namespace, replaces flat `/etc/` scatter)
2. `/usr/local/bin/splitgate` dispatcher script — ergonomic CLI for day-to-day ops

**In scope:**
- Create `/etc/splitgate/` directory on RPi, move all app files there
- New `scripts/splitgate` dispatcher deployed to `/usr/local/bin/splitgate`
- Update all internal path references in every script
- Update `deploy.sh` remote path variables + new deploy stages
- Move Phase 9 log path from `/var/log/vpn-gateway.log` → `/etc/splitgate/logs/vpn-gateway.log`
- Update `configs/logrotate-vpn-gateway` to new log path
- Update `vpn-rollback.sh` teardown to remove `/etc/splitgate/` and `/usr/local/bin/splitgate`

**Out of scope:**
- New monitoring features
- Changes to routing logic
- New subcommands beyond the 5 defined
</domain>

<decisions>
## Implementation Decisions

### Directory
- **D-01:** Brand directory: `/etc/splitgate/` on RPi. All app scripts, configs, and data files live here.
- **D-02:** Log subdirectory: `/etc/splitgate/logs/` — overrides Phase 9 D-01 (`/var/log/vpn-gateway.log`). All Phase 9 log path references updated in this phase.

### Files that move to `/etc/splitgate/`
- **D-03:** Scripts: `routing.sh`, `vpn-rollback.sh`, `update-vpn-routes`, `vpn-status.sh`, `watch-routes.py`, `asn-lookup.py`
- **D-04:** Config/data: `vpn-gateway.env`, `white-list.txt` (generated at runtime), `white-list-extended.txt`
- **D-05:** Logs: `/etc/splitgate/logs/vpn-gateway.log`

### Files that stay in system locations (not moved)
- **D-06:** `/etc/cron.d/vpn-routes` — cron daemon requires exact location
- **D-07:** `/etc/dnsmasq.conf` — dnsmasq requires exact location
- **D-08:** `/etc/amnezia/amneziawg/awg0.conf` — AmneziaWG requires exact location
- **D-09:** `/etc/NetworkManager/dispatcher.d/10-vpn-routes` — NM dispatcher requires exact location
- **D-10:** `/etc/systemd/system/vpn-routing.service` — systemd requires exact location
- **D-11:** `/etc/logrotate.d/vpn-gateway` — logrotate requires exact location
- **D-12:** `/etc/iptables/rules.v4` — iptables-save requires exact location

### Dispatcher (`splitgate`)
- **D-13:** Single dispatcher at `/usr/local/bin/splitgate`, bash script.
- **D-14:** Subcommands and their targets:
  - `status`   → `sudo /etc/splitgate/vpn-status.sh`
  - `watch`    → `sudo python3 /etc/splitgate/watch-routes.py`
  - `rollback` → `sudo /etc/splitgate/vpn-rollback.sh`
  - `routing`  → `sudo /etc/splitgate/routing.sh`
  - `update`   → `sudo /etc/splitgate/update-vpn-routes`
- **D-15:** Args pass-through — all args after subcommand forwarded to target script.
- **D-16:** Unknown subcommand → print `Usage: splitgate {status|watch|rollback|routing|update} [args...]` + `exit 1`.
- **D-17:** Dispatcher deployed via deploy.sh new stage, `chmod +x`, `root:root`.

### Rollback
- **D-18:** `vpn-rollback.sh` teardown removes `/usr/local/bin/splitgate` and `/etc/splitgate/` directory tree.

### Phase 9 override
- **D-19:** Phase 9 D-01 (`/var/log/vpn-gateway.log`) superseded. New path: `/etc/splitgate/logs/vpn-gateway.log`. `configs/logrotate-vpn-gateway` updated. All scripts writing to the log updated.
</decisions>

<canonical_refs>
## Files Downstream Agents Must Read

- `.planning/phases/09-operational-logging/09-CONTEXT.md` — Phase 9 log decisions being overridden (D-01 specifically)
- `deploy.sh` — all `*_REMOTE` path variables, stage structure, total stage count
- `scripts/routing.sh` — path references to update
- `scripts/vpn-status.sh` — path references to update
- `scripts/vpn-rollback.sh` — path references + teardown logic to update
- `scripts/update-vpn-routes` — path references to update
- `scripts/10-vpn-routes` — references `/etc/routing.sh`, needs update
- `systemd/vpn-routing.service` — `ExecStart` path needs update
- `configs/logrotate-vpn-gateway` — log path needs update (if file exists post Phase 9)
</canonical_refs>

<code_context>
## Reusable Assets & Patterns

- `deploy.sh` stage pattern: numbered stages with `echo "Stage N: ..."` header, `ssh "$SSH_HOST" "..."` execution, idempotent commands. Follow exact same pattern for new `/etc/splitgate/` mkdir stage and dispatcher deploy stage.
- `scripts/vpn-rollback.sh` teardown: already removes remote files via `ssh "$SSH_HOST" "sudo rm -f ..."`. Extend with new paths.
- All `*_REMOTE` variables declared at top of `deploy.sh` (lines ~34-66). Update those vars; stage bodies reference them automatically.
  - Dispatcher template (from plan):
    ```bash
    #!/bin/bash
    SPLITGATE_DIR="/etc/splitgate"
    CMD="${1:-}"
    shift || true
    case "$CMD" in
      status)   exec sudo "$SPLITGATE_DIR/vpn-status.sh" "$@" ;;
      watch)    exec sudo python3 "$SPLITGATE_DIR/watch-routes.py" "$@" ;;
      rollback) exec sudo "$SPLITGATE_DIR/vpn-rollback.sh" "$@" ;;
      routing)  exec sudo "$SPLITGATE_DIR/routing.sh" "$@" ;;
      update)   exec sudo "$SPLITGATE_DIR/update-vpn-routes" "$@" ;;
      *)
        echo "Usage: splitgate {status|watch|rollback|routing|update} [args...]"
        exit 1
        ;;
    esac
    ```
</code_context>
