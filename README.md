# RPi VPN Gateway

Raspberry Pi 4 configured as a split-tunnel VPN gateway — non-RU traffic exits via AmneziaWG VPN, Russian IP ranges exit direct via ISP, transparent to all LAN devices.

[Документация на русском](docs/README.ru.md)

---

## What This Does

The RPi acts as the default gateway for all LAN devices. All outbound traffic is routed through
the RPi, which splits it into two paths:

- **Non-RU traffic** exits through the AmneziaWG VPN tunnel (`awg0`).
- **Russian IP ranges** (downloaded daily from `russia.iplist.opencck.org`) exit direct via the
  ISP gateway (router at `192.168.1.1`).
- **Custom exceptions** (`/etc/splitgate/white-list-extended.txt`) can force additional CIDRs via ISP.
- **RU list exclusion filter** (`/etc/splitgate/ru-exclude.txt`) can exclude specific CIDRs from the downloaded RU list so they route via VPN instead of ISP.
- **VPN server host route** (`YOUR_VPN_SERVER_IP/32`) is always kept via ISP to prevent a routing loop.

LAN devices are configured to use the RPi as their gateway via a router DHCP option. They
require no individual configuration — the split is fully transparent.

```
Internet
  ↓
Router (192.168.1.1) — ISP uplink
  ↓ eth0
RPi4 (192.168.1.254) — VPN gateway
  ↓
LAN devices (default gateway = 192.168.1.254 via router DHCP)

Traffic routing:
  Non-RU → awg0 → AmneziaWG VPN (endpoint: YOUR_VPN_SERVER_IP:36348)
  RU CIDRs + exceptions → eth0 → ISP direct (via 192.168.1.1)
```

Key environment variables (from `/etc/splitgate/vpn-gateway.env` on the RPi, sourced from `.env` in this repo):

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

## Prerequisites

### SSH alias

`deploy.sh` connects to the RPi via the SSH alias `pi4`. Add this to `~/.ssh/config` on your
Mac:

```
Host pi4
    HostName 192.168.1.254
    User ar
    IdentityFile ~/.ssh/id_ed25519
```

Verify: `ssh pi4 "echo ok"` — must succeed without a password prompt. `deploy.sh` uses
`BatchMode=yes` which blocks password fallback.

### Keys and .env.secrets

VPN private/public/preshared keys are stored in `.env.secrets` (gitignored — never committed).

```bash
cp .env.secrets.example .env.secrets
# Edit .env.secrets and fill in the three keys:
#   AWG_PRIVATE_KEY=<44-char base64>
#   AWG_PUBLIC_KEY=<44-char base64>
#   AWG_PRESHARED_KEY=<44-char base64>
```

Each key must be a valid 44-character base64 string (43 alphanumeric chars + one `=` pad).
`deploy.sh` validates all three before any remote operation.

`deploy.sh` renders `awg0.conf` from `amnezia.key.template.txt` by substituting the placeholders
`{{PrivateKey}}`, `{{PublicKey}}`, and `{{PresharedKey}}` with the values from `.env.secrets`
via a sed pipeline. The rendered config is written to a mode-600 temp file and SCPed to
`/etc/amnezia/amneziawg/awg0.conf` (mode 600, root:root) on the RPi.

### Router DHCP

After the RPi is fully deployed and verified, configure your router to advertise it as the
LAN gateway:

1. Open your router web UI: `http://192.168.1.1`
2. Home network → Segments → Default → IP parameters
3. Set **Gateway address** to `192.168.1.254`
4. Save

After saving, LAN devices will use the RPi as their gateway on next DHCP lease renewal.
To apply immediately: disconnect/reconnect Wi-Fi, or run `ipconfig /renew` on Windows.

**DNS for domain resolution:** To enable domain name display in `vpn-status.sh`, also set
the DNS server in your router:

1. Home network → Segments → Default → DNS server
2. Set to `192.168.1.254` (dnsmasq on the RPi)
3. Save

Without this step, the DOMAIN column in `vpn-status.sh` will show raw IPs.

**Rollback:** Clear the Gateway address field in your router (set it back to empty or `192.168.1.1`).

---

## Deploy

`deploy.sh` is the single deploy orchestrator. It runs 27 stages in sequence from your Mac,
connecting to the RPi via SSH. You never run individual scripts manually during initial setup.

