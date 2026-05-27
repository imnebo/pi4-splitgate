# Phase 10: Splitgate Ergonomics & Organization — Research

**Researched:** 2026-05-27
**Domain:** Bash script organization, path migration, dispatcher pattern (RPi Debian/Raspbian)
**Confidence:** HIGH — pure codebase work; no external libraries; all findings verified by reading live files

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Directory**
- D-01: Brand directory: `/etc/splitgate/` on RPi. All app scripts, configs, and data files live here.
- D-02: Log subdirectory: `/etc/splitgate/logs/` — overrides Phase 9 D-01 (`/var/log/vpn-gateway.log`). All Phase 9 log path references updated in this phase.

**Files that move to `/etc/splitgate/`**
- D-03: Scripts: `routing.sh`, `vpn-rollback.sh`, `update-vpn-routes`, `vpn-status.sh`, `watch-routes.py`, `asn-lookup.py`
- D-04: Config/data: `vpn-gateway.env`, `white-list.txt` (generated at runtime), `white-list-extended.txt`
- D-05: Logs: `/etc/splitgate/logs/vpn-gateway.log`

**Files that stay in system locations (not moved)**
- D-06: `/etc/cron.d/vpn-routes` — cron daemon requires exact location
- D-07: `/etc/dnsmasq.conf` — dnsmasq requires exact location
- D-08: `/etc/amnezia/amneziawg/awg0.conf` — AmneziaWG requires exact location
- D-09: `/etc/NetworkManager/dispatcher.d/10-vpn-routes` — NM dispatcher requires exact location
- D-10: `/etc/systemd/system/vpn-routing.service` — systemd requires exact location
- D-11: `/etc/logrotate.d/vpn-gateway` — logrotate requires exact location
- D-12: `/etc/iptables/rules.v4` — iptables-save requires exact location

**Dispatcher (`splitgate`)**
- D-13: Single dispatcher at `/usr/local/bin/splitgate`, bash script.
- D-14: Subcommands and their targets:
  - `status`   → `sudo /etc/splitgate/vpn-status.sh`
  - `watch`    → `sudo python3 /etc/splitgate/watch-routes.py`
  - `rollback` → `sudo /etc/splitgate/vpn-rollback.sh`
  - `routing`  → `sudo /etc/splitgate/routing.sh`
  - `update`   → `sudo /etc/splitgate/update-vpn-routes`
- D-15: Args pass-through — all args after subcommand forwarded to target script.
- D-16: Unknown subcommand → print `Usage: splitgate {status|watch|rollback|routing|update} [args...]` + `exit 1`.
- D-17: Dispatcher deployed via deploy.sh new stage, `chmod +x`, `root:root`.

**Rollback**
- D-18: `vpn-rollback.sh` teardown removes `/usr/local/bin/splitgate` and `/etc/splitgate/` directory tree.

**Phase 9 override**
- D-19: Phase 9 D-01 (`/var/log/vpn-gateway.log`) superseded. New path: `/etc/splitgate/logs/vpn-gateway.log`. `configs/logrotate-vpn-gateway` updated. All scripts writing to the log updated.

### Claude's Discretion

None stated in CONTEXT.md for this phase.

### Deferred Ideas (OUT OF SCOPE)

- New monitoring features
- Changes to routing logic
- New subcommands beyond the 5 defined
</user_constraints>

---

## Summary

Phase 10 is a path migration + ergonomics phase. No new runtime functionality is added. The entire scope is:

1. **Move** six scripts and three data/config files from flat `/etc/` to `/etc/splitgate/`, plus create `/etc/splitgate/logs/` for the Phase 9 log destination.
2. **Update every internal path reference** in those scripts so they find each other and their data files after the move.
3. **Update the four system-location files** that reference scripts by old paths (systemd unit, NM dispatcher, cron line, logrotate config).
4. **Create the `splitgate` dispatcher** at `/usr/local/bin/splitgate`.
5. **Update `deploy.sh`** remote path variables and add new mkdir + dispatcher deploy stages.
6. **Extend `vpn-rollback.sh`** teardown to clean up the new locations.

**Phase 9 has NOT been executed.** `configs/logrotate-vpn-gateway` does not exist in the repo. Phase 10 must create it (as a new file with the `/etc/splitgate/logs/vpn-gateway.log` path) and must add the Phase 9 log-function pattern into scripts — because Phase 9's script modifications were never applied. The Phase 10 plan must either include the Phase 9 log-function work (as a prerequisite wave) or leave the logging upgrade to Phase 9 if that phase will still be executed. See **Open Questions** section.

