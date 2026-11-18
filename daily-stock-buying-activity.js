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
  "UNUSUAL ACTIVITY WATCH":["🟡","ma-watch"],
  "DISCLOSED BUY DEAL WATCH":["🟡","ma-watch"],
  "DISCLOSED SELL DEAL WATCH":["🟡","ma-watch"],
  "DISCLOSED DEAL ACTIVITY WATCH":["🟡","ma-watch"]
 };
 var m=map[signal]||["⚪","ma-neutral"];
 return '<span class="dsba-signal '+m[1]+'">'+m[0]+' '+esc(signal||"DATA UNAVAILABLE")+'</span>';
}
function render(data){
 if(!data||!Array.isArray(data.rows)){root.innerHTML='<div class="dsba-note">Daily buying activity डेटा उपलब्ध नहीं।</div>';return;}
 var rows=data.rows;
 var buyingCandidates=rows.filter(function(r){
  return ["LONG BUILD-UP","DISCLOSED BUY DEAL WATCH","DELIVERY WATCH","EARLY BUYING WATCH"].indexOf(r.signal)>=0;
 });
 var priorityOrder={"LONG BUILD-UP":0,"DISCLOSED BUY DEAL WATCH":1,"DELIVERY WATCH":2,"EARLY BUYING WATCH":3};
 buyingCandidates.sort(function(a,b){
  var tier=(priorityOrder[a.signal]||0)-(priorityOrder[b.signal]||0);
  if(tier)return tier;
  return (Number(b.volume_ratio)||0)-(Number(a.volume_ratio)||0)
   ||(Number(b.change_pct)||0)-(Number(a.change_pct)||0)
   ||(Number(b.activity_days)||0)-(Number(a.activity_days)||0)
   ||String(a.symbol).localeCompare(String(b.symbol));
 });
 var sellingCandidates=rows.filter(function(r){
  return ["SHORT BUILD-UP","DISCLOSED SELL DEAL WATCH","SELLING WATCH","LONG UNWINDING"].indexOf(r.signal)>=0;
 });
 var sellingPriority={"SHORT BUILD-UP":0,"DISCLOSED SELL DEAL WATCH":1,"SELLING WATCH":2,"LONG UNWINDING":3};
 sellingCandidates.sort(function(a,b){
  var tier=(sellingPriority[a.signal]||0)-(sellingPriority[b.signal]||0);
  if(tier)return tier;
  return (Number(a.change_pct)||0)-(Number(b.change_pct)||0)
   ||(Number(b.volume_ratio)||0)-(Number(a.volume_ratio)||0)
   ||(Number(b.activity_days)||0)-(Number(a.activity_days)||0)
   ||String(a.symbol).localeCompare(String(b.symbol));
 });
 var sellingShortlist=sellingCandidates.slice(0,10);
 var sellingHtml='<div class="dsba-details" style="margin:8px 0"><b>भारी बिकवाली / Selling Pressure</b> <span class="dsba-meta">('+sellingShortlist.length+' / '+sellingCandidates.length+')</span>'+
  '<div class="dsba-note">यह EOD selling-pressure watch है, short recommendation नहीं। SHORT BUILD-UP के लिए भाव गिरना और Futures OI बढ़ना चाहिए; केवल भाव/वॉल्यूम से seller की पहचान नहीं होती।</div>'+
  (sellingShortlist.length?'<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Stock</th><th>Price %</th><th>Volume</th><th>OI</th><th>Delivery %</th><th>Signal</th></tr></thead><tbody>'+
   sellingShortlist.map(function(r){
    var oi=r.oi_change_pct==null?(r.category==="F&O"?"उपलब्ध नहीं":"लागू नहीं"):(Number(r.oi_change_pct)>0?"+":"")+fmt(r.oi_change_pct)+'%';
    return '<tr><td><b>'+esc(r.symbol)+'</b>'+(r.new_discovery?'<small class="dsba-discovery">NEW DISCOVERY</small>':'')+'</td>'+
     '<td class="'+(Number(r.change_pct)>=0?"dsba-positive":"dsba-negative")+'">'+(Number(r.change_pct)>0?"+":"")+fmt(r.change_pct)+'%</td>'+
     '<td>'+fmt(r.volume_ratio)+'x औसत</td><td>'+esc(oi)+'</td>'+
     '<td>'+(r.delivery_pct==null?'उपलब्ध नहीं':fmt(r.delivery_pct)+'%')+'</td>'+
     '<td>'+badge(r.signal)+'<small class="dsba-strength">'+esc(r.strength||'')+'</small></td></tr>';
   }).join('')+'</tbody></table></div>':
   '<div class="dsba-note">इस रिपोर्ट में सत्यापित selling-direction संकेत उपलब्ध नहीं हैं।</div>')+
  (sellingCandidates.length>10?'<div class="dsba-note">बाकी '+(sellingCandidates.length-10)+' selling-direction संकेत नीचे पूरी सूची में सुरक्षित हैं।</div>':'')+'</div>';
 var shortlist=buyingCandidates.slice(0,10);
 var shortlistHtml='<div class="dsba-details" style="margin:8px 0"><b>पहले देखने योग्य खरीद संकेत</b> <span class="dsba-meta">('+shortlist.length+' / '+buyingCandidates.length+')</span>'+
  '<div class="dsba-note">यह उपलब्ध EOD प्रमाण के आधार पर प्राथमिकता सूची है, Buy recommendation नहीं। DELIVERY WATCH में डिलीवरी संकेत, जबकि EARLY BUYING में केवल सकारात्मक भाव + असामान्य वॉल्यूम है; OI/डिलीवरी/सौदे की पुष्टि अलग से देखें।</div>'+
  (shortlist.length?'<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Stock</th><th>Price %</th><th>Volume</th><th>OI</th><th>Delivery %</th><th>Signal</th></tr></thead><tbody>'+
   shortlist.map(function(r){
    var oi=r.oi_change_pct==null?(r.category==="F&O"?"उपलब्ध नहीं":"लागू नहीं"):(Number(r.oi_change_pct)>0?"+":"")+fmt(r.oi_change_pct)+'%';
    return '<tr><td><b>'+esc(r.symbol)+'</b>'+(r.new_discovery?'<small class="dsba-discovery">NEW DISCOVERY</small>':'')+'</td>'+
     '<td class="'+(Number(r.change_pct)>=0?"dsba-positive":"dsba-negative")+'">'+(Number(r.change_pct)>0?"+":"")+fmt(r.change_pct)+'%</td>'+
     '<td>'+fmt(r.volume_ratio)+'x औसत</td><td>'+esc(oi)+'</td>'+
     '<td>'+(r.delivery_pct==null?'उपलब्ध नहीं':fmt(r.delivery_pct)+'%')+'</td>'+
     '<td>'+badge(r.signal)+'<small class="dsba-strength">'+esc(r.strength||'')+'</small></td></tr>';
   }).join('')+'</tbody></table></div>':
   '<div class="dsba-note">इस रिपोर्ट में सत्यापित खरीद-दिशा वाले संकेत उपलब्ध नहीं हैं।</div>')+
  (buyingCandidates.length>10?'<div class="dsba-note">बाकी '+(buyingCandidates.length-10)+' खरीद-दिशा संकेत नीचे पूरी सूची में सुरक्षित हैं।</div>':'')+'</div>';
 var fno=rows.filter(function(r){return r.category==="F&O";});
 var other=rows.filter(function(r){return r.category!=="F&O";});
 var html='<div class="dsba-head"><b>DAILY STOCK BUYING ACTIVITY</b><span>218 F&O + अन्य NSE शेयर</span></div>'+
 '<div class="dsba-meta">डेटा तारीख: '+esc(data.as_of||"उपलब्ध नहीं")+' · रिपोर्ट अपडेट: '+esc(data.generated_at||"समय उपलब्ध नहीं")+' · स्रोत: NSE official CM EOD</div>'+
 (data.coverage_counts?'<div class="dsba-meta">डेटा कवरेज: Cash '+fmt(data.coverage_counts.cash_quote_valid_symbols,0)+'/'+fmt(data.coverage_counts.nse_eq_symbols_scanned,0)+' · Futures OI '+fmt(data.coverage_counts.fno_symbols_with_same_expiry_oi,0)+'/'+fmt(data.coverage_counts.fno_symbols_in_master,0)+' F&O · Delivery '+fmt(data.coverage_counts.delivery_symbols_matched,0)+'/'+fmt(data.coverage_counts.delivery_eq_symbols_scanned,0)+' · Bulk/Block रिपोर्ट '+fmt(data.coverage_counts.bulk_block_reports_verified,0)+'/2 · Deals '+fmt(data.coverage_counts.bulk_block_deal_rows,0)+'</div>':'')+
 (function(){var stamp=Date.parse(String(data.as_of||"")+"T15:30:00+05:30");var age=Date.now()-stamp;return !Number.isFinite(stamp)?'<div class="dsba-note">चेतावनी: रिपोर्ट की तारीख सत्यापित नहीं हो सकी। इसे वर्तमान डेटा न मानें।</div>':age>96*60*60*1000?'<div class="dsba-note">चेतावनी: यह NSE EOD रिपोर्ट 4 दिन से अधिक पुरानी है। पिछला डेटा सुरक्षित रखा गया है, लेकिन नया EOD अपडेट उपलब्ध नहीं हुआ—इसे वर्तमान संकेत न मानें।</div>':"";})()+
 '<div class="dsba-summary"><span>F&O संकेत: <b>'+fno.length+'</b></span><span>अन्य NSE संकेत: <b>'+other.length+'</b></span><span>STRONG: <b>'+fmt(data.strength_summary&&data.strength_summary.STRONG,0)+'</b></span><span>WATCH: <b>'+fmt(data.strength_summary&&data.strength_summary.WATCH,0)+'</b></span><span>EARLY: <b>'+fmt(data.strength_summary&&data.strength_summary.EARLY,0)+'</b></span><span>स्कैन: <b>'+fmt(data.universe&&data.universe.nse_eq_symbols_scanned,0)+'</b> EQ शेयर</span></div>'+
 shortlistHtml+
 sellingHtml+
 '<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Stock</th><th>Category</th><th>Price</th><th>OI</th><th>Delivery %</th><th>Active Sessions</th><th>Signal</th><th>Buying Evidence</th></tr></thead><tbody>';
 if(!rows.length)html+='<tr><td colspan="8">इस EOD स्कैन में कोई सत्यापित Buying / Activity संकेत नहीं मिला।</td></tr>';
 rows.forEach(function(r){
  var dealText=(r.deal_evidence||[]).map(function(d){
   return "NSE "+esc(d.kind||"")+" "+esc(d.side||"")+" · "+esc(d.client||"नाम उपलब्ध नहीं")+" · "+fmt(d.quantity,0)+" शेयर · ₹"+fmt(d.price);
  }).join(" | ");
  var unavailableFields=Array.isArray(r.missing_fields)?r.missing_fields.filter(function(x){return x!=="Futures OI लागू नहीं";}):[];
  var notApplicableFields=Array.isArray(r.missing_fields)&&r.missing_fields.indexOf("Futures OI लागू नहीं")>=0;
  var fieldLabels={"Cash Volume":"कैश वॉल्यूम","Cash Volume baseline":"वॉल्यूम का पिछला औसत","Security-wise Delivery %":"डिलीवरी %","Futures OI":"Futures OI"};
  html+='<tr><td><b>'+esc(r.symbol)+'</b>'+(r.new_discovery?'<small class="dsba-discovery">NEW DISCOVERY</small>':'')+'</td><td>'+esc(r.category)+'</td><td class="'+(Number(r.change_pct)>=0?"dsba-positive":"dsba-negative")+'">₹'+fmt(r.price)+'<small class="dsba-strength">'+(Number(r.change_pct)>0?"+":"")+fmt(r.change_pct)+'%</small></td><td>'+(r.oi_change_pct==null?"—":(Number(r.oi_change_pct)>0?"+":"")+fmt(r.oi_change_pct)+'%')+'</td><td>'+(r.delivery_pct==null?"—":fmt(r.delivery_pct)+'%')+'</td><td>'+fmt(r.activity_days,0)+'</td><td>'+badge(r.signal)+'<small class="dsba-strength">'+esc(r.strength||"")+'</small></td><td>'+esc((r.evidence||[]).join(" · "))+(dealText?'<small class="dsba-strength">'+dealText+'</small>':'')+(unavailableFields.length?'<small class="dsba-strength">डेटा उपलब्ध नहीं: '+esc(unavailableFields.map(function(x){return fieldLabels[x]||x;}).join(', '))+'</small>':'')+(notApplicableFields?'<small class="dsba-strength">लागू नहीं: Futures OI</small>':'')+'<small class="dsba-strength">वॉल्यूम औसत से '+fmt(r.volume_ratio)+' गुना · आधार: '+fmt(r.average_volume_sessions,0)+' सत्र</small></td></tr>';
 });
 html+='</tbody></table></div>'+
 '<div class="dsba-note">OI केवल उसी expiry के दो लगातार सत्रों से सत्यापित होने पर दिखेगा। Delivery % केवल उसी तारीख की NSE Full Bhavcopy से मिलेगा। EARLY BUYING WATCH केवल भाव + असामान्य वॉल्यूम का शुरुआती संकेत है, पक्की खरीदारी नहीं। यह EOD स्कैन है—इंट्राडे एंट्री अलर्ट नहीं।</div>'+
 '<details class="dsba-details"><summary>पिछले संकेतों का नतीजा (1 / 3 / 5 सत्र)</summary>'+
 '<div class="dsba-summary"><span>1 सत्र: सही '+fmt((data.outcome_summary&&data.outcome_summary[1]||{}).right,0)+' · गलत '+fmt((data.outcome_summary&&data.outcome_summary[1]||{}).wrong,0)+' · Pending '+fmt((data.outcome_summary&&data.outcome_summary[1]||{}).pending,0)+'</span><span>3 सत्र: सही '+fmt((data.outcome_summary&&data.outcome_summary[3]||{}).right,0)+' · गलत '+fmt((data.outcome_summary&&data.outcome_summary[3]||{}).wrong,0)+' · Pending '+fmt((data.outcome_summary&&data.outcome_summary[3]||{}).pending,0)+'</span><span>5 सत्र: सही '+fmt((data.outcome_summary&&data.outcome_summary[5]||{}).right,0)+' · गलत '+fmt((data.outcome_summary&&data.outcome_summary[5]||{}).wrong,0)+' · Pending '+fmt((data.outcome_summary&&data.outcome_summary[5]||{}).pending,0)+'</span></div>'+
 (Array.isArray(data.signal_history)&&data.signal_history.length?
  '<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>तारीख</th><th>Stock</th><th>संकेत</th><th>1 सत्र</th><th>3 सत्र</th><th>5 सत्र</th></tr></thead><tbody>'+
  data.signal_history.slice(0,30).map(function(h){return '<tr><td>'+esc(h.date)+'</td><td><b>'+esc(h.symbol)+'</b></td><td>'+esc(h.signal)+'</td><td>'+esc(h.outcomes&&h.outcomes["1D"])+'</td><td>'+esc(h.outcomes&&h.outcomes["3D"])+'</td><td>'+esc(h.outcomes&&h.outcomes["5D"])+'</td></tr>';}).join('')+
  '</tbody></table></div>':
  '<div class="dsba-note">अभी पर्याप्त ऐतिहासिक सत्र उपलब्ध नहीं हैं।</div>')+
 '<div class="dsba-note">नतीजे केवल NSE cash EOD price-volume दिशा पर आधारित हैं। Pending नतीजे सही/गलत में नहीं गिने जाते; यह संस्थागत खरीदारी की पुष्टि नहीं है।</div></details>'+
 '<details class="dsba-details"><summary>बड़े सौदों की गतिविधि (Bulk / Block Deals)</summary>'+
 (data.coverage&&data.coverage.bulk_block_deals==="partial"?'<div class="dsba-note">चेतावनी: NSE की केवल एक रिपोर्ट सत्यापित हुई है। नीचे की सूची आंशिक है; दूसरी रिपोर्ट उपलब्ध नहीं है।</div>':'')+
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
style.textContent='.dsba-head{display:flex;justify-content:space-between;gap:6px;align-items:center;flex-wrap:wrap;font-weight:900;color:var(--text,#e8edf5)}.dsba-head span,.dsba-meta,.dsba-note,.dsba-strength{font-size:11px;color:var(--muted,#aab4c4)}.dsba-meta{margin:4px 0 6px}.dsba-summary{display:flex;gap:5px;flex-wrap:wrap;margin:5px 0 7px}.dsba-summary span{background:rgba(128,145,165,.12);border-radius:7px;padding:5px 7px;font-size:11px}.dsba-table-wrap{overflow-x:auto}.dsba-table{width:100%;border-collapse:collapse;font-size:12px;min-width:760px}.dsba-table th,.dsba-table td{padding:6px 6px;border-bottom:1px solid rgba(140,150,165,.2);text-align:left;vertical-align:top}.dsba-table th{color:var(--muted,#aab4c4);font-weight:800;white-space:nowrap}.dsba-positive{color:#2ecc71;font-weight:800}.dsba-negative{color:#ff5c67;font-weight:800}.dsba-signal{font-weight:800;white-space:nowrap}.dsba-buy{color:#2ecc71}.dsba-sell{color:#ff5c67}.dsba-watch{color:#f5c542}.dsba-cover{color:#45b9f3}.dsba-neutral{color:#aab4c4}.dsba-strength{display:block;margin-top:2px}.dsba-note{line-height:1.45;margin:6px 0}.dsba-details{margin-top:5px}.dsba-discovery{display:block;margin-top:2px;color:#45b9f3;font-size:10px;font-weight:800;letter-spacing:.2px}.dsba-details summary{cursor:pointer;font-weight:800;color:var(--text,#e8edf5);padding:5px 0}';
document.head.appendChild(style);
fetch("daily_stock_buying_activity.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("activity report unavailable");return r.json();}).then(render).catch(function(){root.innerHTML='<div class="dsba-note">Daily Stock Buying Activity डेटा अभी उपलब्ध नहीं। NSE EOD scan सफल होने पर यहाँ दिखेगा।</div>';});
})();