# RPi VPN Gateway — Technical Reference

[← README](../README.md) | [Документация на русском](README.ru.md)

---

## Environment Variables

Stored in `/etc/splitgate/vpn-gateway.env` on the RPi; source is `.env` in this repo.

| Variable | Value | Description |
|----------|-------|-------------|
| `RPI_LAN_IP` | `192.168.1.254` | RPi LAN IP address |
| `KEENETIC_GW` | `192.168.1.1` | ISP gateway (your router) |
| `VPN_SERVER_IP` | `YOUR_VPN_SERVER_IP` | AmneziaWG server endpoint IP |
| `VPN_IFACE` | `awg0` | VPN tunnel interface name |
| `LAN_SUBNET` | `192.168.1.0/24` | Local LAN subnet |
| `RU_SUBNET_URL` | `https://russia.iplist.opencck.org/?format=text&data=cidr4` | RU CIDR list source |
| `CRON_UPDATE_HOUR` | `5` | Hour (0-23) for daily subnet refresh cron |

---

## Deploy Stage Groups

`deploy.sh` runs 27 stages from your Mac via SSH. Full deploy: `bash src/deploy.sh`.

| Group | Stages | What happens |
|-------|--------|--------------|
| Preflight | 1–3 | Check required local files, source `.env` + `.env.secrets`, validate keys, verify SSH connectivity |
| AmneziaWG install | 4 | Stream `src/scripts/install-awg.sh` over SSH to the RPi; DKMS build may take 10–30 min |
| Splitgate namespace | 5 | Create `/etc/splitgate/` and `/etc/splitgate/logs/` on the RPi |
| Config deploy | 6–10 | Render and deploy `awg0.conf` (mode 600), deploy `vpn-gateway.env` (mode 644), post-deploy file checks |
| Routing deploy | 11–12 | SCP `routing.sh` to `/etc/splitgate/routing.sh`, activate split-tunnel routing (unless `--no-run`) |
| Autostart | 13–14 | Deploy `vpn-routing.service`, reload systemd, enable `awg-quick@awg0` + `vpn-routing.service` at boot |
| Cron + rollback | 15–17 | Deploy `update-vpn-routes`, write `/etc/cron.d/vpn-routes` (daily at `CRON_UPDATE_HOUR:00`), deploy `vpn-rollback.sh` |
| Logging | 18–21 | Install dnsmasq (before config), deploy `dnsmasq.conf`, deploy `vpn-status.sh`, deploy `watch-routes.py` |
| Exceptions + NM | 22–23 | Conditionally deploy `white-list-extended.txt` and `ru-exclude.txt` if present; deploy NM dispatcher `10-vpn-routes` |
| ASN helper | 24 | Deploy `asn-lookup.py` to `/etc/splitgate/asn-lookup.py` |
| Final activation | 25 | Re-run `routing.sh` to apply all iptables LOG rules and exception routes |
| Splitgate artifacts | 26–27 | Deploy `splitgate` dispatcher to `/usr/local/bin/splitgate` (chmod +x); deploy `logrotate-vpn-gateway` |

---

## Verify Routing

Run on the RPi via SSH after deploy. All commands require `sudo` or run as root.

### 4 routing checks

```bash
# 1. Default route must go through the VPN tunnel
ssh pi4 "ip route show default"
# Expected output contains: default dev awg0

# 2. Foreign IP (8.8.8.8) must route via VPN
ssh pi4 "ip route get 8.8.8.8"
# Expected output contains: dev awg0

# 3. Russian IP (77.88.8.8 — Yandex) must route via ISP
ssh pi4 "ip route get 77.88.8.8"
# Expected output contains: via 192.168.1.1

# 4. VPN server IP must route via ISP (loop prevention)
ssh pi4 "ip route get YOUR_VPN_SERVER_IP"
# Expected output contains: via 192.168.1.1
```

### iptables LOG rules check

```bash
ssh pi4 "sudo iptables -L FORWARD -n -v | grep LOG"
# Expected: two LOG rules — [VPN] on awg0, [ISP] on eth0
```

### vpn-status.sh quick check

