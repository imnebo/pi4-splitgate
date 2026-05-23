# Phase 8 Discussion Log

**Date:** 2026-05-23
**Mode:** Interactive (default)

## Summary

Single-question discussion — user's requirements were clear, only gray areas were naming/behavior/deploy pattern.

## Areas Discussed

### Area: Implementation decisions

**Q: Which areas to discuss?**
Options: File naming / Absent file behavior / Deploy pattern
User: File naming → Claude decides. Absent file → silent skip. Deploy → same as white-list-extended.txt (Stage 21 pattern), no new stage.

## Decisions Captured

- D-01: `configs/ru-exclude.txt` (local), `/etc/ru-exclude.txt` (RPi)
- D-02: Format: one CIDR per line, `#` comments, blank lines skipped
- D-03: `.example` committed, actual file gitignored
- D-04: Absent/empty file → silent skip, URL unchanged
- D-05: Bash URL construction: append `&exclude[cidr4]=LINE` per CIDR
- D-06: Only `RU_SUBNET_URL` reference in curl changes; rest of script untouched
- D-07: Stage 21 pattern — conditional SCP alongside white-list-extended deploy
- D-08: No TOTAL_STAGES bump
- D-09: SHA256 rebuild behavior correct as-is (URL change → different server response → hash mismatch → rebuild)

## Deferred Ideas

None.
