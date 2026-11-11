import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


class DashboardStaleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("Node.js is required to execute the dashboard guard")
        html = Path("dashboard.html").read_text(encoding="utf-8")
        start = html.index("function updateTradeGuard(data) {")
        end_marker = "\n}\n\nfunction classify"
        end = html.index(end_marker, start) + 2
        function_source = html[start:end]
        script = r"""
const fs = require("fs");
const html = fs.readFileSync("dashboard.html", "utf8");
const start = html.indexOf("function updateTradeGuard(data) {");
const end = html.indexOf("\n}\n\nfunction classify", start) + 2;
const fn = html.slice(start, end);
const box = { className: "", innerHTML: "", attrs: {},
  setAttribute(k, v) { this.attrs[k] = v; } };
global.document = { getElementById() { return box; } };
global.esc = value => String(value).replace(/[&<>"']/g, ch => ({
  "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
}[ch]));
Date.now = () => Date.parse("2026-11-11T10:00:00Z");
eval(fn);
const cases = {
  fresh: { updated: "2026-11-11T09:30:00Z", trends: { stale: false } },
  old: { updated: "2026-11-11T09:14:00Z" },
  invalid: { updated: "not-a-date" },
  nested_stale: { updated: "2026-11-11T09:50:00Z", market_news: { stale: true } },
  future: { updated: "2026-11-11T10:10:00Z" }
};
const result = {};
for (const [name, data] of Object.entries(cases)) {
  updateTradeGuard(data);
  result[name] = { className: box.className, html: box.innerHTML, aria: box.attrs["aria-label"] };
}
console.log(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.results = json.loads(completed.stdout.strip())
        cls.html = html

    def test_fresh_data_keeps_existing_trinetra_branding(self):
        result = self.results["fresh"]
        self.assertEqual(result["className"], "brand-logo-only")
        self.assertIn("TRINETRA", result["html"])

    def test_data_older_than_45_minutes_blocks_trading(self):
        result = self.results["old"]
        self.assertEqual(result["className"], "block")
        self.assertIn("NO TRADE", result["html"])
        self.assertIn("45 मिनट", result["html"])

    def test_invalid_timestamp_blocks_trading(self):
        result = self.results["invalid"]
        self.assertEqual(result["className"], "block")
        self.assertIn("टाइमस्टैम्प", result["html"])

    def test_nested_stale_source_blocks_trading(self):
        result = self.results["nested_stale"]
        self.assertEqual(result["className"], "block")
        self.assertIn("पुराना/fallback", result["html"])

    def test_future_timestamp_blocks_trading(self):
        result = self.results["future"]
        self.assertEqual(result["className"], "block")
        self.assertIn("भविष्य", result["html"])

    def test_fetch_failure_shows_no_trade_instead_of_brand_only(self):
        self.assertIn("NO TRADE — डेटा लोड विफल", self.html)
        self.assertIn('guard.className = "block"', self.html)


if __name__ == "__main__":
    unittest.main()
