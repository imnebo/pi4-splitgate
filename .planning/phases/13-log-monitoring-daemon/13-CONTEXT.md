# Phase 13: Log Monitoring, Routing Refinement & Daemon — Context

**Gathered:** 2026-05-29
**Status:** Ready for planning
**Source:** Discussion session (log analysis of output_watch.log, 2026-05-28)

<domain>
## Phase Boundary

Phase 13 delivers:
1. **Routing config refinement** — add missing Russian CIDRs to `isp-routes-custom.txt`; add non-RU false-positive candidates to `vpn-routes-custom.txt` (commented, for manual activation)
2. **watch-routes.py daemon mode** — `--daemon` flag writes to dated daily log files (`watch-YYYY-MM-DD.log`); connection status (✓/✗) via `/proc/net/nf_conntrack` with 30s deduplication
3. **systemd service** — `splitgate-watch.service` so daemon survives SSH disconnects and reboots
4. **Rename: `vpn-gateway.log` → `install.log`** — across routing.sh, update-vpn-routes, vpn-rollback.sh, logrotate config, deploy.sh
5. **Rename: `ru-exclude.txt` → `ru-list-exclude.txt`** — more descriptive; across routing.sh, update-vpn-routes, deploy.sh, example file
6. **Install log improvements** — routing.sh and update-vpn-routes show: download source, actual excluded CIDRs (not just count), route count downloaded, custom file entry counts
7. **Documentation** — README.md, docs/README.ru.md, docs/REFERENCE.md, STATE.md updated

User workflow enabled:
- SSH in → `grep "[ISP] ✗" /etc/splitgate/logs/watch-2026-05-29.log` → see which ISP routes fail
- Uncomment candidates in `vpn-routes-custom.txt` → re-run `routing.sh`
- `ISP + ✓` = no action needed

</domain>

<decisions>
## Implementation Decisions

### D-01: Routing — Missing RU CIDRs (isp-routes-custom.txt)
Add these /24 subnets (confirmed RU ASN, currently routed via VPN incorrectly):
- `87.228.71.0/24` — Selectel (JSC Selectel, RU)
- `95.213.181.0/24` — Selectel
- `185.162.92.0/24` — MIRAN-AS (captive116.keenetic.ru)
- `89.169.29.0/24` — RU-JSCIOT (captive113/115.keenetic.ru)
- `31.135.14.0/24` — RU datacenter (vlan1354.dci6)
- `31.173.34.0/24` — SonicDuo-AS
- `81.9.21.0/24` — SOVAM-AS
- `85.26.231.0/24` — MegaFon PJSC
- `193.28.44.0/24` — Raiffeisenbank (RBRU-AS)
- `128.75.237.0/24` — VimpelCom/Corbina
- `178.249.69.0/24` — RU (suspicious hostname cloud.example.com, ASN confirmed RU)

### D-02: Routing — Non-RU Candidates (vpn-routes-custom.txt)
Add commented block. User uncomments when a service fails under ISP routing. Not forced now.
Key candidates from log (non-RU, going via ISP as false positives):
- Cherry Servers LT (`84.32.100.0/22`) — 325 hits
- Google PoPs: lhr/par/tzhema/ncberi (`192.178.25.0/24`, `192.178.170.0/24`, `216.58.198.0/24`, `216.58.201.0/24`, `216.58.207.0/24`)
- Cloudflare non-DNS: `8.6.112.0/24`, `8.47.69.0/24`
- Amazon CloudFront hel51: `18.165.122.0/24`
- Amazon EC2 ap-se-1: `13.228.133.0/24`
- Akamai NL/US: `2.16.238.0/24`, `2.17.251.0/24`, `2.22.145.0/24`, `2.23.88.0/24`, `23.11.40.0/24`, `23.216.134.0/24`, `95.100.107.0/24`, `95.101.27.0/24`, `184.86.251.0/24`
- Microsoft Azure EU: `51.116.246.0/24`, `51.116.253.0/24`

### D-03: watch-routes.py — Connection Status Mechanism
Use `/proc/net/nf_conntrack` (plain file read, no subprocess, no pip deps).
Constants:
- `STATUS_DELAY = 3` — seconds to wait before conntrack check
- `DEDUP_TTL = 30` — seconds before same (src, dst, dport) logged again
Status: `✓` if ESTABLISHED or TIME_WAIT found, `✗` otherwise.
UDP connections often show `✗` (conntrack entry short-lived) — acceptable/expected.

### D-04: watch-routes.py — Output Format
One complete line written after STATUS_DELAY. Format:
```
2026-05-29T10:14:00 [ISP] ✓ 10.0.0.237 → yandex.ru TCP:443 | TELETECH, RU
2026-05-29T10:14:05 [ISP] ✗ 10.0.0.237 → github.com TCP:443 | FASTLY, US
```
The 3s delay is invisible when reading a file log. It fits within the existing ASN BUFFER_TIMEOUT=6s window.
Status always on — no flag. The status IS the purpose of daemon mode.

### D-05: watch-routes.py — Daemon Mode Flag
Add `--daemon` flag:
- Without `--daemon`: stdout (existing interactive behavior, unchanged)
- With `--daemon`: write to dated log file, no stdout

### D-06: watch-routes.py — Dated Log Files
Log path: `/etc/splitgate/logs/watch-YYYY-MM-DD.log` (e.g. `watch-2026-05-29.log`).
Managed by watch-routes.py internally:
- Constants: `LOG_DIR = "/etc/splitgate/logs"`
- `_open_log_file()` → opens `f"{LOG_DIR}/watch-{date.today().isoformat()}.log"` in append mode
- Main loop checks `date.today()` on each write; if day changed → close old, open new
Cleanup: `find /etc/splitgate/logs -name "watch-*.log" -mtime +14 -delete` in logrotate postrotate.

