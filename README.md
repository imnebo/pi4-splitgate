# RPi VPN Gateway

Raspberry Pi 4 configured as a split-tunnel VPN gateway — non-RU traffic exits via AmneziaWG VPN, Russian IP ranges exit direct via ISP, transparent to all LAN devices.

[Документация на русском](docs/README.ru.md) | [Technical Reference](docs/REFERENCE.md)

---

## What This Does

The RPi acts as the default gateway for all LAN devices. Traffic is split into two paths:

- **Non-RU traffic** exits through the AmneziaWG VPN tunnel (`awg0`)
- **Russian IP ranges** (updated daily from `russia.iplist.opencck.org`) exit direct via ISP
- **LAN devices** require no individual configuration — the split is fully transparent

```
Internet
  ↓
Router (192.168.1.1) — ISP uplink
  ↓ eth0
RPi4 (192.168.1.254) — VPN gateway
  ↓
LAN devices (default gateway = 192.168.1.254 via router DHCP)

Non-RU → awg0 → AmneziaWG VPN (endpoint: YOUR_VPN_SERVER_IP:36348)
RU CIDRs → eth0 → ISP direct (via 192.168.1.1)
```

---

## Deploy

### 1. SSH alias

Add to `~/.ssh/config` on your Mac:

```
Host pi4
    HostName 192.168.1.254
    User ar
    IdentityFile ~/.ssh/id_ed25519
```

Verify: `ssh pi4 "echo ok"` — must succeed without a password prompt.

### 2. VPN keys

```bash
cp .env.secrets.example .env.secrets
# Fill in AWG_PRIVATE_KEY, AWG_PUBLIC_KEY, AWG_PRESHARED_KEY (44-char base64 each)
```

### 3. Router setup (Keenetic)

**Gateway** — set RPi as the LAN default gateway:

1. `http://192.168.1.1` → Home network → Segments → Default → IP parameters
2. Set **Gateway address** to `192.168.1.254` → Save
3. LAN devices apply on next DHCP renewal (or disconnect/reconnect Wi-Fi)

**DNS** — required for domain names in `splitgate status`:

1. Home network → Segments → Default → DNS server → set to `192.168.1.254` → Save

**Rollback**: clear Gateway address in router (set back to `192.168.1.1`).

### 4. Run deploy

```bash
bash src/deploy.sh            # deploy all files + activate routing
bash src/deploy.sh --no-run   # deploy files only (use before tunnel is up)
```

### 5. Bring up the tunnel

```bash
ssh pi4 "sudo awg-quick up awg0"   # bring up VPN tunnel (manual — not idempotent)
ssh pi4 "sudo awg show"            # verify peer handshake
```

---

## Commands

Run on RPi via SSH. `splitgate` is the dispatcher CLI at `/usr/local/bin/splitgate`.

| Command | What it does |
|---------|-------------|
| `splitgate status` | Recent connections with VPN/ISP routing and org info |
| `splitgate watch` | Real-time traffic stream |
| `splitgate rollback` | Undo VPN gateway entirely |
| `splitgate routing` | Rebuild split-tunnel routes |
| `splitgate update` | Refresh RU IP list now |

```bash
# Show recent connections
ssh pi4 "splitgate status"
ssh pi4 "splitgate status --via=vpn --last=100"
ssh pi4 "splitgate status --summary"                        # top-20 orgs by connection count

# Watch real-time traffic
ssh pi4 "splitgate watch"
ssh pi4 "splitgate watch --src 192.168.1.x --tag VPN"

# Rollback
ssh pi4 "splitgate rollback"
```

[Full CLI reference, verify routing, troubleshooting →](docs/REFERENCE.md)
