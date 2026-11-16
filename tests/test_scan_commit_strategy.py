import unittest
from pathlib import Path


class ScanCommitStrategyTests(unittest.TestCase):
    def test_scan_outputs_are_not_rebased_into_mixed_json_snapshots(self):
        workflow = Path(".github/workflows/scan.yml").read_text(encoding="utf-8")
        self.assertIn('git fetch origin "$GITHUB_REF_NAME"', workflow)
        self.assertIn('git reset --mixed "origin/$GITHUB_REF_NAME"', workflow)
        self.assertIn('git push origin "HEAD:$GITHUB_REF_NAME"', workflow)
        self.assertNotIn("git pull --rebase -X theirs", workflow)


if __name__ == "__main__":
    unittest.main()