### D-07: Rename vpn-gateway.log → install.log
All references:
- `src/scripts/routing.sh` L46: `LOG_FILE=".../vpn-gateway.log"` → `install.log`
- `src/scripts/update-vpn-routes` L25: same
- `src/scripts/vpn-rollback.sh` L34: same
- `src/configs/logrotate-vpn-gateway` L2: log path
- `src/deploy.sh` L497: summary text

### D-08: Rename ru-exclude.txt → ru-list-exclude.txt
More descriptive: "exclude these CIDRs from the auto-downloaded RU list".
All references:
- `src/scripts/routing.sh` L92: EXCLUDE_FILE var
- `src/scripts/update-vpn-routes` L41: EXCLUDE_FILE var
- `src/deploy.sh` L74-76: EXCLUDE_LIST_LOCAL/REMOTE/TMP vars + L416-421 stage text + L497 summary
- `src/configs/ru-exclude.txt.example` → rename to `ru-list-exclude.txt.example`
- `src/configs/ru-exclude.txt` (gitignored) → update internal comments

### D-09: Install Log Improvements
In `update-vpn-routes`:
- Log download source domain (extract from RU_SUBNET_URL or hard-code domain)
- Log actual excluded CIDRs (not just count): "Excluding: CIDR1, CIDR2, ..."
- Log route count after download: "Downloaded N routes"
In `routing.sh`:
- Log excluded CIDRs explicitly (not just count)  
- After Stage 5b (ISP custom file): log entry count
- After Stage 5c (VPN force file): log entry count
Target `install.log` lines:
```
[2026-05-29 10:00:00] [vpn-routes] Checking RU subnet list (russia.iplist.opencck.org)...
[2026-05-29 10:00:00] [vpn-routes] Excluding 2 CIDR(s): 185.199.108.0/22, 1.0.0.0/24
[2026-05-29 10:00:00] [vpn-routes] Downloaded 12847 routes — unchanged, no rebuild
```

### D-10: systemd Service
New file: `src/systemd/splitgate-watch.service`
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
deploy.sh: new stage to SCP + systemctl daemon-reload + systemctl enable --now splitgate-watch.

### Claude's Discretion
- Exact conntrack regex pattern (match both original and reply direction)
- Whether to keep `--no-asn` path unchanged (yes — no status check if ASN disabled)
- Logrotate file name (keep `logrotate-vpn-gateway` or rename) — keep filename, update content
- Order of plans in waves (keep parallel where possible)
- Whether to bump TOTAL_STAGES in deploy.sh vs add a separate counter

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Current implementation
- `src/scripts/watch-routes.py` — full script to extend (STATUS_DELAY, DEDUP_TTL, --daemon, log file rotation)
- `src/scripts/routing.sh` — Stage 1 (download/exclude), Stage 5b (ISP custom), Stage 5c (VPN force); LOG_FILE at L46; EXCLUDE_FILE at L92
- `src/scripts/update-vpn-routes` — log() at L25; EXCLUDE_FILE at L41; logging blocks L38-53, L55-68
- `src/scripts/vpn-rollback.sh` — log() at L34
- `src/configs/logrotate-vpn-gateway` — log path at L2
- `src/deploy.sh` — EXCLUDE_LIST vars L74-76; Stage 22c L416-421; summary L497; TOTAL_STAGES

### Config files to modify
- `src/configs/isp-routes-custom.txt` — add RU CIDRs
- `src/configs/vpn-routes-custom.txt` — add commented non-RU candidates
- `src/configs/ru-exclude.txt.example` — rename + update internal docs

### Existing patterns
- `src/systemd/vpn-routing.service` — existing systemd unit, use as template for splitgate-watch.service
- `.planning/phases/12-buffered-asn-output/12-01-PLAN.md` — PLAN.md format reference
- `.planning/STATE.md` — decisions log (D-09 through D-19 used; new decisions start at D-20+)

### Project docs to update
- `README.md`, `docs/README.ru.md`, `docs/REFERENCE.md`

</canonical_refs>

<specifics>
## Specific Ideas

- Log analysis source: `logs/output_watch.log` (1.5MB, 13783 lines, 2026-05-28, ~16h session)
- The `/proc/net/nf_conntrack` format: `ipv4 2 tcp 6 431999 ESTABLISHED src=X dst=Y sport=Z dport=W ...`
- Match pattern: `src=<src>.*dst=<dst>.*dport=<dpt>.*(ESTABLISHED|TIME_WAIT)` OR reply direction
- `date.today().isoformat()` → `2026-05-29` format for log filename
- Cherry Servers `84.32.100.60` had 325 hits via ISP — largest non-RU false positive
- Keenetic captive portals (`captive113/115/116.keenetic.ru`) had 700+ hits via VPN — most impactful RU fix
</specifics>

<deferred>
## Deferred Ideas

- Variant B (conntrack -E event mode) — deferred; overkill for interactive diagnostic tool
- Auto-uncomment VPN candidates when ISP ✗ detected — deferred; user wants manual control
- Aggregate status stats per connection pair — deferred; grep workflow sufficient for now
</deferred>

---

*Phase: 13-log-monitoring-daemon*
*Context gathered: 2026-05-29 via discussion session + log analysis*
