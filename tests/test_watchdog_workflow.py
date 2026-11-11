import unittest
from pathlib import Path


class WatchdogWorkflowConfigTests(unittest.TestCase):
    def test_watchdog_resolves_pdmp_scan_by_workflow_file_path(self):
        watchdog = Path(".github/workflows/scan-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn('/actions/workflows/scan.yml', watchdog)
        self.assertIn('scan_workflow.get("id")', watchdog)
        self.assertNotIn("workflow_id=389470309", watchdog)

    def test_watchdog_recovery_event_is_accepted_by_pdmp_scan(self):
        watchdog = Path(".github/workflows/scan-watchdog.yml").read_text(encoding="utf-8")
        scan = Path(".github/workflows/scan.yml").read_text(encoding="utf-8")
        self.assertIn('event_type": "scan-watchdog"', watchdog)
        self.assertIn("repository_dispatch:", scan)
        self.assertIn("types: [scan-watchdog]", scan)

    def test_watchdog_keeps_ten_minute_stale_data_check(self):
        watchdog = Path(".github/workflows/scan-watchdog.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "*/10 * * * *"', watchdog)
        self.assertIn("age_minutes <= 35", watchdog)


if __name__ == "__main__":
    unittest.main()
