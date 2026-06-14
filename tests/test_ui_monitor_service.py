import json
import tempfile
import unittest
from pathlib import Path

from ui.services.monitor_service import MonitorService, read_recent_jsonl


class RecentJsonlTests(unittest.TestCase):
    def test_reads_only_complete_records_from_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshots.jsonl"
            records = [{"id": i, "value": "x" * 20} for i in range(6)]
            path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            recent = read_recent_jsonl(path, max_bytes=100)

            self.assertTrue(recent)
            self.assertEqual(recent[-1], records[-1])
            self.assertGreater(recent[0]["id"], 0)


class SchedulerLogParsingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "logs").mkdir()
        self.service = MonitorService(str(base))
        self.service.log_file.write_text(
            "\n".join([
                "[2026-06-14 10:00:00] Run #41 started",
                "[2026-06-14 10:00:02] Signals: 2 (Confirmed: 1, Watch: 1)",
                "[2026-06-14 10:00:03] Duration: 3.0s",
                "[2026-06-14 10:00:03] Run #41 completed",
                "[2026-06-14 10:05:00] Run #42 started",
                "[2026-06-14 10:05:02] Signals: 0 (Confirmed: 0, Watch: 0)",
                "[2026-06-14 10:05:04] Duration: 4.0s",
                "[2026-06-14 10:05:04] Run #42 completed",
            ]) + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_last_run_uses_its_own_signal_block(self):
        result = self.service.get_last_run_info()

        self.assertEqual(result["run_id"], 42)
        self.assertEqual(result["signals"], 0)
        self.assertEqual(result["duration"], 4.0)

    def test_recent_runs_keep_signal_counts_with_correct_run(self):
        runs = self.service.get_recent_runs(2)

        self.assertEqual([run["run_id"] for run in runs], [42, 41])
        self.assertEqual(runs[0]["signals"], 0)
        self.assertEqual(runs[1]["signals"], 2)
        self.assertEqual(runs[1]["confirmed"], 1)
        self.assertEqual(runs[1]["watch_only"], 1)


if __name__ == "__main__":
    unittest.main()
