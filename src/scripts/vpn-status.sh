#!/usr/bin/env bash
# /etc/splitgate/vpn-status.sh — VPN Gateway Connection Visibility Tool
#
# Query script that reads journald for iptables [VPN]/[ISP] LOG entries, correlates
# with dnsmasq query log to resolve destination IPs to domain names, and presents a
# readable connection table with filtering flags.
#
# Deployed path: /etc/splitgate/vpn-status.sh (chmod +x)
# Run as:        sudo vpn-status.sh
#                sudo vpn-status.sh --filter=steam
#                sudo vpn-status.sh --device=10.0.0.50
#                sudo vpn-status.sh --last=100 --filter=google --device=10.0.0.100
#                sudo vpn-status.sh --summary
#                sudo vpn-status.sh --summary --device=10.0.0.50 --via=vpn
#
# Decisions honored: D-11 (deployed to /etc/splitgate/vpn-status.sh, run as sudo),
#   D-12 (default 50 entries; columns: timestamp, src-ip, dst-ip, domain, VPN/ISP),
#   D-13 (domain: dnsmasq log correlation first, rDNS fallback via host),
#   D-14 (--filter: partial case-insensitive domain match),
#   D-15 (--device: filter by source LAN device IP),
#   D-16 (--last: override default entry count),
#   D-17 (set -euo pipefail, source /etc/splitgate/vpn-gateway.env),
#   D-03 (Phase 7: single ASN lookup call seeded with all unique DST IPs),
#   D-06 (Phase 7: ORG column after DOMAIN, format "{org} (AS{asn})" or "-"),
#   D-07 (Phase 7: --summary flag, ORG|VPN_COUNT|ISP_COUNT|TOTAL, top 20 by TOTAL)
#
# Security: --filter and --device values are never passed to eval or sh -c; used
# only as fixed-string grep patterns (T-04-07 mitigated).
# T-07-06: dst_ip piped to python3 is restricted to digits+dot by grep -oP extraction.
# T-07-07: malformed JSON from asn-lookup.py caught by python3 ValueError + || true.

set -euo pipefail

# ─── Logging (interactive tool — stdout only, no file write per D-08) ────────
log() { echo "[vpn-status] $*"; }
err() { echo "[vpn-status] ERROR: $*" >&2; }

# ─── Source environment ───────────────────────────────────────────────────────
# /etc/splitgate/vpn-gateway.env is deployed by Phase 1. Provides VPN_IFACE and other vars.
if [[ ! -f /etc/splitgate/vpn-gateway.env ]]; then
    err "/etc/splitgate/vpn-gateway.env not found — cannot determine interface configuration"
    exit 1
fi
# shellcheck source=/dev/null
source /etc/splitgate/vpn-gateway.env

# ─── Defaults ────────────────────────────────────────────────────────────────
LAST=50
FILTER=""
DEVICE=""
VIA=""
SUMMARY=false

# ─── Argument Parsing ────────────────────────────────────────────────────────
for arg in "$@"; do
    case "${arg}" in
        --last=*)
            val="${arg#--last=}"
            if ! [[ "${val}" =~ ^[0-9]+$ ]]; then
                err "--last value must be a positive integer, got: '${val}'"
                exit 1
            fi
            LAST="${val}"
            ;;
        --filter=*)
            FILTER="${arg#--filter=}"
            ;;
        --device=*)
            DEVICE="${arg#--device=}"
            ;;
        --via=*)
            val="${arg#--via=}"
            if [[ "${val}" != "vpn" ]] && [[ "${val}" != "isp" ]]; then
                err "--via value must be 'vpn' or 'isp', got: '${val}'"
                exit 1
            fi
            VIA="${val^^}"
            ;;
        --summary)
            SUMMARY=true
            ;;
        *)
            err "Unknown argument: '${arg}'"
            err "Usage: vpn-status.sh [--last=N] [--filter=STRING] [--device=IP] [--via=vpn|isp] [--summary]"
            exit 1
            ;;
    esac
done

# ─── Fetch iptables LOG entries from kernel journal ───────────────────────────
# (D-12, D-13) Reads [VPN] and [ISP] prefixed LOG entries set by iptables rules.
# journalctl -k: kernel messages only; -g: grep pattern on message body.
raw_lines=""
raw_lines=$(journalctl -k --no-pager -n "${LAST}" -g '\[(VPN|ISP)\]' 2>/dev/null || true)