### Stage groups

| Group | Stages | What happens |
|-------|--------|--------------|
| Preflight | 1–3 | Check required local files, source `.env` + `.env.secrets`, validate keys, verify SSH connectivity |
| AmneziaWG install | 4 | Stream `src/scripts/install-awg.sh` over SSH to the RPi; DKMS build may take 10–30 min |
| Splitgate namespace | 5 | Create `/etc/splitgate/` and `/etc/splitgate/logs/` on the RPi (must precede all file deploys into `/etc/splitgate/`) |
| Config deploy | 6–10 | Render and deploy `awg0.conf` (mode 600), deploy `vpn-gateway.env` (mode 644), post-deploy file checks |
| Routing deploy | 11–12 | SCP `routing.sh` to `/etc/splitgate/routing.sh`, activate split-tunnel routing (unless `--no-run`) |
| Autostart | 13–14 | Deploy `vpn-routing.service`, reload systemd, enable `awg-quick@awg0` + `vpn-routing.service` at boot |
| Cron + rollback | 15–17 | Deploy `update-vpn-routes`, write `/etc/cron.d/vpn-routes` (daily at `CRON_UPDATE_HOUR:00`), deploy `vpn-rollback.sh` |
| Logging | 18–21 | Install dnsmasq (before config), deploy `dnsmasq.conf`, deploy `vpn-status.sh`, deploy `watch-routes.py` |
| Exceptions + NM | 22–23 | Conditionally deploy `white-list-extended.txt` if present; conditionally deploy `ru-exclude.txt` if present; deploy NM dispatcher `10-vpn-routes` |
| ASN helper | 24 | Deploy `asn-lookup.py` to `/etc/splitgate/asn-lookup.py` (Team Cymru bulk-whois helper for ORG enrichment) |
| Final activation | 25 | Re-run `routing.sh` to apply all iptables LOG rules and exception routes |
| Splitgate artifacts | 26–27 | Deploy `splitgate` dispatcher to `/usr/local/bin/splitgate` (chmod +x); deploy `logrotate-vpn-gateway` to `/etc/logrotate.d/vpn-gateway` (mode 644) |

### Run commands

Full deploy (deploy all files + activate routing):

```bash
bash src/deploy.sh
```

Deploy without activating routing (use for first-time deploy before the tunnel is brought up,
or when testing config changes without changing active routes):

```bash
bash src/deploy.sh --no-run
```

If `--no-run` was used, activate routing manually later:

```bash
ssh pi4 "sudo /etc/splitgate/routing.sh"
```

### AmneziaWG installer note

`src/deploy.sh` Stage 4 streams `src/scripts/install-awg.sh` over SSH and runs it on the RPi as root.
You do not invoke `install-awg.sh` directly — it is an internal RPi-side installer called by
the deploy orchestrator only.

### Bring up the tunnel (manual step)

Tunnel bring-up is **not automated** by `deploy.sh`. `awg-quick up` is not idempotent — if the
interface already exists, it errors. Run manually after deploy:

```bash
# Bring up the VPN tunnel
ssh pi4 "sudo awg-quick up awg0"

# Verify peer handshake
ssh pi4 "sudo awg show"
```

If the tunnel is already up, bring it down first:

```bash
ssh pi4 "sudo awg-quick down awg0 && sudo awg-quick up awg0"
```

---

## Verify Routing

Run these checks on the RPi via SSH. All commands require `sudo` or run as root.

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

After generating some LAN traffic, run:

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

If the DOMAIN column shows raw IPs, set router DNS to `192.168.1.254` (see Prerequisites).

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
Each line is enriched with ` | {org}` via a background thread that queries `/etc/splitgate/asn-lookup.py`
without blocking the stream — the org suffix appears on subsequent re-prints of the same IP once
the cache is warm. Press Ctrl+C to stop.

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

Use this workflow when traffic that should exit via ISP is being routed via VPN. Common case:
a service (game server, CDN, streaming platform) whose IP range is not in the RU CIDR list.

### Discovery to deploy walkthrough

**Step 1: Identify traffic exiting via VPN that should use ISP**

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=vpn"
```

Look for domains or IPs that you know should route via ISP. Note their destination IPs.

**Step 2: Resolve the IP to a CIDR**

Use `whois` or `ipinfo.io` to find the network block that owns the IP:

```bash
whois <destination-ip>
# Look for "route:" or "CIDR:" field — e.g. 23.55.0.0/16
```

Alternatively, open `https://ipinfo.io/<destination-ip>` in a browser.

