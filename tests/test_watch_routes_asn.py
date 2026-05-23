"""
tests/test_watch_routes_asn.py — pytest suite for ASN background-thread enrichment
in scripts/watch-routes.py (plan 07-03).

Imports watch-routes.py via importlib because the filename contains a hyphen,
which makes the standard `import` statement invalid.
"""

import importlib.util
import json
import subprocess
import sys
import threading
import types
import unittest
from unittest.mock import MagicMock, patch

# ─── Load the module using importlib (Pitfall 8 — hyphen in filename) ─────────

_SPEC = importlib.util.spec_from_file_location(
    "watch_routes",
    "scripts/watch-routes.py",
)
wr: types.ModuleType = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(wr)  # type: ignore[union-attr]


# ─── Helpers ──────────────────────────────────────────────────────────────────

_SAMPLE_ARGS = dict(
    ts="2026-05-21T11:36:21",
    tag="VPN",
    src="192.168.1.175",
    dst="8.8.8.8",
    proto="TCP",
    dpt="443",
    no_dns=True,
)


def _reset_asn_state() -> None:
    """Clear _asn_cache between tests without replacing the lock object."""
    with wr._asn_lock:
        wr._asn_cache.clear()


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestFormatLineAsnSuffix(unittest.TestCase):
    """Tests 1–3: format_line respects the three _asn_cache value states."""

    def setUp(self) -> None:
        _reset_asn_state()

    def tearDown(self) -> None:
        _reset_asn_state()

    def test_1_cache_hit_with_org_appends_suffix(self) -> None:
        """Test 1: Pre-populated cache with org → line ends with ' | GOOGLE, US'."""
        wr._asn_cache["8.8.8.8"] = {"asn": "15169", "org": "GOOGLE, US"}
        result = wr.format_line(**_SAMPLE_ARGS, enable_asn=True)
        self.assertTrue(
            result.endswith(" | GOOGLE, US"),
            f"Expected ' | GOOGLE, US' suffix, got: {result!r}",
        )

    def test_2_cache_inflight_no_suffix(self) -> None:
        """Test 2: Cache value None (in-flight) → no ' | org' suffix."""
        wr._asn_cache["8.8.8.8"] = None
        result = wr.format_line(**_SAMPLE_ARGS, enable_asn=True)
        self.assertNotIn(" | ", result)

    def test_3_cache_empty_dict_no_suffix(self) -> None:
        """Test 3: Cache value {} (completed, no result) → no ' | org' suffix."""
        wr._asn_cache["8.8.8.8"] = {}
        result = wr.format_line(**_SAMPLE_ARGS, enable_asn=True)
        self.assertNotIn(" | ", result)


class TestLookupAsyncDedup(unittest.TestCase):
    """Test 4: cache miss triggers lookup_async once; second call does not spawn again."""

    def setUp(self) -> None:
        _reset_asn_state()

    def tearDown(self) -> None:
        _reset_asn_state()

    def test_4_cache_miss_triggers_lookup_async_no_duplicate(self) -> None:
        """Test 4: On cache miss, format_line spawns one thread; subsequent call skips."""
        spawned = []

        original_lookup_async = wr.lookup_async

        def mock_lookup_async(ip: str) -> None:
            spawned.append(ip)
            # actually set sentinel so second call sees it
            with wr._asn_lock:
                wr._asn_cache[ip] = None

        with patch.object(wr, "lookup_async", side_effect=mock_lookup_async):
            # First call — cache miss
            wr.format_line(**_SAMPLE_ARGS, enable_asn=True)
            # Second call — should see None sentinel and not re-spawn
            wr.format_line(**_SAMPLE_ARGS, enable_asn=True)

        self.assertEqual(spawned.count("8.8.8.8"), 1, "lookup_async called more than once for same IP")