After generating some LAN traffic:

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh"
```

Example output:

```
TIMESTAMP            SRC-IP             DST-IP             DOMAIN                                   PATH
-------------------- ------------------ ------------------ ---------------------------------------- ----
May 23 11:36:21      192.168.1.175      17.248.209.64      apple.com                                VPN
May 23 11:36:22      192.168.1.175      77.88.8.8          yandex.ru                                ISP
May 23 11:36:23      192.168.1.100      104.64.0.0         store.steampowered.com                   VPN
```

If the DOMAIN column shows raw IPs, set router DNS to `192.168.1.254` (see README → Deploy → Router setup).

### Autostart checks

```bash
ssh pi4 "systemctl is-active awg-quick@awg0"       # expect: active
ssh pi4 "systemctl is-active vpn-routing.service"  # expect: active
ssh pi4 "systemctl is-enabled awg-quick@awg0"      # expect: enabled
ssh pi4 "systemctl is-enabled vpn-routing.service" # expect: enabled
```

---

## Monitoring & Logs

### vpn-status.sh

`/etc/splitgate/vpn-status.sh` reads journald for iptables `[VPN]`/`[ISP]` LOG entries, correlates with
the dnsmasq query log to resolve destination IPs to domain names (with rDNS fallback via `host`),
and prints a human-readable connection table. Output columns: `TIMESTAMP SRC-IP DST-IP DOMAIN ORG PATH`.

The `ORG` column shows the ISP/org name for each destination IP via Team Cymru ASN lookup
(format: `GOOGLE, US (AS15169)` or `-` when unknown). Lookups are cached in
`/tmp/vpn-asn-cache.json`; Cymru unreachable → all ORG cells show `-` (non-fatal).

Must be run as `sudo` — reads kernel journal and dnsmasq logs.

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh"
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=vpn --last=100"
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --device=192.168.1.50 --filter=steam"

# Show top-20 orgs by connection count, split by VPN/ISP:
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --summary"
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --summary --via=vpn"
```

All flags compose: `--last`, `--filter`, `--device`, `--via`, `--summary` can be combined freely.

### watch-routes.py

`/etc/splitgate/watch-routes.py` is a real-time iptables log enricher. It spawns `journalctl -f -k` and
parses `[VPN]`/`[ISP]` lines as they appear, resolving destination IPs via cached rDNS lookups.
Each line is enriched with ` | {org}` via a background thread — the org suffix appears on subsequent
re-prints of the same IP once the cache is warm. Press Ctrl+C to stop.

```bash
ssh pi4 "sudo python3 /etc/splitgate/watch-routes.py"
ssh pi4 "sudo python3 /etc/splitgate/watch-routes.py --src 192.168.1.50 --tag VPN"
ssh pi4 "sudo python3 /etc/splitgate/watch-routes.py --no-asn"   # disable org enrichment
```

### journald

Direct kernel log queries without `vpn-status.sh`:

```bash
# Last 50 kernel routing decisions
ssh pi4 "sudo journalctl -k -n 50 --no-pager | grep -E '\[VPN\]|\[ISP\]'"

# vpn-routing.service start/stop events
ssh pi4 "sudo journalctl -u vpn-routing -n 50 --no-pager"

# Daily subnet update log
ssh pi4 "sudo journalctl -t vpn-routes -n 20 --no-pager"

# NM dispatcher route restore events (carrier-change recovery)
ssh pi4 "sudo journalctl -t vpn-routes -n 5 --no-pager"
```

### DNS note

`dnsmasq` on the RPi (`192.168.1.254`) must be set as the DNS server in your router for domain
resolution to work in `vpn-status.sh`. Without it, all queries go directly to the upstream DNS
resolver, bypassing dnsmasq's query log, and the DOMAIN column will show raw IPs.

---

## Custom Exceptions

Use this when traffic that should exit via ISP is being routed via VPN. Common case: a game server,
CDN, or streaming platform whose IP range is not in the RU CIDR list.

**Step 1: Identify traffic exiting via VPN that should use ISP**

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=vpn"
```

Look for domains or IPs that should route via ISP. Note their destination IPs.

**Step 2: Resolve the IP to a CIDR**

```bash
whois <destination-ip>
# Look for "route:" or "CIDR:" field — e.g. 23.55.0.0/16
```

Alternatively: `https://ipinfo.io/<destination-ip>`