**Step 3: Create the exception file**

```bash
cp src/configs/white-list-extended.txt.example src/configs/white-list-extended.txt
```

Edit `src/configs/white-list-extended.txt` and add your CIDRs (one per line):

```
# Format rules:
# - One CIDR per line (e.g. 23.55.0.0/16)
# - Whole-line comments only (lines starting with #)
# - NO inline comments after a CIDR — ip route add will reject the line
# - No labels, no extra whitespace after the CIDR
23.55.0.0/16
95.181.176.0/22
```

Note: `src/configs/white-list-extended.txt` is gitignored and will not be committed. The
`.example` file (which is committed) documents the format.

**Step 4: Deploy**

```bash
bash src/deploy.sh
```

Stage 22 SCPs `src/configs/white-list-extended.txt` to `/etc/splitgate/white-list-extended.txt` on the RPi.
Stage 25 re-runs `routing.sh`, which loads exception routes in Stage 5b.

**Step 5: Verify**

```bash
ssh pi4 "ip route get <your-exception-ip>"
# Expected output contains: via 192.168.1.1
```

Then confirm in `vpn-status.sh`:

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=isp"
# Your exception traffic should now appear here
```

---

## RU IP List Exclusion Filter

Use this workflow when a CIDR range is incorrectly included in the RU IP list (e.g. a Google
or Cloudflare range that iplist marks as RU) and you want it to route through the VPN.

Unlike custom exceptions (`/etc/splitgate/white-list-extended.txt`) which add ISP-bypass routes on top of
the downloaded list, the exclusion filter removes CIDRs from the downloaded list at the source —
they never appear in `/etc/splitgate/white-list.txt` and therefore follow the default route (VPN).

### How it works

When `/etc/splitgate/ru-exclude.txt` is present on the RPi, `update-vpn-routes` appends
`&exclude[cidr4]=CIDR` query parameters to `RU_SUBNET_URL` before calling curl. The iplist
service filters those ranges server-side. The downloaded file never contains the excluded CIDRs.

If `/etc/splitgate/ru-exclude.txt` is absent or empty, the download URL is unchanged — behavior is
identical to before Phase 8.

### Setup

**Step 1: Identify CIDRs to exclude**

```bash
ssh pi4 "sudo /etc/splitgate/vpn-status.sh --via=isp"
```

Look for traffic that should be routed via VPN but is exiting via ISP. Resolve the destination IP
to its network block using `whois` or `ipinfo.io`.

**Step 2: Create the exclusion file**

```bash
cp src/configs/ru-exclude.txt.example src/configs/ru-exclude.txt
```

Edit `src/configs/ru-exclude.txt` and add your CIDRs (one per line):

```
# Exclude Google ranges incorrectly listed as RU
142.250.0.0/16
142.251.0.0/16
```

Note: `src/configs/ru-exclude.txt` is gitignored and will not be committed. The `.example` file
documents the format.

**Step 3: Deploy**

```bash
bash src/deploy.sh
```

Stage 22b SCPs `src/configs/ru-exclude.txt` to `/etc/splitgate/ru-exclude.txt` on the RPi.

**Step 4: Trigger a route rebuild**

```bash
ssh pi4 "sudo /etc/splitgate/update-vpn-routes"
```

Because the exclusion changes the effective download URL, the new list will have a different SHA256
from the existing `/etc/splitgate/white-list.txt`, triggering an automatic route rebuild. Verify via:

```bash
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
- Restores the default route via `KEENETIC_GW` (`192.168.1.1`)
- Removes `/usr/local/bin/splitgate` (D-18)
- Removes `/etc/splitgate/` tree entirely — scripts, data files, env (D-18)

### What rollback preserves

- `/etc/amnezia/amneziawg/awg0.conf` (mode 600) — VPN config kept for re-activation
- AmneziaWG packages — not uninstalled

Note: `/etc/dnsmasq.conf` remains on disk (system file, not removed). dnsmasq is stopped.

### After rollback

Revert the router DHCP gateway back to `192.168.1.1`:

