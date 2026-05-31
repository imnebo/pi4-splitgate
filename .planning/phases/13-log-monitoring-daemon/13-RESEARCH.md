# Phase 13: Log Monitoring, Routing Refinement & Daemon — Research

**Researched:** 2026-05-29
**Domain:** Python daemon design, systemd units, /proc/net/nf_conntrack, logrotate, Bash script refactoring
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01**: Add 11 specific /24 RU CIDRs to `isp-routes-custom.txt` (Selectel, MIRAN/Keenetic captive portals, RU-JSCIOT, SonicDuo, SOVAM, MegaFon, Raiffeisenbank, VimpelCom, cloud.example.com/RU)
- **D-02**: Add commented non-RU candidate block to `vpn-routes-custom.txt` (Cherry Servers LT, Google PoPs, Cloudflare, Amazon CloudFront hel51, Amazon EC2 ap-se-1, Akamai NL/US, Azure EU) — user uncomments when a service fails
- **D-03**: Connection status via `/proc/net/nf_conntrack` (plain file read, no subprocess, no pip deps); STATUS_DELAY=3s; DEDUP_TTL=30s; ✓=ESTABLISHED or TIME_WAIT found, ✗=otherwise; UDP ✗ is acceptable/expected
- **D-04**: Output format: `2026-05-29T10:14:00 [ISP] ✓ 10.0.0.237 → yandex.ru TCP:443 | TELETECH, RU` — one line after STATUS_DELAY; status always on
- **D-05**: `--daemon` flag — without it: stdout (existing interactive behavior, unchanged); with it: write to dated log file, no stdout
- **D-06**: Log path `/etc/splitgate/logs/watch-YYYY-MM-DD.log`; Python manages file rotation (open new file at midnight by checking date.today() on each write); LOG_DIR constant; cleanup via `find /etc/splitgate/logs -name "watch-*.log" -mtime +14 -delete` in logrotate postrotate
- **D-07**: Rename `vpn-gateway.log` → `install.log` in routing.sh L46, update-vpn-routes L25, vpn-rollback.sh L34, logrotate-vpn-gateway L2, deploy.sh summary L497
- **D-08**: Rename `ru-exclude.txt` → `ru-list-exclude.txt` everywhere: routing.sh L92, update-vpn-routes L41, deploy.sh L74-76 + L416-421 + L497, `ru-exclude.txt.example` file rename, `ru-exclude.txt` (gitignored) internal comments
- **D-09**: Install log improvements — update-vpn-routes: log download source domain, log actual excluded CIDRs (not just count), log route count; routing.sh: log excluded CIDRs explicitly, log ISP custom file entry count (Stage 5b), log VPN force file entry count (Stage 5c)
- **D-10**: New systemd service `splitgate-watch.service`; ExecStart uses `--daemon`; StandardOutput=null; StandardError=append to watch-error.log; Restart=on-failure; deploy.sh new stage: SCP + daemon-reload + enable --now

### Claude's Discretion

- Exact conntrack regex pattern (match both original and reply direction)
- Whether to keep `--no-asn` path unchanged (yes — no status check if ASN disabled)
- Logrotate file name — keep `logrotate-vpn-gateway`, update content only
- Order of plans in waves (keep parallel where possible)
- Whether to bump TOTAL_STAGES in deploy.sh vs add a separate counter

### Deferred Ideas (OUT OF SCOPE)

- Variant B (conntrack -E event mode)
- Auto-uncomment VPN candidates when ISP ✗ detected
- Aggregate status stats per connection pair
</user_constraints>

---

## Summary

Phase 13 has four categories of work: (1) config-only additions to routing text files, (2) systematic string renames across four scripts plus deploy.sh, (3) extending watch-routes.py with `--daemon` mode, and (4) a new systemd service unit plus a new deploy.sh stage.

The most technically involved part is the conntrack-based connection status. The `/proc/net/nf_conntrack` file is a plain text file, always present when iptables NAT/MASQUERADE rules are active (which they are on this gateway). Its format is well-defined: the original-direction tuple always has the LAN client as `src` and the remote server as `dst`, so a search for `src=<src_ip>.*dst=<dst_ip>.*dport=<dpt>` in the original tuple (followed by the reply tuple) reliably confirms whether a connection is established. The 3-second delay before reading conntrack fits cleanly within the existing 6-second BUFFER_TIMEOUT window.

The rename work (D-07, D-08) is mechanical but touches 6 files. The deploy.sh stage numbering requires care: TOTAL_STAGES is currently 27 and the last numbered stage is 26 (logrotate). Adding the splitgate-watch service deploy brings it to 28. The existing use of non-numeric sub-labels (21b, 21c) for the custom-file stages means the final stage number displayed to the user is currently 26 but TOTAL_STAGES=27 — a cosmetic discrepancy inherited from Phase 10. The new stage should be numbered 27 in the echo and TOTAL_STAGES bumped to 28.

