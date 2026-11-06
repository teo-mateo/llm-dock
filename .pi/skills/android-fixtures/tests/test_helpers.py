import importlib.util
import io
from contextlib import redirect_stdout
from unittest.mock import patch
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from server import FixtureServer
from scenarios import sessions

UI_PATH = SKILL.parent / "android-emulator/scripts/ui.py"
spec = importlib.util.spec_from_file_location("android_ui", UI_PATH)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.server = FixtureServer(("127.0.0.1", 0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def get(self, path):
        with urlopen(self.base + path, timeout=3) as response:
            return json.load(response)

    def post(self, path, body):
        request = Request(self.base + path, data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_auth_is_synthetic_and_unknown_paths_fail(self):
        self.assertEqual(self.get("/api/health"), {"status": "healthy"})
        self.assertEqual(self.post("/api/auth/session", {"password": "fixture"})["token"], "fixture-only-token")
        with self.assertRaises(HTTPError) as caught:
            self.get("/api/not-implemented")
        self.assertEqual(caught.exception.code, 404)

    def test_scenario_cli_changes_get_without_affecting_server_data(self):
        subprocess.run([sys.executable, str(SKILL / "scripts/scenario.py"), "waiting",
                        "--port", str(self.server.server_port)], capture_output=True, check=True)
        rows = self.get("/api/pi/sessions")["sessions"]
        self.assertTrue(rows[0]["live"])
        self.assertEqual(len(rows[0]["prompts"]), 1)
        self.assertFalse(rows[1]["live"])
        rows[0]["prompts"].clear()
        self.assertEqual(len(self.get("/api/pi/sessions")["sessions"][0]["prompts"]), 1)

    def test_connected_sse_receives_open_then_close(self):
        with urlopen(self.base + "/api/pi/sessions/stream", timeout=3) as stream:
            initial = self.read_frame(stream)
            self.assertEqual(initial["type"], "snapshot")
            self.assertEqual(initial["sessions"][0]["prompts"], [])
            self.post("/__fixture/scenario", {"name": "waiting"})
            live, ended = self.read_frame(stream), self.read_frame(stream)
            self.assertEqual(live["type"], "session")
            self.assertEqual(live["session_id"], "fixture-live")
            self.assertEqual(len(live["prompts"]), 1)
            self.assertFalse(ended["live"])
            self.post("/__fixture/scenario", {"name": "empty"})
            self.assertEqual(self.read_frame(stream)["prompts"], [])

    def read_frame(self, stream):
        while True:
            line = stream.readline()
            if not line:
                self.fail("stream ended before expected data")
            if line.startswith(b"data: "):
                return json.loads(line[6:])

    def test_compatibility_and_invalid_scenarios(self):
        self.assertNotIn("prompts", sessions("absent")[0])
        self.assertTrue(all(not row["live"] for row in sessions("offline")))
        with self.assertRaises(HTTPError) as caught:
            self.post("/__fixture/scenario", {"name": "typo"})
        self.assertEqual(caught.exception.code, 400)


class UiTests(unittest.TestCase):
    def test_exact_tag_and_package_suffix_not_substring(self):
        xml = '<hierarchy><node resource-id="app:id/answer-10" bounds="[0,0][1,1]"/><node resource-id="app:id/answer-1" bounds="[10,20][30,40]"/></hierarchy>'
        self.assertEqual(ui.find_bounds(xml, "answer-1"), (10, 20, 30, 40))
        self.assertIsNone(ui.find_bounds(xml, "answer"))

    def test_dump_trailing_diagnostic_is_not_xml(self):
        raw = 'noise\n<?xml version="1.0"?><hierarchy></hierarchy>\nUI dumped to /dev/tty'
        self.assertEqual(ui.hierarchy(raw), '<?xml version="1.0"?><hierarchy></hierarchy>')

    def test_slow_dump_retries_within_budget(self):
        result = subprocess.CompletedProcess([], 0, '<hierarchy><node resource-id="ready" bounds="[0,0][20,20]"/></hierarchy>')
        with patch.object(sys, "argv", ["ui.py", "--device", "emulator-5554", "wait", "ready"]), \
             patch.object(ui.subprocess, "run", side_effect=[subprocess.TimeoutExpired("adb", 5), result]) as run, \
             patch.object(ui.time, "monotonic", side_effect=[0, 0.1, 5.1, 5.2]), redirect_stdout(io.StringIO()):
            ui.main()
        self.assertEqual(run.call_count, 2)
        self.assertLessEqual(run.call_args.kwargs["timeout"], 5)

    def test_slow_dump_stops_at_deadline(self):
        with patch.object(sys, "argv", ["ui.py", "--device", "emulator-5554", "wait", "ready"]), \
             patch.object(ui.subprocess, "run", side_effect=subprocess.TimeoutExpired("adb", 5)), \
             patch.object(ui.time, "monotonic", side_effect=[0, 0.1, 15.1]):
            with self.assertRaisesRegex(ValueError, "UI dump timed out waiting for tag: ready"):
                ui.main()

    def test_physical_device_is_rejected_before_adb(self):
        result = subprocess.run([sys.executable, str(UI_PATH), "--device", "physical-phone",
                                 "tap", "anything"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("only emulator targets", result.stderr)


if __name__ == "__main__":
    unittest.main()