# ─── Pre-fetch dnsmasq query log (one query, used for all correlations) ───────
# Fetch last 10 minutes of dnsmasq output once to avoid repeated journalctl calls.
dnsmasq_log=""
dnsmasq_log=$(journalctl -u dnsmasq --no-pager --since "10 minutes ago" 2>/dev/null || true)

# ─── Process each connection entry ────────────────────────────────────────────
entries=()

while IFS= read -r line; do
    # Skip lines that don't contain [VPN] or [ISP]
    if ! echo "${line}" | grep -qE '\[(VPN|ISP)\]'; then
        continue
    fi

    # Extract timestamp (first 3 fields: Month Day HH:MM:SS)
    ts=$(echo "${line}" | awk '{print $1, $2, $3}')

    # Extract routing decision: VPN or ISP
    decision=$(echo "${line}" | grep -oP '\[(VPN|ISP)\]' | tr -d '[]')

    # Extract source IP (SRC= field)
    src_ip=$(echo "${line}" | grep -oP 'SRC=\K[0-9.]+' || true)

    # Extract destination IP (DST= field)
    dst_ip=$(echo "${line}" | grep -oP 'DST=\K[0-9.]+' || true)

    # Skip malformed lines missing required fields
    [[ -z "${src_ip}" || -z "${dst_ip}" || -z "${decision}" ]] && continue

    # Apply --device filter immediately after extraction (D-15)
    if [[ -n "${DEVICE}" ]] && [[ "${src_ip}" != "${DEVICE}" ]]; then
        continue
    fi

    # ─── Domain Resolution (D-13): two-step ───────────────────────────────────
    domain=""

    # Step 1: dnsmasq log correlation
    # Search for "reply <hostname> is <dst_ip>" in the pre-fetched dnsmasq log.
    # dnsmasq logs: "reply store.steampowered.com is 104.64.0.0" when a query
    # response includes that IP — correlate by dst_ip.
    if [[ -n "${dnsmasq_log}" ]]; then
        # Look for reply lines resolving to dst_ip
        matched_reply=$(echo "${dnsmasq_log}" | grep -F "reply " | grep -F " is ${dst_ip}" | tail -1 || true)
        if [[ -n "${matched_reply}" ]]; then
            # Extract hostname: "reply <hostname> is <ip>"
            domain=$(echo "${matched_reply}" | grep -oP 'reply \K\S+(?= is )' || true)
        fi
    fi

    # Step 2: rDNS fallback via host (D-13)
    if [[ -z "${domain}" ]]; then
        rdns_out=$(host "${dst_ip}" 2>/dev/null || true)
        if [[ -n "${rdns_out}" ]]; then
            # host output: "X.X.X.X.in-addr.arpa domain name pointer hostname."
            domain=$(echo "${rdns_out}" | grep -oP '\.arpa\. domain name pointer \K\S+' | tail -1 || true)
            # Strip trailing dot if present
            domain="${domain%.}"
        fi
    fi

    # If both resolution steps failed, use raw IP
    if [[ -z "${domain}" ]]; then
        domain="${dst_ip}"
    fi

    # Apply --filter after domain resolution (D-14): case-insensitive fixed-string match
    if [[ -n "${FILTER}" ]]; then
        if ! echo "${domain}" | grep -qiF "${FILTER}"; then
            continue
        fi
    fi

    # Truncate domain to 40 chars for display
    display_domain="${domain:0:40}"

    entries+=("${ts}|${src_ip}|${dst_ip}|${display_domain}|${decision}")

done <<< "${raw_lines}"

# ─── ASN enrichment block (D-03, D-06) ───────────────────────────────────────
# Collect unique DST IPs from ALL entries BEFORE output-time filter (Pitfall 6).
# This ensures the org_map is populated for the full entry set, so both
# regular mode and --summary mode have consistent data.
declare -A org_map

declare -A _seen_ips
unique_ips=()
for _entry in "${entries[@]}"; do
    IFS='|' read -r _ts _src _dst _domain _dec <<< "${_entry}"
    if [[ -z "${_seen_ips[${_dst}]+x}" ]]; then
        _seen_ips["${_dst}"]=1
        unique_ips+=("${_dst}")
    fi
done
unset _seen_ips

