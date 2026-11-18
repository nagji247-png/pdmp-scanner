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
function mainEvidence(r,side){
 var deals=Array.isArray(r.deal_evidence)?r.deal_evidence:[];
 var deal=deals.find(function(d){return String(d.side||"").toUpperCase()===side;});
 if(deal){
  var who=deal.client&&String(deal.client).trim();
  return "NSE disclosed "+side+(who?" · "+who:"");
 }
 var signal=String(r.signal||"");
 if(signal==="LONG BUILD-UP")return "Price ↑ + Futures OI ↑";
 if(signal==="SHORT BUILD-UP")return "Price ↓ + Futures OI ↑";
 if(signal==="LONG UNWINDING")return "Price ↓ + Futures OI ↓";
 if(signal==="DELIVERY WATCH")return "Delivery "+(r.delivery_pct==null?"उपलब्ध नहीं":fmt(r.delivery_pct)+"%");
 if(signal==="SELLING WATCH")return "Price ↓ + Volume "+fmt(r.volume_ratio)+"x";
 if(signal==="EARLY BUYING WATCH")return "Price ↑ + Volume "+fmt(r.volume_ratio)+"x";
 if(signal==="DISCLOSED BUY DEAL WATCH")return "NSE disclosed BUY";
 if(signal==="DISCLOSED SELL DEAL WATCH")return "NSE disclosed SELL";
 return Array.isArray(r.evidence)&&r.evidence.length?r.evidence.map(function(x){return String(x);}).join(" · "):"प्रमाण उपलब्ध नहीं";
}
function priceCell(r){
 var change=Number(r.change_pct),cls=change>0?"dsba-positive":change<0?"dsba-negative":"dsba-flat";
 return '<td class="dsba-price '+cls+'">₹'+fmt(r.price)+'<small>'+(change>0?"+":"")+fmt(r.change_pct)+'%</small></td>';
}
function stockRow(r,side){
 return '<tr data-stock="'+esc(r.symbol)+'"><td><button class="dsba-stock-open" data-symbol="'+esc(r.symbol)+'">'+esc(r.symbol)+'</button>'+(r.new_discovery?'<small class="dsba-discovery">NEW DISCOVERY</small>':'')+'</td>'+
  priceCell(r)+'<td>'+esc(mainEvidence(r,side))+'</td><td>'+(r.oi_change_pct==null?"—":(Number(r.oi_change_pct)>0?"+":"")+fmt(r.oi_change_pct)+"%")+'</td>'+
  '<td>'+(r.delivery_pct==null?"—":fmt(r.delivery_pct)+"%")+'</td><td>'+fmt(r.activity_days,0)+'</td><td>'+badge(r.signal)+'</td></tr>';
}
function shortlistRow(r,side){return stockRow(r,side);}