**Step 3: Create the exception file**

```bash
cp src/configs/white-list-extended.txt.example src/configs/white-list-extended.txt
```

Edit and add CIDRs (one per line, whole-line comments only, no inline comments):

```
23.55.0.0/16
95.181.176.0/22
```

Note: `src/configs/white-list-extended.txt` is gitignored — never committed.

**Step 4: Deploy**

```bash
bash src/deploy.sh
```

Stage 22 SCPs the file to `/etc/splitgate/white-list-extended.txt`. Stage 25 re-runs `routing.sh`.

**Step 5: Verify**

```bash
ssh pi4 "ip route get <your-exception-ip>"
# Expected output contains: via 192.168.1.1

ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=isp"
# Your exception traffic should appear here
```

---

## RU IP List Exclusion Filter

Use this when a CIDR range is incorrectly included in the RU IP list (e.g. a Google or Cloudflare
range that iplist marks as RU) and you want it to route through the VPN.

Unlike custom exceptions which add ISP-bypass routes on top of the downloaded list, the exclusion
filter removes CIDRs from the downloaded list at the source — they never appear in
`/etc/splitgate/white-list.txt` and follow the default route (VPN).

**How it works:** When `/etc/splitgate/ru-exclude.txt` is present, `update-vpn-routes` appends
`&exclude[cidr4]=CIDR` query parameters to `RU_SUBNET_URL` before calling curl. The iplist
service filters those ranges server-side. If the file is absent or empty, behavior is unchanged.

**Step 1: Identify CIDRs to exclude**

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=isp"
```

Look for traffic that should be VPN-routed but exits via ISP. Resolve the destination IP to its
network block using `whois` or `ipinfo.io`.

**Step 2: Create the exclusion file**

```bash
cp src/configs/ru-exclude.txt.example src/configs/ru-exclude.txt
```

Edit and add CIDRs:

```
# Exclude Google ranges incorrectly listed as RU
142.250.0.0/16
142.251.0.0/16
```

Note: `src/configs/ru-exclude.txt` is gitignored — never committed.

**Step 3: Deploy**

```bash
bash src/deploy.sh
```

Stage 22b SCPs `src/configs/ru-exclude.txt` to `/etc/splitgate/ru-exclude.txt`.

**Step 4: Trigger a route rebuild**

```bash
ssh pi4 "sudo /etc/splitgate/update-vpn-routes"
ssh pi4 "sudo journalctl -t vpn-routes -n 10 --no-pager"
# expect: "Excluding N CIDR(s) from RU subnet download" followed by rebuild log
```

**Step 5: Verify**

```bash
ssh pi4 "ip route get <excluded-cidr-ip>"
# Expected output contains: dev awg0  (routes via VPN, not ISP)
```

---

## Rollback

`/etc/splitgate/vpn-rollback.sh` fully undoes the VPN gateway in one idempotent command.

```bash
ssh pi4 "sudo /etc/splitgate/vpn-rollback.sh"
```

### What rollback removes

- Stops and disables `vpn-routing.service` and `awg-quick@awg0`
- Stops and disables `dnsmasq`
- Flushes all routes on `awg0` and the VPN server host route
- Removes MASQUERADE iptables rules on `awg0` + `eth0`
- Removes iptables FORWARD ACCEPT and LOG rules
- Removes `/etc/cron.d/vpn-routes`
- Restores default route via `KEENETIC_GW` (`192.168.1.1`)
- Removes `/usr/local/bin/splitgate`
- Removes `/etc/splitgate/` tree entirely — scripts, data files, env

### What rollback preserves

- `/etc/amnezia/amneziawg/awg0.conf` (mode 600) — kept for re-activation
- AmneziaWG packages — not uninstalled
- `/etc/dnsmasq.conf` — remains on disk (system file); dnsmasq is stopped

### After rollback

Revert the router DHCP gateway back to `192.168.1.1`:

1. `http://192.168.1.1` → Home network → Segments → Default → IP parameters
2. Clear the Gateway address field (or set to `192.168.1.1`) → Save

