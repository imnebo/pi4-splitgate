#!/usr/bin/env python3
"""
asn-lookup.py — Team Cymru bulk-whois ASN/org lookup helper for the RPi VPN gateway.

Reads one IPv4 address per line from stdin (or positional CLI args), performs a
single batched TCP query to whois.cymru.com:43 for any IPs not already in the
file-backed JSON cache, and emits a single-line JSON object on stdout:

    {"8.8.8.8": {"asn": "15169", "org": "GOOGLE, US"}, ...}

IPs absent from the result either had no BGP entry or Cymru was unreachable.
Empty stdin produces "{}" on stdout.  Exit code is always 0.

Cache:
    Path:   /tmp/vpn-asn-cache.json
    Format: {"<ip>": {"asn": "<digits>", "org": "<as-name>"}}
    Write:  atomic (tmpfile + os.replace) with mode 0o666 so both root and
            non-root callers (vpn-status.sh / watch-routes.py) can share it.

Usage:
    python3 scripts/asn-lookup.py                  # IPs from stdin (one per line)
    python3 scripts/asn-lookup.py 8.8.8.8 1.1.1.1 # direct-CLI mode
    python3 scripts/asn-lookup.py --help           # show this message

Requirements: stdlib only — no pip dependencies.
"""

import argparse
import json
import os
import socket
import sys
import tempfile

# ─── Module-level constants ───────────────────────────────────────────────────

CACHE_FILE = "/tmp/vpn-asn-cache.json"
CYMRU_HOST = "whois.cymru.com"
CYMRU_PORT = 43
DEFAULT_TIMEOUT = 10.0


# ─── Cymru bulk lookup ────────────────────────────────────────────────────────


def _cymru_bulk_lookup(ips: list, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Send a batch query to Team Cymru whois; return {ip: {asn, org}}.

    Protocol: one TCP connection, send 'begin\\nverbose\\n<IPs>\\nend\\n',
    read pipe-separated response lines until EOF.  Verbose mode fields:
      index 0 = ASN | index 1 = IP | index 6 = AS Name (org)

    Returns {} on empty input (no socket opened).
    Returns partial results (possibly {}) on socket.timeout or OSError —
    callers degrade gracefully.
    """
    if not ips:
        return {}

    query = "begin\nverbose\n" + "\n".join(ips) + "\nend\n"
    results: dict = {}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)          # must be BEFORE connect() — Pitfall 3
        s.connect((CYMRU_HOST, CYMRU_PORT))
        s.sendall(query.encode())
        f = s.makefile("rb")
        for raw_line in f:
            line = raw_line.decode("utf-8", errors="replace").strip()
            # Skip Cymru header ("Bulk mode; whois.cymru.com [timestamp]")
            # and any line without the pipe-separator — Pitfall 1
            if line.startswith("Bulk mode") or "|" not in line:
                continue
            # Strip whitespace from every field — Pitfall 2
            parts = [p.strip() for p in line.split("|")]
            # Verbose mode: AS | IP | BGP Prefix | CC | Registry | Allocated | AS Name
            if len(parts) >= 7:
                asn = parts[0]
                ip  = parts[1]
                org = parts[6]
                if ip:
                    results[ip] = {"asn": asn, "org": org}
        f.close()
        s.close()
    except (socket.timeout, OSError):
        pass  # Return whatever partial results we collected
    return results


# ─── Cache helpers ────────────────────────────────────────────────────────────


def load_cache() -> dict:
    """Load the file cache; return {} on missing file or corrupt JSON."""
    try:
        with open(CACHE_FILE, "r") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict) -> None:
    """Write *cache* atomically to CACHE_FILE (tmpfile + os.replace).

    Creates the file with mode 0o666 so both root (vpn-status.sh) and
    non-root (watch-routes.py) invocations can update the shared cache —
    Pitfall 4.
    """
    cache_dir = os.path.dirname(CACHE_FILE) or "."
    fd, tmp_path = tempfile.mkstemp(dir=cache_dir)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(cache, fh)
        os.replace(tmp_path, CACHE_FILE)   # atomic on POSIX — Pitfall 3 / T-07-03
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return
    # Ensure world-writable so root-created cache is writable by non-root later
    try:
        os.chmod(CACHE_FILE, 0o666)
    except OSError:
        pass  # Best-effort; non-fatal


# ─── High-level lookup ────────────────────────────────────────────────────────


def lookup_ips(ips: list) -> dict:
    """Return ASN/org info for all *ips*, using cache where possible.

    Steps:
      1. Load the file cache.
      2. Determine which IPs are not yet cached.
      3. Batch-query Cymru for uncached IPs.
      4. Merge new results into the cache and save atomically.
      5. Return the subset of the cache restricted to the requested IPs.
    """
    cache = load_cache()

    uncached = [ip for ip in ips if ip not in cache]
    new_results = _cymru_bulk_lookup(uncached)  # returns {} instantly on empty list
    if new_results:
        cache.update(new_results)
        save_cache(cache)

    return {ip: cache[ip] for ip in ips if ip in cache}


# ─── CLI entry point ──────────────────────────────────────────────────────────


def main() -> None:
    """Parse args, collect IPs, run lookup, print JSON to stdout, exit 0."""
    parser = argparse.ArgumentParser(
        description=(
            "Team Cymru bulk-whois ASN/org lookup for IPv4 addresses.\n"
            "\n"
            "Reads one IPv4 per line from stdin (or positional args), queries\n"
            "whois.cymru.com:43 in a single TCP session, and writes a JSON dict\n"
            "to stdout: {\"ip\": {\"asn\": \"...\", \"org\": \"...\"}}.\n"
            "\n"
            "Cache file: " + CACHE_FILE + "\n"
            "IPs already in the cache are never re-queried.\n"
            "Network errors are non-fatal; missing IPs are absent from the dict.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "ips",
        nargs="*",
        metavar="IP",
        help="IPv4 addresses to look up (default: read from stdin, one per line).",
    )
    args = parser.parse_args()

    if args.ips:
        ip_list = [ip.strip() for ip in args.ips if ip.strip()]
    else:
        ip_list = [line.strip() for line in sys.stdin if line.strip()]

    result = lookup_ips(ip_list)
    sys.stdout.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
