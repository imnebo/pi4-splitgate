# Phase 8: RU IP List Exclusion Filter - Context

**Gathered:** 2026-05-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Allow operators to define CIDR ranges to exclude from the RU IP list download. When `update-vpn-routes` fetches the list, it appends `exclude[cidr4]=...` query parameters to `RU_SUBNET_URL` for each CIDR in a local exclusion file — the iplist service filters those ranges server-side, so they never appear in `/etc/white-list.txt` and therefore route through the VPN instead of the ISP.

Deliverables:
1. **`configs/ru-exclude.txt.example`** — committed example file with commented format instructions
2. **`scripts/update-vpn-routes`** extended — reads `/etc/ru-exclude.txt` if present, builds URL with `exclude[cidr4]=...` params, passes to curl
3. **`deploy.sh`** extended — conditionally deploys `configs/ru-exclude.txt` to `/etc/ru-exclude.txt` alongside Stage 21 (white-list-extended.txt), no new stage number
4. **`configs/ru-exclude.txt`** gitignored (user's actual exclusion list — never committed)
5. **README.md + docs/README.ru.md** updated to document the new file and workflow

Phase ends when: cron or manual `update-vpn-routes` run with a non-empty `/etc/ru-exclude.txt` fetches the filtered list; without the file the behavior is unchanged.

</domain>

<decisions>
## Implementation Decisions

### Exclusion File
- **D-01:** Local path: `configs/ru-exclude.txt`. RPi path: `/etc/ru-exclude.txt`. Matches the `white-list` naming family.
- **D-02:** Format: one CIDR per line (e.g. `142.250.0.0/16`). Lines starting with `#` are comments and skipped. Blank lines skipped.
- **D-03:** `configs/ru-exclude.txt.example` committed to repo as documentation (non-functional, clearly labelled). Actual `configs/ru-exclude.txt` gitignored.

### Absent File Behavior
- **D-04:** If `/etc/ru-exclude.txt` does not exist or is empty → download proceeds with `RU_SUBNET_URL` unchanged (no `exclude` params). Silent skip — no error, no log warning.

### URL Construction
- **D-05:** `update-vpn-routes` builds the effective URL in bash: start with `${RU_SUBNET_URL}`, then for each non-comment non-blank line in `/etc/ru-exclude.txt` append `&exclude[cidr4]=${line}`. Pass the final URL to curl. No percent-encoding of `/` — the iplist service accepts raw CIDRs in query params.
- **D-06:** URL construction happens BEFORE the curl call, replacing the bare `${RU_SUBNET_URL}` reference. The rest of the script (SHA256 compare, atomic mv, routing.sh call) is unchanged.

### Deploy Pattern
- **D-07:** Same conditional SCP pattern as Stage 21 (`white-list-extended.txt`): if `configs/ru-exclude.txt` exists locally → SCP to `/etc/ru-exclude.txt` on RPi. If absent → skip silently. No new stage number — extend Stage 21 block or add adjacent to it. `EXCLUDE_LIST_LOCAL="configs/ru-exclude.txt"`, `EXCLUDE_LIST_REMOTE="/etc/ru-exclude.txt"`.
- **D-08:** No TOTAL_STAGES bump required (the new conditional is inside the existing stage block).

### SHA256 / Rebuild Behavior
- **D-09:** No changes needed. Adding or changing the exclusion list changes the effective URL → server returns different content → SHA256 of downloaded file differs from stored `/etc/white-list.txt` → rebuild triggered automatically on next cron run. This is the correct behavior; no special handling needed.

### Claude's Discretion
- Exact placement of the exclusion deploy block within Stage 21 (before or after white-list-extended deploy — either is fine)
- Whether to log the number of excluded CIDRs via `logger -t "vpn-routes"` (recommended for visibility)
- Whether to add a EXCLUDE_LIST_TMP path variable in deploy.sh (yes, for consistency with other _TMP vars)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scripts to Modify
- `scripts/update-vpn-routes` — FULL FILE; specifically the constants block (SUBNET_FILE, SUBNET_TMP), the `source /etc/vpn-gateway.env` call, Stage 1 curl invocation on line 40; URL construction inserts between source and curl
- `deploy.sh` — FULL FILE; specifically Stage 21 block (conditional white-list-extended.txt SCP), the path variable block (lines 53–66), and the final-summary block (PHASE 5/6/7 lines to add PHASE 8 sibling)

### Config Files
- `configs/white-list-extended.txt.example` — exact template to mirror for `ru-exclude.txt.example` (format, comment style, header)
- `.env` — `RU_SUBNET_URL` definition; the base URL that gets the exclude params appended

### Prior Phase Context
- `.planning/phases/05-custom-route-exceptions-ip/05-CONTEXT.md` — D-12/D-13: conditional deploy pattern for white-list-extended.txt (same pattern for exclude file)
- `.planning/phases/03-autostart-cron-rollback/03-CONTEXT.md` — D-07: update-vpn-routes deploy target and idempotency constraints

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/update-vpn-routes` lines 40–51 (curl call + download failure handling): URL construction inserts before line 40 as a new block that builds `EFFECTIVE_URL` from `RU_SUBNET_URL` + exclude params; then line 40 changes `"${RU_SUBNET_URL}"` → `"${EFFECTIVE_URL}"`
- deploy.sh Stage 21 (conditional SCP for white-list-extended.txt): copy/adapt this block for the exclude file deploy, placing it adjacent to Stage 21

### Established Patterns
- `white-list-extended.txt` deploy pattern: `if [[ -f "$WHITE_LIST_EXT_LOCAL" ]]; then scp ... fi` — mirror exactly for `ru-exclude.txt`
- Comment-skip in bash: `while IFS= read -r line; do [[ "$line" =~ ^# || -z "$line" ]] && continue; ...; done < /etc/ru-exclude.txt`
- All path variables declared in the path variable block at top of deploy.sh alongside similar vars

### Integration Points
- `update-vpn-routes` sources `/etc/vpn-gateway.env` → reads `RU_SUBNET_URL` → the new block reads `/etc/ru-exclude.txt` (if present) and builds `EFFECTIVE_URL` → existing curl call uses `EFFECTIVE_URL`
- deploy.sh Stage 21 block extended: after the white-list-extended conditional, add the ru-exclude conditional
- `.gitignore`: add `configs/ru-exclude.txt` alongside existing gitignored user files

</code_context>

<specifics>
## Specific Ideas

- User-provided URL example: `https://russia.iplist.opencck.org/?format=text&data=cidr4&exclude[cidr4]=142.250.0.0/16&exclude[cidr4]=142.251.0.0/16`
- Each excluded CIDR becomes a separate `&exclude[cidr4]=CIDR` parameter (not comma-separated)
- Use case: exclude Google/Cloudflare ranges that iplist marks as RU but should go through VPN

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 8-ru-ip-list-exclusion-filter*
*Context gathered: 2026-05-23*