### Re-activate after rollback

```bash
bash src/deploy.sh
```

---

## Filesystem Layout on the RPi

```
/etc/splitgate/
├── routing.sh
├── vpn-rollback.sh
├── vpn-status.sh
├── update-vpn-routes
├── watch-routes.py
├── asn-lookup.py
├── vpn-gateway.env
├── white-list.txt          (generated at runtime)
├── white-list-extended.txt (optional)
├── ru-exclude.txt          (optional)
└── logs/                   (created at deploy; Phase 9 writes vpn-gateway.log here)

/usr/local/bin/splitgate    (dispatcher CLI)
/etc/logrotate.d/vpn-gateway (rotates /etc/splitgate/logs/vpn-gateway.log)
```

Files that stay at system locations (required by their consuming daemon):

- `/etc/systemd/system/vpn-routing.service` — systemd requires exact path
- `/etc/cron.d/vpn-routes` — cron daemon requires exact path
- `/etc/dnsmasq.conf` — dnsmasq requires exact path
- `/etc/NetworkManager/dispatcher.d/10-vpn-routes` — NM dispatcher requires exact path
- `/etc/iptables/rules.v4` — iptables-persistent requires exact path
- `/etc/amnezia/amneziawg/awg0.conf` — AmneziaWG requires exact path

---

## Script CLI Reference

### src/deploy.sh

**Synopsis:** `bash src/deploy.sh [--no-run]`

Runs from your Mac. Connects to the RPi via `SSH_HOST=pi4` (from `.env`). 27 stages.
Sources `.env` and `.env.secrets`; validates keys before any remote operation.

| Flag | Description |
|------|-------------|
| `--no-run` | Deploy all files but skip `routing.sh` activation. Use for first-time deploys before the tunnel is up, or when testing config changes without activating routes. |

```bash
bash src/deploy.sh              # full deploy + activate routing
bash src/deploy.sh --no-run     # deploy only — activate routing manually later
ssh pi4 "sudo /etc/splitgate/routing.sh"   # activate after --no-run deploy
```

---

### routing.sh (deployed to /etc/splitgate/routing.sh)

**Synopsis:** `sudo /etc/splitgate/routing.sh [--no-update]`

Flush-and-rebuild split-tunnel routing. Idempotent — safe to re-run at any time.

On each run: downloads RU CIDRs → flushes existing VPN routes → adds VPN server host route →
adds RU CIDR routes via `KEENETIC_GW` → loads `white-list-extended.txt` (if present) →
sets default route via `awg0` → configures MASQUERADE and iptables LOG rules → saves via `iptables-save`.

| Flag | Description |
|------|-------------|
| `--no-update` | Skip downloading fresh RU subnets; use existing `/etc/splitgate/white-list.txt`. Used by `update-vpn-routes` after an atomic file swap to avoid double-download. |

```bash
ssh pi4 "sudo /etc/splitgate/routing.sh"             # full run with download
ssh pi4 "sudo /etc/splitgate/routing.sh --no-update" # rebuild without download
ssh pi4 "ip route show default"     # expect: default dev awg0
ssh pi4 "ip route get 8.8.8.8"      # expect: dev awg0
ssh pi4 "ip route get 77.88.8.8"    # expect: via 192.168.1.1
```

---

### vpn-status.sh (deployed to /etc/splitgate/vpn-status.sh)

**Synopsis:** `sudo /etc/splitgate/vpn-status.sh [--last=N] [--filter=STRING] [--device=IP] [--via=vpn|isp] [--summary]`

Reads journald `[VPN]`/`[ISP]` LOG entries, correlates with dnsmasq query log for domain
resolution, falls back to rDNS (`host`). Output columns: `TIMESTAMP SRC-IP DST-IP DOMAIN ORG PATH`.

The `ORG` column shows `{org} (AS{asn})` via Team Cymru bulk-whois, or `-` when unresolvable.
Results are cached in `/tmp/vpn-asn-cache.json` (mode 0666, shared between root and non-root).

Must run as `sudo`.