if [[ ${#unique_ips[@]} -gt 0 ]] && [[ -f /etc/splitgate/asn-lookup.py ]] && command -v python3 >/dev/null 2>&1; then
    asn_json=$(printf '%s\n' "${unique_ips[@]}" | python3 /etc/splitgate/asn-lookup.py 2>/dev/null || true)
    if [[ -n "${asn_json}" ]]; then
        while IFS='=' read -r _ip _label; do
            [[ -n "${_ip}" ]] && org_map["${_ip}"]="${_label}"
        done < <(python3 -c "
import json,sys
d=json.loads(sys.stdin.read())
for ip,v in d.items():
    asn=v.get('asn','')
    org=v.get('org','')
    if asn and org:
        print(ip+'='+org+' (AS'+asn+')')
" <<< "${asn_json}" 2>/dev/null || true)
    fi
fi

# ─── --summary mode (D-07) ───────────────────────────────────────────────────
# When --summary is active, print aggregate ORG | VPN_COUNT | ISP_COUNT | TOTAL
# table (top 20 by TOTAL desc) and exit. Filters (--filter, --device, --via)
# compose with --summary so operators can scope the aggregate to a device or path.
if [[ "${SUMMARY}" == "true" ]]; then
    declare -A _vpn_cnt _isp_cnt
    for _entry in "${entries[@]}"; do
        IFS='|' read -r _ts _src _dst _domain _dec <<< "${_entry}"
        # Apply same filters as regular mode
        [[ -n "${FILTER}" && "${_entry}" != *"${FILTER}"* ]] && continue
        [[ -n "${DEVICE}" && "${_src}" != "${DEVICE}" ]] && continue
        if [[ -n "${VIA}" ]]; then
            [[ "${VIA}" == "VPN" && "${_dec}" != "VPN" ]] && continue
            [[ "${VIA}" == "ISP" && "${_dec}" != "ISP" ]] && continue
        fi
        _org_key="${org_map[${_dst}]:-unknown}"
        if [[ "${_dec}" == "VPN" ]]; then
            _vpn_cnt["${_org_key}"]=$(( ${_vpn_cnt["${_org_key}"]:-0} + 1 ))
        else
            _isp_cnt["${_org_key}"]=$(( ${_isp_cnt["${_org_key}"]:-0} + 1 ))
        fi
    done
    printf "%-40s %-10s %-10s %s\n" "ORG" "VPN_COUNT" "ISP_COUNT" "TOTAL"
    printf "%-40s %-10s %-10s %s\n" "----------------------------------------" "----------" "----------" "-----"
    declare -A _all_orgs
    for _k in "${!_vpn_cnt[@]}" "${!_isp_cnt[@]}"; do _all_orgs["$_k"]=1; done
    {
        for _k in "${!_all_orgs[@]}"; do
            printf '%s\t%s\t%s\n' "${_k}" "${_vpn_cnt[${_k}]:-0}" "${_isp_cnt[${_k}]:-0}"
        done
    } | python3 -c "
import sys
rows=[]
for line in sys.stdin:
    p=line.rstrip('\n').split('\t')
    if len(p)==3:
        o,v,i=p[0],int(p[1]),int(p[2])
        rows.append((o,v,i,v+i))
rows.sort(key=lambda x:-x[3])
for o,v,i,t in rows[:20]:
    print(f'{o:<40} {v:<10} {i:<10} {t}')
" 2>/dev/null || true
    exit 0
fi

# ─── Output ───────────────────────────────────────────────────────────────────
printf "%-20s %-18s %-18s %-40s %-30s %s\n" "TIMESTAMP" "SRC-IP" "DST-IP" "DOMAIN" "ORG" "PATH"
printf "%-20s %-18s %-18s %-40s %-30s %s\n" "--------------------" "------------------" "------------------" "----------------------------------------" "------------------------------" "----"

if [[ ${#entries[@]} -eq 0 ]]; then
    echo "(no connections matched — try --last=200 or remove filters)"
else
    for entry in "${entries[@]}"; do
        IFS='|' read -r ts src_ip dst_ip domain decision <<< "${entry}"
        if [[ -n "${VIA}" ]] && [[ "${decision}" != "${VIA}" ]]; then continue; fi
        org="${org_map[${dst_ip}]:--}"
        printf "%-20s %-18s %-18s %-40s %-30s %s\n" "${ts}" "${src_ip}" "${dst_ip}" "${domain}" "${org}" "${decision}"
    done
fi

exit 0