1. Open your router web UI: `http://192.168.1.1`
2. Home network → Segments → Default → IP parameters
3. Clear the Gateway address field (or set to `192.168.1.1`)
4. Save

### Re-activate after rollback

```bash
bash src/deploy.sh
```

Deploy re-installs everything. The existing `awg0.conf` on the RPi is overwritten with a
freshly rendered copy from your template + `.env.secrets`.

---

## splitgate CLI

`splitgate` is the ergonomic dispatcher installed at `/usr/local/bin/splitgate` that runs the five core tools without typing their full paths. Deployed by `deploy.sh` Stage 26.

| Command | Runs |
|---------|------|
| `splitgate status [args...]` | `sudo /etc/splitgate/vpn-status.sh [args...]` |
| `splitgate watch [args...]` | `sudo python3 /etc/splitgate/watch-routes.py [args...]` |
| `splitgate rollback [args...]` | `sudo /etc/splitgate/vpn-rollback.sh [args...]` |
| `splitgate routing [args...]` | `sudo /etc/splitgate/routing.sh [args...]` |
| `splitgate update [args...]` | `sudo /etc/splitgate/update-vpn-routes [args...]` |

Running `splitgate` with no arguments (or an unknown subcommand) prints `Usage: splitgate {status|watch|rollback|routing|update} [args...]` and exits 1.

**Examples:**

```bash
# Check routing status
ssh pi4 "splitgate status"
ssh pi4 "splitgate status --via=vpn --last=100"

# Watch real-time traffic
ssh pi4 "splitgate watch"

# Run rollback
ssh pi4 "splitgate rollback"

# Rebuild routes
ssh pi4 "splitgate routing --no-update"

# Trigger manual route update
ssh pi4 "splitgate update"
```

---

## Filesystem Layout on the RPi

After Phase 10 deploy, the RPi filesystem is organized as follows:

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

Files that intentionally stay at system locations (required by their consuming daemon):

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

**Flags:**

| Flag | Description |
|------|-------------|
| `--no-run` | Deploy all files but skip `routing.sh` activation. Use for first-time deploys before the tunnel is up, or when testing config changes without activating routes. |

**Examples:**

```bash
# Full deploy + activate routing (normal usage)
bash src/deploy.sh

# Deploy only — activate routing manually later
bash src/deploy.sh --no-run

# Activate routing after --no-run deploy
ssh pi4 "sudo /etc/splitgate/routing.sh"
```

---

### src/scripts/routing.sh (deployed to /etc/splitgate/routing.sh)

**Synopsis:** `sudo /etc/splitgate/routing.sh [--no-update]`

Flush-and-rebuild split-tunnel routing. Idempotent — safe to re-run at any time.

On each run: downloads RU CIDRs from `RU_SUBNET_URL` → flushes existing VPN routes →
adds VPN server host route → adds RU CIDR routes via `KEENETIC_GW` → loads
`/etc/splitgate/white-list-extended.txt` (if present) → sets default route via `awg0` → configures
MASQUERADE and iptables LOG rules → saves via `iptables-save`.

Sources `/etc/splitgate/vpn-gateway.env` for all variables.

**Flags:**

| Flag | Description |
|------|-------------|
| `--no-update` | Skip downloading fresh RU subnets; use existing `/etc/splitgate/white-list.txt`. Safe when the subnet file is current. Used by `update-vpn-routes` after an atomic file swap to avoid double-download. |

**Examples:**

```bash
# Full run with fresh RU subnet download
ssh pi4 "sudo /etc/splitgate/routing.sh"

# Rebuild routes using existing subnet file (no download)
ssh pi4 "sudo /etc/splitgate/routing.sh --no-update"

# Check result
ssh pi4 "ip route show default"     # expect: default dev awg0
ssh pi4 "ip route get 8.8.8.8"      # expect: dev awg0
ssh pi4 "ip route get 77.88.8.8"    # expect: via 192.168.1.1
```

---

### src/scripts/vpn-status.sh (deployed to /etc/splitgate/vpn-status.sh)

**Synopsis:** `sudo /etc/splitgate/vpn-status.sh [--last=N] [--filter=STRING] [--device=IP] [--via=vpn|isp] [--summary]`

