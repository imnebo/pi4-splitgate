---
plan: "12-01"
completed: "2026-05-28"
---

# Summary: Buffered ASN Output (Plan 12-01)

## What was built

Added a pending buffer to `src/scripts/watch-routes.py` so lines for new destination IPs are held until their ASN/org lookup completes rather than printing immediately without enrichment.

## Changes

**src/scripts/watch-routes.py:**
- `import time` added
- `_BUFFER_TIMEOUT = 6.0`, `_pending: dict[str, list]`, `_pending_lock` added as module globals
- `_flush_entries(entries, asn_result)` — formats and prints buffered lines with resolved org
- `_do_lookup()` — now pops+flushes `_pending[ip]` immediately after writing `_asn_cache[ip]`
- `_pending_watchdog()` — daemon thread; flushes entries older than `_BUFFER_TIMEOUT` every 1 s
- `main()` — starts watchdog before journalctl loop; buffers new/in-flight IPs via `_pending`; cached IPs still print immediately

**src/tests/test_watch_routes_asn.py:**
- Fixed stale path `scripts/` → `src/scripts/` (broken since Phase 10)
- Added `TestPendingBuffer` class with 7 new tests (B1–B7)
- Total: 17 tests, all passing

## Behavior

| IP state | Before | After |
|----------|--------|-------|
| New (first seen) | Prints immediately, no `\| org` | Held ~1–3 s, prints with `\| org` |
| In-flight | Second packet prints without `\| org` | Buffered alongside first packet |
| Cached (resolved) | Prints with `\| org` | Unchanged — prints immediately |
| Lookup stalled | Line never gets org | Flushed after 6 s, no org suffix |
| `--no-asn` | Prints immediately | Unchanged |