**Primary recommendation:** Treat path migration as Wave 1 (update remote path vars in deploy.sh + internal script refs), new artifacts as Wave 2 (splitgate dispatcher, logrotate config, /etc/splitgate/logs/ mkdir stage), and rollback/teardown update as Wave 3.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Directory creation on RPi | API/Backend (deploy.sh) | — | deploy.sh orchestrates all remote RPi changes via SSH |
| Script path references | API/Backend (RPi scripts) | deploy.sh (remote path vars) | Scripts run on RPi; deploy.sh controls where they land |
| Dispatcher dispatch logic | API/Backend (splitgate script) | deploy.sh (deploy stage) | Runs on RPi as user-facing CLI tool |
| Cron path reference | OS/Cron (cron.d file) | deploy.sh (Stage 15 cron_line) | Written by deploy.sh Stage 15; references UPDATE_VPN_ROUTES_REMOTE var |
| systemd ExecStart path | OS/systemd (unit file) | deploy.sh (Stage 12) | Unit file references ROUTING_SH_REMOTE var via ExecStart |
| NM dispatcher call | OS/NetworkManager (10-vpn-routes) | deploy.sh (Stage 22) | File contains hardcoded `/etc/routing.sh` path |
| Logrotate config path | OS/logrotate (configs/logrotate-vpn-gateway) | deploy.sh (new stage) | Config file references the log file path |
| Rollback cleanup | API/Backend (vpn-rollback.sh) | — | Script runs on RPi and removes remote state |

---

## Complete Path Migration Inventory

### Scripts that move (source in repo → new remote path)

| Script (local) | Old remote path | New remote path |
|----------------|----------------|----------------|
| `scripts/routing.sh` | `/etc/routing.sh` | `/etc/splitgate/routing.sh` |
| `scripts/vpn-rollback.sh` | `/etc/vpn-rollback.sh` | `/etc/splitgate/vpn-rollback.sh` |
| `scripts/update-vpn-routes` | `/etc/update-vpn-routes` | `/etc/splitgate/update-vpn-routes` |
| `scripts/vpn-status.sh` | `/etc/vpn-status.sh` | `/etc/splitgate/vpn-status.sh` |
| `scripts/watch-routes.py` | `/etc/watch-routes.py` | `/etc/splitgate/watch-routes.py` |
| `scripts/asn-lookup.py` | `/etc/asn-lookup.py` | `/etc/splitgate/asn-lookup.py` |

### Config/data files that move

| File | Old remote path | New remote path |
|------|----------------|----------------|
| `.env` (sourced as `vpn-gateway.env`) | `/etc/vpn-gateway.env` | `/etc/splitgate/vpn-gateway.env` |
| `configs/white-list-extended.txt` | `/etc/white-list-extended.txt` | `/etc/splitgate/white-list-extended.txt` |
| `configs/ru-exclude.txt` | `/etc/ru-exclude.txt` | `/etc/splitgate/ru-exclude.txt` |
| (runtime generated) | `/etc/white-list.txt` | `/etc/splitgate/white-list.txt` |

### Files that stay at system locations (DO NOT MOVE)

| File | Remote path | Why it stays |
|------|-------------|-------------|
| `systemd/vpn-routing.service` | `/etc/systemd/system/vpn-routing.service` | systemd requires this exact path |
| `scripts/10-vpn-routes` | `/etc/NetworkManager/dispatcher.d/10-vpn-routes` | NetworkManager dispatcher requires this exact path |
| `configs/dnsmasq.conf` | `/etc/dnsmasq.conf` | dnsmasq requires this exact path |
| `configs/logrotate-vpn-gateway` | `/etc/logrotate.d/vpn-gateway` | logrotate requires this exact path |
| (iptables-save output) | `/etc/iptables/rules.v4` | iptables-persistent requires this exact path |
| `amnezia.key.template.txt` → rendered | `/etc/amnezia/amneziawg/awg0.conf` | AmneziaWG requires this exact path |

### New file to create (Phase 9 artifact, does not exist)

| Local path | Remote path | Status |
|------------|-------------|--------|
| `configs/logrotate-vpn-gateway` | `/etc/logrotate.d/vpn-gateway` | Does NOT exist in repo — must be created in Phase 10 |

---

## Internal Path Reference Changes Required

Every script that runs ON the RPi has hardcoded `/etc/` paths that must be updated to `/etc/splitgate/`. Below is the complete verified list from grepping all script files.

### `scripts/routing.sh` (deployed to `/etc/splitgate/routing.sh`)