| Flag | Description |
|------|-------------|
| `--last=N` | Show last N journald kernel entries (default: 50) |
| `--filter=STRING` | Case-insensitive partial match on the DOMAIN column |
| `--device=IP` | Filter by source LAN device IP (SRC field) |
| `--via=vpn\|isp` | Show only VPN-routed or ISP-routed connections |
| `--summary` | Print top-20 ORG aggregate table (ORG \| VPN_COUNT \| ISP_COUNT \| TOTAL) instead of per-row table |

All flags compose freely.

```bash
sudo /etc/splitgate/vpn-status.sh
sudo /etc/splitgate/vpn-status.sh --via=vpn --last=100
sudo /etc/splitgate/vpn-status.sh --device=192.168.1.50 --filter=steam
sudo /etc/splitgate/vpn-status.sh --summary
sudo /etc/splitgate/vpn-status.sh --summary --device=192.168.1.50 --via=vpn
sudo /etc/splitgate/vpn-status.sh --last=200   # extend window when output is empty
```

---

### vpn-rollback.sh (deployed to /etc/splitgate/vpn-rollback.sh)

**Synopsis:** `sudo /etc/splitgate/vpn-rollback.sh`

No flags. Fully idempotent — safe to re-run.

```bash
ssh pi4 "sudo /etc/splitgate/vpn-rollback.sh"
ssh pi4 "ip route show default"  # expect: default via 192.168.1.1
bash src/deploy.sh               # re-activate after rollback
```

---

### update-vpn-routes (deployed to /etc/splitgate/update-vpn-routes)

**Synopsis:** `sudo /etc/splitgate/update-vpn-routes`

Normally called by cron daily at `CRON_UPDATE_HOUR:00` (default 5:00 AM). Can be run manually.

Behavior:
- Builds `EFFECTIVE_URL` from `RU_SUBNET_URL`; appends `&exclude[cidr4]=CIDR` for each line in
  `/etc/splitgate/ru-exclude.txt` (if present)
- Downloads RU subnet list and SHA256-compares against existing `/etc/splitgate/white-list.txt`
- If hash matches: exits 0 (no rebuild)
- If hash differs: atomically swaps file, then runs `routing.sh --no-update`
- If download fails: exits 0 (existing routes remain intact); checks for missing VPN server host
  route and rebuilds if absent (carrier-change recovery)

Logs via `logger -t "vpn-routes"` (visible in journald).

```bash
ssh pi4 "sudo /etc/splitgate/update-vpn-routes"
ssh pi4 "sudo journalctl -t vpn-routes -n 10 --no-pager"
ssh pi4 "sudo cat /etc/cron.d/vpn-routes"
```

---

### watch-routes.py (deployed to /etc/splitgate/watch-routes.py)

**Synopsis:** `sudo python3 /etc/splitgate/watch-routes.py [--src IP] [--no-dns] [--tag {VPN,ISP,both}] [--no-asn]`

Real-time iptables log enricher. Spawns `journalctl -f -k --no-pager -o short-iso` and
parses `[VPN]`/`[ISP]` lines as they arrive. Resolves destination IPs via cached rDNS lookups
(in-memory cache, 2-second timeout). Lines are enriched with ` | {org}` via a background thread
without blocking the stream — org suffix appears once the cache is warm for that IP.

Requires Python 3 (stdlib only — no pip dependencies).

| Flag | Description |
|------|-------------|
| `--src IP` | Show only entries where SRC matches this IP address |
| `--no-dns` | Skip reverse DNS lookups; show raw destination IPs |
| `--tag VPN\|ISP\|both` | Filter by routing tag (default: both) |
| `--no-asn` | Disable background ASN/org enrichment |

```bash
sudo python3 /etc/splitgate/watch-routes.py
sudo python3 /etc/splitgate/watch-routes.py --src 192.168.1.50 --tag VPN
sudo python3 /etc/splitgate/watch-routes.py --no-dns
sudo python3 /etc/splitgate/watch-routes.py --tag ISP --no-dns --no-asn
```

---

### asn-lookup.py (deployed to /etc/splitgate/asn-lookup.py)

**Synopsis:** `python3 /etc/splitgate/asn-lookup.py [IPs...]`

