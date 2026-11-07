import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from server import FixtureServer
from transcript import INSTANCE_ID, SESSION_ID, TURNS, TranscriptFixture
from transcript_http import CONTROL_PATH, SESSION_PATH


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.server = FixtureServer(("127.0.0.1", 0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.call("/__fixture/scenario", {"name": "cache"})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def call(self, path, body=None, method=None):
        request = Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"}, method=method)
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def control(self, action, **kwargs):
        return self.call(CONTROL_PATH, {"action": action, **kwargs})

    def stream(self, after):
        return urlopen(f"{self.base}{SESSION_PATH}/stream?after={after}", timeout=3)

    def frame(self, stream):
        while True:
            line = stream.readline()
            if line.startswith(b"data: "):
                return json.loads(line[6:])
            if not line:
                self.fail("fixture stream ended")

    def test_representative_payload_and_identity_are_deterministic(self):
        first = self.call(CONTROL_PATH)
        self.assertEqual(first["event_count"], TURNS * 16)
        self.assertGreater(first["event_json_bytes"], 6 * 1024 * 1024)
        self.assertGreater(first["event_bytes_by_type"]["tool_end"], 2 * 1024 * 1024)
        self.assertGreater(first["event_bytes_by_type"]["assistant_message"], 512 * 1024)
        rows = self.call("/api/pi/sessions")["sessions"]
        self.assertEqual((rows[0]["session_id"], rows[0]["instance_id"]), (SESSION_ID, INSTANCE_ID))
        self.assertEqual(rows[0]["first_seen"], self.call("/api/pi/sessions")["sessions"][0]["first_seen"])
        second = TranscriptFixture()
        self.assertEqual(first["event_json_bytes"], second.stats()["event_json_bytes"])
        self.assertEqual(len({event["seq"] for event in second.events}), TURNS * 16)

    def test_full_paged_replay_is_ordered_lossless_and_summary_follows_events(self):
        with self.stream(0) as stream:
            observed = []
            while True:
                frame = self.frame(stream)
                if frame["type"] == "session":
                    break
                self.assertEqual(frame["type"], "events")
                self.assertLessEqual(len(frame["events"]), 500)
                observed.extend(event["seq"] for event in frame["events"])
            self.assertEqual(observed, list(range(1, TURNS * 16 + 1)))
            with self.server.state.condition:
                self.assertTrue(self.server.state.condition.wait_for(
                    lambda: self.server.state.transcript.requests[-1]["summary_sent"], timeout=3))
            request = self.call(CONTROL_PATH)["requests"][-1]
            self.assertEqual(request["after"], 0)
            self.assertEqual(request["sent_events"], TURNS * 16)
            self.assertEqual(sum(batch["count"] for batch in request["batches"]), TURNS * 16)

    def test_resume_and_live_suffix_send_only_new_events(self):
        latest = self.call(CONTROL_PATH)["latest_seq"]
        with self.stream(latest - 3) as stream:
            self.assertEqual([event["seq"] for event in self.frame(stream)["events"]], list(range(latest - 2, latest + 1)))
            self.assertEqual(self.frame(stream)["type"], "session")
            self.control("append")
            suffix = self.frame(stream)
            self.assertEqual([event["seq"] for event in suffix["events"]], list(range(latest + 1, latest + 17)))
            self.assertEqual(self.frame(stream)["type"], "session")
        stats = self.call(CONTROL_PATH)
        self.assertEqual(stats["requests"][-1]["sent_events"], 19)
        self.assertEqual(stats["suffixes"], 1)
        self.assertEqual(stats["requests"][-1]["after"], latest - 3)

    def test_replay_and_summary_gates_are_independent_observable_boundaries(self):
        latest = self.call(CONTROL_PATH)["latest_seq"]
        self.control("gate", gate="replay")
        with self.stream(latest - 1) as stream:
            waiting = self.call(CONTROL_PATH)["requests"][-1]
            self.assertEqual(waiting["sent_events"], 0)
            self.assertFalse(waiting["summary_sent"])
            self.control("gate", gate="summary")
            self.assertEqual(self.frame(stream)["events"][0]["seq"], latest)
            self.assertFalse(self.call(CONTROL_PATH)["requests"][-1]["summary_sent"])
            self.control("gate", gate="open")
            self.assertEqual(self.frame(stream)["type"], "session")

    def test_offline_recovery_and_validation_do_not_fake_success(self):
        latest = self.control("offline")["latest_seq"]
        with self.assertRaises(HTTPError) as caught:
            self.stream(latest)
        self.assertEqual(caught.exception.code, 503)
        self.control("append")
        self.control("online")
        with self.stream(latest) as stream:
            self.assertEqual(len(self.frame(stream)["events"]), 16)
            self.assertEqual(self.frame(stream)["type"], "session")
        for path in (SESSION_PATH + "/stream?after=-1", SESSION_PATH + "/stream?after=bad"):
            with self.assertRaises(HTTPError) as caught:
                self.call(path)
            self.assertEqual(caught.exception.code, 400)
        with self.assertRaises(HTTPError) as caught:
            self.control("gate", gate="typo")
        self.assertEqual(caught.exception.code, 400)

    def test_live_delete_rejected_then_ended_delete_notifies_list_and_detail(self):
        with self.assertRaises(HTTPError) as caught:
            self.call(SESSION_PATH, method="DELETE")
        self.assertEqual(caught.exception.code, 409)
        latest = self.call(CONTROL_PATH)["latest_seq"]
        with urlopen(self.base + "/api/pi/sessions/stream", timeout=3) as listing, self.stream(latest) as detail:
            self.assertEqual(self.frame(listing)["type"], "snapshot")
            self.assertEqual(self.frame(detail)["type"], "session")
            self.control("end")
            self.assertFalse(self.frame(listing)["live"])
            self.assertFalse(self.frame(detail)["live"])
            self.assertEqual(self.call(SESSION_PATH, method="DELETE"), {"deleted": True})
            self.assertEqual(self.frame(listing)["type"], "session_removed")
            self.assertEqual(self.frame(detail)["type"], "session_removed")
        self.assertEqual(self.call("/api/pi/sessions"), {"sessions": []})
        with self.assertRaises(HTTPError) as caught:
            self.stream(latest)
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