Reads journald `[VPN]`/`[ISP]` LOG entries, correlates with dnsmasq query log for domain
resolution, falls back to rDNS (`host`). Output columns: `TIMESTAMP SRC-IP DST-IP DOMAIN ORG PATH`.

The `ORG` column shows `{org} (AS{asn})` via Team Cymru bulk-whois (e.g. `GOOGLE, US (AS15169)`),
or `-` when the IP is unresolvable or Cymru is unreachable. All unique DST IPs are looked up in a
single batched subprocess call. Results are cached in `/tmp/vpn-asn-cache.json` (mode 0666,
shared between root and non-root callers).

Must run as `sudo`.

**Flags:**

| Flag | Description |
|------|-------------|
| `--last=N` | Show last N journald kernel entries (default: 50) |
| `--filter=STRING` | Case-insensitive partial match on the DOMAIN column |
| `--device=IP` | Filter by source LAN device IP (SRC field) |
| `--via=vpn\|isp` | Show only VPN-routed or ISP-routed connections; composes with other filters |
| `--summary` | Print top-20 ORG aggregate table (ORG \| VPN_COUNT \| ISP_COUNT \| TOTAL) instead of per-row table; composes with `--filter`, `--device`, `--via` |

All flags compose freely.

**Examples:**

```bash
# Show last 50 connections with ORG column (default)
sudo /etc/splitgate/vpn-status.sh

# Show last 100 VPN-routed connections
sudo /etc/splitgate/vpn-status.sh --via=vpn --last=100

# Filter by device + domain keyword
sudo /etc/splitgate/vpn-status.sh --device=192.168.1.50 --filter=steam

# Show only ISP-routed connections
sudo /etc/splitgate/vpn-status.sh --via=isp

# Top-20 orgs by total connection count
sudo /etc/splitgate/vpn-status.sh --summary

# Top orgs for a specific device, VPN-only
sudo /etc/splitgate/vpn-status.sh --summary --device=192.168.1.50 --via=vpn

# Extend window when output is empty
sudo /etc/splitgate/vpn-status.sh --last=200
```

---

### src/scripts/vpn-rollback.sh (deployed to /etc/splitgate/vpn-rollback.sh)

**Synopsis:** `sudo /etc/splitgate/vpn-rollback.sh`

No flags. Fully idempotent — safe to re-run.

**Examples:**

```bash
# Run rollback
ssh pi4 "sudo /etc/splitgate/vpn-rollback.sh"

# Verify default route restored
ssh pi4 "ip route show default"
# Expected: default via 192.168.1.1

# Re-activate after rollback
bash src/deploy.sh
```

---

### src/scripts/update-vpn-routes (deployed to /etc/splitgate/update-vpn-routes)

**Synopsis:** `sudo /etc/splitgate/update-vpn-routes`

Normally called by cron daily at `CRON_UPDATE_HOUR:00` (default 5:00 AM). Can be run manually
for a one-off update.

Behavior:
- Builds `EFFECTIVE_URL` from `RU_SUBNET_URL`; if `/etc/splitgate/ru-exclude.txt` exists, appends
  `&exclude[cidr4]=CIDR` for each non-comment, non-blank line (see Exclusion Filter below)
- Downloads RU subnet list to a temp file using `EFFECTIVE_URL`
- SHA256-compares against existing `/etc/splitgate/white-list.txt`
- If hash matches: exits 0 (no rebuild, no disruption)
- If hash differs: atomically swaps the file, then runs `/etc/splitgate/routing.sh --no-update`
- If download fails: exits 0 (no cron failure mail; existing routes remain intact)
- On download failure, also checks whether the VPN server host route is missing (carrier-change
  recovery) — if missing, rebuilds routes from the existing subnet file

Logs via `logger -t "vpn-routes"` (visible in journald).

**Exclusion Filter (`/etc/splitgate/ru-exclude.txt`):**

To route specific CIDR ranges through the VPN instead of the ISP (i.e., exclude them from the
RU direct-route list), create `/etc/splitgate/ru-exclude.txt` on the RPi with one CIDR per line:

```text
# Lines starting with # are ignored
# Blank lines are ignored
1.2.3.0/24
5.6.7.0/22
```

When this file exists and has valid entries, the script appends `&exclude[cidr4]=CIDR` query
parameters to the download URL so the upstream server omits those CIDRs from the response.
If the file is absent or empty, behavior is identical to the default (no exclusions).

