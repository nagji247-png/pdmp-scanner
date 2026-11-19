(function(){
"use strict";
var root=document.getElementById("sector-early-radar");
if(!root)return;
var style=document.createElement("style");
style.textContent=[
".ser-wrap{background:radial-gradient(ellipse at 50% 0%,#102a52 0%,#06152d 58%,#041126 100%);border:1px solid #245ca1;border-radius:18px;padding:12px;color:#edf6ff;box-shadow:0 0 22px #0875d322,inset 0 0 22px #061b3c;overflow:hidden}",
".ser-brand{display:flex;align-items:center;gap:10px;margin:0 2px 12px;min-width:0}.ser-eye{font-size:34px;line-height:1}.ser-brand-name{font-size:clamp(20px,4vw,32px);font-weight:950;letter-spacing:1px;line-height:1}.ser-tagline{color:#55c5ff;font-size:clamp(10px,2vw,14px);font-weight:800;margin-top:4px}.ser-live{margin-left:auto;border:1px solid #078e4e;background:#075c3b;color:#d9ffe9;border-radius:24px;padding:7px 10px;font-weight:900;font-size:12px;white-space:nowrap}",
".ser-title{border:1px solid #2877d4;border-radius:14px;background:linear-gradient(110deg,#08244b,#061b39);padding:12px 10px;display:flex;align-items:center;gap:10px;box-shadow:0 0 15px #1674d633}.ser-radar{font-size:38px;color:#00e46c;line-height:1}.ser-title-main{font-size:clamp(16px,3.5vw,26px);font-weight:950;line-height:1.15}.ser-subtitle{font-size:clamp(10px,2.1vw,15px);font-weight:750;color:#d6e9ff;margin-top:7px;line-height:1.35}",
".ser-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:10px 0 12px}.ser-stat{min-width:0;text-align:center;border:1px solid #22568e;border-radius:12px;padding:8px 3px;background:linear-gradient(145deg,#0c3451,#09223e);box-shadow:inset 0 0 12px #16b8c522}.ser-stat:nth-child(2){background:linear-gradient(145deg,#38213b,#1a1d3c);border-color:#59416d}.ser-stat:nth-child(3){background:linear-gradient(145deg,#162e52,#0c1d3d)}.ser-stat:nth-child(4){background:linear-gradient(145deg,#092d5b,#071c40)}.ser-stat strong{display:block;font-size:clamp(20px,5vw,36px);font-weight:950;line-height:1.1}.ser-stat span{display:block;font-size:clamp(9px,2vw,14px);font-weight:800;line-height:1.3;margin-top:4px;color:#d9eaff}.ser-up{color:#37ff9a}.ser-down{color:#ff5969}.ser-cyan{color:#12dfff}",
".ser-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.ser-side{min-width:0;border-radius:16px;padding:3px;overflow:hidden}.ser-side.buy{border:2px solid #00dc67;background:linear-gradient(145deg,#063e2a,#071d2b);box-shadow:0 0 15px #00db6744}.ser-side.sell{border:2px solid #ff3e59;background:linear-gradient(145deg,#4b1328,#1d1834);box-shadow:0 0 15px #ff315544}.ser-side-head{font-size:clamp(13px,3vw,22px);font-weight:950;text-align:center;padding:8px 2px;line-height:1.2}.ser-side.buy .ser-side-head{color:#d8ffea}.ser-side.sell .ser-side-head{color:#ffe2e7}.ser-signal{border-radius:12px;background:#041a2c;border:1px solid #087d5c;padding:9px 8px;margin:2px 0 5px;min-height:150px}.ser-side.sell .ser-signal{background:#17152c;border-color:#8f2949}.ser-signal-top{display:flex;align-items:center;justify-content:space-between;gap:4px;flex-wrap:wrap}.ser-sector{font-size:clamp(12px,2.8vw,19px);font-weight:950;overflow-wrap:anywhere}.ser-pill{font-size:clamp(8px,1.8vw,12px);font-weight:950;border-radius:20px;padding:6px 7px;white-space:normal;text-align:center;line-height:1.1;background:#078d47;color:#fff}.ser-side.sell .ser-pill{background:#d92d49}.ser-change{font-size:clamp(23px,5vw,38px);font-weight:950;line-height:1.15;margin:7px 0 4px}.ser-side.buy .ser-change{color:#00f58a}.ser-side.sell .ser-change{color:#ff6577}.ser-detail{font-size:clamp(9px,2vw,13px);font-weight:750;color:#dceaff;line-height:1.4;overflow-wrap:anywhere}.ser-empty{font-size:clamp(10px,2.2vw,14px);font-weight:800;line-height:1.45;color:#c9d9ed;margin-top:9px}.ser-divider{height:1px;background:#279a75;margin:8px 0}.ser-side.sell .ser-divider{background:#a23d62}",
".ser-flow{margin-top:11px;border:1px solid #2875d1;border-radius:14px;background:linear-gradient(145deg,#092d5a,#071b3b);padding:10px;box-shadow:inset 0 0 15px #1674d322}.ser-flow-title{font-size:clamp(17px,3.5vw,25px);font-weight:950;margin-bottom:8px}.ser-flow-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.ser-flow-item{min-width:0;text-align:center;border-right:1px solid #2e6bb3;padding:3px}.ser-flow-item:last-child{border:0}.ser-flow-item b{display:block;font-size:clamp(9px,1.8vw,13px);overflow-wrap:anywhere}.ser-flow-item strong{display:block;color:#16e78a;font-size:clamp(12px,2.8vw,21px);margin-top:5px;overflow-wrap:anywhere}",
".ser-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-top:10px;padding:9px;border:1px solid #245ca1;border-radius:12px;background:#061a36;color:#d7e8ff;font-size:clamp(9px,1.9vw,12px);font-weight:750}.ser-foot b{color:#67c9ff}.ser-muted{color:#a9bfdc}.ser-loading{padding:24px 8px;text-align:center;color:#c8dcf7;font-weight:800}",
"@media(max-width:360px){.ser-wrap{padding:8px}.ser-stats{gap:4px}.ser-stat{padding:7px 1px}.ser-columns{gap:6px}.ser-signal{padding:7px 5px}.ser-pill{padding:5px 4px}.ser-brand{gap:6px}.ser-eye{font-size:28px}}"
].join("");
document.head.appendChild(style);
function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function num(v){return typeof v==="number"&&isFinite(v)?v:null;}
function pct(v){var n=num(v);return n===null?"—":(n>0?"+":"")+n.toFixed(2)+"%";}
function count(v){return Number.isFinite(Number(v))?String(Math.max(0,Math.floor(Number(v)))):"—";}
function signalCard(item,side){
if(!item)return '<div class="ser-signal"><div class="ser-empty">अभी कोई सत्यापित इंट्राडे संकेत उपलब्ध नहीं।</div></div>';
var buying=side==="buy",label=item.status==="confirmed"?(buying?"CONFIRMED BUYING":"CONFIRMED SELLING"):(buying?"EARLY BUYING":"EARLY SELLING");
var stamp=item.first_detected_at||item.detected_at||"पहली पहचान उपलब्ध नहीं";
var confirm=item.status==="confirmed"?"पुष्टि मिल गई":"पुष्टि बाकी";
return '<div class="ser-signal"><div class="ser-signal-top"><span class="ser-sector">'+esc(item.sector||"सेक्टर")+'</span><span class="ser-pill">'+label+'</span></div><div class="ser-change">'+pct(item.change_pct)+'</div><div class="ser-detail">'+esc(item.rising_stocks||item.falling_stocks||"—")+' शेयर · '+esc(item.volume_rising||"—")+' में वॉल्यूम बढ़ा</div><div class="ser-empty">पहली पहचान: '+esc(stamp)+'<br>स्थिति: '+(item.status==="confirmed"?"पुष्ट":"शुरुआती संकेत")+'<br>पुष्टि: '+confirm+'</div></div>';
}
function render(data){
var snap=data&&data.sector_early_radar;
var valid=!!(snap&&snap.mode==="intraday"&&snap.source&&snap.source_timestamp&&Array.isArray(snap.sectors));
var buys=valid?snap.sectors.filter(function(x){return x.direction==="buying";}):[];
var sells=valid?snap.sectors.filter(function(x){return x.direction==="selling";}):[];
var confirmed=valid?snap.sectors.filter(function(x){return x.status==="confirmed";}).length:0;
var unusual=valid?count(snap.summary&&snap.summary.unusual_stocks):"—";
var fpi=valid&&snap.fpi&&snap.fpi.updated?esc(snap.fpi.updated):"डेटा उपलब्ध नहीं";
var firstBuy=buys[0],secondBuy=buys[1],firstSell=sells[0],secondSell=sells[1];
var stamp=valid?esc(snap.source_timestamp):"इंट्राडे स्रोत उपलब्ध नहीं";
root.innerHTML='<div class="ser-wrap">'+
'<div class="ser-brand"><span class="ser-eye">👁️</span><div><div class="ser-brand-name">TRINETRA</div><div class="ser-tagline">Crowd Trap · Contrarian Edge</div></div><div class="ser-live">● '+(valid?"LIVE":"WAITING")+'</div></div>'+
'<div class="ser-title"><span class="ser-radar">◉</span><div><div class="ser-title-main">MARKET ACTIVITY RADAR</div><div class="ser-subtitle">आज बाजार में कहाँ हलचल है? · 218 स्टॉक · 18 सेक्टर</div></div></div>'+
'<div class="ser-stats"><div class="ser-stat"><strong class="ser-up">'+count(buys.length)+'</strong><span>तेजी वाले<br>सेक्टर</span></div><div class="ser-stat"><strong class="ser-down">'+count(sells.length)+'</strong><span>मंदी वाले<br>सेक्टर</span></div><div class="ser-stat"><strong>'+unusual+'</strong><span>असामान्य<br>स्टॉक</span></div><div class="ser-stat"><strong class="ser-cyan">'+count(confirmed)+'</strong><span>पुष्टि हुए<br>संकेत</span></div></div>'+
'<div class="ser-columns"><div class="ser-side buy"><div class="ser-side-head">↗ तेजी वाले सेक्टर</div>'+signalCard(firstBuy,"buy")+'<div class="ser-divider"></div>'+signalCard(secondBuy,"buy")+'</div><div class="ser-side sell"><div class="ser-side-head">↘ मंदी वाले सेक्टर</div>'+signalCard(firstSell,"sell")+'<div class="ser-divider"></div>'+signalCard(secondSell,"sell")+'</div></div>'+
'<div class="ser-flow"><div class="ser-flow-title">▤ FPI प्रवाह बदलाव</div><div class="ser-flow-grid"><div class="ser-flow-item"><b>Telecommunication</b><strong>'+fpi+'</strong></div><div class="ser-flow-item"><b>Information Technology</b><strong>'+fpi+'</strong></div><div class="ser-flow-item"><b>Financial Services</b><strong>'+fpi+'</strong></div></div></div>'+
'<div class="ser-foot"><span>ⓘ <b>'+(valid?"सत्यापित इंट्राडे डेटा":"इंट्राडे डेटा उपलब्ध नहीं — कोई शुरुआती संकेत नहीं दिखाया जा रहा")+'</b></span><span>⟳ अपडेट: <b>'+stamp+'</b></span></div></div>';
}
function load(){
fetch("data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("HTTP "+r.status);return r.json();}).then(render).catch(function(){render(null);});
}
load();
window.setInterval(load,60000);
document.addEventListener("visibilitychange",function(){if(!document.hidden)load();});
})();