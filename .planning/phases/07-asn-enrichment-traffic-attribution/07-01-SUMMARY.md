---
plan: "07-01"
status: complete
completed_at: "2026-05-23T10:30:00Z"
commits:
  - "1667197: feat(07-01): add scripts/asn-lookup.py — Cymru bulk-whois ASN helper + cache"
---

# 07-01 Summary: scripts/asn-lookup.py

## What was built

`scripts/asn-lookup.py` — a standalone Python stdlib helper that reads IPv4 addresses from stdin (or positional CLI args), performs a single batched TCP query to whois.cymru.com:43 for any IPs not in the file-backed JSON cache, and emits a single JSON object on stdout: `{"ip": {"asn": "...", "org": "..."}}`.

Key implementation details:
- Module constants: `CACHE_FILE = "/tmp/vpn-asn-cache.json"`, `CYMRU_HOST`, `CYMRU_PORT = 43`, `DEFAULT_TIMEOUT = 10.0`
- `_cymru_bulk_lookup`: opens one TCP socket, calls `s.settimeout()` before `s.connect()`, sends `begin\nverbose\n<IPs>\nend\n`, reads via `s.makefile("rb")`, skips "Bulk mode" header, strips whitespace from all pipe-separated fields, returns partial dict on timeout/OSError
- `load_cache` / `save_cache`: atomic write via `tempfile.mkstemp` + `os.replace`, `os.chmod(CACHE_FILE, 0o666)` after write so root and non-root callers share the cache
- `lookup_ips`: cache-first, always calls `_cymru_bulk_lookup(uncached)` (returns `{}` immediately on empty list), merges and persists new results only if non-empty
- `main()`: argparse with description mentioning stdin and `/tmp/vpn-asn-cache.json`; positional IPs or stdin fallback; always exits 0

`tests/test_asn_lookup.py` created with 15 tests (13 plan-required + 2 variants for Test 3 and Test 8), all using `unittest.mock.patch` — zero live Cymru calls.

## Verification

All checks passed:

- `python3 -m pytest tests/test_asn_lookup.py -x -v` — 15/15 tests PASSED
- `python3 -c "import ast; ast.parse(...)"` — syntax valid
- Empty stdin → `{}` and exit 0 — PASSED
- `grep` checks: `stdlib`, `whois.cymru.com`, `/tmp/vpn-asn-cache.json`, `os.replace`, `settimeout`, `0o666` — all present
- No pip imports (`requests`, `httpx`, `aiohttp`, `cymruwhois`) — PASSED

## Notes for downstream plans

**Interface contract (stable):**
```
python3 /etc/asn-lookup.py            # reads IPs from stdin (one per line)
python3 /etc/asn-lookup.py 8.8.8.8   # direct-CLI positional mode
```
stdout: exactly one line — `{"ip": {"asn": "15169", "org": "GOOGLE, US"}}` or `{}`
exit code: always 0

**Cache location:** `/tmp/vpn-asn-cache.json` — mode `0o666`, shared between root and non-root callers

**Import note (Plan 08 / watch-routes.py):** The hyphenated filename `asn-lookup.py` prevents Python `import`; always call via `subprocess`. Both Plans 07-02 and 07-03 must use subprocess invocation.

**Deployed path:** Research assumed `/etc/asn-lookup.py` — consistent with all other phase scripts. Plan 07-03 will add the deploy.sh Stage 24 to SCP and chmod the file there.

**Test isolation:** Tests redirect `asn_lookup.CACHE_FILE` to a `tempfile.mkdtemp()` path so the real `/tmp/vpn-asn-cache.json` is never touched during `pytest`.