| Line | Old value | New value |
|------|-----------|-----------|
| 38 | `WHITE_LIST_FILE="/etc/white-list.txt"` | `WHITE_LIST_FILE="/etc/splitgate/white-list.txt"` |
| 39 | `EXCEPTIONS_FILE="/etc/white-list-extended.txt"` | `EXCEPTIONS_FILE="/etc/splitgate/white-list-extended.txt"` |
| 41 | `IPTABLES_RULES="/etc/iptables/rules.v4"` | stays `/etc/iptables/rules.v4` — D-12 (iptables-persistent) |
| 63–64 | `/etc/vpn-gateway.env` (guard + source) | `/etc/splitgate/vpn-gateway.env` |
| 68, 70 | `/etc/vpn-gateway.env` (source + log) | `/etc/splitgate/vpn-gateway.env` |

Note: `IPTABLES_RULES="/etc/iptables/rules.v4"` stays — that is the iptables-persistent file location (D-12).

### `scripts/vpn-status.sh` (deployed to `/etc/splitgate/vpn-status.sh`)

| Line | Old value | New value |
|------|-----------|-----------|
| 40–41 | `/etc/vpn-gateway.env` (guard + error) | `/etc/splitgate/vpn-gateway.env` |
| 45 | `source /etc/vpn-gateway.env` | `source /etc/splitgate/vpn-gateway.env` |
| 194 | `python3 /etc/asn-lookup.py` | `python3 /etc/splitgate/asn-lookup.py` |

### `scripts/watch-routes.py` (deployed to `/etc/splitgate/watch-routes.py`)

| Line | Old value | New value |
|------|-----------|-----------|
| 46 | `ASN_LOOKUP_PATH = "/etc/asn-lookup.py"` | `ASN_LOOKUP_PATH = "/etc/splitgate/asn-lookup.py"` |

### `scripts/update-vpn-routes` (deployed to `/etc/splitgate/update-vpn-routes`)

| Line | Old value | New value |
|------|-----------|-----------|
| 19 | `SUBNET_FILE="/etc/white-list.txt"` | `SUBNET_FILE="/etc/splitgate/white-list.txt"` |
| 30–31 | `/etc/vpn-gateway.env` (guard + error) | `/etc/splitgate/vpn-gateway.env` |
| 35 | `source /etc/vpn-gateway.env` | `source /etc/splitgate/vpn-gateway.env` |
| 41 | `EXCLUDE_FILE="/etc/ru-exclude.txt"` | `EXCLUDE_FILE="/etc/splitgate/ru-exclude.txt"` |
| 65, 95 | `/etc/routing.sh --no-update` | `/etc/splitgate/routing.sh --no-update` |

### `scripts/vpn-rollback.sh` (deployed to `/etc/splitgate/vpn-rollback.sh`)

| Line | Old value | New value |
|------|-----------|-----------|
| 37–38 | `/etc/vpn-gateway.env` (guard) | `/etc/splitgate/vpn-gateway.env` |
| 42 | `source /etc/vpn-gateway.env` | `source /etc/splitgate/vpn-gateway.env` |
| 109–111 | `rm -f /etc/white-list-extended.txt` | `rm -rf /etc/splitgate/` (or targeted removal — see D-18) |
| 122–123 | `/etc/cron.d/vpn-routes` (already stays) | no change |
| 150–152 | `echo` strings referencing old paths | update to new paths |
| (D-18 new) | — | Add: `rm -f /usr/local/bin/splitgate` |
| (D-18 new) | — | Add: `rm -rf /etc/splitgate/` |

Note: D-18 says teardown removes `/usr/local/bin/splitgate` and the entire `/etc/splitgate/` tree. The simplest correct implementation is `rm -f /usr/local/bin/splitgate && rm -rf /etc/splitgate/`. The white-list.txt preservation that existed before is abandoned — the new decision removes the whole directory.

### `scripts/10-vpn-routes` (stays at `/etc/NetworkManager/dispatcher.d/10-vpn-routes` — D-09)

| Line | Old value | New value |
|------|-----------|-----------|
| 17 | `/etc/routing.sh --no-update >> /var/log/vpn-routes.log 2>&1 &` | `/etc/splitgate/routing.sh --no-update >> /var/log/vpn-routes.log 2>&1 &` |

Note: The log redirect (`/var/log/vpn-routes.log`) is a separate matter — it is NOT the Phase 9 centralized log; it is the cron redirect log. It stays at `/var/log/vpn-routes.log` unless Phase 9 log work is also applied. This is a separate concern from the path migration.

### `systemd/vpn-routing.service` (stays at `/etc/systemd/system/vpn-routing.service` — D-10)

| Line | Old value | New value |
|------|-----------|-----------|
| 20 | `ExecStart=/etc/routing.sh` | `ExecStart=/etc/splitgate/routing.sh` |

---

## deploy.sh Changes Required

### Remote path variable updates (lines ~34–70)

