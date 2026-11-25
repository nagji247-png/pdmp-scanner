"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");

const html = fs.readFileSync("dashboard.html", "utf8");
const start = html.indexOf("function renderStandaloneStockBasket(b, assetName) {");
const end = html.indexOf("\n\nfunction card(", start);
assert(start >= 0 && end > start, "existing TRINETRA renderer must be present");
const rendererSource = html.slice(start, end);

const store = {};
const context = {
  stockBasketDetailStore: store,
  esc: value => String(value ?? "").replace(/[&<>"]/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"
  })[ch])
};
vm.createContext(context);
vm.runInContext(rendererSource, context, { timeout: 1000 });
const render = context.renderStandaloneStockBasket;

function makeBreakdown(score, included) {
  return {
    stock_basket_diagnostic: null,
    experimental_combined_final: {
      status: "available",
      score,
      included_components: included,
      normalized_weights_pct: { option_buildup: 100 }
    },
    experimental_combined_components: {
      option_buildup: { status: "available", score, test_only: true }
    }
  };
}

for (const [asset, score, label] of [
  ["NIFTY", 8.4088367182, "+8.41/10"],
  ["BANKNIFTY", 9.9772556563, "+9.98/10"],
  ["SENSEX", -1.234, "−1.23/10"]
]) {
  const breakdown = makeBreakdown(score, ["option_buildup"]);
  const before = JSON.stringify(breakdown);
  const output = render(breakdown, asset);
  assert.match(output, /TRINETRA 🔱/);
  assert(output.includes(label), asset + " score label missing");
  assert.equal((output.match(/stock-basket-compact-score-row/g) || []).length, 1);
  assert.equal((output.match(/stock-basket-compact-title/g) || []).length, 1);
  assert.equal(JSON.stringify(breakdown), before, asset + " input data must not be mutated");
  assert.equal(store[asset].combined.score, score);
}
assert.deepEqual(store.SENSEX.combinedComponents.option_buildup, { status: "available", score: -1.234, test_only: true });

for (const bad of [
  { status: "unavailable", score: 0 },
  { status: "available", score: 11 },
  { status: "available", score: "not-a-number" }
]) {
  const output = render({ experimental_combined_final: bad }, "NIFTY");
  assert.match(output, /डेटा जमा \/ जाँच जारी/);
  assert.doesNotMatch(output, /0\.00\/10/);
}

assert.match(html, /const isIndianIndex = INDIAN_INDEXES\.includes\(name\);/);
assert.match(html, /isIndianIndex\s*\?\s*renderStandaloneStockBasket\(/);
console.log("PASS: independent index scores; no fake zero; no input mutation; existing row only.");