**Primary recommendation:** Implement conntrack check as a single line open+grep using Python's `in` operator on the raw file contents with a compiled regex; keep the logic inside the existing ASN-buffer flush path so the STATUS_DELAY finishes before `_flush_entries` writes to the log file.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Connection status check | RPi OS (/proc) | Python watch-routes.py | /proc/net/nf_conntrack is kernel-provided; Python reads it as a plain file |
| Dated log file rotation | Python (watch-routes.py) | logrotate (cleanup only) | Script manages file handle; logrotate only cleans up old dated files |
| Daemon lifecycle | systemd (splitgate-watch.service) | — | systemd handles restart-on-failure, survive SSH disconnect, boot start |
| Route config additions | Config files (isp-routes-custom.txt, vpn-routes-custom.txt) | routing.sh (unchanged) | routing.sh reads these files unchanged; only file content changes |
| Log/file renames | Scripts (routing.sh, update-vpn-routes, vpn-rollback.sh) | logrotate config, deploy.sh | String renames in multiple files, no structural changes |
| Install log verbosity | Bash scripts (routing.sh, update-vpn-routes) | — | Bash already collects the data; just needs to log more of it |

---

## Standard Stack

No new external packages. This phase uses only:

| Component | Version | Purpose |
|-----------|---------|---------|
| Python 3 stdlib | 3.11+ (Bookworm) | watch-routes.py extension — `datetime.date`, `re`, existing threading |
| systemd | Bookworm systemd | splitgate-watch.service unit |
| logrotate | Bookworm logrotate | postrotate hook for watch-*.log cleanup |
| /proc/net/nf_conntrack | Linux kernel | Connection status without external tools |

**Installation:** No new packages to install. All capabilities are OS-provided on Debian Bookworm (RPi OS).

---

## Package Legitimacy Audit

Not applicable — this phase installs zero new packages.

---

## Architecture Patterns

### System Architecture Diagram

```
journalctl -f -k
       │
       ▼
  [LOG_RE regex match]
       │ match: ts, tag, src, dst, proto, dpt
       ▼
  [--daemon mode only]
       │
       ├─► ASN lookup thread (background, unchanged)
       │         └─► _pending buffer → _flush_entries (at BUFFER_TIMEOUT or lookup done)
       │
       └─► STATUS_DELAY sleep (3s)
                 │
                 ▼
           /proc/net/nf_conntrack  ← plain file read, no subprocess
                 │
                 ▼ ✓ / ✗
           _open_log_file()  ← checks date.today(); reopens if midnight passed
                 │
                 ▼
           /etc/splitgate/logs/watch-YYYY-MM-DD.log  ← append write
```

Non-daemon path (`--daemon` absent) is entirely unchanged — existing interactive stdout behavior.

### Recommended Project Structure

New files to add in this phase:

```
src/
├── systemd/
│   ├── vpn-routing.service           (existing — template)
│   └── splitgate-watch.service       (NEW — D-10)
└── configs/
    ├── isp-routes-custom.txt         (modify — D-01)
    ├── vpn-routes-custom.txt         (modify — D-02)
    ├── logrotate-vpn-gateway         (modify — D-06, D-07)
    ├── ru-list-exclude.txt.example   (rename from ru-exclude.txt.example — D-08)
    └── ru-exclude.txt.example        (delete after rename — D-08)
```

---

## Core Technical Findings

### Finding 1: /proc/net/nf_conntrack Format [VERIFIED: official documentation, Fedora Magazine]

Each line in `/proc/net/nf_conntrack` follows this exact layout:

```
tcp 6 43184 ESTABLISHED src=192.168.2.5 dst=10.25.39.80 sport=5646 dport=443 src=10.25.39.80 dst=192.168.2.5 sport=443 dport=5646 [ASSURED] mark=0 use=1
udp 17 3 src=10.0.0.237 dst=8.8.8.8 sport=54321 dport=53 src=8.8.8.8 dst=10.0.0.237 sport=53 dport=54321 [UNREPLIED] mark=0 use=1
```