function evidenceText(r){return Array.isArray(r.evidence)?r.evidence.join(" · "):"प्रमाण उपलब्ध नहीं";}
function rowKind(r){
 if(["LONG BUILD-UP","DISCLOSED BUY DEAL WATCH","DELIVERY WATCH","EARLY BUYING WATCH","SHORT COVERING"].indexOf(r.signal)>=0)return "buy";
 if(["SHORT BUILD-UP","DISCLOSED SELL DEAL WATCH","SELLING WATCH","LONG UNWINDING"].indexOf(r.signal)>=0)return "sell";
 if(r.signal==="UNUSUAL ACTIVITY WATCH")return "unusual";
 if(r.signal==="DISCLOSED DEAL ACTIVITY WATCH"||Array.isArray(r.deal_evidence)&&r.deal_evidence.length)return "deals";
 return "other";
}
function chartUrl(r){
 var stockSymbol=String(r.symbol||"").replace(/[^A-Z0-9&_-]/gi,"");
 var exchange=stockSymbol==="FAZE3Q"?"BSE":"NSE";
 var symbol=encodeURIComponent(exchange+":"+stockSymbol);
 return "https://www.tradingview.com/widgetembed/?symbol="+symbol+"&interval=D&hidesidetoolbar=1&symboledit=1&saveimage=0&toolbarbg=%230f172a&theme=dark&style=1&timezone=Asia%2FKolkata&withdateranges=1&hideideas=1";
}
function openStock(r){
 var kind=rowKind(r), label=kind==="buy"?"BUYING":kind==="sell"?"SELLING":kind==="deals"?"DISCLOSED DEAL":kind==="unusual"?"UNUSUAL ACTIVITY":"ACTIVITY";
 var dealRows=(r.deal_evidence||[]).map(function(d){return '<tr><td>'+esc(d.kind)+'</td><td>'+esc(d.side)+'</td><td>'+esc(d.client)+'</td><td>'+fmt(d.quantity,0)+'</td><td>₹'+fmt(d.price)+'</td></tr>';}).join("");
 var fields=[
  ["Category",r.category],["EOD Date",r.as_of],["Closing Price","₹"+fmt(r.price)],["Price Change",(Number(r.change_pct)>0?"+":"")+fmt(r.change_pct)+"%"],
  ["Cash Volume",fmt(r.volume,0)],["Average Volume",fmt(r.average_volume_20,0)],["Volume Ratio",fmt(r.volume_ratio)+"x"],
  (r.oi_change_pct==null?null:["Futures OI Change",(Number(r.oi_change_pct)>0?"+":"")+fmt(r.oi_change_pct)+"%"]),
  (r.futures_change_pct==null?null:["Futures Price Change",(Number(r.futures_change_pct)>0?"+":"")+fmt(r.futures_change_pct)+"%"]),
  (r.futures_expiry?["Futures Expiry",r.futures_expiry]:null),["Delivery %",r.delivery_pct==null?"उपलब्ध नहीं":fmt(r.delivery_pct)+"%"],
  ["Delivery Quantity",fmt(r.delivery_qty,0)],["Delivery 20-session avg",r.delivery_avg_pct_20==null?"उपलब्ध नहीं":fmt(r.delivery_avg_pct_20)+"%"],
  ["Active Sessions",fmt(r.activity_days,0)],["Strength",r.strength||"उपलब्ध नहीं"],["Signal",r.signal]
 ];
 var html='<div class="dsba-modal-backdrop" data-close-modal="1"><section class="dsba-modal" role="dialog" aria-modal="true"><button class="dsba-back" data-back-stock="1">← Back to List</button><button class="dsba-close" data-close-modal="1">✕</button>'+
 '<h3>'+esc(r.symbol)+' · '+label+'</h3><div class="dsba-modal-sub">'+esc(r.signal)+' · '+esc(r.as_of||"EOD तारीख उपलब्ध नहीं")+'</div>'+
 '<div class="dsba-chart-actions"><button class="dsba-action" data-chart-toggle="1">TradingView Chart खोलें</button><a class="dsba-action dsba-link" href="'+chartUrl(r)+'" target="_blank" rel="noopener">Chart अलग टैब में</a></div>'+
 '<div class="dsba-chart" hidden><iframe title="'+esc(r.symbol)+' TradingView chart" src="'+chartUrl(r)+'" loading="lazy" referrerpolicy="no-referrer" allowfullscreen></iframe></div>'+
 '<div class="dsba-proof"><b>मुख्य प्रमाण</b><p>'+esc(mainEvidence(r,kind==="sell"?"SELL":"BUY"))+'</p><b>उपलब्ध प्रमाण</b><p>'+esc(evidenceText(r))+'</p></div>'+
 '<div class="dsba-table-wrap"><table class="dsba-table dsba-detail-table"><tbody>'+fields.filter(Boolean).map(function(x){return '<tr><th>'+esc(x[0])+'</th><td>'+esc(x[1])+'</td></tr>';}).join("")+'</tbody></table></div>'+
 (dealRows?'<h4>NSE Disclosed Deals</h4><div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Type</th><th>Side</th><th>Client</th><th>Quantity</th><th>Price</th></tr></thead><tbody>'+dealRows+'</tbody></table></div>':'')+
 (Array.isArray(r.missing_fields)&&r.missing_fields.length?'<p class="dsba-note">डेटा उपलब्ध नहीं: '+esc(r.missing_fields.join(" · "))+'</p>':'')+
 '</section></div>';
 root.insertAdjacentHTML("beforeend",html);
}
function openCategory(title,items){
 var html='<div class="dsba-modal-backdrop" data-close-modal="1"><section class="dsba-modal" role="dialog" aria-modal="true"><button class="dsba-close" data-close-modal="1">✕</button><h3>'+esc(title)+'</h3><div class="dsba-modal-sub">कुल '+items.length+' शेयर · सभी उपलब्ध योग्य रिकॉर्ड</div>'+
 (items.length?'<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Stock</th><th>Price</th><th>मुख्य प्रमाण</th><th>OI</th><th>Delivery %</th><th>Active Sessions</th><th>Signal</th></tr></thead><tbody>'+items.map(function(r){return stockRow(r,rowKind(r)==="sell"?"SELL":"BUY");}).join("")+'</tbody></table></div>':'<p class="dsba-note">इस श्रेणी में अभी सत्यापित डेटा उपलब्ध नहीं है।</p>')+'</section></div>';
 root.insertAdjacentHTML("beforeend",html);
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
 var sellingHtml='<div class="dsba-details" style="margin:8px 0"><b>TOP SELLING ACTIVITY</b><div class="dsba-meta">भारी बिकवाली का दबाव · ('+sellingShortlist.length+' / '+sellingCandidates.length+')</div>'+
  '<div class="dsba-note">यह EOD selling-pressure watch है, short recommendation नहीं। SHORT BUILD-UP के लिए भाव गिरना और उसी expiry का Futures OI बढ़ना चाहिए। केवल भाव/वॉल्यूम या Delivery % से seller की पहचान नहीं होती।</div>'+
  (sellingShortlist.length?'<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Stock</th><th>Price</th><th>मुख्य प्रमाण</th><th>OI</th><th>Delivery %</th><th>Active Sessions</th><th>Signal</th></tr></thead><tbody>'+
   sellingShortlist.map(function(r){return shortlistRow(r,"SELL");}).join('')+'</tbody></table></div>':
   '<div class="dsba-note">इस रिपोर्ट में सत्यापित selling-direction संकेत उपलब्ध नहीं हैं।</div>')+
  (sellingCandidates.length>10?'<div class="dsba-note">बाकी '+(sellingCandidates.length-10)+' selling-direction संकेत नीचे पूरी सूची में सुरक्षित हैं।</div>':'')+'</div>';
 var shortlist=buyingCandidates.slice(0,10);
 var shortlistHtml='<div class="dsba-details" style="margin:8px 0"><b>TOP BUYING ACTIVITY</b><div class="dsba-meta">भारी खरीदारी के संकेत · ('+shortlist.length+' / '+buyingCandidates.length+')</div>'+
  '<div class="dsba-note">यह उपलब्ध EOD प्रमाण के आधार पर प्राथमिकता सूची है, Buy recommendation नहीं। Delivery % अकेले संस्थागत खरीदारी साबित नहीं करता; disclosed BUY तभी दिखेगा जब NSE deal record उपलब्ध हो।</div>'+
  (shortlist.length?'<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Stock</th><th>Price</th><th>मुख्य प्रमाण</th><th>OI</th><th>Delivery %</th><th>Active Sessions</th><th>Signal</th></tr></thead><tbody>'+
   shortlist.map(function(r){return shortlistRow(r,"BUY");}).join('')+'</tbody></table></div>':
   '<div class="dsba-note">इस रिपोर्ट में सत्यापित खरीद-दिशा वाले संकेत उपलब्ध नहीं हैं।</div>')+
  (buyingCandidates.length>10?'<div class="dsba-note">बाकी '+(buyingCandidates.length-10)+' खरीद-दिशा संकेत नीचे पूरी सूची में सुरक्षित हैं।</div>':'')+'</div>';
 var fno=rows.filter(function(r){return r.category==="F&O";});
 var other=rows.filter(function(r){return r.category!=="F&O";});
 var html='<div class="dsba-head"><b>DAILY STOCK BUYING ACTIVITY</b><span>218 F&O + अन्य NSE शेयर</span></div>'+
 '<div class="dsba-meta">डेटा तारीख: '+esc(data.as_of||"उपलब्ध नहीं")+' · रिपोर्ट अपडेट: '+esc(data.generated_at||"समय उपलब्ध नहीं")+' · स्रोत: NSE official CM EOD</div>'+
 (data.coverage_counts?'<div class="dsba-meta">डेटा कवरेज: Cash '+fmt(data.coverage_counts.cash_quote_valid_symbols,0)+'/'+fmt(data.coverage_counts.nse_eq_symbols_scanned,0)+' · Futures OI '+fmt(data.coverage_counts.fno_symbols_with_same_expiry_oi,0)+'/'+fmt(data.coverage_counts.fno_symbols_in_master,0)+' F&O · Delivery '+fmt(data.coverage_counts.delivery_symbols_matched,0)+'/'+fmt(data.coverage_counts.delivery_eq_symbols_scanned,0)+' · Bulk/Block रिपोर्ट '+fmt(data.coverage_counts.bulk_block_reports_verified,0)+'/2 · Deals '+fmt(data.coverage_counts.bulk_block_deal_rows,0)+'</div>':'')+
 (function(){var stamp=Date.parse(String(data.as_of||"")+"T15:30:00+05:30");var age=Date.now()-stamp;return !Number.isFinite(stamp)?'<div class="dsba-note">चेतावनी: रिपोर्ट की तारीख सत्यापित नहीं हो सकी। इसे वर्तमान डेटा न मानें।</div>':age>96*60*60*1000?'<div class="dsba-note">चेतावनी: यह NSE EOD रिपोर्ट 4 दिन से अधिक पुरानी है। पिछला डेटा सुरक्षित रखा गया है, लेकिन नया EOD अपडेट उपलब्ध नहीं हुआ—इसे वर्तमान संकेत न मानें।</div>':"";})()+
 '<div class="dsba-summary"><span>F&O संकेत: <b>'+fno.length+'</b></span><span>अन्य NSE संकेत: <b>'+other.length+'</b></span><span>STRONG: <b>'+fmt(data.strength_summary&&data.strength_summary.STRONG,0)+'</b></span><span>WATCH: <b>'+fmt(data.strength_summary&&data.strength_summary.WATCH,0)+'</b></span><span>EARLY: <b>'+fmt(data.strength_summary&&data.strength_summary.EARLY,0)+'</b></span><span>स्कैन: <b>'+fmt(data.universe&&data.universe.nse_eq_symbols_scanned,0)+'</b> EQ शेयर</span></div>'+
 '<div class="dsba-overview">'+
 '<button class="dsba-overview-card dsba-card-buy" data-category="buy"><strong>'+rows.filter(function(r){return rowKind(r)==="buy";}).length+'</strong><span>BUYING ACTIVITY</span><small>खरीदारी के संकेत</small></button>'+
 '<button class="dsba-overview-card dsba-card-sell" data-category="sell"><strong>'+rows.filter(function(r){return rowKind(r)==="sell";}).length+'</strong><span>SELLING ACTIVITY</span><small>बिकवाली का दबाव</small></button>'+
 '<button class="dsba-overview-card dsba-card-unusual" data-category="unusual"><strong>'+rows.filter(function(r){return rowKind(r)==="unusual";}).length+'</strong><span>UNUSUAL ACTIVITY</span><small>असामान्य गतिविधि</small></button>'+
 '<button class="dsba-overview-card dsba-card-deals" data-category="deals"><strong>'+rows.filter(function(r){return Array.isArray(r.deal_evidence)&&r.deal_evidence.length>0;}).length+'</strong><span>DISCLOSED DEALS</span><small>Bulk / Block सौदे</small></button>'+
 '</div>'+
 shortlistHtml+
 sellingHtml+
 '<div class="dsba-details" style="margin:8px 0"><b>NSE Disclosed Deals</b>'+
 (function(){var top=shortlist.concat(sellingShortlist),deals=[];top.forEach(function(r){(r.deal_evidence||[]).forEach(function(d){deals.push({symbol:r.symbol,kind:d.kind,side:d.side,client:d.client});});});return deals.length?'<div class="dsba-table-wrap"><table class="dsba-table"><thead><tr><th>Stock</th><th>Type</th><th>Side</th><th>Client</th></tr></thead><tbody>'+deals.map(function(d){return '<tr><td>'+esc(d.symbol)+'</td><td>'+esc(d.kind||"—")+'</td><td>'+esc(d.side||"—")+'</td><td>'+esc(d.client||"नाम उपलब्ध नहीं")+'</td></tr>';}).join("")+'</tbody></table></div>':'<div class="dsba-note">Top 10 शेयरों के लिए इस तारीख का सत्यापित NSE disclosed deal रिकॉर्ड उपलब्ध नहीं है।</div>';})()+
 '</div>'+
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
 root.onclick=function(event){
  var back=event.target.closest("[data-back-stock]");
  if(back){var current=back.closest(".dsba-modal-backdrop");if(current)current.remove();return;}
  var close=event.target.closest("[data-close-modal]");
  if(close&&(close.classList.contains("dsba-close")||event.target===close)){var backdrop=close.closest(".dsba-modal-backdrop");if(backdrop)backdrop.remove();return;}
  var chart=event.target.closest("[data-chart-toggle]");
  if(chart){var panel=chart.parentNode.nextElementSibling;if(panel){panel.hidden=!panel.hidden;chart.textContent=panel.hidden?"TradingView Chart खोलें":"TradingView Chart बंद करें";}return;}
  var card=event.target.closest("[data-category]");
  if(card){var key=card.getAttribute("data-category");openCategory(card.querySelector("span").textContent,rows.filter(function(r){return key==="deals"?(Array.isArray(r.deal_evidence)&&r.deal_evidence.length>0):rowKind(r)===key;}));return;}
  var stock=event.target.closest("[data-symbol]");
  if(stock){var item=rows.find(function(r){return r.symbol===stock.getAttribute("data-symbol");});if(item){openStock(item);}return;}
  var row=event.target.closest("tr[data-stock]");
  if(row){var item=rows.find(function(r){return r.symbol===row.getAttribute("data-stock");});if(item)openStock(item);}
 };
}
var style=document.createElement("style");
style.textContent='.dsba-head{display:flex;justify-content:space-between;gap:6px;align-items:center;flex-wrap:wrap;font-weight:900;color:var(--text,#e8edf5)}.dsba-head span,.dsba-meta,.dsba-note,.dsba-strength{font-size:11px;color:var(--muted,#aab4c4)}.dsba-meta{margin:4px 0 6px}.dsba-summary{display:flex;gap:5px;flex-wrap:wrap;margin:5px 0 7px}.dsba-summary span{background:rgba(128,145,165,.12);border-radius:7px;padding:5px 7px;font-size:11px}.dsba-table-wrap{overflow-x:auto}.dsba-table{width:100%;border-collapse:collapse;font-size:12px;min-width:760px}.dsba-table th,.dsba-table td{padding:6px 6px;border-bottom:1px solid rgba(140,150,165,.2);text-align:left;vertical-align:top}.dsba-table th{color:var(--muted,#aab4c4);font-weight:800;white-space:nowrap}.dsba-positive{color:#2ecc71;font-weight:800}.dsba-negative{color:#ff5c67;font-weight:800}.dsba-flat{color:#d6dce5;font-weight:800}.dsba-price{white-space:nowrap}.dsba-price small{display:block;font-size:10px;margin-top:2px}.dsba-signal{font-weight:800;white-space:nowrap}.dsba-buy{color:#2ecc71}.dsba-sell{color:#ff5c67}.dsba-watch{color:#f5c542}.dsba-cover{color:#45b9f3}.dsba-neutral{color:#aab4c4}.dsba-strength{display:block;margin-top:2px}.dsba-note{line-height:1.45;margin:6px 0}.dsba-details{margin-top:5px}.dsba-discovery{display:block;margin-top:2px;color:#45b9f3;font-size:10px;font-weight:800;letter-spacing:.2px}.dsba-details summary{cursor:pointer;font-weight:800;color:var(--text,#e8edf5);padding:5px 0}.dsba-overview{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:10px 0}.dsba-overview-card{min-height:126px;text-align:left;padding:16px;border-radius:16px;border:1px solid #34506a;background:#102b42;color:#e8edf5;cursor:pointer;display:flex;flex-direction:column;gap:5px}.dsba-overview-card strong{font-size:34px;line-height:1.1}.dsba-overview-card span{font-size:12px;font-weight:900;letter-spacing:.3px}.dsba-overview-card small{font-size:12px;color:#b7c5d7}.dsba-card-buy{background:linear-gradient(145deg,#10382f,#0c2929);border-color:#258568}.dsba-card-buy strong{color:#27d9a5}.dsba-card-sell{background:linear-gradient(145deg,#3b202b,#271b2b);border-color:#a64760}.dsba-card-sell strong{color:#ff7188}.dsba-card-unusual{background:linear-gradient(145deg,#382b19,#2b241b);border-color:#a87935}.dsba-card-unusual strong{color:#ffbd59}.dsba-card-deals{background:linear-gradient(145deg,#142e49,#10243b);border-color:#3679a9}.dsba-card-deals strong{color:#62bafa}.dsba-stock-open{border:0;background:transparent;color:#78c8ff;text-decoration:underline;font:inherit;font-weight:800;cursor:pointer;padding:0}.dsba-modal-backdrop{position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.78);display:flex;align-items:center;justify-content:center;padding:12px}.dsba-modal{position:relative;width:min(100%,960px);max-height:92vh;overflow:auto;background:#101a2b;color:#e8edf5;border:1px solid #40536a;border-radius:14px;padding:16px;box-shadow:0 16px 60px rgba(0,0,0,.5)}.dsba-modal h3{margin:2px 40px 5px 0;font-size:18px}.dsba-modal h4{margin:14px 0 6px}.dsba-modal-sub{font-size:12px;color:#aab8ca;margin-bottom:10px}.dsba-back{border:1px solid #53677e;border-radius:8px;background:#1c2b40;color:#fff;padding:7px 10px;cursor:pointer;margin:0 8px 10px 0}.dsba-close{position:absolute;right:12px;top:10px;border:1px solid #53677e;border-radius:8px;background:#1c2b40;color:#fff;padding:7px 10px;cursor:pointer}.dsba-chart-actions{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.dsba-action{display:inline-block;border:1px solid #4d7596;background:#173753;color:#eaf5ff;border-radius:8px;padding:8px 11px;font-size:12px;text-decoration:none;cursor:pointer}.dsba-chart{height:420px;margin:8px 0 14px;border:1px solid #354b62;border-radius:8px;overflow:hidden}.dsba-chart iframe{width:100%;height:100%;border:0}.dsba-proof{background:#17263a;border-radius:8px;padding:10px;margin:10px 0;font-size:12px}.dsba-proof p{margin:4px 0 9px;color:#c2d1e1}.dsba-detail-table{min-width:0}.dsba-detail-table th{width:42%}@media(max-width:520px){.dsba-overview-card{min-height:112px;padding:12px}.dsba-overview-card strong{font-size:30px}.dsba-chart{height:340px}.dsba-modal{padding:13px}}';
document.head.appendChild(style);
fetch("daily_stock_buying_activity.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("activity report unavailable");return r.json();}).then(render).catch(function(){root.innerHTML='<div class="dsba-note">Daily Stock Buying Activity डेटा अभी उपलब्ध नहीं। NSE EOD scan सफल होने पर यहाँ दिखेगा।</div>';});
})();