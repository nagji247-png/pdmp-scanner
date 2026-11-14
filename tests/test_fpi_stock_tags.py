import json
import shutil
import subprocess
import unittest
from pathlib import Path


class FpiStockTagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("Node.js is required to execute the stock-tag helper")
        html = Path("dashboard.html").read_text(encoding="utf-8")
        start = html.index("function renderStockFpiTags(dashboardData, payload, sectorMap) {")
        end = html.index("\n}\n\nfunction renderFpiSectorTilt", start) + 2
        function_source = html[start:end]
        script = r"""
const fn = FUNCTION_SOURCE;
Date.now = () => Date.parse("2026-11-14T01:18:00Z");
function run({flow, scores, updated = "2026-11-14T01:12:00Z", endDate = "2026-10-31", verifiedOn = "2026-11-14"}) {
  const tags = [];
  const nameNode = { insertAdjacentElement(_position, tag) { tags.push(tag); } };
  function element() {
    return {
      children: [], attributes: {},
      append(...children) { this.children.push(...children); },
      setAttribute(key, value) { this.attributes[key] = value; },
      textContent: "", title: "", className: ""
    };
  }
  const cards = [{ dataset: { assetName: "TEST" }, querySelector(sel) { return sel === ".name" ? nameNode : null; } }];
  global.document = {
    querySelectorAll(sel) {
      if (sel === ".fpi-stock-tag") return tags;
      if (sel === ".card[data-asset-name]") return cards;
      return [];
    },
    createElement() { return element(); }
  };
  const headlines = scores.map((score, i) => ({ age_h: 4 + i, score }));
  const data = { updated, instruments: { TEST: { headlines } } };
  const payload = { history: [{ end_date: endDate, sectors: [{ name: "Test Sector", net_equity_cr: flow }] }] };
  const map = { verified_on: verifiedOn, stocks: { TEST: { sector: "Test Sector" } } };
  eval(fn);
  renderStockFpiTags(data, payload, map);
  return tags.map(x => ({
    label: x.children[0].textContent,
    details: x.children[1].children.map(child => child.textContent).join(" ")
  }));
}
console.log(JSON.stringify({
  aligned: run({flow: 100, scores: [2, 2]}),
  opposite: run({flow: -100, scores: [2, 2]}),
  weak: run({flow: -100, scores: [2, 0]}),
  staleDashboard: run({flow: -100, scores: [2, 2], updated: "2026-11-11T00:00:00Z"}),
  staleFpi: run({flow: -100, scores: [2, 2], endDate: "2026-09-01"}),
  staleMap: run({flow: -100, scores: [2, 2], verifiedOn: "2026-01-01"}),
  lowFlow: run({flow: -49, scores: [2, 2]})
}));
""".replace("FUNCTION_SOURCE", json.dumps(function_source))
        completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        cls.results = json.loads(completed.stdout.strip())

    def test_aligned_news_and_fpi_show_hawa_saath(self):
        self.assertEqual(self.results["aligned"][0]["label"], "हवा साथ 👁️")

    def test_opposite_news_and_fpi_show_hawa_ultee(self):
        self.assertEqual(self.results["opposite"][0]["label"], "हवा उल्टी 👁️")

    def test_expanded_detail_shows_separate_news_and_real_fpi_flow(self):
        detail = self.results["opposite"][0]["details"]
        self.assertIn("खबरों का रुख: बुलिश", detail)
        self.assertIn("FPI सेक्टर प्रवाह: −₹100 करोड़ · बिकवाली", detail)
        self.assertIn("अपने-आप में बेचने का संकेत नहीं", detail)

    def test_weak_or_insufficient_evidence_suppresses_tag(self):
        self.assertEqual(self.results["weak"], [])

    def test_stale_dashboard_fpi_or_mapping_suppresses_tag(self):
        self.assertEqual(self.results["staleDashboard"], [])
        self.assertEqual(self.results["staleFpi"], [])
        self.assertEqual(self.results["staleMap"], [])

    def test_small_sector_flow_suppresses_tag(self):
        self.assertEqual(self.results["lowFlow"], [])


if __name__ == "__main__":
    unittest.main()