Key layout facts: [CITED: https://fedoramagazine.org/network-address-translation-part-2-the-conntrack-tool/]

- Column 1: protocol name (`tcp`, `udp`, `icmp`)
- Column 2: protocol number (`6` for TCP, `17` for UDP)
- Column 3: timeout in seconds (remaining before entry expires)
- Column 4: TCP state only (`ESTABLISHED`, `TIME_WAIT`, `SYN_SENT`, `CLOSE_WAIT` — absent for UDP)
- Then: `src=` `dst=` `sport=` `dport=` — **original direction** (LAN client → remote)
- Then: `src=` `dst=` `sport=` `dport=` — **reply direction** (remote → LAN client, addresses swapped)
- Then: `[ASSURED]` or `[UNREPLIED]` flags, `mark=N`, `use=N`

**For the gateway's purpose:** The original direction has `src=<LAN_client_ip> dst=<remote_ip> sport=<random> dport=<server_port>`. This is exactly what iptables logs as SRC= and DST=.

**Conntrack module availability:** On this gateway, iptables NAT MASQUERADE rules are already active. NAT requires `nf_conntrack` and automatically loads it as a dependency. `/proc/net/nf_conntrack` is guaranteed to exist when the gateway is running. [ASSUMED: based on kernel module dependency chain — nf_nat depends on nf_conntrack]

### Finding 2: Conntrack Regex Pattern (Claude's Discretion)

The search pattern needs to match the original-direction tuple. The simplest approach:

```python
# Source: derived from known /proc/net/nf_conntrack format
import re

_CT_RE = re.compile(
    r"\bsrc=" + re.escape(src) +
    r"\s+dst=" + re.escape(dst) +
    r"\s+sport=\d+\s+dport=" + re.escape(dpt)
)

def _check_conntrack(src: str, dst: str, dpt: str) -> str:
    """Return '✓' if ESTABLISHED or TIME_WAIT found for (src, dst, dport), else '✗'."""
    try:
        with open("/proc/net/nf_conntrack", "r") as f:
            content = f.read()
    except OSError:
        return "✗"
    pat = re.compile(
        r"(ESTABLISHED|TIME_WAIT).*\bsrc=" + re.escape(src) +
        r"\s+dst=" + re.escape(dst) +
        r".*\bdport=" + re.escape(str(dpt))
    )
    return "✓" if pat.search(content) else "✗"
```

**Note on UDP:** UDP conntrack entries have no state field (no ESTABLISHED/TIME_WAIT). They will always return ✗ — this is the accepted/expected behavior per D-03.

**Deduplication with DEDUP_TTL=30s:** Use a dict `{(src, dst, dport): last_logged_monotonic}`. Before doing the STATUS_DELAY sleep, check the dict; skip if `now - last < DEDUP_TTL`. [ASSUMED: pattern; no upstream docs needed — pure Python]

### Finding 3: Python Dated Log File Rotation [ASSUMED]

The standard pattern for manual (non-logging-module) date-based rotation in a long-running Python process:

```python
import datetime

_log_file = None
_log_date = None

def _open_log_file():
    """Open or reopen the dated log file; rotate at midnight."""
    global _log_file, _log_date
    today = datetime.date.today()
    if _log_date == today and _log_file is not None:
        return _log_file
    # Close old handle
    if _log_file is not None:
        try:
            _log_file.close()
        except OSError:
            pass
    path = f"{LOG_DIR}/watch-{today.isoformat()}.log"
    _log_file = open(path, "a", encoding="utf-8")  # noqa: WPS515
    _log_date = today
    return _log_file

def _write_daemon_line(line: str) -> None:
    f = _open_log_file()
    f.write(line + "\n")
    f.flush()
```

**Thread safety:** watch-routes.py's main loop is single-threaded for output; only ASN background threads run concurrently, and they call `_flush_entries` which calls `print()`. In daemon mode, `_flush_entries` must be changed to call `_write_daemon_line` instead of `print`. Since the main loop and the ASN watchdog thread both call `_flush_entries`, a write lock is needed:

```python
_daemon_write_lock = threading.Lock()

def _write_daemon_line(line: str) -> None:
    with _daemon_write_lock:
        f = _open_log_file()
        f.write(line + "\n")
        f.flush()
```

`f.flush()` after each write is important — without it, lines may sit in the OS buffer and not appear in the file until the buffer fills or the process exits. [ASSUMED]

### Finding 4: systemd Service Unit — StandardOutput=null [ASSUMED]

For a Python daemon that self-manages its log file:

- `StandardOutput=null` — discards stdout; correct choice since the daemon writes to its own dated files and stdout is empty in daemon mode
- `StandardError=append:/etc/splitgate/logs/watch-error.log` — captures Python tracebacks and startup errors to a persistent file

`StandardOutput=journal` would duplicate the daemon's file output into journald, which is wasteful. `StandardOutput=null` is the correct choice for a self-logging daemon. [CITED: https://www.ctrl.blog/entry/systemd-log-levels.html]

The locked decision D-10 already specifies `StandardOutput=null` — this research confirms it is correct.

### Finding 5: deploy.sh Stage Numbering Analysis [VERIFIED: codebase grep]

Current state (verified from source):

- `TOTAL_STAGES=27` (line 89)
- Stage 1 through 26 are labeled in echo statements
- Stage 26 = logrotate config deploy (the last stage currently)
- Stage 24 = routing.sh activation (labeled `[24/...]`)
- Stage 25 = splitgate dispatcher (`[25/...]`)
- Stage 26 = logrotate (`[26/...]`)

The sub-labeled stages (21b, 21c) are NOT counted separately in TOTAL_STAGES. The numeric gap between displayed label (26) and TOTAL_STAGES (27) is a pre-existing cosmetic discrepancy from Phase 10 (the logrotate stage was added as "Stage 27" in STATE.md comments but the deploy.sh echo says `[26/...]`).

**For Phase 13:** The new splitgate-watch.service stage should:
- Echo `[27/${TOTAL_STAGES}]` (next after logrotate's `[26/...]`)
- Bump `TOTAL_STAGES` from 27 to 28
- Be placed AFTER logrotate (Stage 26) and BEFORE the final summary

This resolves the cosmetic discrepancy: displayed label will match TOTAL_STAGES - 1 (as logrotate is `[26/28]`) — acceptable, same as existing pattern.

### Finding 6: Logrotate for watch-*.log Cleanup [CITED: man7.org/linux/man-pages/man8/logrotate.8.html]

The plan (D-06) is to add a `postrotate` script inside the existing `logrotate-vpn-gateway` stanza that runs:

```bash
find /etc/splitgate/logs -name "watch-*.log" -mtime +14 -delete
```

This is the correct approach — logrotate's `postrotate` block supports arbitrary shell commands including `find`. With `sharedscripts` the postrotate script runs once per rotation cycle, not once per matched file.

**Important:** The existing stanza targets `vpn-gateway.log` specifically (renamed to `install.log`). Adding the watch-*.log cleanup to its postrotate means cleanup happens whenever `install.log` is rotated (daily). Since `install.log` is set to `daily` rotation, this happens every day — appropriate for 14-day cleanup.

Logrotate does NOT itself rotate the watch-*.log files (they are self-managed by Python with date-based names). The postrotate hook only handles deletion of files older than 14 days.

Revised logrotate stanza after this phase:

```
/etc/splitgate/logs/install.log {
    daily
    rotate 14
    compress
    dateext
    missingok
    notifempty
    create 0640 root root
    sharedscripts
    postrotate
        find /etc/splitgate/logs -name "watch-*.log" -mtime +14 -delete 2>/dev/null || true
    endscript
}
```

### Finding 7: isp-routes-custom.txt — Current State [VERIFIED: codebase read]

The file currently contains only comments — no active CIDRs. All 11 D-01 CIDRs are new additions. The file format is one CIDR per line, no inline comments, `#` whole-line comments allowed.

### Finding 8: vpn-routes-custom.txt — Current State [VERIFIED: codebase read]

The file already has 18 active CIDRs (GitHub CDN, AWS CloudFront Frankfurt/Amsterdam/US, Cloudflare DNS, Akamai, Google). D-02 adds a new **commented** section for candidates the user may activate. The new section should be appended at the bottom with a header comment block.

### Finding 9: ru-exclude.txt.example — Stale References [VERIFIED: codebase read]

The `.example` file contains references to `/etc/ru-exclude.txt` (old path — pre-Phase 10) and `configs/ru-exclude.txt` (old deploy path). After the rename to `ru-list-exclude.txt`, both the filename and all internal documentation comments need updating. References at lines 4, 18-22 of the example file.

### Finding 10: deploy.sh Summary Text — Full Audit [VERIFIED: codebase grep]

Files/lines requiring changes for D-07 (vpn-gateway.log → install.log):
- `src/scripts/routing.sh` line 46: `LOG_FILE="/etc/splitgate/logs/vpn-gateway.log"`
- `src/scripts/update-vpn-routes` line 25: hardcoded `>> /etc/splitgate/logs/vpn-gateway.log`
- `src/scripts/vpn-rollback.sh` line 34: hardcoded `tee -a /etc/splitgate/logs/vpn-gateway.log`
- `src/configs/logrotate-vpn-gateway` line 2: `/etc/splitgate/logs/vpn-gateway.log {`
- `src/deploy.sh` line 497: summary echo text

Files/lines requiring changes for D-08 (ru-exclude.txt → ru-list-exclude.txt):
- `src/scripts/routing.sh` line 92: `EXCLUDE_FILE="/etc/splitgate/ru-exclude.txt"`
- `src/scripts/update-vpn-routes` line 41: `EXCLUDE_FILE="/etc/splitgate/ru-exclude.txt"`
- `src/deploy.sh` line 74: `EXCLUDE_LIST_LOCAL="configs/ru-exclude.txt"`
- `src/deploy.sh` line 75: `EXCLUDE_LIST_REMOTE="/etc/splitgate/ru-exclude.txt"`
- `src/deploy.sh` line 76: `EXCLUDE_LIST_TMP="/tmp/ru-exclude.tmp"`
- `src/deploy.sh` line 417: echo text "Deploying ru-exclude.txt"
- `src/deploy.sh` line 421: echo text "ru-exclude.txt deployed"
- `src/deploy.sh` line 440: comment mentions ru-exclude.txt
- `src/deploy.sh` line 495: summary echo text
- `src/configs/ru-exclude.txt.example` → rename file to `ru-list-exclude.txt.example`; update all internal references
- `src/configs/ru-exclude.txt` (gitignored) → internal comment references at lines 4, 18-22

**Additional reference in scripts:** `src/scripts/routing.sh` line 89 (comment), line 157 (comment); `src/scripts/update-vpn-routes` lines 4-5, 38 (comment), 50 (log message "Excluding ${exclude_count} CIDR(s) from RU subnet download") — these should also be updated to reference the new filename.

### Finding 11: Install Log Verbosity (D-09) — Exact Code Insertion Points

**update-vpn-routes** — changes needed:

1. Log download source domain (line 56 area, after `log "Checking for RU subnet list update..."`):
   ```bash
   log "Checking RU subnet list ($(echo "${RU_SUBNET_URL}" | sed 's|https\?://||;s|/.*||'))..."
   ```
   Or simpler: hardcode `russia.iplist.opencck.org` since the URL base never changes.

2. Log actual excluded CIDRs (replace line 51 `log "Excluding ${exclude_count} CIDR(s) from RU subnet download"`):
   Collect CIDRs into an array or comma-separated string while iterating, then log them.

3. Log route count after download (after successful download/mv, line 90 area):
   ```bash
   route_count=$(grep -c . "${SUBNET_FILE}" || true)
   log "Downloaded ${route_count} routes"
   ```
   Note: this should check whether routes were rebuilt or unchanged.

**routing.sh** — changes needed:

1. Log excluded CIDRs explicitly (replace line 101 `log "Stage 1: Applying ${exclude_count} exclusion(s) from ${EXCLUDE_FILE}"`):
   Same approach as update-vpn-routes — collect while iterating, log the list.

2. After Stage 5b complete (line 202 area, `log "ISP-custom routes added: ${EX_ADDED} routes via ${KEENETIC_GW}"`):
   This already logs entry count — D-09 requires logging it, which it already does. However the log message should explicitly count entries in the file (including non-active comment lines vs active CIDRs). Current `EX_ADDED` counts actual routes added — that's sufficient.

3. After Stage 5c complete (line 221 area): Same as 5b — `VPN_FORCED` is already logged.

The D-09 install log example shows distinct messages for excluded CIDRs and route count. The log verbosity improvement is primarily in `update-vpn-routes` for the download path and in `routing.sh` for the exclude URL construction.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Connection state detection | Custom conntrack CLI invocation | Read `/proc/net/nf_conntrack` directly | Subprocess adds latency; proc file is always present when NAT active |
| Log rotation | Custom date-check + file rotation logic from scratch | Standard Python `open()` + `date.today()` check per write | Simple; no deps |
| Daemon process management | Double-fork, PID files, signal handlers | systemd `Restart=on-failure` | systemd is already used for vpn-routing.service; consistent pattern |
| Time-based log cleanup | Cron entry | logrotate postrotate with `find -mtime +14 -delete` | logrotate already deployed and managing install.log |

**Key insight:** The gateway has no pip package management — every new dependency would need manual apt install on the RPi. The constraint "stdlib only" is non-negotiable.

---

## Runtime State Inventory

This phase renames two strings that appear in running system state:

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — conntrack is kernel-managed; no persistent app data stores the log filename | None |
| Live service config | `/etc/logrotate.d/vpn-gateway` on RPi references `/etc/splitgate/logs/vpn-gateway.log` | deploy.sh stage re-deploys updated logrotate config |
| OS-registered state | None — no systemd timers or task scheduler entries reference these filenames | None |
| Secrets/env vars | None — log filename not in vpn-gateway.env | None |
| Build artifacts / installed files on RPi | `/etc/splitgate/logs/vpn-gateway.log` (live file on RPi) — rename to `install.log` is needed for new entries; old file accumulates no more entries after deploy | deploy.sh does NOT rename existing file; `mv` would be a migration step. Old `vpn-gateway.log` stays harmlessly on RPi (no script will write to it after deploy). logrotate stanza will stop rotating it (missingok handles absence). |

**Live file note:** The old `vpn-gateway.log` on the RPi will orphan after deploy — scripts stop writing to it, logrotate stops rotating it (missingok). The file can be manually removed or left to age. The plan should explicitly note this — it is NOT a blocking issue but operators should be aware.

Similarly, `ru-exclude.txt` on the RPi: after deploy, routing.sh and update-vpn-routes will look for `ru-list-exclude.txt`. If the operator has a live `ru-exclude.txt` on the RPi, it will be silently ignored. The deploy stage that renames this file must: SCP as `ru-list-exclude.txt` AND (if the old file exists) the operator should `mv` or the deploy stage should handle it. **This is a non-trivial migration concern** — the deploy.sh stage should rename (or re-SCP) the file with the new remote path.

---

## Common Pitfalls

### Pitfall 1: conntrack `dpt` vs `dport` in regex
**What goes wrong:** The iptables LOG line uses `DPT=443` (uppercase, short); /proc/net/nf_conntrack uses `dport=443` (lowercase, full). The regex must match `dport=`, not `dpt=`.
**How to avoid:** Verify the conntrack read pattern uses `dport=` not `dpt=`.

### Pitfall 2: conntrack not present when gateway is down
**What goes wrong:** If routing.sh has not run (gateway not set up), /proc/net/nf_conntrack may not exist. `open()` will raise `OSError`.
**How to avoid:** Wrap the conntrack read in `try/except OSError: return "✗"` — already specified in the code pattern above.

### Pitfall 3: daemon mode stdout leak
**What goes wrong:** If `print()` is called anywhere in the daemon path (e.g., inside `_flush_entries`), systemd captures it via stdout unless `StandardOutput=null`. With `StandardOutput=null` it is discarded. But in non-daemon mode, `print()` must still work.
**How to avoid:** `_flush_entries` must check whether daemon mode is active and call `_write_daemon_line` instead of `print`. The `--daemon` flag should set a module-level bool `_DAEMON_MODE` that all output paths check.

### Pitfall 4: file handle leak on midnight rotation
**What goes wrong:** If `_log_file.close()` raises (e.g., disk full), `_log_date` is not updated and the function retries `close()` on every subsequent write.
**How to avoid:** Update `_log_date` and `_log_file` unconditionally after the `close()` attempt (inside a `try/finally`).

### Pitfall 5: logrotate postrotate runs as root but watch log dir is root:root already
**What goes wrong:** logrotate runs as root; `find` and `delete` work. No issue.
**However:** The `postrotate` script must use the exact glob `watch-*.log` — any typo leaves files accumulating indefinitely.
**How to avoid:** Test the pattern manually before committing: `find /etc/splitgate/logs -name "watch-*.log" -mtime +14`.

### Pitfall 6: ru-exclude.txt live migration on RPi
**What goes wrong:** After deploy, scripts look for `/etc/splitgate/ru-list-exclude.txt`. If the operator had a live `/etc/splitgate/ru-exclude.txt` on the RPi, it is silently ignored — exclusions stop working.
**How to avoid:** The deploy.sh stage for ru-list-exclude.txt should rename the old file on the RPi if present:
```bash
ssh -o BatchMode=yes "${SSH_HOST}" "if [ -f /etc/splitgate/ru-exclude.txt ] && [ ! -f /etc/splitgate/ru-list-exclude.txt ]; then sudo mv /etc/splitgate/ru-exclude.txt /etc/splitgate/ru-list-exclude.txt; fi"
```
Alternatively, always deploy as `ru-list-exclude.txt` (EXCLUDE_LIST_REMOTE updated to new path) and document the migration.

### Pitfall 7: deploy.sh EXCLUDE_LIST_TMP still references old name
**What goes wrong:** After renaming EXCLUDE_LIST_LOCAL/REMOTE, EXCLUDE_LIST_TMP is still `/tmp/ru-exclude.tmp`. This works but is inconsistent and confusing.
**How to avoid:** Also rename `EXCLUDE_LIST_TMP="/tmp/ru-list-exclude.tmp"` in deploy.sh.

### Pitfall 8: vpn-rollback.sh still references old filenames after rename
**What goes wrong:** vpn-rollback.sh Step 7b prints the tree it removes (lines 155). After D-08 rename, `ru-exclude.txt` in that echo becomes stale.
**How to avoid:** The D-08 reference audit must include vpn-rollback.sh line 155 (the echo text).

### Pitfall 9: dedup dict grows unbounded
**What goes wrong:** The dedup dict `{(src, dst, dport): last_seen_ts}` accumulates entries for every unique connection triplet and is never cleared.
**How to avoid:** On each dedup check, also evict entries older than `DEDUP_TTL * 4` (e.g., 120s) — simple TTL eviction keeps the dict small for long-running daemons.

---

## Code Examples

### conntrack check (pattern for discretion)
```python
# Source: derived from /proc/net/nf_conntrack format (Fedora Magazine docs)
import re, threading
_daemon_write_lock = threading.Lock()
_CT_STATE_RE = re.compile(r"\b(ESTABLISHED|TIME_WAIT)\b")

def _check_conntrack(src: str, dst: str, dpt: str) -> str:
    """Return '✓' if ESTABLISHED/TIME_WAIT for (src,dst,dport) found, else '✗'."""
    try:
        with open("/proc/net/nf_conntrack", "r") as f:
            for line in f:
                # Match original direction tuple: src=<src> ... dst=<dst> ... dport=<dpt>
                if (f"src={src}" in line and f"dst={dst}" in line and f"dport={dpt}" in line
                        and _CT_STATE_RE.search(line)):
                    return "✓"
    except OSError:
        return "✗"
    return "✗"
```

Note: scanning line-by-line (not reading entire file) is safer on a busy gateway where conntrack can have thousands of entries.

### dated log file writer (daemon mode)
```python
# Source: standard Python pattern [ASSUMED]
import datetime, threading, os

LOG_DIR = "/etc/splitgate/logs"
_log_file = None
_log_date = None
_daemon_write_lock = threading.Lock()

def _open_log_file():
    global _log_file, _log_date
    today = datetime.date.today()
    if _log_date == today and _log_file is not None:
        return _log_file
    # rotate: close old
    old = _log_file
    _log_file = None
    _log_date = None
    if old is not None:
        try:
            old.close()
        except OSError:
            pass
    os.makedirs(LOG_DIR, exist_ok=True)
    path = f"{LOG_DIR}/watch-{today.isoformat()}.log"
    _log_file = open(path, "a", encoding="utf-8")
    _log_date = today
    return _log_file

def _write_daemon_line(line: str) -> None:
    with _daemon_write_lock:
        f = _open_log_file()
        f.write(line + "\n")
        f.flush()
```

### splitgate-watch.service (D-10, based on vpn-routing.service template)
```ini
[Unit]
Description=Splitgate route watcher
After=network.target

[Service]
ExecStart=/usr/bin/python3 /etc/splitgate/watch-routes.py --daemon
StandardOutput=null
StandardError=append:/etc/splitgate/logs/watch-error.log
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
```

### logrotate stanza after rename + postrotate (D-06, D-07)
```
/etc/splitgate/logs/install.log {
    daily
    rotate 14
    compress
    dateext
    missingok
    notifempty
    create 0640 root root
    sharedscripts
    postrotate
        find /etc/splitgate/logs -name "watch-*.log" -mtime +14 -delete 2>/dev/null || true
    endscript
}
```

### deploy.sh new stage (Stage 27)
```bash
WATCH_SERVICE_LOCAL="systemd/splitgate-watch.service"
WATCH_SERVICE_REMOTE="/etc/systemd/system/splitgate-watch.service"
WATCH_SERVICE_TMP="/tmp/splitgate-watch.service.tmp"

# Stage 27: Deploy splitgate-watch.service
echo "[27/${TOTAL_STAGES}] Deploying splitgate-watch.service to ${SSH_HOST}:${WATCH_SERVICE_REMOTE}..."
scp -o BatchMode=yes "${WATCH_SERVICE_LOCAL}" "${SSH_HOST}:${WATCH_SERVICE_TMP}"
ssh -o BatchMode=yes "${SSH_HOST}" \
    "sudo mv ${WATCH_SERVICE_TMP} ${WATCH_SERVICE_REMOTE} && \
     sudo chmod 644 ${WATCH_SERVICE_REMOTE} && \
     sudo chown root:root ${WATCH_SERVICE_REMOTE} && \
     sudo systemctl daemon-reload && \
     sudo systemctl enable --now splitgate-watch.service"
echo "       splitgate-watch.service deployed and enabled."
```

### deploy.sh ru-list-exclude.txt migration snippet
```bash
# In Stage 21c — after SCP of ru-list-exclude.txt:
# Also rename old ru-exclude.txt on RPi if present
ssh -o BatchMode=yes "${SSH_HOST}" \
    "if sudo test -f /etc/splitgate/ru-exclude.txt && ! sudo test -f /etc/splitgate/ru-list-exclude.txt; then \
     sudo mv /etc/splitgate/ru-exclude.txt /etc/splitgate/ru-list-exclude.txt; fi"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Logger syslog (-t tag) | File-append log() function | Phase 9 | Centralized file, no journald dependency |
| Flat /etc/ file layout | /etc/splitgate/ namespace | Phase 10 | All app files under one directory |
| No ASN enrichment | Background thread + 6s buffer | Phase 12 | Buffered output prevents blocking |

**Pattern established:** All new scripts in this project use `log() { echo "[date] [component] $*" >> FILE; }`. The watch-routes.py daemon mode follows the same convention (with Python equivalent), writing `[ISO_TS] [ISP/VPN] status src → dst proto | org`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | nf_conntrack auto-loaded as dependency of iptables NAT/MASQUERADE on this gateway | Finding 2 | If module not loaded, all conntrack reads return ✗ (graceful degradation — daemon still works, just shows ✗ for all) |
| A2 | `_open_log_file()` / `_write_daemon_line()` pattern is thread-safe with a write lock | Finding 3 | Without lock, two threads (main loop + watchdog) could interleave writes or double-close the file handle |
| A3 | Dedup dict needs TTL eviction to prevent unbounded growth | Pitfall 9 | Without eviction, long-running daemon accumulates stale entries (memory leak, small but real on RPi) |
| A4 | `f.flush()` after each write is necessary for daemon log visibility | Finding 3 | Without flush, lines appear in the file only when the buffer fills or the process exits — not useful for `tail -f` |

---

## Open Questions

1. **Should the old `vpn-gateway.log` on the RPi be renamed or left to age?**
   - What we know: After deploy, no script writes to it. logrotate `missingok` handles absence gracefully.
   - What's unclear: Operator preference — does leaving an orphaned file cause confusion?
   - Recommendation: Document in deploy summary that `vpn-gateway.log` is superseded by `install.log`. Add an optional cleanup step in the deploy stage or rollback notes.

2. **Should `--no-asn` mode skip the conntrack check as well?**
   - CONTEXT.md says: "Whether to keep `--no-asn` path unchanged (yes — no status check if ASN disabled)" — this is Claude's Discretion, meaning yes, skip conntrack when `--no-asn`. The logic: `--no-asn` is the "pure no-network mode" per the existing docstring; conntrack is a proc read (no network), so it could remain. But the existing decision says no — keep `--no-asn` path identical to today's behavior.
   - Recommendation: In `--no-asn` + `--daemon` mode, skip STATUS_DELAY and conntrack check; output format omits the `✓/✗` field. This is the simplest correct interpretation.

3. **`splitgate-watch.service` dependency on `vpn-routing.service`?**
   - What we know: watch-routes.py only reads journalctl — it does not depend on routing being active to function.
   - What's unclear: Should the service declare `After=vpn-routing.service` to ensure it starts after routing, or is `After=network.target` sufficient?
   - Recommendation: `After=network.target` is sufficient. The CONTEXT.md D-10 spec shows this, and it matches the intended usage (the watcher is an observer, not dependent on routing state).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | watch-routes.py daemon | ✓ (RPi Bookworm) | 3.11 | — |
| systemd | splitgate-watch.service | ✓ (RPi Bookworm) | 252 | — |
| /proc/net/nf_conntrack | conntrack status check | ✓ when NAT active | kernel 6.12.25+rpt | Returns ✗ gracefully if absent |
| logrotate | watch-*.log cleanup | ✓ (already deployed) | Bookworm | — |
| find (GNU) | postrotate cleanup | ✓ (Bookworm) | 4.9.0 | — |

**Missing dependencies with no fallback:** None.

---

## Project Constraints (from CLAUDE.md)

- **Safety**: Scripts must be idempotent; routing.sh safe to re-run at any time — no change to routing.sh's idempotency model in this phase
- **Rollback**: vpn-rollback.sh must clean up the new service (`splitgate-watch.service`) — the plan must add `systemctl stop/disable splitgate-watch.service` to vpn-rollback.sh Step 1
- **Secrets**: No new secrets introduced
- **After every commit, immediately run `git push`**
- **After completing any task, review README.md, docs/README.ru.md, docs/REFERENCE.md** — Phase 13 touches file paths, log names, and adds a new service. All three docs must be updated
- **Before closing any task, grep the entire project for references to every renamed concept** — D-07 and D-08 are rename operations; full grep audit required before closing

---

## Sources

### Primary (HIGH confidence)
- Codebase direct read — all line numbers and current values verified by reading src/ files
- [Fedora Magazine: conntrack format](https://fedoramagazine.org/network-address-translation-part-2-the-conntrack-tool/) — /proc/net/nf_conntrack line layout confirmed
- [man7.org logrotate(8)](https://man7.org/linux/man-pages/man8/logrotate.8.html) — postrotate, sharedscripts, glob patterns

### Secondary (MEDIUM confidence)
- [WebSearch: nf_conntrack ESTABLISHED TIME_WAIT fields](https://netfilter.vger.kernel.narkive.com/oFMLLOkV/nf-conntrack-format) — format cross-verified
- [systemd StandardOutput options](https://www.ctrl.blog/entry/systemd-log-levels.html) — StandardOutput=null behavior confirmed

### Tertiary (LOW confidence / ASSUMED)
- Python thread-safe file write pattern (A2) — standard stdlib pattern, not verified against official docs in this session

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — stdlib only, no new packages
- Architecture: HIGH — verified from codebase + kernel docs
- Pitfalls: HIGH — verified from codebase analysis (rename audit is exhaustive)
- conntrack format: HIGH — confirmed from official Linux documentation
- Python daemon pattern: MEDIUM — standard pattern, ASSUMED thread-safety analysis

**Research date:** 2026-05-29
**Valid until:** 2026-06-29 (stable domain — kernel proc format and systemd behavior do not change)