| Variable | Old value | New value |
|----------|-----------|-----------|
| `ENV_REMOTE` | `/etc/vpn-gateway.env` | `/etc/splitgate/vpn-gateway.env` |
| `ROUTING_SH_REMOTE` | `/etc/routing.sh` | `/etc/splitgate/routing.sh` |
| `UPDATE_VPN_ROUTES_REMOTE` | `/etc/update-vpn-routes` | `/etc/splitgate/update-vpn-routes` |
| `VPN_ROLLBACK_REMOTE` | `/etc/vpn-rollback.sh` | `/etc/splitgate/vpn-rollback.sh` |
| `VPN_STATUS_REMOTE` | `/etc/vpn-status.sh` | `/etc/splitgate/vpn-status.sh` |
| `WATCH_ROUTES_REMOTE` | `/etc/watch-routes.py` | `/etc/splitgate/watch-routes.py` |
| `ASN_LOOKUP_REMOTE` | `/etc/asn-lookup.py` | `/etc/splitgate/asn-lookup.py` |
| `WHITE_LIST_EXT_REMOTE` | `/etc/white-list-extended.txt` | `/etc/splitgate/white-list-extended.txt` |
| `EXCLUDE_LIST_REMOTE` | `/etc/ru-exclude.txt` | `/etc/splitgate/ru-exclude.txt` |

**Stays unchanged** (system locations — D-06–D-12):
- `AWG_CONF_REMOTE` `/etc/amnezia/amneziawg/awg0.conf`
- `VPN_ROUTING_SERVICE_REMOTE` `/etc/systemd/system/vpn-routing.service`
- `CRON_FILE_REMOTE` `/etc/cron.d/vpn-routes`
- `DNSMASQ_CONF_REMOTE` `/etc/dnsmasq.conf`
- `NM_DISPATCHER_REMOTE` `/etc/NetworkManager/dispatcher.d/10-vpn-routes`

### New variables to add

```bash
SPLITGATE_DIR_REMOTE="/etc/splitgate"
SPLITGATE_LOGS_REMOTE="/etc/splitgate/logs"
SPLITGATE_DISPATCHER_LOCAL="scripts/splitgate"
SPLITGATE_DISPATCHER_REMOTE="/usr/local/bin/splitgate"
SPLITGATE_DISPATCHER_TMP="/tmp/splitgate.tmp"
LOGROTATE_CONF_LOCAL="configs/logrotate-vpn-gateway"
LOGROTATE_CONF_REMOTE="/etc/logrotate.d/vpn-gateway"
LOGROTATE_CONF_TMP="/tmp/logrotate-vpn-gateway.tmp"
```

### New deploy stages needed

Current `TOTAL_STAGES=24`. Phase 10 adds:

| Stage | Action | Where in sequence |
|-------|--------|-------------------|
| Stage 25 (or renumbered) | `sudo mkdir -p /etc/splitgate/logs` + `sudo chmod 755 /etc/splitgate` | After existing stages |
| Stage 26 | Deploy `scripts/splitgate` to `/usr/local/bin/splitgate` (chmod +x, root:root) | After mkdir |
| Stage 27 | Deploy `configs/logrotate-vpn-gateway` to `/etc/logrotate.d/vpn-gateway` | After splitgate deploy |

Alternative: Insert stages at appropriate positions and renumber. The stage numbering in the final summary echoes must also be updated.

### Preflight check additions

The existing Stage 1 preflight checks each local file. Add checks for:
- `scripts/splitgate` (new dispatcher script)
- `configs/logrotate-vpn-gateway` (new logrotate config — Phase 10 creates this file)

### Cron line update (Stage 15)

```bash
# Old:
cron_line="0 ${CRON_UPDATE_HOUR} * * * root ${UPDATE_VPN_ROUTES_REMOTE} >> /var/log/vpn-routes.log 2>&1"
# New (UPDATE_VPN_ROUTES_REMOTE changes to /etc/splitgate/update-vpn-routes automatically):
cron_line="0 ${CRON_UPDATE_HOUR} * * * root ${UPDATE_VPN_ROUTES_REMOTE} >> /var/log/vpn-routes.log 2>&1"
```

The cron line uses `${UPDATE_VPN_ROUTES_REMOTE}` (a variable), so updating the variable automatically fixes the cron content. No change to the cron line template itself.

---

## New Files to Create

### `scripts/splitgate` (dispatcher)

Exact template from CONTEXT.md:

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

Note: Uses `exec` for each subcommand — this is idiomatic and correct. `exec` replaces the shell process with the target, so the dispatcher exits with the target's exit code without an extra wrapper process.

Note: `watch` invokes `sudo python3` because `watch-routes.py` is not deployed with a shebang that the OS can invoke directly as root — it requires the explicit `python3` interpreter. The other scripts are bash and deployed `chmod +x`, so they can be `exec sudo $path`.