Number of excluded CIDRs is logged: `journalctl -t vpn-routes | grep "Excluding"`.

**Examples:**

```bash
# Manual one-off run
ssh pi4 "sudo /etc/splitgate/update-vpn-routes"

# Check result
ssh pi4 "sudo journalctl -t vpn-routes -n 10 --no-pager"

# Check cron schedule
ssh pi4 "sudo cat /etc/cron.d/vpn-routes"
# Expected: 0 5 * * * root /etc/splitgate/update-vpn-routes >> /var/log/vpn-routes.log 2>&1
```

---

### src/scripts/watch-routes.py (deployed to /etc/splitgate/watch-routes.py)

**Synopsis:** `sudo python3 /etc/splitgate/watch-routes.py [--src IP] [--no-dns] [--tag {VPN,ISP,both}] [--no-asn]`

Real-time iptables log enricher. Spawns `journalctl -f -k --no-pager -o short-iso` and
parses `[VPN]`/`[ISP]` lines as they arrive. Resolves destination IPs via cached rDNS lookups
(in-memory cache, 2-second timeout per lookup). Each line is also enriched with ` | {org}` via a
background thread that calls `/etc/splitgate/asn-lookup.py` without blocking the stream — lines print
immediately; the org suffix appears once the cache is warm for that IP.

Requires Python 3 (stdlib only — no pip dependencies).

**Flags:**

| Flag | Description |
|------|-------------|
| `--src IP` | Show only entries where SRC matches this IP address |
| `--no-dns` | Skip reverse DNS lookups; show raw destination IPs |
| `--tag VPN\|ISP\|both` | Filter by routing tag (default: both) |
| `--no-asn` | Disable background ASN/org enrichment; lines print without ` \| {org}` suffix |

**Examples:**

```bash
# Real-time view of all connections with org enrichment
sudo python3 /etc/splitgate/watch-routes.py

# Watch one device's VPN traffic only
sudo python3 /etc/splitgate/watch-routes.py --src 192.168.1.50 --tag VPN

# Skip DNS lookups for faster output (useful during high traffic)
sudo python3 /etc/splitgate/watch-routes.py --no-dns

# Watch all ISP-routed traffic without DNS or ASN lookup
sudo python3 /etc/splitgate/watch-routes.py --tag ISP --no-dns --no-asn
```

---

### src/scripts/asn-lookup.py (deployed to /etc/splitgate/asn-lookup.py)

**Synopsis:** `python3 /etc/splitgate/asn-lookup.py [IPs...]`

Shared Team Cymru bulk-whois helper. Reads IPv4 addresses from stdin (one per line) or from
positional arguments, queries `whois.cymru.com:43` in a single batched TCP session, and writes a
JSON dict `{"<ip>": {"asn": "<digits>", "org": "<name>"}}` to stdout.

Results are cached in `/tmp/vpn-asn-cache.json` (mode 0666 — readable by both root and
non-root). Cache is read at startup; only uncached IPs are queried. Cymru unreachable → returns
`{}` (or partial results), exit 0. Never fatal on network errors.

Stdlib only — no pip dependencies.

**Examples:**

```bash
# Look up two IPs
printf "8.8.8.8\n1.1.1.1\n" | python3 /etc/splitgate/asn-lookup.py

# Direct CLI mode
python3 /etc/splitgate/asn-lookup.py 8.8.8.8

# Force cache refresh (delete cache file first)
rm -f /tmp/vpn-asn-cache.json
printf "8.8.8.8\n" | python3 /etc/splitgate/asn-lookup.py
```

---

## Troubleshooting & Known Gotchas

Each entry follows the pattern: **Symptom → Cause → Fix**.

---

**LAN devices cannot reach the internet at all (FORWARD chain DROP)**

Symptom: All LAN device traffic is silently dropped after RPi is set as gateway. `ssh pi4 "sudo iptables -L FORWARD -n"` shows default policy `DROP` with no ACCEPT rules.

Cause: Docker (if installed on the RPi) sets the FORWARD chain default policy to DROP. Without explicit ACCEPT rules, no LAN traffic passes through the RPi.

Fix: Re-run `sudo /etc/splitgate/routing.sh` — Stage 7c adds `FORWARD -i eth0 ACCEPT` and `FORWARD RELATED,ESTABLISHED ACCEPT` rules. These are always re-applied by routing.sh on every run.

