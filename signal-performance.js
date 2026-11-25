(function(){
"use strict";
var root=document.getElementById("signal-performance-tracker");
if(!root)return;
var style=document.createElement("style");
style.textContent="#signal-performance-tracker{margin:0 14px 16px;border:1px solid #194b82;border-radius:14px;background:linear-gradient(160deg,rgba(5,20,43,.98),rgba(2,10,26,.99));color:#e7f2ff;padding:12px;min-width:0}#signal-performance-tracker .sp-head{display:flex;align-items:center;justify-content:space-between;gap:10px}#signal-performance-tracker .sp-head b{font-size:14px;color:#eaf6ff}#signal-performance-tracker .sp-head small{display:block;color:#9bb2d2;font-size:10px;margin-top:3px}#signal-performance-tracker .sp-live{font-size:9px;color:#6cecff;border:1px solid #23618c;border-radius:20px;padding:4px 8px}#signal-performance-tracker .sp-overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:10px}#signal-performance-tracker .sp-overview>div{background:#0b1d37;border:1px solid #183b62;border-radius:9px;padding:8px;min-width:0}#signal-performance-tracker .sp-overview small{display:block;color:#9bb2d2;font-size:9px}#signal-performance-tracker .sp-overview strong{display:block;font-size:19px;margin-top:3px;overflow-wrap:anywhere}#signal-performance-tracker .sp-details{margin-top:9px;border-top:1px solid #183b62;padding-top:7px}#signal-performance-tracker summary{cursor:pointer;color:#6cecff;font-weight:800;padding:5px 0}#signal-performance-tracker .sp-table-wrap{overflow-x:auto;margin-top:8px}#signal-performance-tracker .sp-table{width:100%;min-width:760px;border-collapse:collapse;font-size:10px}#signal-performance-tracker .sp-table th,#signal-performance-tracker .sp-table td{text-align:left;padding:8px 6px;border-bottom:1px solid #183252;white-space:nowrap}#signal-performance-tracker .sp-table th{color:#8fb4d8}#signal-performance-tracker .sp-good{color:#20e6ac}#signal-performance-tracker .sp-bad{color:#ff7184}#signal-performance-tracker .sp-foot,#signal-performance-tracker .sp-note{font-size:10px;color:#9bb2d2;line-height:1.5;margin-top:9px}#signal-performance-tracker .sp-history{margin-top:10px;padding-top:7px;border-top:1px solid #183252}#signal-performance-tracker .sp-event{padding:7px 0;border-bottom:1px solid #183252;font-size:10px}#signal-performance-tracker .sp-event span{display:block;color:#9bb2d2;margin-top:3px}@media(max-width:520px){#signal-performance-tracker{margin-left:10px;margin-right:10px;padding:10px}#signal-performance-tracker .sp-overview strong{font-size:17px}}";
document.head.appendChild(style);

function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function fmt(v,suffix){return v==null?"—":(typeof v==="number"?v.toFixed(2):String(v))+(suffix||"");}
function render(data){
 var summary=data&&data.summary||{},names=["MARKET ACTIVITY RADAR","LATEST ACTIVITY ALERTS","SECTOR ACTIVITY","DAILY STOCK BUYING ACTIVITY","NEXT-SESSION REVERSAL"];
 var total=0,correct=0,wrong=0,net=0,netN=0;
 names.forEach(function(n){var x=summary[n]||{};total+=Number(x.evaluated||0);correct+=Number(x.correct||0);wrong+=Number(x.incorrect||0);if(typeof x.net_return_pct==="number"){net+=x.net_return_pct;netN++;}});
 var accuracy=correct+wrong?((correct/(correct+wrong))*100).toFixed(1)+"%":"—";
 var rows=names.map(function(n){
  var x=summary[n]||{};
  var netValue=typeof x.net_return_pct==="number"?fmt(x.net_return_pct,"%"):"—";
  var pf=x.profit_factor==null?"—":String(x.profit_factor);
  return '<tr><td>'+esc(n)+'</td><td>'+Number(x.total||0)+'</td><td class="sp-good">'+Number(x.correct||0)+'</td><td class="sp-bad">'+Number(x.incorrect||0)+'</td><td>'+Number(x.flat||0)+'</td><td>'+fmt(x.accuracy_pct,"%")+'</td><td>'+netValue+'</td><td>'+esc(pf)+'</td></tr>';
 }).join("");
 var events=Array.isArray(data&&data.events)?data.events:[];
 var pending=events.filter(function(e){return e.status==="pending";}).length;
 var updated=data&&data.updated?new Date(data.updated).toLocaleString("en-IN",{timeZone:"Asia/Kolkata"}):"अभी अपडेट नहीं";
 root.innerHTML='<div class="sp-head"><div><b>📊 SIGNAL PERFORMANCE TRACKER</b><small>सभी विभागों के सिग्नल का हिसाब · अगले ट्रेडिंग सेशन का क्लोज</small></div><span class="sp-live">रिकॉर्ड</span></div>'+
 '<div class="sp-overview"><div><small>Accuracy</small><strong>'+accuracy+'</strong></div><div><small>जाँचे गए</small><strong>'+total+'</strong></div><div><small>Net Return</small><strong class="'+(net>=0?"sp-good":"sp-bad")+'">'+(netN?fmt(net,"%"):"—")+'</strong></div></div>'+
 '<details class="sp-details"><summary>▼ पाँचों विभागों का पूरा हिसाब खोलें</summary>'+
 '<div class="sp-table-wrap"><table class="sp-table"><thead><tr><th>विभाग</th><th>कुल</th><th>सही</th><th>गलत</th><th>Flat</th><th>Unverified</th><th>Accuracy</th><th>Net Return</th><th>Profit Factor</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+
 '<div class="sp-foot">लंबित सिग्नल: '+pending+' · कुल दर्ज: '+events.length+' · डेटा अपडेट: '+esc(updated)+'</div>'+
 '<div class="sp-note">Average Profit / Average Loss और Sample Size हर विभाग के रिकॉर्ड से निकाले जाते हैं। Unverified रिकॉर्ड Accuracy में शामिल नहीं होते। रिटर्न प्रतिशत सकल मूल्य-परिवर्तन है; ब्रोकरेज और स्लिपेज शामिल नहीं हैं।</div>'+
 '<details class="sp-history"><summary>📂 हाल के सिग्नल रिकॉर्ड ('+events.length+')</summary><div class="sp-events">'+events.slice(-30).reverse().map(function(e){return '<div class="sp-event"><b>'+esc(e.department)+' · '+esc(e.instrument)+'</b><span>'+esc(e.direction)+' · '+esc(e.signal_date)+' · '+esc(e.status==="evaluated"?e.result:"जाँच बाकी")+'</span></div>';}).join("")+'</div></details>'+
 '</details>';
}
root.innerHTML='<div class="sp-head"><div><b>📊 SIGNAL PERFORMANCE TRACKER</b><small>सिग्नल का हिसाब लोड हो रहा है…</small></div></div>';
fetch("signal-performance.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("HTTP "+r.status);return r.json();}).then(render).catch(function(){root.innerHTML='<div class="sp-head"><div><b>📊 SIGNAL PERFORMANCE TRACKER</b><small>अभी कोई सत्यापित रिकॉर्ड उपलब्ध नहीं है।</small></div></div>';});
})();