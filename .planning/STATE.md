---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Phase 8 complete — all plans done
stopped_at: Phase 8 complete — 3/3 plans executed
last_updated: "2026-05-27T15:45:00.000Z"
progress:
  total_phases: 10
  completed_phases: 8
  total_plans: 20
  completed_plans: 20
  percent: 80
---

# State: RPi VPN Gateway

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-18)

**Core value:** Non-RU traffic exits through AmneziaWG VPN; RU traffic exits direct via ISP — transparent to LAN devices, survives reboots, fully reversible.
**Current focus:** Phase 6 — documentation

## Current Phase

**Phase 8: RU IP List Exclusion Filter — COMPLETE ✓**

EFFECTIVE_URL in update-vpn-routes, Stage 21b in deploy.sh, example file + docs complete 2026-05-27.

## Phase Progress

| Phase | Status | Plans | Progress |
|-------|--------|-------|----------|
| 1 — Foundation & Config | ✓ Complete | 2/2 done | 100% |
| 2 — Routing & NAT | ✓ Complete | 2/2 done | 100% |
| 3 — Autostart, Cron & Rollback | ✓ Complete | 3/3 done | 100% |
| 4 — Traffic Logging & Visibility | ✓ Complete | 3/3 done | 100% |
| 5 — Custom Route Exceptions | ✓ Complete | 2/2 done | 100% |
| 6 — Documentation | ◆ Planned | 0/2 | 0% |
| 7 — ASN Enrichment & Traffic Attribution | ✓ Complete | 3/3 done | 100% |
| 8 — RU IP List Exclusion Filter | ✓ Complete | 3/3 done | 100% |

## Requirements

- v1 total: 20
- Completed: 20 (INST-01, INST-02 — by install-awg.sh; CONF-01, CONF-02 — by deploy.sh; ROUT-01–04, NAT-01–03 — by scripts/routing.sh; AUTO-01–03, ROLL-01–02, VRFY-01–04 — by Phase 3)
- In progress: 0

## Decisions

- D-01: bivlked/RomikB AmneziaWG installer used as primary install path for RPi arm64 (auto-detects +rpt kernel suffix)
- D-02: AWG_DEB_URL env var fallback documented inline in install-awg.sh for manual deb install
- D-03: Script assumes RPi OS already running — no OS install step
- Tunnel bring-up excluded from installer and deploy.sh (not idempotent; left as manual post-deploy step — Pitfall 5)
- D-04: SSH_HOST="pi4" via system ~/.ssh/config — no hardcoded IP in deploy.sh
- D-05/D-06: SSH user ar + BatchMode=yes enforces key auth; password fallback blocked
- D-07/D-08: .env.secrets gitignored; AWG_PRIVATE_KEY/PUBLIC/PRESHARED_KEY variable names canonical
- D-09: sed pipeline substitution of {{PrivateKey}}/{{PublicKey}}/{{PresharedKey}} in amnezia.key.claude.txt
- D-10: validate_key() with ^[A-Za-z0-9+/]{43}=$ regex guards all key use before any SSH operation
- chmod 600 on mktemp BEFORE writing key material (T-01-SEC); trap EXIT for cleanup
- D-11: install-awg.sh Stage 6 uses /sys/module/amneziawg check instead of lsmod grep — /sys/module is set synchronously on load; lsmod can lag on kernel 6.12.25+rpt-rpi-v8
- routing.sh D-06: Flush-and-rebuild (ip route flush dev awg0) for idempotent routing — clean slate on every run
- routing.sh D-07: iptables idempotency via iptables -C check before every -A — no duplicate MASQUERADE rules
- deploy.sh D-11: routing.sh deployed via SCP /tmp staging then sudo mv + chmod +x (matches Phase 1 pattern)
- deploy.sh D-12: --no-run flag skips routing.sh activation; without it, routing.sh runs automatically after deploy
- Phase 5 D-06/D-08: routing.sh renames SUBNET_FILE → WHITE_LIST_FILE (/etc/white-list.txt); Stage 5b added to load /etc/white-list-extended.txt when present (silent skip when absent)
- Phase 5 D-14: vpn-rollback.sh Step 4c added — rm -f /etc/white-list-extended.txt; /etc/white-list.txt preserved (not removed) during rollback
- Phase 5 D-10/D-11: vpn-status.sh --via=vpn|isp filter applied at output time (not entry collection); strict string validation; composes with --filter/--device/--last
- Phase 5 deploy: deploy.sh TOTAL_STAGES=22; Stage 21 conditionally SCPs exception file (skip if absent); Stage 22 activation drops --no-update for first-deploy correctness
- Phase 7 D-06: ORG column placed after DOMAIN and before PATH; format "{org} (AS{asn})" or "-" for unknown
- Phase 7 D-07: --summary aggregate mode top-20 by TOTAL desc; composes with --filter/--device/--via
- Phase 7 test: Docker image python:3.11-slim-bookworm for macOS re-exec (debian:bookworm-slim lacks python3)
- Phase 7 D-08: watch-routes.py _asn_cache uses None sentinel (in-flight) / {} (completed-no-result) / dict (resolved) — three states prevent duplicate thread spawns
- Phase 7 D-09: enable_asn keyword-only param on format_line() — backward-compatible default True; --no-asn flag maps to enable_asn=False
- Phase 7 D-10: deploy.sh Stage 23 deploys asn-lookup.py; Stage 24 activates routing.sh — routing activation remains last runtime stage
- Phase 8 D-05/D-06: EFFECTIVE_URL initialized to RU_SUBNET_URL; /etc/ru-exclude.txt lines appended as &exclude[cidr4]=CIDR; absent/empty file → URL unchanged
- Phase 8 D-07/D-08: EXCLUDE_LIST_LOCAL=configs/ru-exclude.txt; Stage 21b conditional SCP to /etc/ru-exclude.txt (chmod 644, root:root); no TOTAL_STAGES bump (remains 24); configs/ru-exclude.txt gitignored

