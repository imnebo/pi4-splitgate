# Context

`deploy.sh` runs `routing.sh` twice:
- **Stage 11** — activated right after routing.sh is deployed (stage 10), before white-list-extended.txt and ru-exclude.txt exist on the Pi
- **Stage 24** — re-activates routing.sh at the very end, after those config files land (stages 21/21b)

Stage 24 was added when Phase 5/8 introduced those extra files — routing.sh reads them at runtime, so a second run was needed. The result: every deploy runs routing.sh twice with 13 stages between them. Stage 24 also ignores `--no-run`.

Additionally, stage 21b (ru-exclude.txt) prints `[21/24]` — same number as stage 21 (white-list-extended.txt). Display bug.

# Fix

**File**: `deploy.sh`

### 1. Remove stage 11 block (lines 296–304)

Delete the early routing.sh activation. routing.sh will now only run at stage 24, after all config files are deployed.

```bash
# DELETE this block:
# ─── Stage 11: Activate routing.sh (unless --no-run) (D-12) ─────────────────
if [ "${RUN_ROUTING}" = "true" ]; then
  echo "[11/${TOTAL_STAGES}] Activating routing.sh on ${SSH_HOST}..."
  ssh -o BatchMode=yes "${SSH_HOST}" "sudo ${ROUTING_SH_REMOTE}"
  echo "       routing.sh activation complete — split-tunnel active"
else
  echo "[11/${TOTAL_STAGES}] Skipping routing.sh activation (--no-run). Run manually:"
  echo "       ssh ${SSH_HOST} \"sudo ${ROUTING_SH_REMOTE}\""
fi
```

### 2. Wrap stage 24 in `--no-run` check (line 397–400)

```bash
# BEFORE:
echo "[24/${TOTAL_STAGES}] Activating routes via routing.sh on ${SSH_HOST}..."
ssh -o BatchMode=yes "${SSH_HOST}" "sudo ${ROUTING_SH_REMOTE}"
echo "       routing.sh re-run complete — ..."

# AFTER:
if [ "${RUN_ROUTING}" = "true" ]; then
  echo "[24/${TOTAL_STAGES}] Activating routes via routing.sh on ${SSH_HOST}..."
  ssh -o BatchMode=yes "${SSH_HOST}" "sudo ${ROUTING_SH_REMOTE}"
  echo "       routing.sh activation complete — split-tunnel active, exception routes loaded"
else
  echo "[24/${TOTAL_STAGES}] Skipping routing.sh activation (--no-run). Run manually:"
  echo "       ssh ${SSH_HOST} \"sudo ${ROUTING_SH_REMOTE}\""
fi
```

### 3. Fix stage 21b display number (line 375)

```bash
# BEFORE:
echo "[21/${TOTAL_STAGES}] Deploying ru-exclude.txt to ${SSH_HOST} (if present)..."

# AFTER:
echo "[21b/${TOTAL_STAGES}] Deploying ru-exclude.txt to ${SSH_HOST} (if present)..."
```

### 4. Update header comment (line 13)

```bash
# BEFORE:
#   D-12: --no-run flag skips routing.sh activation; without it, runs automatically

# AFTER:
#   D-12: --no-run flag skips routing.sh final activation (stage 24); without it, runs automatically after all config files deployed
```

# Verification

Run `./deploy.sh --no-run` → routing.sh should NOT fire at stage 11 OR stage 24.
Run `./deploy.sh` → routing.sh fires exactly once, at `[24/24]`, after white-list-extended.txt and ru-exclude.txt are deployed.
Check output: `[21/24]` appears once (white-list-extended.txt), `[21b/24]` appears once (ru-exclude.txt).