---

**No [VPN] or [ISP] entries appear in journald**

Symptom: `journalctl -k | grep -E '\[VPN\]|\[ISP\]'` returns nothing even after LAN traffic flows through the RPi.

Cause: LOG rules must be added to the FORWARD chain **before** ACCEPT rules. LOG is non-terminating (continues to the next rule); ACCEPT terminates. If ACCEPT is first, the LOG rule is never reached and no entries are written to journald.

Fix: Re-run `sudo /etc/splitgate/routing.sh` — Stage 7b adds LOG rules; Stage 7c adds ACCEPT rules in the correct order. Every run starts with a flush, so rule order is always correct after re-run.

---

**Router web UI / app becomes inaccessible from LAN devices**

Symptom: Cannot reach `http://192.168.1.1` from LAN devices after RPi is configured as gateway.

Cause: An unconstrained MASQUERADE rule on `eth0` rewrites source IPs for all outbound traffic — including intra-LAN traffic to `192.168.1.1`. The router sees all requests as coming from `192.168.1.254` and blocks them.

Fix: `routing.sh` Stage 7 uses `! -d LAN_SUBNET` in the eth0 MASQUERADE rule, which excludes intra-LAN traffic from MASQUERADE. Re-run `sudo /etc/splitgate/routing.sh` to restore the correct rule.

---

**dnsmasq fails to start or conflicts with an existing config**

Symptom: Stage 17/18 of `deploy.sh` fails; `systemctl status dnsmasq` shows a config parse error or port conflict.

Cause: If `dnsmasq` config is deployed before the `dnsmasq` package is installed, `apt-get install dnsmasq` will overwrite the deployed config with the package default, or prompt interactively.

Fix: Re-run `bash src/deploy.sh` — Stage 18 always installs `dnsmasq` before Stage 19 deploys the config. The install uses `DEBIAN_FRONTEND=noninteractive` to prevent interactive prompts.

---

**Tunnel bring-up fails or `awg-quick up awg0` returns "already exists"**

Symptom: `sudo awg-quick up awg0` errors with "RTNETLINK answers: File exists" or similar; or the interface is in an unknown state.

Cause: `awg-quick up` is not idempotent. `deploy.sh` intentionally does not bring up the tunnel for this reason (see deploy section).

Fix: Bring the interface down first, then bring it back up:

```bash
ssh pi4 "sudo awg-quick down awg0 && sudo awg-quick up awg0"
```

Or restart via systemd:

```bash
ssh pi4 "sudo systemctl restart awg-quick@awg0"
```

---

**vpn-status.sh shows no entries even after browsing the web**

Symptom: `vpn-status.sh` output shows `(no connections matched — try --last=200 or remove filters)` even though LAN devices are generating traffic.

Cause (A): dnsmasq is not configured as the DNS server in your router — queries bypass the RPi entirely, so dnsmasq has no log to correlate. (This does not directly suppress the `[VPN]`/`[ISP]` entries, but check this first.)

Cause (B): The LAN device has not renewed its DHCP lease since the router gateway was changed — it is still using its old gateway (e.g. `192.168.1.1` directly) and traffic does not pass through the RPi.

Fix: In your router web UI: navigate to DHCP/LAN settings → set Gateway address to `192.168.1.254`. Then renew the DHCP lease on the LAN device (disconnect/reconnect Wi-Fi, or `ipconfig /renew` on Windows). Also set DNS server to `192.168.1.254` in the same settings page.

---

**DOMAIN column in vpn-status.sh shows raw IPs instead of hostnames**

Symptom: The DOMAIN column in `vpn-status.sh` output shows IP addresses instead of domain names.

Cause: dnsmasq is not the DNS server for LAN devices. DNS queries go directly to an upstream resolver, bypassing dnsmasq's query log. Without dnsmasq log entries, `vpn-status.sh` cannot correlate DST IPs to domain names; rDNS fallback also fails for CDN IPs (no PTR records).

Fix: Set your router DNS server to `192.168.1.254` (see Prerequisites → Router DHCP). After renewal, LAN DNS queries flow through dnsmasq, which logs them for correlation.

---

**Split-tunnel routes disappear after router reboots (NM carrier-change)**