## Hardware Verified

- install-awg.sh: ✓ verified on RPi 4 (kernel 6.12.25+rpt-rpi-v8) — 2026-05-19
  - INST-01: awg + awg-quick at /usr/bin ✓
  - INST-02: ip_forward=1 persisted via /etc/sysctl.d/99-vpn-gateway.conf ✓
  - amneziawg kernel module loaded ✓

## Last Session

**Stopped at:** Phase 8 complete — 3/3 plans executed
**Timestamp:** 2026-05-27T15:45:00Z
**Resume:** Phase 8 complete. EFFECTIVE_URL in update-vpn-routes, Stage 21b in deploy.sh, ru-exclude.txt.example + docs done. Next: Phase 9 (Operational Logging) or Phase 6 (Documentation).

---
*Initialized: 2026-05-18*
*Updated: 2026-05-27 — Phase 8 complete; EFFECTIVE_URL exclusion filter in update-vpn-routes; Stage 21b + EXCLUDE_LIST vars in deploy.sh (TOTAL_STAGES=24); configs/ru-exclude.txt.example added*

## Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260521-jex | Add scripts/watch-routes.py — real-time iptables log viewer with reverse DNS caching | 2026-05-21 | cf6bafa | [260521-jex-add-scripts-watch-routes-py-real-time-ip](./quick/260521-jex-add-scripts-watch-routes-py-real-time-ip/) |

## Accumulated Context

### Roadmap Evolution

- Phase 4 added: Traffic Logging & Visibility — per-connection route logging (VPN/ISP), subnets, domain names
- Phase 5 added: Custom Route Exceptions — per-IP/domain overrides forcing traffic through ISP
- Phase 6 added: Documentation — ops runbook (deploy, verify, rollback, add exceptions)
- Phase 7 added: ASN Enrichment & Traffic Attribution
- Phase 9 added: Operational Logging — centralized logs for diagnosing system failures; 14-day rotation

### Phase 4 Post-execution Fixes (applied after plans, discovered during live testing)

- routing.sh: FORWARD chain policy is DROP (Docker). Added ACCEPT rules (-i eth0, RELATED,ESTABLISHED) — without them LAN forwarding silently dropped
- routing.sh: LOG rules must be BEFORE ACCEPT — LOG is non-terminating, ACCEPT terminates; wrong order = no journald entries
- routing.sh: eth0 MASQUERADE must exclude LAN subnet (`! -d LAN_SUBNET`) — full MASQUERADE caused Keenetic web/app admin to block requests appearing from 192.168.1.254
- deploy.sh: Stage 17/18 order swapped — dnsmasq must be installed before config deployed to avoid dpkg interactive prompt
- SSH_HOST moved from deploy.sh hardcode to .env
