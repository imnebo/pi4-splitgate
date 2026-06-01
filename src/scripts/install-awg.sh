#!/usr/bin/env bash
# scripts/install-awg.sh
#
# RPi-side AmneziaWG installer.
# Run via: sudo bash -s < scripts/install-awg.sh
#          (or: ssh pi4 "sudo bash -s" < scripts/install-awg.sh)
#
# Decisions honored:
#   D-01 — Client-gateway install only: install AmneziaWG tools + kernel module,
#          do not run a server provisioning installer on the RPi.
#   D-02 — Debian 13 maps the Amnezia Ubuntu PPA to noble; Raspberry Pi 4 arm64
#          uses linux-headers-rpi-v8 for DKMS.
#   D-03 — Assumes RPi OS already running (Raspberry Pi OS / Debian, arm64); no OS install step.
#
# Threat mitigations:
#   T-01-01 — APT repository is configured with a scoped Signed-By keyring.
#   T-01-02 — set -euo pipefail; no read prompts; scope limited to package install + sysctl + mkdir.

set -euo pipefail

# ─── Constants ────────────────────────────────────────────────────────────────
AWG_CONFIG_DIR="/etc/amnezia/amneziawg"
SYSCTL_CONF="/etc/sysctl.d/99-vpn-gateway.conf"
APT_KEYRING="/etc/apt/keyrings/amnezia-ppa.gpg"
APT_SOURCE="/etc/apt/sources.list.d/amnezia-ppa.sources"
PPA_URI="https://ppa.launchpadcontent.net/amnezia/ppa/ubuntu"

log() {
    echo "[install-awg] $*"
}

err() {
    echo "[install-awg] ERROR: $*" >&2
}

# ─── Stage 1: Idempotency short-circuit ───────────────────────────────────────
# Check if both awg and awg-quick are already installed; if so, skip package install.
# Stages 4 (sysctl) and 5 (config dir) ALWAYS run to converge state.
AWG_ALREADY_INSTALLED=false
if command -v awg >/dev/null 2>&1 && command -v awg-quick >/dev/null 2>&1; then
    log "AmneziaWG already installed — skipping package install"
    AWG_ALREADY_INSTALLED=true
fi

if [[ "$AWG_ALREADY_INSTALLED" == false ]]; then
    log "Stage 2: Installing AmneziaWG client tools + DKMS module"

    install -d -m 0755 /etc/apt/keyrings
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates curl gpg dkms build-essential linux-headers-rpi-v8 fake-hwclock

    log "Configuring Amnezia APT repository (${PPA_URI}, suite noble for Debian 13/RPi)..."
    curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x57290828" \
        | gpg --dearmor -o "${APT_KEYRING}.tmp"
    mv "${APT_KEYRING}.tmp" "${APT_KEYRING}"
    chmod 0644 "${APT_KEYRING}"

    cat > "${APT_SOURCE}" <<EOF
Types: deb
URIs: ${PPA_URI}
Suites: noble
Components: main
Signed-By: ${APT_KEYRING}
EOF

    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y amneziawg-dkms amneziawg-tools
fi

# ─── Stage 4: Persistent IP forwarding (INST-02) ─────────────────────────────
# Apply immediately and persist via sysctl.d (survives reboot).
# /etc/sysctl.d/ is the standard drop-in location on Debian Bookworm.
# File 99-vpn-gateway.conf sorts last, winning over any conflicting entries.
log "Stage 4: Enabling persistent IP forwarding (INST-02)"
sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward=1" | tee "$SYSCTL_CONF" >/dev/null
log "Written: $SYSCTL_CONF"
sysctl --system >/dev/null
# Verify immediately
IP_FWD=$(sysctl -n net.ipv4.ip_forward)
if [[ "$IP_FWD" != "1" ]]; then
    err "net.ipv4.ip_forward is '$IP_FWD' (expected 1) after sysctl --system"
    exit 4
fi
log "IP forwarding confirmed: net.ipv4.ip_forward = $IP_FWD"

# ─── Stage 4b: Fake hardware clock for Pi without RTC ───────────────────────
# AWG handshakes can fail after reboot if the Pi clock jumps backwards before
# NTP sync. fake-hwclock preserves a recent timestamp across power cycles.
log "Stage 4b: Ensuring fake-hwclock is enabled"
if ! dpkg -l fake-hwclock 2>/dev/null | grep -q '^ii'; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y fake-hwclock
fi
systemctl enable fake-hwclock-load.service fake-hwclock-save.timer >/dev/null 2>&1 || true
fake-hwclock save || true
log "fake-hwclock enabled and current time saved"

# ─── Stage 5: Pre-create AmneziaWG config directory ──────────────────────────
# The amneziawg-tools package may not create /etc/amnezia/amneziawg/ automatically.
# See RESEARCH.md Pitfall 4: github.com/amnezia-vpn/amneziawg-tools/issues/16
# Default permissions (0755, root:root) are correct — Plan 02 deploy.sh sets 0600 on awg0.conf.
log "Stage 5: Pre-creating config directory: $AWG_CONFIG_DIR"
mkdir -p "$AWG_CONFIG_DIR"
log "Directory confirmed: $AWG_CONFIG_DIR ($(stat -c '%a %U:%G' "$AWG_CONFIG_DIR" 2>/dev/null || stat -f '%Sp %Su:%Sg' "$AWG_CONFIG_DIR" 2>/dev/null || echo 'stat unavailable'))"

# ─── Stage 6: Post-install verification ──────────────────────────────────────
log "Stage 6: Post-install verification"

# Load amneziawg kernel module (required before awg0 can come up).
# See RESEARCH.md Pitfall 1: module may be installed but not loaded.
log "Loading amneziawg kernel module..."
if ! modprobe amneziawg; then
    err "modprobe amneziawg failed — kernel module may not be installed correctly"
    exit 5
fi

# Verify module is now listed
# /sys/module/ is set synchronously on load; lsmod can lag on some RPi kernels.
if [[ ! -d /sys/module/amneziawg ]]; then
    err "amneziawg module not visible in /sys/module after modprobe"
    exit 6
fi
log "Kernel module loaded: amneziawg (verified via /sys/module)"

# Verify awg binary
AWG_PATH=$(command -v awg 2>/dev/null || true)
if [[ -z "$AWG_PATH" ]]; then
    err "awg binary not found in PATH after install (INST-01 not satisfied)"
    exit 7
fi
log "Binary: awg -> $AWG_PATH"

# Verify awg-quick binary
AWGQ_PATH=$(command -v awg-quick 2>/dev/null || true)
if [[ -z "$AWGQ_PATH" ]]; then
    err "awg-quick binary not found in PATH after install (INST-01 not satisfied)"
    exit 8
fi
log "Binary: awg-quick -> $AWGQ_PATH"

# NOTE: Tunnel bring-up is performed by deploy.sh after config deployment.
# awg-quick up is guarded there with an existing-interface check.

log "──────────────────────────────────────────────"
log "AmneziaWG install complete. Summary:"
log "  awg:           $AWG_PATH"
log "  awg-quick:     $AWGQ_PATH"
log "  sysctl:        $SYSCTL_CONF (ip_forward=1)"
log "  config dir:    $AWG_CONFIG_DIR"
log "  kernel module: amneziawg (loaded)"
log ""
log "Next: deploy awg0.conf via deploy.sh, then bring up the tunnel manually."
log "──────────────────────────────────────────────"