Symptom: VPN routing breaks after the router reboots or the eth0 link goes down and comes back up. `ssh pi4 "ip route show | wc -l"` drops to approximately 2 (only local routes). `ip route get 8.8.8.8` no longer shows `dev awg0`.

Cause: When the router reboots, the eth0 link drops (carrier-change event). NetworkManager (NM) flushes all eth0 routes on the link-down event — including the ~1360 RU CIDR routes and the VPN server host route added by `routing.sh`. When eth0 comes back up, only the local link route is restored by NM. Without the VPN server host route (`YOUR_VPN_SERVER_IP/32 via 192.168.1.1`), `ip route get YOUR_VPN_SERVER_IP` resolves via `awg0` (policy table 51820), creating a routing loop. No VPN connection → no internet → the daily cron download also fails → the system cannot self-heal without intervention.

Fix: `deploy.sh` Stage 23 deploys `/etc/NetworkManager/dispatcher.d/10-vpn-routes` — an NM dispatcher script that automatically restores routes by running `routing.sh --no-update` in the background when `eth0 up` is detected.

Verify the dispatcher is working:

```bash
ssh pi4 "sudo journalctl -t vpn-routes -n 5 --no-pager"
# Expected: "eth0 up — restoring VPN split-tunnel routes"
```

Fallback: `update-vpn-routes` also checks for a missing VPN server host route on download failure and triggers a rebuild. Both mechanisms are deployed by `bash src/deploy.sh`.

If routes are currently missing and need manual recovery:

```bash
ssh pi4 "sudo /etc/splitgate/routing.sh"
```

See quick task `260523-nmr` in the Development Phases section for the full incident timeline.

---

## Development Phases

| Phase | Name | Goal | Link |
|-------|------|------|------|
| 1 | Foundation & Config | AmneziaWG installed, config deployed, tunnel operational | [.planning/phases/01-foundation-config/](.planning/phases/01-foundation-config/) |
| 2 | Routing & NAT | Split-tunnel routing active, LAN devices NATed | [.planning/phases/02-routing-nat/](.planning/phases/02-routing-nat/) |
| 3 | Autostart, Cron & Rollback | Survives reboots, daily refresh, one-command rollback | [.planning/phases/03-autostart-cron-rollback/](.planning/phases/03-autostart-cron-rollback/) |
| 4 | Traffic Logging & Visibility | Per-connection VPN/ISP routing decisions logged and queryable | [.planning/phases/04-traffic-logging-visibility-vpn-isp/](.planning/phases/04-traffic-logging-visibility-vpn-isp/) |
| 5 | Custom Route Exceptions | Per-CIDR ISP-bypass exceptions on top of auto-downloaded RU list | [.planning/phases/05-custom-route-exceptions-ip/](.planning/phases/05-custom-route-exceptions-ip/) |
| 6 | Documentation | Ops runbook: deploy, verify, rollback, add exceptions | [.planning/phases/06-documentation/](.planning/phases/06-documentation/) |
| 7 | ASN Enrichment & Traffic Attribution | Enrich vpn-status.sh and watch-routes.py with ISP/org attribution via Team Cymru | [.planning/phases/07-asn-enrichment-traffic-attribution/](.planning/phases/07-asn-enrichment-traffic-attribution/) |
| 8 | RU IP List Exclusion Filter | Exclude specific CIDRs from the downloaded RU list so they route via VPN | [.planning/phases/08-ru-ip-list-exclusion-filter/](.planning/phases/08-ru-ip-list-exclusion-filter/) |
| 10 | Splitgate Ergonomics | Consolidated all RPi files under `/etc/splitgate/`, added `splitgate` dispatcher CLI, added log rotation for `/etc/splitgate/logs/vpn-gateway.log` | [.planning/phases/10-splitgate-ergonomics/](.planning/phases/10-splitgate-ergonomics/) |

### Quick Tasks

Out-of-band work completed alongside the main phases:

| ID | Description | Commit |
|----|-------------|--------|
| 260521-jex | Add `scripts/watch-routes.py` — real-time iptables log enricher with rDNS caching | cf6bafa |
| 260523-nmr | Fix NM carrier-change route flush — add NM dispatcher (`10-vpn-routes`) to restore split-tunnel routes on eth0 up; add fallback rebuild in `update-vpn-routes` on missing VPN server host route | 847ff31 |
