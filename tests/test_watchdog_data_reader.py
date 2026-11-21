import json
import unittest
from unittest.mock import MagicMock, Mock

from watchdog_data_reader import read_json_object


class WatchdogDataReaderTests(unittest.TestCase):
    def response(self, body, status=200, content_type="application/json"):
        item = MagicMock()
        item.read.return_value = body
        item.status = status
        item.headers = {"Content-Type": content_type}
        item.__enter__ = Mock(return_value=item)
        item.__exit__ = Mock(return_value=False)
        return item

    def test_reads_complete_large_json_object(self):
        payload = {"updated": "2026-11-21T10:00:00Z", "padding": "x" * (1024 * 1024 + 50)}
        raw = json.dumps(payload).encode("utf-8")
        opener = Mock(return_value=self.response(raw))
        result, byte_count = read_json_object(
            "https://raw.example/data.json", opener=opener, sleep_fn=Mock()
        )
        self.assertEqual(result, payload)
        self.assertEqual(byte_count, len(raw))
        self.assertGreater(byte_count, 1024 * 1024)
        request = opener.call_args.args[0]
        self.assertEqual(request.get_header("Cache-control"), "no-cache, no-store")
        self.assertIn("watchdog=", request.full_url)

    def test_retries_empty_then_valid_response(self):
        opener = Mock(side_effect=[
            self.response(b"", content_type="text/plain"),
            self.response(b'{"updated":"2026-11-21T10:00:00Z"}'),
        ])
        pause = Mock()
        data, _ = read_json_object("https://raw.example/data.json", opener=opener, sleep_fn=pause)
        self.assertIn("updated", data)
        self.assertEqual(opener.call_count, 2)
        pause.assert_called_once_with(5)

    def test_retries_malformed_json_then_valid_response(self):
        opener = Mock(side_effect=[
            self.response(b"{not-json"),
            self.response(b'{"ok":true}'),
        ])
        data, _ = read_json_object("https://raw.example/data.json", opener=opener, sleep_fn=Mock())
        self.assertEqual(data, {"ok": True})

    def test_rejects_non_object_json(self):
        with self.assertRaisesRegex(RuntimeError, "root must be a JSON object"):
            read_json_object(
                "https://raw.example/data.json",
                opener=Mock(return_value=self.response(b"[]")),
                sleep_fn=Mock(),
                attempts=1,
            )

    def test_fails_safely_after_all_retries(self):
        opener = Mock(return_value=self.response(b""))
        pause = Mock()
        with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
            read_json_object(
                "https://raw.example/data.json", opener=opener, sleep_fn=pause
            )
        self.assertEqual(opener.call_count, 3)
        self.assertEqual(pause.call_count, 2)


if __name__ == "__main__":
    unittest.main()