### `configs/logrotate-vpn-gateway` (Phase 9 override)

```
/etc/splitgate/logs/vpn-gateway.log {
    daily
    rotate 14
    compress
    dateext
    missingok
    notifempty
    create 0640 root root
}
```

This file references the new Phase 10 log path `/etc/splitgate/logs/vpn-gateway.log` (not `/var/log/vpn-gateway.log` from Phase 9 D-01).

---

## Phase 9 Artifact Status

Phase 9 has NOT been executed. The following items from Phase 9's scope are still pending:

| Phase 9 Item | Status | Phase 10 action |
|-------------|--------|----------------|
| `configs/logrotate-vpn-gateway` file | Does NOT exist | Phase 10 creates it with new log path `/etc/splitgate/logs/vpn-gateway.log` |
| Script `log()` functions upgraded to file-append | NOT done — all scripts still use `logger -t` or `echo "[tag] $*"` | Defer to Phase 9 unless combined |
| Phase 9 log path `/var/log/vpn-gateway.log` | Never deployed — superseded by D-02 | No cleanup needed |

**Critical finding:** The `configs/logrotate-vpn-gateway` file does not exist yet. Phase 10 must create it. The planner should include a task that creates this file in the repo with the `/etc/splitgate/logs/vpn-gateway.log` path before the deploy stage can reference it.