Shared Team Cymru bulk-whois helper. Reads IPv4 addresses from stdin (one per line) or from
positional arguments, queries `whois.cymru.com:43` in a single batched TCP session, and writes a
JSON dict `{"<ip>": {"asn": "<digits>", "org": "<name>"}}` to stdout.

Results are cached in `/tmp/vpn-asn-cache.json` (mode 0666 — readable by both root and non-root).
Cymru unreachable → returns `{}` (or partial results), exit 0. Never fatal on network errors.

```bash
printf "8.8.8.8\n1.1.1.1\n" | python3 /etc/splitgate/asn-lookup.py
python3 /etc/splitgate/asn-lookup.py 8.8.8.8
rm -f /tmp/vpn-asn-cache.json && printf "8.8.8.8\n" | python3 /etc/splitgate/asn-lookup.py
```

---

## Troubleshooting & Known Gotchas

Each entry: **Symptom → Cause → Fix**.

---

**LAN devices cannot reach the internet at all (FORWARD chain DROP)**

Symptom: All LAN device traffic is silently dropped after RPi is set as gateway. `sudo iptables -L FORWARD -n` shows default policy `DROP` with no ACCEPT rules.

Cause: Docker (if installed on the RPi) sets the FORWARD chain default policy to DROP.

Fix: Re-run `sudo /etc/splitgate/routing.sh` — Stage 7c adds `FORWARD -i eth0 ACCEPT` and `FORWARD RELATED,ESTABLISHED ACCEPT` rules.

---

**No [VPN] or [ISP] entries appear in journald**

Symptom: `journalctl -k | grep -E '\[VPN\]|\[ISP\]'` returns nothing even after LAN traffic flows through the RPi.

Cause: LOG rules must be added to the FORWARD chain **before** ACCEPT rules. LOG is non-terminating; ACCEPT terminates. If ACCEPT is first, LOG is never reached.

Fix: Re-run `sudo /etc/splitgate/routing.sh` — Stage 7b adds LOG rules before Stage 7c adds ACCEPT rules.

---

**Router web UI / app becomes inaccessible from LAN devices**

Symptom: Cannot reach `http://192.168.1.1` from LAN devices after RPi is configured as gateway.

Cause: An unconstrained MASQUERADE rule on `eth0` rewrites source IPs for all outbound traffic — including intra-LAN traffic to `192.168.1.1`. Router sees all requests from `192.168.1.254` and blocks them.

Fix: `routing.sh` Stage 7 uses `! -d LAN_SUBNET` in the eth0 MASQUERADE rule. Re-run `sudo /etc/splitgate/routing.sh` to restore the correct rule.

---

**dnsmasq fails to start or conflicts with an existing config**

Symptom: Stage 17/18 of `deploy.sh` fails; `systemctl status dnsmasq` shows a config parse error or port conflict.

Cause: If `dnsmasq` config is deployed before the package is installed, `apt-get install dnsmasq` overwrites the deployed config.

Fix: Re-run `bash src/deploy.sh` — Stage 18 always installs `dnsmasq` before Stage 19 deploys the config.

---

**Tunnel bring-up fails or `awg-quick up awg0` returns "already exists"**

Symptom: `sudo awg-quick up awg0` errors with "RTNETLINK answers: File exists".

Cause: `awg-quick up` is not idempotent. `deploy.sh` does not bring up the tunnel for this reason.

Fix:
```bash
ssh pi4 "sudo awg-quick down awg0 && sudo awg-quick up awg0"
# or:
ssh pi4 "sudo systemctl restart awg-quick@awg0"
```

---

**vpn-status.sh shows no entries even after browsing the web**

Symptom: `vpn-status.sh` output shows `(no connections matched — try --last=200 or remove filters)`.

Cause A: dnsmasq is not configured as the DNS server in your router — queries bypass the RPi.

Cause B: LAN device has not renewed its DHCP lease since the router gateway was changed.

Fix: In your router web UI: set Gateway address to `192.168.1.254` and DNS server to `192.168.1.254`. Then renew the DHCP lease on the LAN device (disconnect/reconnect Wi-Fi, or `ipconfig /renew` on Windows).

---

**DOMAIN column in vpn-status.sh shows raw IPs instead of hostnames**

Symptom: DOMAIN column shows IP addresses instead of domain names.