class TestDoLookupSubprocess(unittest.TestCase):
    """Tests 5 & 6: _do_lookup populates _asn_cache correctly."""

    def setUp(self) -> None:
        _reset_asn_state()

    def tearDown(self) -> None:
        _reset_asn_state()

    def test_5_do_lookup_valid_json_populates_cache(self) -> None:
        """Test 5: Subprocess returns valid JSON → _asn_cache[ip] == parsed dict."""
        ip = "8.8.8.8"
        payload = json.dumps({ip: {"asn": "15169", "org": "GOOGLE, US"}})

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = payload + "\n"

        with patch("subprocess.run", return_value=mock_result):
            wr._do_lookup(ip)

        with wr._asn_lock:
            cached = wr._asn_cache.get(ip)

        self.assertEqual(cached, {"asn": "15169", "org": "GOOGLE, US"})

    def test_6_do_lookup_timeout_sets_empty_dict(self) -> None:
        """Test 6: subprocess.TimeoutExpired → _asn_cache[ip] == {}."""
        ip = "9.9.9.9"

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="python3", timeout=5.0)):
            wr._do_lookup(ip)

        with wr._asn_lock:
            cached = wr._asn_cache.get(ip, "__unset__")

        self.assertEqual(cached, {}, f"Expected empty dict sentinel, got: {cached!r}")


class TestLookupAsyncIdempotent(unittest.TestCase):
    """Test 7: Concurrent lookup_async calls result in exactly one subprocess invocation."""

    def setUp(self) -> None:
        _reset_asn_state()

    def tearDown(self) -> None:
        _reset_asn_state()

    def test_7_concurrent_lookup_async_single_subprocess(self) -> None:
        """Test 7: Two lookup_async calls for same IP → subprocess.run called at most once."""
        ip = "1.1.1.1"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({ip: {"asn": "13335", "org": "CLOUDFLARE"}}) + "\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            # Trigger both calls; second should see sentinel and bail early.
            wr.lookup_async(ip)
            wr.lookup_async(ip)
            # Allow daemon threads to complete
            for t in threading.enumerate():
                if t.name != "MainThread" and t.daemon:
                    t.join(timeout=2.0)

        self.assertLessEqual(
            mock_run.call_count, 1,
            f"Expected at most 1 subprocess.run call, got {mock_run.call_count}",
        )


class TestNoAsnFlag(unittest.TestCase):
    """Test 8: --no-asn flag prevents org suffix."""

    def setUp(self) -> None:
        _reset_asn_state()

    def tearDown(self) -> None:
        _reset_asn_state()

    def test_8_no_asn_flag_disables_enrichment(self) -> None:
        """Test 8: enable_asn=False → never appends ' | org', even with cached result."""
        wr._asn_cache["8.8.8.8"] = {"asn": "15169", "org": "GOOGLE, US"}
        result = wr.format_line(**_SAMPLE_ARGS, enable_asn=False)
        self.assertNotIn(" | ", result, "Expected no ' | org' suffix when enable_asn=False")


class TestHelpFlag(unittest.TestCase):
    """Test 9 (re-spec'd as --help includes --no-asn)."""

    def test_help_exits_0_and_contains_no_asn(self) -> None:
        """Test 9 (as --help): --help exits 0 and stdout mentions --no-asn."""
        import subprocess as sp
        result = sp.run(
            [sys.executable, "scripts/watch-routes.py", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--no-asn", result.stdout)


class TestBackwardCompat(unittest.TestCase):
    """Test 9 alt: Existing positional format_line call still works."""

    def setUp(self) -> None:
        _reset_asn_state()

    def tearDown(self) -> None:
        _reset_asn_state()

    def test_9_backward_compat_positional_call(self) -> None:
        """Test 9: format_line with original positional args (no enable_asn) works."""
        wr._asn_cache["8.8.8.8"] = {"asn": "15169", "org": "GOOGLE, US"}
        # Call using all positional args (no keyword enable_asn)
        result = wr.format_line(
            "2026-05-21T11:36:21",
            "VPN",
            "192.168.1.175",
            "8.8.8.8",
            "TCP",
            "443",
            True,  # no_dns
        )
        # enable_asn defaults to True, so org suffix should appear
        self.assertTrue(
            result.endswith(" | GOOGLE, US"),
            f"Backward-compat call failed; got: {result!r}",
        )


if __name__ == "__main__":
    unittest.main()
