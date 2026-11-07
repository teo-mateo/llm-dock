import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("measure_cache", SCRIPTS / "measure_cache.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


class MeasurementTests(unittest.TestCase):
    def test_cached_zero_backlog_waits_for_summary_without_requiring_event_transition(self):
        for after, expected_catchup in ((16000, True), (16016, False)):
            waiting = {"after": after, "sent_events": 0, "summary_sent": False}
            finished = {"after": after, "sent_events": 16016 - after, "summary_sent": True}
            states = [
                {"event_count": 16016, "latest_seq": 16016}, {}, {"requests": [waiting]},
            ]
            if expected_catchup:
                states.append({})
            states.extend([{}, {"event_count": 16016, "latest_seq": 16016,
                                "event_json_bytes": 8_356_257, "requests": [finished]}])
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "measurement.json"
                with patch.object(sys, "argv", ["measure_cache.py", "hit", "--device", "emulator-5554", "--output", str(output)]), \
                     patch.object(measure, "fixture", side_effect=states), \
                     patch.object(measure, "ui") as ui, \
                     patch.object(measure, "checkpoint", return_value={"items": 7007}):
                    measure.main()
                labels = [call.args[2] for call in ui.call_args_list if call.args[1] == "wait-text"]
                self.assertEqual("Catching up…" in labels, expected_catchup)
                self.assertEqual(json.loads(output.read_text())["request"]["sent_events"], 16016 - after)

    def test_measurement_refuses_physical_device_before_network_or_ui(self):
        with patch.object(sys, "argv", ["measure_cache.py", "miss", "--device", "phone", "--output", "/unused"]), \
             patch.object(measure, "fixture") as fixture:
            with self.assertRaises(SystemExit):
                measure.main()
            fixture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
