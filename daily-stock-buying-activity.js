(function(){
"use strict";
var root=document.getElementById("daily-stock-buying-activity");
if(!root)return;
function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function fmt(v,d){return v==null?"—":Number(v).toLocaleString("en-IN",{maximumFractionDigits:d==null?2:d});}
function badge(signal){
 var map={
  "LONG BUILD-UP":["🟢","ma-buy"],
  "SHORT BUILD-UP":["🔴","ma-sell"],
  "DELIVERY WATCH":["🟡","ma-watch"],
  "SHORT COVERING":["🔵","ma-cover"],
  "LONG UNWINDING":["⚪","ma-neutral"],
  "SELLING WATCH":["🔴","ma-sell"],
  "EARLY BUYING WATCH":["🟡","ma-watch"],
  "UNUSUAL ACTIVITY WATCH":["🟡","ma-watch"]
 };
 var m=map[signal]||["⚪","ma-neutral"];
 return '<span class="dsba-signal '+m[1]+'">'+m[0]+' '+esc(signal||"DATA UNAVAILABLE")+'</span>';
}
function render(data){
 if(!data||!Array.isArray(data.rows)){root.innerHTML='<div class="dsba-note">Daily buying activity डेटा उपलब्ध नहीं।</div>';return;}
 var rows=data.rows;
 var fno=rows.filter(function(r){return r.category==="F&O";});
 var other=rows.filter(function(r){return r.category!=="F&O";});
 var html='<div class="dsba-head"><b>DAILY STOCK BUYING ACTIVITY</b><span>218 F&O + अन्य NSE शेयर</span></div>'+
 '<div class="dsba-meta">डेटा तारीख: '+esc(data.as_of||"उपलब्ध नहीं")+' · स्रोत: NSE official CM EOD</div>'+
 '<div class="dsba-summary"><span>F&O संकेत: <b>'+fno.length+'</b></span><span>अन्य NSE संकेत: <b>'+other.length+'</b></span><span>स्कैन: <b>'+fmt(data.universe&&data.universe.nse_eq_symbols_scanned,0)+'</b> EQ शेयर</span></div>'+
 '<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Stock</th><th>Category</th><th>Price</th><th>OI</th><th>Delivery %</th><th>Activity Days</th><th>Signal</th><th>Buying Evidence</th></tr></thead><tbody>';
 if(!rows.length)html+='<tr><td colspan="8">इस EOD स्कैन में निर्धारित unusual-volume सीमा पार करने वाला कोई शेयर नहीं मिला।</td></tr>';
 rows.forEach(function(r){
  html+='<tr><td><b>'+esc(r.symbol)+'</b></td><td>'+esc(r.category)+'</td><td class="'+(Number(r.change_pct)>=0?"dsba-positive":"dsba-negative")+'">₹'+fmt(r.price)+'<small class="dsba-strength">'+(Number(r.change_pct)>0?"+":"")+fmt(r.change_pct)+'%</small></td><td>'+(r.oi_change_pct==null?"—":(Number(r.oi_change_pct)>0?"+":"")+fmt(r.oi_change_pct)+'%')+'</td><td>'+(r.delivery_pct==null?"—":fmt(r.delivery_pct)+'%')+'</td><td>'+fmt(r.activity_days,0)+'</td><td>'+badge(r.signal)+'<small class="dsba-strength">'+esc(r.strength||"")+'</small></td><td>'+esc((r.evidence||[]).join(" · "))+'<small class="dsba-strength">वॉल्यूम औसत से '+fmt(r.volume_ratio)+' गुना</small></td></tr>';
 });
 html+='</tbody></table></div>'+
 '<div class="dsba-note">OI केवल उसी expiry के दो लगातार सत्रों से सत्यापित होने पर दिखेगा। Delivery % केवल उसी तारीख की NSE Full Bhavcopy से मिलेगा। EARLY BUYING WATCH केवल भाव + असामान्य वॉल्यूम का शुरुआती संकेत है, पक्की खरीदारी नहीं। यह EOD स्कैन है—इंट्राडे एंट्री अलर्ट नहीं।</div>'+
 '<details class="dsba-details"><summary>बड़े सौदों की गतिविधि (Bulk / Block Deals)</summary>'+
 (Array.isArray(data.bulk_block_deals)&&data.bulk_block_deals.length?
  '<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Stock</th><th>Buyer / Seller</th><th>Side</th><th>Activity</th><th>Quantity</th><th>Price</th></tr></thead><tbody>'+
  data.bulk_block_deals.map(function(d){return '<tr><td><b>'+esc(d.symbol)+'</b></td><td>'+esc(d.client)+'</td><td>'+esc(d.side)+'</td><td>'+esc(d.kind)+' Deal</td><td>'+fmt(d.quantity,0)+'</td><td>₹'+fmt(d.price)+'</td></tr>';}).join('')+
  '</tbody></table></div>':
  (data.coverage&&data.coverage.bulk_block_deals==="verified"?
   '<div class="dsba-note">इस तारीख की दोनों सत्यापित NSE रिपोर्टों में कोई Bulk / Block Deal रिकॉर्ड नहीं मिला।</div>':
   data.coverage&&data.coverage.bulk_block_deals==="partial"?
   '<div class="dsba-note">NSE की एक रिपोर्ट उपलब्ध है, दूसरी अनुपलब्ध है; सूची आंशिक है।</div>':
   '<div class="dsba-note">NSE की आधिकारिक Bulk / Block Deal रिपोर्ट अभी उपलब्ध नहीं हुई; नाम/मात्रा नहीं गढ़ी जाएगी।</div>'))+
 '</details>';
 root.innerHTML=html;
}
var style=document.createElement("style");
style.textContent='.dsba-head{display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap;font-weight:900;color:var(--text,#e8edf5)}.dsba-head span,.dsba-meta,.dsba-note,.dsba-strength{font-size:11px;color:var(--muted,#aab4c4)}.dsba-meta{margin:6px 0 10px}.dsba-summary{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px}.dsba-summary span{background:rgba(128,145,165,.12);border-radius:8px;padding:7px 9px;font-size:12px}.dsba-table-wrap{overflow-x:auto}.dsba-table{width:100%;border-collapse:collapse;font-size:12px;min-width:760px}.dsba-table th,.dsba-table td{padding:9px 8px;border-bottom:1px solid rgba(140,150,165,.2);text-align:left;vertical-align:top}.dsba-table th{color:var(--muted,#aab4c4);font-weight:800;white-space:nowrap}.dsba-positive{color:#2ecc71;font-weight:800}.dsba-negative{color:#ff5c67;font-weight:800}.dsba-signal{font-weight:800;white-space:nowrap}.dsba-buy{color:#2ecc71}.dsba-sell{color:#ff5c67}.dsba-watch{color:#f5c542}.dsba-cover{color:#45b9f3}.dsba-neutral{color:#aab4c4}.dsba-strength{display:block;margin-top:4px}.dsba-note{line-height:1.55;margin:10px 0}.dsba-details{margin-top:10px}.dsba-details summary{cursor:pointer;font-weight:800;color:var(--text,#e8edf5);padding:8px 0}';
document.head.appendChild(style);
fetch("daily_stock_buying_activity.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("activity report unavailable");return r.json();}).then(render).catch(function(){root.innerHTML='<div class="dsba-note">Daily Stock Buying Activity डेटा अभी उपलब्ध नहीं। NSE EOD scan सफल होने पर यहाँ दिखेगा।</div>';});
})();