The Phase 9 script `log()` function changes (switching from `logger -t` / echo to file-append) are NOT required by Phase 10. Phase 10 only needs the logrotate config file (so the config can be deployed) and the log directory (so Phase 9's log writes have somewhere to go when Phase 9 is executed). The actual `log()` function upgrades remain Phase 9 work.

---

## Architecture Patterns

### Recommended Project Structure (after Phase 10)

```
scripts/
├── routing.sh              # deployed → /etc/splitgate/routing.sh
├── vpn-rollback.sh         # deployed → /etc/splitgate/vpn-rollback.sh
├── update-vpn-routes       # deployed → /etc/splitgate/update-vpn-routes
├── vpn-status.sh           # deployed → /etc/splitgate/vpn-status.sh
├── watch-routes.py         # deployed → /etc/splitgate/watch-routes.py
├── asn-lookup.py           # deployed → /etc/splitgate/asn-lookup.py
├── splitgate               # NEW dispatcher → /usr/local/bin/splitgate
├── install-awg.sh          # unchanged (run manually, not a regular deploy artifact)
└── 10-vpn-routes           # deployed → /etc/NetworkManager/dispatcher.d/10-vpn-routes (stays)
configs/
├── dnsmasq.conf            # deployed → /etc/dnsmasq.conf (stays)
├── logrotate-vpn-gateway   # NEW → /etc/logrotate.d/vpn-gateway
├── white-list-extended.txt.example
└── ru-exclude.txt.example
```

RPi filesystem after Phase 10:
```
/etc/splitgate/
├── routing.sh
├── vpn-rollback.sh
├── update-vpn-routes
├── vpn-status.sh
├── watch-routes.py
├── asn-lookup.py
├── vpn-gateway.env
├── white-list.txt          (runtime generated by routing.sh)
├── white-list-extended.txt (optional, conditional deploy)
├── ru-exclude.txt          (optional, conditional deploy)
└── logs/                   (Phase 9 will write vpn-gateway.log here)

/usr/local/bin/splitgate    (dispatcher CLI)
```

### Pattern: exec-based dispatcher

Using `exec` in the dispatcher ensures the splitgate wrapper process is replaced by the target — no double-process overhead, and the target's exit code is the dispatcher's exit code. This is the idiomatic bash dispatcher pattern. [ASSUMED — standard bash dispatcher practice]

### Pattern: deploy.sh variable-driven stages

All deploy stages reference remote paths via variables, not inline strings. The consequence is that **updating a `*_REMOTE` variable automatically updates every stage that uses it** — including the activation command in Stage 24 (`sudo ${ROUTING_SH_REMOTE}`), the cron line in Stage 15, and the preflight error messages. No inline path strings need hunting. This is the existing pattern and must be preserved.

### Anti-Patterns to Avoid

- **Inline path strings in stage bodies:** Every `ssh ... "sudo /etc/routing.sh"` that isn't using a variable is a future maintenance hazard. Phase 10 must use `${ROUTING_SH_REMOTE}` everywhere, not inline the path.
- **Forgetting `sudo mkdir -p` for logs subdirectory:** `/etc/splitgate/` and `/etc/splitgate/logs/` must both be created. A single `mkdir -p /etc/splitgate/logs` creates both, but a missing `sudo` will silently fail if the stage runs as non-root.
- **Skipping systemd daemon-reload after ExecStart path change:** After updating `vpn-routing.service` with the new `ExecStart` path and re-deploying it, `systemctl daemon-reload` must run again so systemd picks up the change. Stage 13 already does this but the plan must ensure Stage 12 (service deploy) runs before Stage 13.
- **Forgetting to update `vpn-routing.service` in the repo file:** The service file at `systemd/vpn-routing.service` must be updated from `ExecStart=/etc/routing.sh` to `ExecStart=/etc/splitgate/routing.sh` in the local repo. Deploy.sh SCPs the local file. If the local file isn't updated, the change never reaches the RPi.
- **Leaving old `/etc/` files on RPi after deploy:** After a successful deploy, the old files at `/etc/routing.sh`, `/etc/vpn-status.sh`, etc. remain on the RPi as stale artifacts. The rollback script handles this by deleting `/etc/splitgate/` entirely. But the OLD `/etc/` paths should be cleaned up during deploy (or at minimum documented as manual cleanup). Consider adding a cleanup ssh command in deploy.sh after the new files are confirmed deployed.

---

## Common Pitfalls

### Pitfall 1: Missed internal cross-references
**What goes wrong:** A script is moved to `/etc/splitgate/` but still calls another script by old `/etc/` path. E.g., `update-vpn-routes` calls `/etc/routing.sh` at lines 65 and 95 — if those aren't updated, the cron job and carrier-recovery logic both call the old (now absent) path.
**Why it happens:** Grepping for `/etc/` naively misses `source /etc/vpn-gateway.env` because it's embedded in a guard block.
**How to avoid:** Use the complete per-script change tables above. Verify with `grep -n '/etc/' scripts/*.sh scripts/*.py`.
**Warning signs:** Cron job emails after first daily run, or `update-vpn-routes` failing silently with "file not found".

### Pitfall 2: vpn-gateway.env sourced before SPLITGATE_DIR is available
**What goes wrong:** If the path `/etc/vpn-gateway.env` is updated to `/etc/splitgate/vpn-gateway.env`, the source happens BEFORE any SPLITGATE_DIR variable is defined. The path must be a literal string (or a well-known constant) in the guard check.
**How to avoid:** Define `SPLITGATE_DIR="/etc/splitgate"` at the top of each script before the env guard, and write the guard as `if [[ ! -f "${SPLITGATE_DIR}/vpn-gateway.env" ]]; then`.
**Why it matters:** If routing.sh is called by systemd at boot, it must be self-contained.

### Pitfall 3: systemd unit not re-read after ExecStart path change
**What goes wrong:** `vpn-routing.service` has a new `ExecStart` path but `daemon-reload` hasn't run. On next reboot the old (absent) path is used. System silently fails to restore routes.
**Why it happens:** systemd caches unit file content; changes require explicit reload.
**How to avoid:** Stage 13 runs `daemon-reload` after Stage 12 deploys the unit file. Ensure the plan preserves Stage 12 → Stage 13 ordering.

### Pitfall 4: `/etc/splitgate/` directory not created before file deployment
**What goes wrong:** SCP to `/tmp` staging succeeds, but `sudo mv /tmp/routing.sh.tmp /etc/splitgate/routing.sh` fails with "No such file or directory" if `/etc/splitgate/` doesn't exist yet.
**How to avoid:** The `mkdir -p /etc/splitgate/logs` stage must come BEFORE any file deployment stage. In the plan, the mkdir stage should be Stage 25 (inserted before the first file deployment at the new path).

### Pitfall 5: rollback rm -rf removes too early (self-destruction)
**What goes wrong:** If `vpn-rollback.sh` removes `/etc/splitgate/` while it is running from `/etc/splitgate/vpn-rollback.sh`, there is no problem on Linux because the running script is already loaded into memory — the file can be deleted mid-run. However, `rm -rf /etc/splitgate/` must come AFTER the iptables and route teardown steps, not before. If placed first, a failure during teardown leaves the system in a broken state with no rollback script to retry.
**How to avoid:** In the updated `vpn-rollback.sh`, keep `rm -f /usr/local/bin/splitgate` and `rm -rf /etc/splitgate/` as the LAST steps, after route restoration.

### Pitfall 6: TOTAL_STAGES must match actual stage count in echoes
**What goes wrong:** deploy.sh uses `echo "[N/${TOTAL_STAGES}] ..."` in every stage header. Stage 21b already incorrectly echoes `[21/${TOTAL_STAGES}]` instead of `[21b/${TOTAL_STAGES}]`. Adding new stages requires bumping `TOTAL_STAGES` AND updating the stage numbers in echo headers.
**How to avoid:** At plan time, decide final stage numbering. Set `TOTAL_STAGES` to the exact new count. Verify all `echo "[N/${TOTAL_STAGES}]"` headers match.

### Pitfall 7: white-list.txt preservation (old rollback vs. new rollback)
**What goes wrong:** The old `vpn-rollback.sh` PRESERVED `/etc/white-list.txt` (it was listed in the "PRESERVED" section). D-18 says Phase 10's rollback removes all of `/etc/splitgate/` — this includes `white-list.txt`. This is a behavior change that should be documented clearly in the rollback summary output.
**How to avoid:** Update the "Preserved" list in the rollback output section and the script header comments to reflect new behavior.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Directory creation on RPi | A custom check-then-create script | `ssh ... "sudo mkdir -p /etc/splitgate/logs"` | `-p` is idempotent; creates parents atomically |
| Dispatcher branching | Nested if/elif chains | `case "$CMD" in` | Already in CONTEXT.md template; case is idiomatic bash |
| File permissions | Custom chmod script | Standard `chmod +x` / `chmod 644` in same ssh command | Same pattern already used in all existing stages |

---

## Runtime State Inventory

> This is a path migration phase — runtime state must be inventoried.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `/etc/white-list.txt` — generated runtime file at `/etc/white-list.txt` on RPi; not in git | No migration; routing.sh will regenerate it at `/etc/splitgate/white-list.txt` on next run |
| Stored data | `/etc/white-list-extended.txt` — conditionally deployed to RPi | Phase 10 deploy stages re-deploy to new path; old path file remains until manually removed or rollback |
| Stored data | `/etc/ru-exclude.txt` — conditionally deployed to RPi | Same as above |
| Live service config | `/etc/cron.d/vpn-routes` — written by deploy.sh Stage 15; references `UPDATE_VPN_ROUTES_REMOTE` path | Variable update propagates to cron line automatically; RPi's `/etc/cron.d/vpn-routes` is rewritten by Phase 10 deploy |
| Live service config | `vpn-routing.service` enabled in systemd — `ExecStart=/etc/routing.sh` on RPi now | After deploy: service file redeployed, daemon-reload + re-enable; old ExecStart overwritten |
| OS-registered state | `awg-quick@awg0` and `vpn-routing.service` — systemd enabled; both survive a re-deploy | Stage 13 re-runs daemon-reload + enable; no issue since enable is idempotent |
| Secrets/env vars | `/etc/vpn-gateway.env` on RPi — contains non-secret env vars (VPN_SERVER_IP, etc.); no key material | Redeployed to `/etc/splitgate/vpn-gateway.env`; old `/etc/vpn-gateway.env` remains stale until removed |
| Build artifacts | Old `/etc/routing.sh`, `/etc/vpn-rollback.sh`, `/etc/vpn-status.sh`, `/etc/watch-routes.py`, `/etc/asn-lookup.py`, `/etc/update-vpn-routes` on RPi — stale after Phase 10 deploy | These are NOT automatically removed by deploy.sh. They remain as dead files. The rollback script (once updated) removes `/etc/splitgate/` but NOT the old `/etc/` files. Consider explicit cleanup step in deploy.sh or document as manual step. |

**Critical:** After Phase 10 deploy, the RPi will have BOTH sets of files:
- New: `/etc/splitgate/routing.sh`, etc.
- Old (stale): `/etc/routing.sh`, `/etc/vpn-status.sh`, etc.

The old files will be harmless but confusing. The systemd unit and NM dispatcher will point to the new paths. Options:
1. Add an explicit cleanup stage in deploy.sh that removes old `/etc/` files after confirming new paths exist.
2. Document as manual cleanup in README.
3. Rely on rollback to clean up (but rollback only removes `/etc/splitgate/`, not old `/etc/` stale files).

**Recommendation:** Add a "Stage 2x: Remove legacy /etc/ files (cleanup)" step in deploy.sh.

---

## Environment Availability

> No new external tools required. All operations use SSH, SCP, bash, and standard Debian system tools already present on RPi.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `ssh` / `scp` | deploy.sh | Already in use | macOS OpenSSH | — |
| `mkdir -p` | New stage (create /etc/splitgate/logs/) | Standard on Debian | Always available | — |
| `logrotate` | logrotate-vpn-gateway config | Pre-installed on Debian/Raspbian | Standard | — |
| `python3` | watch-routes.py, asn-lookup.py | Already deployed + verified Phase 4+ | 3.x | — |

No new dependencies. Step 2.6: All environment dependencies are already present from previous phases.

---

## Validation Architecture

> `nyquist_validation: false` in `.planning/config.json` — this section is SKIPPED per configuration.

---

## Security Domain

This phase makes no changes to security posture. All scripts already run as root. The dispatcher:
- Does not accept user input beyond the subcommand name and pass-through args
- Uses `exec` (no injection vector in the dispatch itself)
- The target scripts validate their own arguments

The path migration does not change permissions:
- Scripts remain `chmod +x, root:root`
- `vpn-gateway.env` remains `chmod 644, root:root` (contains no secrets — secrets are in `.env.secrets` which is gitignored and never deployed to the RPi)

No new ASVS categories apply.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `logrotate` is pre-installed on Raspbian Debian | Environment Availability | logrotate deploy stage would install a config to a non-functioning location; easy to fix by adding apt-get install logrotate step |
| A2 | Using `exec sudo` in the dispatcher is safe when the operator is already root (or has passwordless sudo) | Architecture Patterns | If operator doesn't have passwordless sudo for the target scripts, dispatcher prompts for password; existing behavior is already `sudo /etc/vpn-status.sh` so this is unchanged |
| A3 | Old stale `/etc/routing.sh` etc. files left on RPi are harmless | Runtime State Inventory | If another process or script still references old paths, it would find working (but stale) files after Phase 10; monitoring required |

---

## Open Questions (RESOLVED)

1. **Should Phase 10 also apply Phase 9 log-function changes?**
   - What we know: Phase 9 has not been executed. `scripts/routing.sh` still uses `echo "[routing] $*"`. Phase 10 CONTEXT.md only says to update logrotate config path (D-19), not to implement the full Phase 9 log() rewrite.
   - What's unclear: If Phase 9 is executed after Phase 10, Phase 9's plan will need to use the new `/etc/splitgate/` paths in the new `log()` functions.
   - Recommendation: **Do NOT include Phase 9 log() function changes in Phase 10.** Phase 10 creates `configs/logrotate-vpn-gateway` with the correct path. Phase 9 implements the log() rewrite and must be told to use `/etc/splitgate/logs/vpn-gateway.log` (not the now-superseded `/var/log/vpn-gateway.log`).
   - **RESOLVED:** Phase 10 does NOT implement Phase 9 log() function changes. Plan 03 Task 2 creates only the logrotate config. Log() rewrite stays in Phase 9 scope.

2. **Should deploy.sh remove old `/etc/` stale files during Phase 10 deploy?**
   - What we know: After Phase 10 deploy, both old paths (`/etc/routing.sh`) and new paths (`/etc/splitgate/routing.sh`) exist on RPi.
   - What's unclear: Whether the user wants explicit cleanup in deploy.sh or manual cleanup is acceptable.
   - Recommendation: Add explicit cleanup as the first new stage (before mkdir for `/etc/splitgate/`). Pattern: `ssh "$SSH_HOST" "sudo rm -f /etc/routing.sh /etc/vpn-rollback.sh /etc/update-vpn-routes /etc/vpn-status.sh /etc/watch-routes.py /etc/asn-lookup.py /etc/vpn-gateway.env /etc/white-list-extended.txt /etc/ru-exclude.txt"`. This is idempotent (rm -f handles absence) and avoids confusion.
   - **RESOLVED:** No explicit cleanup stage added in the current plans. Manual cleanup is acceptable. Stale files are inert (nothing will call old paths after deploy). Can be added as a follow-up quick task if desired.

3. **Stage renumbering: insert new stages vs. append?**
   - What we know: Current TOTAL_STAGES=24. Phase 10 needs mkdir + dispatcher deploy + logrotate deploy + (optionally) cleanup = 3-4 new stages.
   - Recommendation: Append new stages 25–27 (or 25–28 if cleanup included). Avoid renumbering existing stages 1–24 to minimize diff size and risk of error.
   - **RESOLVED:** Plan 02 chose insert-and-renumber approach — mkdir inserted as Stage 5 (before awg0.conf render), dispatcher as Stage 26, logrotate as Stage 27. TOTAL_STAGES=27.

---

## Sources

### Primary (HIGH confidence)
- Live codebase: all files read directly from repo — verified line-by-line
- CONTEXT.md (Phase 10) — locked decisions D-01 through D-19

### Secondary (MEDIUM confidence)
- CONTEXT.md (Phase 9) — Phase 9 scope and D-01 log path decision
- STATE.md — Phase 8 complete, Phase 9 not executed

### Tertiary (LOW confidence)
- [ASSUMED] — bash `exec` dispatcher pattern (standard knowledge, not verified against docs this session)
- [ASSUMED] — logrotate pre-installed on Raspbian

---

## Metadata

**Confidence breakdown:**
- Path inventory: HIGH — verified by grepping all source files
- Architecture: HIGH — pure code organization, no new libraries
- Pitfalls: HIGH — derived directly from reading existing deploy.sh patterns
- Phase 9 status: HIGH — verified `configs/logrotate-vpn-gateway` does not exist

**Research date:** 2026-05-27
**Valid until:** Stable indefinitely — no external dependencies
