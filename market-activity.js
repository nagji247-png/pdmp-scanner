(function () {
  "use strict";

  var root = document.getElementById("market-activity");
  if (!root) return;

  var master = null;
  var fpi = null;
  var marketData = null;
  var searchTerm = "";

  var style = document.createElement("style");
  style.textContent = [
    ".market-activity-box{min-width:0;color:#e7f2ff}",
    ".ma-intro{font-size:11px;color:#9bb2d2;line-height:1.5;margin-bottom:10px}",
    ".ma-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:9px 0 12px}",
    ".ma-stat{min-width:0;padding:10px;border:1px solid #1b426a;border-radius:10px;background:linear-gradient(145deg,#102747,#0a1930)}",
    ".ma-stat b{display:block;font-size:20px;color:#36e7ff;line-height:1.2}",
    ".ma-stat span{font-size:10px;color:#a9bfdc}",
    ".ma-search{width:100%;min-width:0;padding:11px 12px;border:1px solid #285078;border-radius:9px;background:#07172d;color:#e7f2ff;font-size:13px;margin:4px 0 10px}",
    ".ma-sector{border:1px solid #1b426a;border-radius:11px;background:linear-gradient(145deg,#10213c,#0a172c);margin:8px 0;overflow:hidden}",
    ".ma-sector summary{display:block;padding:11px;cursor:pointer;list-style:none}",
    ".ma-sector summary::-webkit-details-marker{display:none}",
    ".ma-sector-head{display:flex;justify-content:space-between;align-items:center;gap:8px}",
    ".ma-sector-name{font-size:13px;font-weight:850;color:#e7f2ff;min-width:0}",
    ".ma-sector-count{font-size:10px;color:#9bb2d2;white-space:nowrap}",
    ".ma-sector-meta{display:flex;flex-wrap:wrap;gap:6px 12px;margin-top:7px;font-size:10px;color:#a9bfdc}",
    ".ma-up{color:#20e6ac}.ma-down{color:#ff7184}.ma-neutral{color:#a9bfdc}.ma-warn{color:#ffca72}",
    ".ma-sector-body{padding:0 9px 9px}",
    ".ma-stock{border-top:1px solid #1a3557;padding:9px 2px;min-width:0}",
    ".ma-stock-top{display:flex;justify-content:space-between;align-items:center;gap:8px}",
    ".ma-symbol{font-size:12px;font-weight:900;color:#6cecff;overflow-wrap:anywhere}",
    ".ma-tag{font-size:9px;color:#9bb2d2;border:1px solid #29486b;border-radius:5px;padding:2px 5px}",
    ".ma-stock-meta{font-size:10px;color:#a9bfdc;line-height:1.55;margin-top:4px;overflow-wrap:anywhere}",
    ".ma-stock-signal{font-size:10px;margin-top:5px;line-height:1.45}",
    ".ma-fpi{font-size:10px;color:#d7eaff;margin-top:6px;padding-top:6px;border-top:1px dashed #29486b}",
    ".ma-empty{font-size:11px;color:#ffca72;padding:9px 2px;line-height:1.5}",
    ".ma-foot{font-size:10px;color:#829bbd;line-height:1.5;margin-top:10px}",
    "@media(max-width:560px){.ma-summary{gap:7px}.ma-stat{padding:9px}.ma-sector summary{padding:10px}.ma-stock{padding:8px 1px}}"
  ].join("");
  document.head.appendChild(style);

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }

  function money(value) {
    var n = Number(value);
    if (!Number.isFinite(n)) return "डेटा उपलब्ध नहीं";
    return (n > 0 ? "+" : n < 0 ? "−" : "") + "₹" + Math.abs(n).toLocaleString("en-IN", {maximumFractionDigits:1}) + " Cr";
  }

  function dateLabel(value) {
    if (!value) return "तारीख़ उपलब्ध नहीं";
    var d = new Date(value + "T00:00:00");
    return Number.isNaN(d.getTime()) ? esc(value) : d.toLocaleDateString("en-IN", {day:"2-digit",month:"short",year:"numeric"});
  }

  function getLatestFpi() {
    var history = fpi && Array.isArray(fpi.history) ? fpi.history : [];
    return history.length ? history[0] : null;
  }

  function getFpiMap() {
    var latest = getLatestFpi();
    var out = {};
    (latest && Array.isArray(latest.sectors) ? latest.sectors : []).forEach(function (item) {
      if (item && item.name) out[item.name] = item.net_equity_cr;
    });
    return out;
  }

  function getQuote(symbol) {
    var item = marketData && marketData.instruments ? marketData.instruments[symbol] : null;
    if (!item || item.type !== "stock") return null;
    return item;
  }

  function renderStock(symbol, info, fpiDate) {
    var quote = getQuote(symbol);
    var priceText = "भाव: डेटा उपलब्ध नहीं";
    var directionText = "कीमत की दिशा: डेटा उपलब्ध नहीं";
    var directionClass = "ma-neutral";
    var signal = "PDMP संकेत: पर्याप्त सत्यापित स्टॉक-स्तरीय डेटा उपलब्ध नहीं";
    var newsText = "खबरों का रुख: स्टॉक-स्तरीय खबर उपलब्ध नहीं";
    var score = quote && Number.isFinite(Number(quote.score)) ? Number(quote.score) : null;
    var change = quote && Number.isFinite(Number(quote.change_pct)) ? Number(quote.change_pct) : null;

    if (quote && Number.isFinite(Number(quote.price))) {
      priceText = "भाव: ₹" + Number(quote.price).toLocaleString("en-IN", {maximumFractionDigits:2}) +
        (quote.price_as_of ? " · " + esc(quote.price_as_of) : "");
    }
    if (change !== null) {
      directionText = "कीमत: " + (change > 0 ? "ऊपर ↑ " : change < 0 ? "नीचे ↓ " : "लगभग स्थिर ") +
        "(" + (change > 0 ? "+" : "") + change.toFixed(2) + "%)";
      directionClass = change > 0 ? "ma-up" : change < 0 ? "ma-down" : "ma-neutral";
    }
    if (quote && (Number(quote.pos_n) + Number(quote.neg_n) > 0)) {
      newsText = "खबरों का रुख: तेजी " + Number(quote.pos_n || 0) + " · मंदी " + Number(quote.neg_n || 0);
    }
    if (score !== null && Math.abs(score) >= 2 && change !== null) {
      if (change > 0 && score < 0) signal = "PDMP: कीमत ऊपर, स्कोर मंदी — संभावित तेजी का अंतर जाँचें";
      else if (change < 0 && score > 0) signal = "PDMP: कीमत नीचे, स्कोर तेजी — संभावित मंदी का अंतर जाँचें";
      else signal = "PDMP स्कोर: " + (score > 0 ? "+" : "") + score.toFixed(2) + " · कीमत के साथ दिशा मिलाएँ";
    }

    return '<div class="ma-stock">' +
      '<div class="ma-stock-top"><span class="ma-symbol">' + esc(symbol) + '</span><span class="ma-tag">TAG · ' + esc(symbol) + '</span></div>' +
      '<div class="ma-stock-meta">सेक्टर: ' + esc(info.sector) + '<br>इंडस्ट्री: ' + esc(info.industry) + '</div>' +
      '<div class="ma-stock-meta">' + priceText + '<br><span class="' + directionClass + '">' + directionText + '</span></div>' +
      '<div class="ma-stock-meta">' + newsText + '<br>वॉल्यूम: डेटा उपलब्ध नहीं · भीड़ का रुख: डेटा उपलब्ध नहीं</div>' +
      '<div class="ma-stock-signal ma-warn">' + signal + '</div>' +
      '<div class="ma-fpi">FPI: सेक्टर-स्तरीय डेटा अलग से देखें · व्यक्तिगत स्टॉक FPI डेटा उपलब्ध नहीं</div>' +
      '</div>';
  }

  function render() {
    if (!master || !master.stocks) {
      root.innerHTML = '<div class="ma-empty">NSE F&amp;O मास्टर लोड नहीं हुआ। दोबारा प्रयास करें।</div>';
      return;
    }

    var stockMap = master.stocks;
    var symbols = Object.keys(stockMap).sort();
    var sectors = {};
    symbols.forEach(function (symbol) {
      var info = stockMap[symbol] || {};
      var sector = info.sector || "सेक्टर उपलब्ध नहीं";
      if (!sectors[sector]) sectors[sector] = [];
      sectors[sector].push({symbol:symbol,info:info});
    });

    var fpiMap = getFpiMap();
    var latestFpi = getLatestFpi();
    var quoteCount = symbols.filter(function (s) { return !!getQuote(s); }).length;
    var fpiLabel = latestFpi ? esc(latestFpi.label || (latestFpi.from_date + " – " + latestFpi.to_date)) : "डेटा उपलब्ध नहीं";
    var filteredCount = 0;
    var sectorHtml = "";

    Object.keys(sectors).sort().forEach(function (sector) {
      var stocks = sectors[sector].filter(function (entry) {
        if (!searchTerm) return true;
        var hay = [entry.symbol, entry.info.industry, entry.info.sector].join(" ").toLowerCase();
        return hay.indexOf(searchTerm) !== -1;
      });
      if (!stocks.length) return;
      filteredCount += stocks.length;

      var up = 0, down = 0, flat = 0, available = 0;
      stocks.forEach(function (entry) {
        var q = getQuote(entry.symbol);
        if (q && Number.isFinite(Number(q.change_pct))) {
          available++;
          if (Number(q.change_pct) > 0) up++;
          else if (Number(q.change_pct) < 0) down++;
          else flat++;
        }
      });
      var flow = fpiMap[sector];
      var fpiHtml = Number.isFinite(Number(flow))
        ? '<span class="' + (Number(flow) > 0 ? "ma-up" : Number(flow) < 0 ? "ma-down" : "ma-neutral") + '">FPI ' + money(flow) + '</span>'
        : '<span>FPI डेटा उपलब्ध नहीं</span>';
      var rows = stocks.map(function (entry) {
        return renderStock(entry.symbol, entry.info, latestFpi && latestFpi.end_date);
      }).join("");

      sectorHtml += '<details class="ma-sector">' +
        '<summary><div class="ma-sector-head"><span class="ma-sector-name">' + esc(sector) + '</span><span class="ma-sector-count">' + stocks.length + ' स्टॉक</span></div>' +
        '<div class="ma-sector-meta"><span>भाव उपलब्ध ' + available + '/' + stocks.length + '</span>' +
        '<span class="ma-up">↑ ' + up + '</span><span class="ma-down">↓ ' + down + '</span><span class="ma-neutral">स्थिर ' + flat + '</span>' + fpiHtml + '</div></summary>' +
        '<div class="ma-sector-body">' + rows + '</div></details>';
    });

    var asOf = marketData && marketData.updated ? esc(marketData.updated) : "अपडेट समय उपलब्ध नहीं";
    var masterDate = esc(master.as_of || "तारीख़ उपलब्ध नहीं");
    root.innerHTML =
      '<div class="ma-intro">यह 218 सत्यापित NSE F&amp;O स्टॉक का सेक्टर-वार संदर्भ है। सेक्टर की कुल तेजी/मंदी का दावा केवल उपलब्ध स्टॉक भावों से नहीं किया जाएगा।</div>' +
      '<div class="ma-summary">' +
      '<div class="ma-stat"><b>' + symbols.length + '</b><span>सत्यापित स्टॉक</span></div>' +
      '<div class="ma-stat"><b>' + Object.keys(sectors).length + '</b><span>सेक्टर</span></div>' +
      '<div class="ma-stat"><b>' + quoteCount + '/' + symbols.length + '</b><span>TRINETRA भाव डेटा उपलब्ध</span></div>' +
      '<div class="ma-stat"><b>' + (symbols.length - quoteCount) + '</b><span>भाव डेटा अभी उपलब्ध नहीं</span></div>' +
      '</div>' +
      '<div class="ma-intro">FPI नवीनतम अवधि: ' + fpiLabel + ' · स्रोत: NSDL सेक्टर-स्तरीय Equity निवेश</div>' +
      '<input class="ma-search" id="ma-search" type="search" placeholder="स्टॉक / Tag / सेक्टर / इंडस्ट्री खोजें…" value="' + esc(searchTerm) + '" aria-label="स्टॉक या सेक्टर खोजें">' +
      '<div class="ma-intro" id="ma-result-count">' + filteredCount + ' स्टॉक दिख रहे हैं · सेक्टर खोलने के लिए टैप करें</div>' +
      (sectorHtml || '<div class="ma-empty">इस खोज से कोई स्टॉक नहीं मिला।</div>') +
      '<div class="ma-foot">डेटा फ़ाइल अपडेट: ' + asOf + ' · सेक्टर मास्टर: ' + masterDate + '. कीमत की तारीख़ हर स्टॉक के साथ अलग दिखाई जाती है। वॉल्यूम, भीड़, स्टॉक-स्तरीय खबर या व्यक्तिगत FPI उपलब्ध न हो तो अनुमान नहीं लगाया जाता। FPI केवल सेक्टर स्तर का है।</div>';

    var input = document.getElementById("ma-search");
    if (input) {
      input.addEventListener("input", function (event) {
        searchTerm = String(event.target.value || "").trim().toLowerCase();
        var cursor = input.selectionStart;
        render();
        var next = document.getElementById("ma-search");
        if (next) { next.focus(); next.setSelectionRange(cursor, cursor); }
      });
    }
  }

  function load() {
    Promise.all([
      fetch("nse-fo-stock-sector-master.json?t=" + Date.now(), {cache:"no-store"}).then(function (r) { if (!r.ok) throw new Error("master"); return r.json(); }),
      fetch("fpi-sector-data.json?t=" + Date.now(), {cache:"no-store"}).then(function (r) { if (!r.ok) throw new Error("fpi"); return r.json(); }),
      fetch("data.json?t=" + Date.now(), {cache:"no-store"}).then(function (r) { if (!r.ok) throw new Error("data"); return r.json(); })
    ]).then(function (values) {
      master = values[0];
      fpi = values[1];
      marketData = values[2];
      render();
    }).catch(function () {
      if (!master) root.innerHTML = '<div class="ma-empty">Market Activity डेटा लोड नहीं हो पाया। कनेक्शन जाँचकर पेज रीफ़्रेश करें।</div>';
    });
  }

  load();
  window.setInterval(load, 5 * 60 * 1000);
})();