Cause: dnsmasq is not the DNS server for LAN devices — DNS queries bypass dnsmasq's query log.

Fix: Set your router DNS server to `192.168.1.254` (see README → Deploy → Router setup).

---

**Split-tunnel routes disappear after router reboots (NM carrier-change)**

Symptom: VPN routing breaks after the router reboots or eth0 link drops. `ip route show | wc -l` drops to ~2. `ip route get 8.8.8.8` no longer shows `dev awg0`.

Cause: When the router reboots, eth0 link drops. NetworkManager flushes all eth0 routes on the link-down event — including all ~1360 RU CIDR routes and the VPN server host route. When eth0 comes back up, NM only restores the local link route. Without the VPN server host route (`YOUR_VPN_SERVER_IP/32 via 192.168.1.1`), traffic to the VPN endpoint resolves via `awg0`, creating a routing loop.

Fix: `deploy.sh` Stage 23 deploys `/etc/NetworkManager/dispatcher.d/10-vpn-routes` — an NM dispatcher script that restores routes by running `routing.sh --no-update` when `eth0 up` is detected.

```bash
ssh pi4 "sudo journalctl -t vpn-routes -n 5 --no-pager"
# Expected: "eth0 up — restoring VPN split-tunnel routes"
```

Manual recovery if routes are currently missing:
```bash
ssh pi4 "sudo /etc/splitgate/routing.sh"
```

---

## Development Phases

| Phase | Name | Goal | Link |
|-------|------|------|------|
| 1 | Foundation & Config | AmneziaWG installed, config deployed, tunnel operational | [.planning/phases/01-foundation-config/](../.planning/phases/01-foundation-config/) |
| 2 | Routing & NAT | Split-tunnel routing active, LAN devices NATed | [.planning/phases/02-routing-nat/](../.planning/phases/02-routing-nat/) |
| 3 | Autostart, Cron & Rollback | Survives reboots, daily refresh, one-command rollback | [.planning/phases/03-autostart-cron-rollback/](../.planning/phases/03-autostart-cron-rollback/) |
| 4 | Traffic Logging & Visibility | Per-connection VPN/ISP routing decisions logged and queryable | [.planning/phases/04-traffic-logging-visibility-vpn-isp/](../.planning/phases/04-traffic-logging-visibility-vpn-isp/) |
| 5 | Custom Route Exceptions | Per-CIDR ISP-bypass exceptions on top of auto-downloaded RU list | [.planning/phases/05-custom-route-exceptions-ip/](../.planning/phases/05-custom-route-exceptions-ip/) |
| 6 | Documentation | Ops runbook: deploy, verify, rollback, add exceptions | [.planning/phases/06-documentation/](../.planning/phases/06-documentation/) |
| 7 | ASN Enrichment & Traffic Attribution | Enrich vpn-status.sh and watch-routes.py with ISP/org via Team Cymru | [.planning/phases/07-asn-enrichment-traffic-attribution/](../.planning/phases/07-asn-enrichment-traffic-attribution/) |
| 8 | RU IP List Exclusion Filter | Exclude specific CIDRs from the downloaded RU list so they route via VPN | [.planning/phases/08-ru-ip-list-exclusion-filter/](../.planning/phases/08-ru-ip-list-exclusion-filter/) |
| 10 | Splitgate Ergonomics | Consolidated RPi files under `/etc/splitgate/`, added `splitgate` dispatcher CLI, log rotation | [.planning/phases/10-splitgate-ergonomics/](../.planning/phases/10-splitgate-ergonomics/) |
| 11 | README Documentation Overhaul | Trim README to 3 quick-start sections; all technical detail in docs/REFERENCE.md | [.planning/phases/11-readme-documentation/](../.planning/phases/11-readme-documentation/) |

### Quick Tasks

| ID | Description | Commit |
|----|-------------|--------|
| 260521-jex | Add `scripts/watch-routes.py` — real-time iptables log enricher with rDNS caching | cf6bafa |
| 260523-nmr | Fix NM carrier-change route flush — add NM dispatcher (`10-vpn-routes`) + fallback rebuild in `update-vpn-routes` | 847ff31 |
