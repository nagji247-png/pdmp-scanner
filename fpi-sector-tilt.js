(function(){
"use strict";
var box=document.getElementById("fpi-sector-tilt");
if(!box)return;
var master=null,companyData={stocks:{}},marketData={instruments:{}},fpiData={history:[]},overlay=null,body=null,activeSector="",lastView=null;
var css=document.createElement("style");
css.textContent=[
".fpi-eye{border:0!important;background:transparent!important;color:#7bdcff!important;padding:0 3px!important;margin:0!important;font-size:13px!important;line-height:1!important;cursor:pointer!important;flex:0 0 auto!important;min-width:0!important}",
".fpi-eye:focus-visible{outline:1px solid #7bdcff;outline-offset:2px;border-radius:3px}",
".fpi-stock-overlay{position:fixed;inset:0;z-index:10020;display:flex;align-items:center;justify-content:center;padding:9px;background:rgba(0,5,16,.84)}",
".fpi-stock-dialog{width:min(100%,720px);max-height:92vh;max-height:92dvh;display:flex;flex-direction:column;overflow:hidden;border:1px solid #28709b;border-radius:12px;background:#07152d;color:#e7f2ff;box-shadow:0 18px 55px #0009}",
".fpi-stock-head{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid #24466c;background:#0b1b33;flex:0 0 auto}",
".fpi-stock-head strong{font-size:13px;color:#6cecff;flex:1;min-width:0;overflow-wrap:anywhere}",
".fpi-stock-head button{border:1px solid #28709b;border-radius:7px;background:#102747;color:#d9edff;padding:7px 10px;font-size:11px;font-weight:800;cursor:pointer}",
".fpi-stock-body{overflow:auto;overscroll-behavior:contain;padding:10px;min-height:0}",
".fpi-stock-row{display:block;width:100%;padding:10px;border:0;border-top:1px solid #1a3557;background:transparent;color:inherit;text-align:left;cursor:pointer}",
".fpi-stock-row:first-child{border-top:0}",
".fpi-stock-row b{display:block;color:#6cecff;font-size:13px}",
".fpi-stock-row small{display:block;color:#9bb2d2;font-size:10px;line-height:1.5;margin-top:4px}",
".fpi-stock-empty{padding:12px;color:#ffca72;font-size:11px;line-height:1.6}",
".fpi-detail-panel{border:1px solid #1b426a;border-radius:9px;background:linear-gradient(145deg,#102747,#0a1930);padding:10px;margin:8px 0}",
".fpi-detail-panel h4{font-size:12px;color:#6cecff;margin:0 0 7px}",
".fpi-detail-panel p{font-size:11px;line-height:1.65;color:#d5e2f3;margin:4px 0;overflow-wrap:anywhere}",
".fpi-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:8px}",
".fpi-detail-stat{padding:8px;border:1px solid #24466c;border-radius:7px;background:#0b1b33;min-width:0}",
".fpi-detail-stat b{display:block;color:#6cecff;font-size:14px;overflow-wrap:anywhere}",
".fpi-detail-stat span{display:block;color:#9bb2d2;font-size:10px;margin-top:3px}",
".fpi-detail-foot{font-size:10px!important;color:#9bb2d2!important;margin-top:7px!important}",
".fpi-detail-link{color:#6cecff;text-decoration:none;font-weight:800}",
"@media(max-width:560px){.fpi-stock-overlay{padding:5px}.fpi-stock-dialog{max-height:94vh;max-height:94dvh;border-radius:10px}.fpi-stock-body{padding:8px}.fpi-detail-grid{gap:6px}.fpi-detail-panel{padding:9px}}"
].join("");
document.head.appendChild(css);
function esc(v){return String(v===null||v===undefined?"":v).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function num(v){if(v===null||v===undefined||v==="")return null;var x=Number(v);return Number.isFinite(x)?x:null;}
function missing(v){return v===null||v===undefined||v===""?"डेटा उपलब्ध नहीं":esc(v);}
function money(v){var x=num(v);return x===null?"डेटा उपलब्ध नहीं":"₹"+x.toLocaleString("en-IN",{maximumFractionDigits:2})+" Cr";}
function pct(v,delta){var x=num(v);if(x===null)return "डेटा उपलब्ध नहीं";var out=x.toFixed(2)+"%";var d=num(delta);if(d!==null)out+=" · पिछली तिमाही से "+(d>0?"+":"")+d.toFixed(2)+" pp";return out;}
function getStocks(sector){var rows=master&&master.stocks?master.stocks:{};return Object.keys(rows).filter(function(symbol){return String(rows[symbol].sector||"")===sector;}).sort().map(function(symbol){return {symbol:symbol,info:rows[symbol],company:companyData.stocks&&companyData.stocks[symbol]||{}};});}
function ensureOverlay(){
 if(overlay)return;
 overlay=document.createElement("div");overlay.className="fpi-stock-overlay";
 overlay.innerHTML='<div class="fpi-stock-dialog" role="dialog" aria-modal="true" aria-label="FPI सेक्टर स्टॉक विवरण"><div class="fpi-stock-head"><button type="button" data-fpi-back hidden>← वापस</button><strong data-fpi-title>FPI सेक्टर</strong><button type="button" data-fpi-close>✕ बंद</button></div><div class="fpi-stock-body" data-fpi-body></div></div>';
 document.body.appendChild(overlay);body=overlay.querySelector("[data-fpi-body]");
 overlay.addEventListener("click",function(e){if(e.target===overlay)close();});
 overlay.querySelector("[data-fpi-close]").addEventListener("click",close);
 overlay.querySelector("[data-fpi-back]").addEventListener("click",function(){renderSector(activeSector);});
 overlay.addEventListener("click",function(e){var stock=e.target.closest("[data-fpi-stock]");if(stock)renderStock(stock.getAttribute("data-fpi-stock"));});
 document.addEventListener("keydown",onKey);
}
function close(){if(overlay){overlay.remove();overlay=null;body=null;document.removeEventListener("keydown",onKey);}}
function onKey(e){if(e.key==="Escape")close();}
function setTitle(value,back){overlay.querySelector("[data-fpi-title]").textContent=value;overlay.querySelector("[data-fpi-back]").hidden=!back;}
function openSector(sector){
 activeSector=sector;ensureOverlay();setTitle(sector+" · सेक्टर स्टॉक",false);
 if(!master){body.innerHTML='<div class="fpi-stock-empty">NSE सेक्टर मास्टर लोड हो रहा है…</div>';loadMaster().then(function(){if(overlay)renderSector(sector);}).catch(function(){if(body)body.innerHTML='<div class="fpi-stock-empty">सेक्टर मास्टर उपलब्ध नहीं।</div>';});return;}
 renderSector(sector);
}
function renderSector(sector){
 if(!overlay)return;
 activeSector=sector;setTitle(sector+" · "+getStocks(sector).length+" F&O स्टॉक",false);
 var rows=getStocks(sector);
 body.innerHTML='<div class="fpi-stock-empty">यह सूची सत्यापित NSE F&O universe के 218 mapped स्टॉक्स तक सीमित है; सेक्टर के सभी listed stocks की पूरी सूची नहीं है।</div>'+(rows.length?rows.map(function(r){
  var q=marketData.instruments&&marketData.instruments[r.symbol]||{};
  var change=num(q.change_pct);
  var price=q.price===null||q.price===undefined?"भाव उपलब्ध नहीं":"₹"+Number(q.price).toLocaleString("en-IN",{maximumFractionDigits:2});
  var movement=change===null?"बदलाव उपलब्ध नहीं":(change>0?"+":"")+change.toFixed(2)+"%";
  return '<button class="fpi-stock-row" type="button" data-fpi-stock="'+esc(r.symbol)+'"><b>'+esc(r.symbol)+'　›</b><small>'+esc(r.company.company_name||r.info.company_name||"कंपनी नाम उपलब्ध नहीं")+' · '+esc(r.info.industry||r.company.industry||"इंडस्ट्री उपलब्ध नहीं")+'<br>'+price+' · '+movement+'</small></button>';
 }).join(""):'<div class="fpi-stock-empty">इस NSDL सेक्टर के लिए सत्यापित NSE F&O stock mapping उपलब्ध नहीं। कोई अनुमानित स्टॉक नहीं जोड़ा गया।</div>');
}
function renderStock(symbol){
 if(!overlay)return;
 var info=master&&master.stocks?master.stocks[symbol]||{}:{};
 var company=companyData.stocks?companyData.stocks[symbol]||{}:{};
 var q=marketData.instruments?marketData.instruments[symbol]||{}:{};
 var sh=company.shareholding||{},financials=company.financials||{},latest=financials.latest||{},quarters=Array.isArray(financials.quarters)?financials.quarters:[],integrated=company.integrated_financials||{},parsed=integrated.parsed||{},iq=parsed.quarter||{},bs=parsed.balance_sheet||{},filing=integrated.filing||{};
 var price=num(q.price);if(price===null)price=num(company.price);
 var previousClose=num(q.previous_close);if(previousClose===null)previousClose=num(company.previous_close);
 var change=num(q.change_pct);if(change===null)change=num(company.change_pct);
 var changeAbs=price!==null&&previousClose!==null?price-previousClose:null;
 if(change===null&&changeAbs!==null&&previousClose!==0)change=changeAbs/previousClose*100;
 var period=latest.period_end||"";
 function periodFresh(){if(!period)return false;var d=new Date(period);if(!Number.isFinite(d.getTime())){var m=period.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/);if(m){var months={Jan:0,Feb:1,Mar:2,Apr:3,May:4,Jun:5,Jul:6,Aug:7,Sep:8,Oct:9,Nov:10,Dec:11};d=new Date(Date.UTC(+m[3],months[m[2]]||0,+m[1]));}}var age=(Date.now()-d.getTime())/86400000;return Number.isFinite(age)&&age>=0&&age<=548;}
 var fresh=periodFresh();
 function old(v){return v===null||v===undefined?"डेटा उपलब्ध नहीं":fresh?esc(v):"पुराना रिकॉर्ड · "+esc(period);}
 function growth(field){if(!fresh)return period?"पुराना रिकॉर्ड · "+esc(period):"डेटा उपलब्ध नहीं";var now=num(quarters[0]&&quarters[0][field]),prev=num(quarters[4]&&quarters[4][field]);if(now===null||prev===null||prev===0)return "डेटा उपलब्ध नहीं";return ((now-prev)/Math.abs(prev)*100).toFixed(2)+"% YoY";}
 function ratio(label,value){return '<div class="fpi-stock-row"><span>'+esc(label)+'</span><b style="float:right">'+missing(value)+'</b></div>';}
 var quoteDate=q.price_as_of||company.price_as_of||company.market_data_as_of||company.checked_at||"उपलब्ध नहीं";
 var quoteSource=q.price_source||company.quote_source||"स्रोत उपलब्ध नहीं";
 var priceText=price===null?"कीमत उपलब्ध नहीं":"₹"+price.toLocaleString("en-IN",{maximumFractionDigits:2});
 var changeText=change===null?"बदलाव उपलब्ध नहीं":(change>0?"+":"")+change.toFixed(2)+"%";
 var changeAbsText=changeAbs===null?"₹ बदलाव उपलब्ध नहीं":(changeAbs>0?"+":"")+"₹"+Math.abs(changeAbs).toLocaleString("en-IN",{maximumFractionDigits:2});
 var priceTime=q.price_time||company.price_time||(company.market_data_type==="end_of_day"?"EOD बंद भाव · सटीक समय उपलब्ध नहीं":"समय उपलब्ध नहीं");
 var equity=num(bs.total_equity_cr),marketCapValue=num(company.market_cap_cr),totalShares=num(sh.total_shares);
 var pbRatio=marketCapValue!==null&&equity!==null&&equity>0?marketCapValue/equity:null;
 var bookValuePerShare=equity!==null&&equity>0&&totalShares!==null&&totalShares>0?equity*10000000/totalShares:null;
 var debtEquity=num(iq.debt_equity_ratio);
 var sector=info.sector||activeSector;
 var industry=company.industry||info.industry||"इंडस्ट्री उपलब्ध नहीं";
 var latestFpi=Array.isArray(fpiData.history)?fpiData.history[0]:null;
 var fpiSector=latestFpi&&Array.isArray(latestFpi.sectors)?latestFpi.sectors.find(function(item){return item.name===sector;}):null;
 var fpiFlow=fpiSector?num(fpiSector.net_equity_cr):null;
 var marketCap=company.market_cap_cr===null||company.market_cap_cr===undefined?"डेटा उपलब्ध नहीं":money(company.market_cap_cr);
 var marketCapDerived=company.market_cap_method==="derived_price_x_nse_shareholding_total_shares";
 var marketCapLabel=marketCapDerived?"Market Cap · गणना":"Market Cap";
 var marketCapNote=marketCapDerived
  ?"गणना: NSE भाव × NSE filed total shares · भाव तारीख़: "+missing(company.market_cap_price_as_of)+" · शेयर संख्या तारीख़: "+missing(company.market_cap_shares_as_of)
  :company.market_cap_source?"स्रोत: "+missing(company.market_cap_source):"प्रत्यक्ष Market Cap स्रोत उपलब्ध नहीं";
 var companyName=company.company_name||"कंपनी नाम उपलब्ध नहीं";
 var businessDescription=company.business_description||company.company_description||company.business_summary||"";
 var panels='';
 panels+='<div class="fpi-detail-panel"><h4>कंपनी का कारोबार</h4><p>कंपनी: '+esc(companyName)+'<br>NSE Symbol: '+esc(symbol)+'<br>इंडस्ट्री: '+esc(industry)+'<br>सेक्टर: '+esc(sector)+'<br>मुख्य व्यवसाय: '+(businessDescription?esc(businessDescription):"आधिकारिक कंपनी विवरण स्रोत से जोड़ना बाकी; अभी केवल सत्यापित Industry / Sector उपलब्ध")+'</p><p class="fpi-detail-foot">स्रोत: '+missing(company.quote_source||"NSE F&O Master")+' · Cache तारीख़: '+missing(company.checked_at)+'</p></div>';
 panels+='<div class="fpi-detail-panel"><h4>KNOW YOUR STOCK</h4><div class="fpi-detail-grid"><div class="fpi-detail-stat"><b>—</b><span>Good Quality · डेटा उपलब्ध नहीं</span></div><div class="fpi-detail-stat"><b>—</b><span>Valuation · डेटा उपलब्ध नहीं</span></div><div class="fpi-detail-stat"><b>—</b><span>Finance Trends · डेटा उपलब्ध नहीं</span></div><div class="fpi-detail-stat"><b>—</b><span>Overall View · अभी तय नहीं</span></div></div><p>Short Term: डेटा उपलब्ध नहीं<br>Long Term: डेटा उपलब्ध नहीं</p></div>';
 panels+='<div class="fpi-detail-panel"><h4>Market Snapshot</h4>'+ratio(marketCapLabel,marketCap)+'<p class="fpi-detail-foot">'+marketCapNote+'</p>'+ratio("1 Year Return","डेटा उपलब्ध नहीं")+ratio("Sector Return","डेटा उपलब्ध नहीं")+ratio("Market Return","डेटा उपलब्ध नहीं")+'</div>';
 panels+='<div class="fpi-detail-panel"><h4>Shareholding Pattern · नवीनतम तिमाही</h4><p>रिपोर्ट तारीख़: '+missing(sh.as_of)+'</p>'+ratio("Promoters",pct(sh.promoter_pct,sh.promoter_change_pp))+ratio("FII",pct(sh.fii_pct,sh.fii_change_pp))+ratio("DII",pct(sh.dii_pct,sh.dii_change_pp))+ratio("Public / Others",pct(sh.public_pct,sh.public_change_pp))+ratio("Employee Trust",pct(sh.employee_trust_pct,null))+'<p class="fpi-detail-foot">स्रोत: '+missing(sh.source)+' · XBRL taxonomy: '+missing(sh.taxonomy)+'</p></div>';
 panels+='<div class="fpi-detail-panel"><h4>Fundamental Ratios</h4>'+ratio("P/E Ratio","डेटा उपलब्ध नहीं · सत्यापित TTM EPS उपलब्ध नहीं")+ratio("P/B Ratio · गणना",pbRatio===null?"डेटा उपलब्ध नहीं":pbRatio.toFixed(2)+"× · Market Cap ÷ NSE XBRL Total Equity")+ratio("Book Value per Share · गणना",bookValuePerShare===null?"डेटा उपलब्ध नहीं":"₹"+bookValuePerShare.toFixed(2)+" · NSE XBRL Equity ÷ filed shares")+ratio("Latest Reported EPS",iq.basic_eps!==null&&iq.basic_eps!==undefined?"₹"+Number(iq.basic_eps).toFixed(2)+" · Integrated XBRL · "+missing(filing.quarter_end):old(latest.eps))+ratio("Book Value","डेटा उपलब्ध नहीं")+ratio("ROE","डेटा उपलब्ध नहीं")+ratio("ROCE","डेटा उपलब्ध नहीं")+ratio("Debt / Equity",debtEquity!==null?debtEquity.toFixed(4)+" · NSE Integrated XBRL · "+missing(filing.quarter_end):(fresh&&latest.debt_equity!==null&&latest.debt_equity!==undefined?Number(latest.debt_equity).toFixed(2)+" · NSE reported · "+missing(period):old(latest.debt_equity)))+ratio("Total Debt","डेटा उपलब्ध नहीं · सत्यापित aggregate debt fact उपलब्ध नहीं")+ratio("Profit Growth (YoY)",growth("net_profit_cr"))+ratio("Sales / Revenue Growth (YoY)",growth("revenue_cr"))+ratio("Operating Profit Margin","डेटा उपलब्ध नहीं")+ratio("Dividend Yield","डेटा उपलब्ध नहीं")+ratio("NSE XBRL Quarter Revenue",money(iq.revenue_cr))+ratio("NSE XBRL Quarter Net Profit",money(iq.net_profit_cr))+ratio("NSE XBRL Basic EPS",iq.basic_eps===null||iq.basic_eps===undefined?"डेटा उपलब्ध नहीं":"₹"+Number(iq.basic_eps).toFixed(2))+ratio("NSE XBRL Total Assets",money(bs.total_assets_cr))+ratio("NSE XBRL Total Equity",money(bs.total_equity_cr))+ratio("NSE XBRL Current Financial Liabilities",money(bs.current_financial_liabilities_cr))+ratio("NSE XBRL Non-current Financial Liabilities",money(bs.noncurrent_financial_liabilities_cr))+ratio("NSE XBRL Current Assets",money(bs.current_assets_cr))+ratio("NSE XBRL Non-current Assets",money(bs.noncurrent_assets_cr))+ratio("NSE XBRL Cash & Cash Equivalents",money(bs.cash_and_cash_equivalents_cr))+ratio("NSE XBRL Inventories",money(bs.inventories_cr))+ratio("NSE XBRL Trade Receivables",money(bs.trade_receivables_cr))+ratio("NSE XBRL Trade Payables",money(bs.trade_payables_cr))+ratio("NSE XBRL Property, Plant & Equipment",money(bs.property_plant_equipment_cr))+ratio("NSE XBRL Paid-up Equity",money(bs.paid_up_equity_cr))+'<p class="fpi-detail-foot">NSE Results Comparison: '+(fresh?"ताज़ा अवधि":"पुराना रिकॉर्ड · "+missing(period))+'<br>Integrated XBRL filing: '+missing(filing.quarter_end)+' · '+missing(filing.consolidated)+' · '+missing(filing.audited)+'<br>XBRL में कुल Liabilities का अलग सत्यापित fact उपलब्ध नहीं होने पर उसे नहीं निकाला जाता; नीचे केवल filed Financial Liabilities और Balance Sheet facts दिखते हैं।<br>XBRL स्रोत: '+missing(parsed.source)+' · '+missing(filing.url)+'<br>स्रोत: '+missing(financials.source)+' · '+missing(financials.note)+'</p></div>';
 panels+='<div class="fpi-detail-panel"><h4>Quality Scorecard</h4><p>Overall Quality Score: डेटा उपलब्ध नहीं<br>Financial Strength: डेटा उपलब्ध नहीं<br>Profitability: डेटा उपलब्ध नहीं<br>Management Risk: डेटा उपलब्ध नहीं<br>Company Growth: डेटा उपलब्ध नहीं<br>Business Quality: डेटा उपलब्ध नहीं</p><p class="fpi-detail-foot">सत्यापित वित्तीय डेटा और प्रकाशित scoring formula के बिना रेटिंग नहीं दी गई।</p></div>';
 panels+='<div class="fpi-detail-panel"><h4>Valuation Scorecard</h4><p>Valuation Score: डेटा उपलब्ध नहीं<br>Attractive / Expensive / Over-Priced: स्कोरिंग नियम सत्यापन बाकी</p><p class="fpi-detail-foot">P/B का सत्यापित गणना-आधारित अनुपात ऊपर दिखता है। P/E और अन्य तुलनीय valuation inputs उपलब्ध होने तथा sector-aware scoring rules तय होने तक मीटर की सुई नहीं चलाई जाती।</p></div>';
 panels+='<div class="fpi-detail-panel"><h4>Insights & Sector Position</h4><p>मुख्य सकारात्मक बातें: डेटा उपलब्ध नहीं<br>मुख्य जोखिम / कमजोरियाँ: डेटा उपलब्ध नहीं<br>सेक्टर में रैंक: डेटा उपलब्ध नहीं</p><p class="fpi-detail-foot">तुलनीय पूरे सेक्टर के verified dataset के बिना rank नहीं निकाली गई।</p></div>';
 panels+='<div class="fpi-detail-panel"><h4>FPI Sector Context · अलग संदर्भ</h4><p>सेक्टर: '+esc(sector)+'<br>NSDL Equity Net Investment: '+(fpiFlow===null?"डेटा उपलब्ध नहीं":(fpiFlow>0?"+":fpiFlow<0?"−":"")+"₹"+Math.abs(fpiFlow).toLocaleString("en-IN",{maximumFractionDigits:2})+" Cr")+'<br>रिपोर्ट अवधि: '+missing(latestFpi&&latestFpi.label||latestFpi&&latestFpi.end_date)+'</p><p class="fpi-detail-foot">स्रोत: '+(latestFpi&&latestFpi.source_url?'<a class="fpi-detail-link" href="'+esc(latestFpi.source_url)+'" target="_blank" rel="noopener">NSDL आधिकारिक रिपोर्ट ↗</a>':"डेटा स्रोत उपलब्ध नहीं")+'<br>यह पूरे सेक्टर का प्रवाह है, इस स्टॉक की अलग FPI खरीदारी/बिकवाली नहीं और PDMP Final Score का हिस्सा नहीं।</p></div>';
 panels+='<div class="fpi-detail-panel"><h4>Price & Trading Activity</h4><p>उपलब्ध कीमत: '+priceText+'<br>दैनिक बदलाव: '+changeText+'<br>वॉल्यूम: '+(q.volume==null?"डेटा उपलब्ध नहीं":Number(q.volume).toLocaleString("en-IN"))+'<br>वॉल्यूम तारीख़: '+missing(q.volume_as_of)+'<br>भाव तारीख़: '+missing(quoteDate)+'<br>स्रोत: '+missing(quoteSource)+'</p><p class="fpi-detail-foot">स्टॉक-स्तरीय वास्तविक buy/sell या FPI order-flow डेटा उपलब्ध नहीं है; कीमत/वॉल्यूम को institutional buying या selling नहीं कहा गया।</p><p><a class="fpi-detail-link" href="https://www.tradingview.com/chart/?symbol=NSE%3A'+encodeURIComponent(symbol)+'" target="_blank" rel="noopener">TradingView Chart खोलें ↗</a></p></div>';
 setTitle(symbol+" · Stock Detail",true);
 body.innerHTML='<div class="fpi-detail-panel"><h4>'+esc(companyName)+' · NSE: '+esc(symbol)+'</h4><div class="fpi-detail-grid"><div class="fpi-detail-stat"><b>'+priceText+'</b><span>अंतिम उपलब्ध भाव</span></div><div class="fpi-detail-stat"><b>'+changeAbsText+'</b><span>आज का बदलाव ₹ में</span></div><div class="fpi-detail-stat"><b>'+changeText+'</b><span>आज का बदलाव % में</span></div></div><p class="fpi-detail-foot">भाव तारीख़: '+missing(quoteDate)+' · समय: '+missing(priceTime)+' · स्रोत: '+missing(quoteSource)+'</p></div>'+panels;
 overlay.querySelector("[data-fpi-back]").hidden=false;
}
function loadMaster(){return fetch("nse-fo-stock-sector-master.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("NSE master HTTP "+r.status);return r.json();}).then(function(v){master=v;return v;});}
function loadData(){
 var tasks=[loadMaster(),fetch("stock-company-data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("company cache");return r.json();}).catch(function(){return {stocks:{}};}),fetch("data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("market data");return r.json();}).catch(function(){return {instruments:{}};}),fetch("fpi-sector-data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("FPI data");return r.json();}).catch(function(){return {history:[]};})];
 Promise.all(tasks).then(function(v){companyData=v[1]||{stocks:{}};marketData=v[2]||{instruments:{}};fpiData=v[3]||{history:[]};}).catch(function(){});
}
box.addEventListener("click",function(e){var eye=e.target.closest("[data-fpi-sector-eye]");if(eye){e.preventDefault();e.stopPropagation();openSector(eye.getAttribute("data-fpi-sector-eye"));return;}var stock=e.target.closest("[data-fpi-stock]");if(stock){renderStock(stock.getAttribute("data-fpi-stock"));}});
loadData();window.setInterval(loadData,5*60*1000);
})();