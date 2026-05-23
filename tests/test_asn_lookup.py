"""
tests/test_asn_lookup.py — Unit tests for scripts/asn-lookup.py

All 13 tests use unittest.mock to avoid live Cymru network calls.
Recorded fixture response mirrors the real Cymru bulk-mode output format.
"""

import importlib.util
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ─── Import asn-lookup.py despite the hyphenated filename ─────────────────────

_SCRIPT = Path(__file__).parent.parent / "scripts" / "asn-lookup.py"
spec = importlib.util.spec_from_file_location("asn_lookup", _SCRIPT)
asn_lookup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(asn_lookup)

# ─── Fixture: recorded Cymru bulk-mode response ───────────────────────────────

CYMRU_FIXTURE = (
    b"Bulk mode; whois.cymru.com [2026-05-23 10:00:00 +0000]\r\n"
    b" 15169  | 8.8.8.8         | 8.8.8.0/24   | US | arin | 2014-03-14 | GOOGLE, US\r\n"
    b" 13335  | 1.1.1.1         | 1.1.1.0/24   | AU | apnic | 2010-07-14 | CLOUDFLARENET, US\r\n"
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_socket_mock(response_bytes: bytes) -> MagicMock:
    """Return a socket mock whose makefile() yields *response_bytes*."""
    mock_sock = MagicMock()
    mock_file = BytesIO(response_bytes)
    mock_sock.makefile.return_value = mock_file
    return mock_sock


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestCymruBulkLookup(unittest.TestCase):
    """Tests 1–5: _cymru_bulk_lookup."""

    def test_1_returns_both_ips_with_asn_and_org(self):
        """Test 1: Given two IPs, returns dict with both IPs, asn all-digits, org non-empty."""
        mock_sock = _make_socket_mock(CYMRU_FIXTURE)
        with patch("socket.socket", return_value=mock_sock):
            result = asn_lookup._cymru_bulk_lookup(["8.8.8.8", "1.1.1.1"])

        self.assertIn("8.8.8.8", result)
        self.assertIn("1.1.1.1", result)
        self.assertTrue(result["8.8.8.8"]["asn"].isdigit(), "asn must be all-digits")
        self.assertTrue(result["1.1.1.1"]["asn"].isdigit(), "asn must be all-digits")
        self.assertTrue(result["8.8.8.8"]["org"], "org must be non-empty")
        self.assertTrue(result["1.1.1.1"]["org"], "org must be non-empty")

    def test_2_empty_list_returns_empty_dict_no_socket(self):
        """Test 2: Empty input → {} and socket.socket is never called."""
        with patch("socket.socket") as mock_socket_cls:
            result = asn_lookup._cymru_bulk_lookup([])
        self.assertEqual(result, {})
        mock_socket_cls.assert_not_called()

    def test_3_socket_timeout_returns_empty_dict(self):
        """Test 3: socket.timeout during connect → return {} (no exception propagated)."""
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = socket.timeout("timed out")
        with patch("socket.socket", return_value=mock_sock):
            result = asn_lookup._cymru_bulk_lookup(["8.8.8.8"])
        self.assertEqual(result, {})

    def test_3b_oserror_returns_empty_dict(self):
        """Test 3 (variant): OSError during connect → return {} (no exception propagated)."""
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = OSError("connection refused")
        with patch("socket.socket", return_value=mock_sock):
            result = asn_lookup._cymru_bulk_lookup(["8.8.8.8"])
        self.assertEqual(result, {})

    def test_4_header_line_is_skipped(self):
        """Test 4: 'Bulk mode; whois.cymru.com [...]' header is not a result key."""
        mock_sock = _make_socket_mock(CYMRU_FIXTURE)
        with patch("socket.socket", return_value=mock_sock):
            result = asn_lookup._cymru_bulk_lookup(["8.8.8.8"])
        for key in result:
            self.assertFalse(
                key.startswith("Bulk mode"),
                f"Header line leaked into result as key: {key!r}",
            )

    def test_5_whitespace_stripped_from_ip_key(self):
        """Test 5: IP key has no surrounding spaces despite Cymru padding."""
        # Fixture line has ' 8.8.8.8         ' between pipes
        mock_sock = _make_socket_mock(CYMRU_FIXTURE)
        with patch("socket.socket", return_value=mock_sock):
            result = asn_lookup._cymru_bulk_lookup(["8.8.8.8"])
        self.assertIn("8.8.8.8", result, "Key must be exactly '8.8.8.8' — no padding")
        self.assertNotIn(" 8.8.8.8 ", result)
        self.assertEqual(result["8.8.8.8"]["asn"], "15169")
        self.assertEqual(result["8.8.8.8"]["org"], "GOOGLE, US")


class TestCache(unittest.TestCase):
    """Tests 6–9: load_cache / save_cache."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmp_dir, "test-cache.json")
        # Redirect module's CACHE_FILE to our temp path for all cache tests
        self._orig_cache_file = asn_lookup.CACHE_FILE
        asn_lookup.CACHE_FILE = self.cache_path

    def tearDown(self):
        asn_lookup.CACHE_FILE = self._orig_cache_file
        # Clean up temp dir
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_6_save_and_load_roundtrip(self):
        """Test 6: save_cache + load_cache round-trip preserves data exactly."""
        data = {"8.8.8.8": {"asn": "15169", "org": "GOOGLE"}}
        asn_lookup.save_cache(data)
        result = asn_lookup.load_cache()
        self.assertEqual(result, data)

    def test_7_save_cache_uses_os_replace(self):
        """Test 7: save_cache calls os.replace for atomic write."""
        data = {"1.1.1.1": {"asn": "13335", "org": "CLOUDFLARENET"}}
        with patch("os.replace", wraps=os.replace) as mock_replace:
            asn_lookup.save_cache(data)
        mock_replace.assert_called_once()
        # Second arg (destination) must be our cache path
        _, dest = mock_replace.call_args[0]
        self.assertEqual(dest, self.cache_path)

    def test_8_missing_cache_returns_empty_dict(self):
        """Test 8: load_cache returns {} when file does not exist."""
        # cache_path doesn't exist yet
        result = asn_lookup.load_cache()
        self.assertEqual(result, {})

    def test_8b_malformed_cache_returns_empty_dict(self):
        """Test 8 (variant): load_cache returns {} on malformed JSON."""
        with open(self.cache_path, "w") as fh:
            fh.write("not valid json {{{{")
        result = asn_lookup.load_cache()
        self.assertEqual(result, {})

    def test_9_cache_file_mode_is_0o666(self):
        """Test 9: file mode is 0o666 after save_cache."""
        data = {"8.8.8.8": {"asn": "15169", "org": "GOOGLE"}}
        asn_lookup.save_cache(data)
        mode = stat.S_IMODE(os.stat(self.cache_path).st_mode)
        self.assertEqual(mode, 0o666, f"Expected 0o666, got {oct(mode)}")


class TestMainCLI(unittest.TestCase):
    """Tests 10–13: subprocess / main() integration."""

    SCRIPT = str(_SCRIPT)

    def test_10_empty_stdin_emits_empty_json_and_exit0(self):
        """Test 10: pipe empty string → stdout is '{}' and exit code is 0."""
        result = subprocess.run(
            [sys.executable, self.SCRIPT],
            input="",
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})

    def test_11_piped_ips_produce_valid_json_dict(self):
        """Test 11: piping IPs → stdout is a valid JSON dict (may be empty if offline)."""
        result = subprocess.run(
            [sys.executable, self.SCRIPT],
            input="8.8.8.8\n1.1.1.1\n",
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        parsed = json.loads(result.stdout)
        self.assertIsInstance(parsed, dict)
        # All returned keys must be IPs from the input
        for key in parsed:
            self.assertIn(key, {"8.8.8.8", "1.1.1.1"})

    def test_12_second_call_uses_cache_no_cymru(self):
        """Test 12: second call with cached IPs passes [] to _cymru_bulk_lookup."""
        data = {"8.8.8.8": {"asn": "15169", "org": "GOOGLE, US"}}
        # Pre-populate the cache so no Cymru call is needed
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmp:
            json.dump(data, tmp)
            tmp_cache = tmp.name

        try:
            orig = asn_lookup.CACHE_FILE
            asn_lookup.CACHE_FILE = tmp_cache

            call_args_seen = []

            def capturing_cymru(ips, timeout=asn_lookup.DEFAULT_TIMEOUT):
                call_args_seen.append(list(ips))
                return {}

            with patch.object(asn_lookup, "_cymru_bulk_lookup", side_effect=capturing_cymru):
                asn_lookup.lookup_ips(["8.8.8.8"])

            # _cymru_bulk_lookup must have been called with empty list (cache hit)
            self.assertEqual(call_args_seen, [[]], f"Expected [[]], got {call_args_seen}")
        finally:
            asn_lookup.CACHE_FILE = orig
            os.unlink(tmp_cache)

    def test_13_help_exits_0_and_contains_required_strings(self):
        """Test 13: --help exits 0 and stdout contains 'stdin' and '/tmp/vpn-asn-cache.json'."""
        result = subprocess.run(
            [sys.executable, self.SCRIPT, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        combined = result.stdout + result.stderr  # argparse may use either
        self.assertIn("stdin", combined, "--help must mention 'stdin'")
        self.assertIn(
            "/tmp/vpn-asn-cache.json", combined,
            "--help must mention '/tmp/vpn-asn-cache.json'",
        )


if __name__ == "__main__":
    unittest.main()
