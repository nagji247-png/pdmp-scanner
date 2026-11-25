(function(){
"use strict";
var root=document.getElementById("signal-performance");
if(!root)return;
function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function num(v,d){return v==null||!Number.isFinite(Number(v))?"—":Number(v).toFixed(d==null?1:d);}
function pct(v){return v==null?"—":(Number(v)>0?"+":"")+num(v,2)+"%";}
function pf(v){return v==null?"—":v==="Infinity"?"∞":num(v,2);}
function render(data){
 if(!data||!data.summary||!Array.isArray(data.events)){root.innerHTML='<div class="sp-note">पहला सत्यापित सिग्नल रिकॉर्ड होने की प्रतीक्षा है। कोई उदाहरण या अनुमानित आँकड़ा नहीं दिखाया जाएगा।</div>';return;}
 var order=["MARKET ACTIVITY RADAR","LATEST ACTIVITY ALERTS","SECTOR ACTIVITY","DAILY STOCK BUYING ACTIVITY","NEXT-SESSION REVERSAL"];
 var rows=order.map(function(name){
  var s=data.summary[name]||{};
  return '<tr><td><b>'+esc(name)+'</b></td><td>'+num(s.total,0)+'</td><td class="sp-good">'+num(s.correct,0)+'</td><td class="sp-bad">'+num(s.incorrect,0)+'</td><td>'+num(s.flat,0)+'</td><td>'+num(s.pending,0)+'</td><td>'+num(s.unverified,0)+'</td><td>'+pct(s.accuracy_pct)+'</td><td>'+pct(s.net_return_pct)+'</td><td>'+pf(s.profit_factor)+'</td></tr>';
 }).join("");
 var evaluated=0,correct=0,incorrect=0,pending=0,unverified=0,flat=0,net=0,hasNet=false;
 order.forEach(function(name){var s=data.summary[name]||{};evaluated+=Number(s.sample_size||0);correct+=Number(s.correct||0);incorrect+=Number(s.incorrect||0);pending+=Number(s.pending||0);unverified+=Number(s.unverified||0);flat+=Number(s.flat||0);if(s.net_return_pct!=null){net+=Number(s.net_return_pct);hasNet=true;}});
 var accuracy=correct+incorrect?correct/(correct+incorrect)*100:null;
 var ranked=order.map(function(name){return {name:name,stats:data.summary[name]||{}};});
 var bestAccuracy=ranked.filter(function(x){return x.stats.accuracy_pct!=null;}).sort(function(a,b){return b.stats.accuracy_pct-a.stats.accuracy_pct;})[0];
 var bestProfit=ranked.filter(function(x){return x.stats.net_return_pct!=null;}).sort(function(a,b){return b.stats.net_return_pct-a.stats.net_return_pct;})[0];
 root.innerHTML=
 '<div class="sp-summary"><div><small>Accuracy</small><b>'+pct(accuracy)+'</b></div><div><small>कुल रिकॉर्ड</small><b>'+num(data.events.length,0)+'</b></div><div><small>Net Signal Return</small><b class="'+(hasNet&&net>=0?"sp-good":"sp-bad")+'">'+(hasNet?pct(net):"—")+'</b></div></div>'+
 '<div class="sp-note">केवल अगले ट्रेडिंग सेशन की सत्यापित क्लोजिंग पर मूल्यांकन। Net Signal Return दिशात्मक प्रतिशत का कुल योग है; यह वास्तविक पोर्टफोलियो/₹ मुनाफा नहीं है। ब्रोकरेज और स्लिपेज शामिल नहीं हैं।</div>'+
 '<details class="sp-details"><summary>पाँचों विभागों का पूरा हिसाब खोलें</summary>'+
 '<div class="sp-table-wrap"><table class="sp-table"><thead><tr><th>विभाग</th><th>कुल</th><th>सही</th><th>गलत</th><th>Flat</th><th>Pending</th><th>Unverified</th><th>Accuracy</th><th>Net %</th><th>PF</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+
 '<div class="sp-rank"><div><b>सबसे सटीक विभाग</b><span>'+(bestAccuracy?esc(bestAccuracy.name)+" · "+pct(bestAccuracy.stats.accuracy_pct):"अभी पर्याप्त परिणाम नहीं")+'</span></div><div><b>सबसे ज्यादा Net Signal Return</b><span>'+(bestProfit?esc(bestProfit.name)+" · "+pct(bestProfit.stats.net_return_pct):"अभी पर्याप्त परिणाम नहीं")+'</span></div></div>'+
 '<div class="sp-note">Average Profit/Loss और Profit Factor केवल सत्यापित सिग्नलों से निकाले जाते हैं। Sample Size: '+num(evaluated,0)+' · Flat: '+num(flat,0)+' · Pending: '+num(pending,0)+' · Unverified: '+num(unverified,0)+'.</div>'+
 '<details class="sp-history"><summary>सिग्नल हिस्ट्री खोलें ('+num(data.events.length,0)+')</summary><div class="sp-table-wrap"><table class="sp-table"><thead><tr><th>सिग्नल समय (IST)</th><th>विभाग</th><th>इंस्ट्रूमेंट</th><th>दिशा</th><th>Entry</th><th>जाँच तारीख</th><th>Return</th><th>नतीजा</th></tr></thead><tbody>'+
 data.events.slice().reverse().slice(0,250).map(function(e){return '<tr><td>'+esc(e.signal_time_ist||e.signal_date)+'</td><td>'+esc(e.department)+'</td><td>'+esc(e.instrument)+'</td><td>'+esc(e.direction)+'</td><td>'+(e.entry_price==null?"—":num(e.entry_price,2))+'</td><td>'+esc(e.evaluation_date||"—")+'</td><td>'+pct(e.signed_return_pct)+'</td><td>'+esc(e.status||"PENDING")+'</td></tr>';}).join("")+
 '</tbody></table></div></details></details>';
}
var style=document.createElement("style");
style.textContent='.sp-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:9px}.sp-summary>div{background:#121f35;border:1px solid #294665;border-radius:9px;padding:10px;min-width:0}.sp-summary small{display:block;color:#9eb0c8;font-size:10px}.sp-summary b{display:block;font-size:19px;margin-top:4px;overflow-wrap:anywhere}.sp-note{font-size:11px;line-height:1.5;color:#aab8ca;margin:7px 0}.sp-details,.sp-history{margin-top:8px}.sp-details summary,.sp-history summary{cursor:pointer;font-weight:800;color:#dfe9f5;padding:8px 0}.sp-table-wrap{overflow-x:auto}.sp-table{border-collapse:collapse;width:100%;min-width:850px;font-size:11px}.sp-table th,.sp-table td{padding:7px 6px;border-bottom:1px solid #293a51;text-align:left;white-space:nowrap}.sp-table th{color:#9eb0c8}.sp-good{color:#36d6a2}.sp-bad{color:#ff7788}.sp-rank{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:10px 0}.sp-rank>div{padding:9px;border-radius:8px;background:#121f35;border:1px solid #294665}.sp-rank b,.sp-rank span{display:block;font-size:11px}.sp-rank span{color:#aab8ca;margin-top:5px;overflow-wrap:anywhere}@media(max-width:520px){.sp-summary b{font-size:16px}.sp-rank{grid-template-columns:1fr}}';
document.head.appendChild(style);
fetch("signal_performance.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("not ready");return r.json();}).then(render).catch(function(){render(null);});
})();