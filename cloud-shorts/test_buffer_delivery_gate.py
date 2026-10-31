"""No real Buffer API calls; safety tests for confirmed-only refill."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from buffer_delivery_gate import parse_confirmed, confirm, dispatch_next

GOOD = {"queued": True, "episode": "clip-01",
        "buffer_post_id": "buffer-post-12345",
        "due_at": "2026-10-31T14:00:00Z"}


class BufferDeliveryGateTests(unittest.TestCase):
    def test_only_real_accepted_post_allows_refill(self):
        self.assertEqual(parse_confirmed("some audit\n" + json.dumps(GOOD)),
                         GOOD)
        with tempfile.TemporaryDirectory() as tmp:
            log, out = Path(tmp) / "res", Path(tmp) / "out"
            log.write_text(json.dumps(GOOD), encoding="utf8")
            confirm(log, out)
            self.assertEqual(out.read_text(), "queued=true\n")

    def test_skipped_rejected_or_missing_due_at_stops_chain(self):
        failures = ['', '{"skipped":"approved MP4 missing"}',
                    '{"queued":true,"episode":"clip-01"}',
                    '{"queued":true,"episode":"clip-01","buffer_post_id":"x"}',
                    '{"queued":true,"episode":"clip-01","buffer_post_id":"x","due_at":null}',
                    '{"queued":false,"episode":"clip-01","buffer_post_id":"x","due_at":"2026-10-31T13:00Z"}']
        for body in failures:
            with self.subTest(body=body), self.assertRaises(RuntimeError):
                parse_confirmed(body)

    def test_dispatch_uses_fixed_repo_and_workflow(self):
        dummy = Mock()
        dummy.status = 204
        session = MagicMock()
        session.__enter__.return_value = dummy
        urlopen = Mock(return_value=session)
        dispatch_next("test-only-token", "GUSTAVA009/moto-shorts-cloud", urlopen=urlopen)
        request = urlopen.call_args[0][0]
        self.assertIn("buffer-backlog.yml/dispatches", request.full_url)
        self.assertEqual(json.loads(request.data), {"ref": "main"})

    def test_other_repo_cannot_trigger(self):
        with self.assertRaises(RuntimeError):
            dispatch_next("token", "wrong/repo", urlopen=Mock())


if __name__ == "__main__":
    unittest.main()
