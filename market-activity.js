(function(){
"use strict";
var root=document.getElementById("market-activity");if(!root)return;
var master=null,fpi=null,marketData=null,companyResearch=null,drawings={snapshots:{}},searchTerm="",stack=[{type:"home",scroll:0}],loading=false,viewRoot=root,popupLayer=null,popupBody=null,bodyOverflowBefore="";
var css=[
".market-activity-box{min-width:0;color:#e7f2ff}",
".ma-kicker{font-size:10px;letter-spacing:1px;color:#6cecff;font-weight:900;margin:14px 0 6px}",
".ma-intro{font-size:11px;color:#9bb2d2;line-height:1.5;margin:5px 0 10px}",
".ma-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:9px 0 14px}",
".ma-stat,.ma-sector,.ma-flow,.ma-panel{border:1px solid #1b426a;border-radius:10px;background:linear-gradient(145deg,#102747,#0a1930);min-width:0}",
".ma-stat{padding:0;overflow:hidden}.ma-stat-button{display:block;width:100%;height:100%;padding:11px;border:0;background:transparent;color:inherit;text-align:left;cursor:pointer}.ma-stat b{display:block;font-size:22px;color:#36e7ff}.ma-stat span{font-size:10px;color:#a9bfdc;line-height:1.4}.ma-stat-button:active{background:#173453}",".ma-stat.bull{border-color:#247a5a;background:linear-gradient(145deg,#10372f,#0a241f)}.ma-stat.bull b{color:#20e6ac}.ma-stat.bear{border-color:#9a3c50;background:linear-gradient(145deg,#3a202c,#241722)}.ma-stat.bear b{color:#ff7184}.ma-stat.unusual{border-color:#a86a24;background:linear-gradient(145deg,#3a2b18,#241d14)}.ma-stat.unusual b{color:#ffbd59}.ma-stat.fpi{border-color:#286a9c;background:linear-gradient(145deg,#102d49,#0a1c32)}.ma-stat.fpi b{color:#62bfff}",
".ma-alert{display:block;width:100%;text-align:left;padding:10px;margin:7px 0;border:1px solid #24466c;border-left:3px solid #f0b64d;border-radius:9px;background:#0b1b33;color:#e7f2ff;font-size:12px;cursor:pointer}.ma-alert.high{border-left-color:#ff596e}.ma-alert.watch{border-left-color:#ffbd59}.ma-alert.flow{border-left-color:#62bfff}.ma-alert-label{font-size:10px;font-weight:900;letter-spacing:.5px;margin-right:6px}.ma-alert.high .ma-alert-label{color:#ff7184}.ma-alert.watch .ma-alert-label{color:#ffbd59}.ma-alert.flow .ma-alert-label{color:#62bfff}",
".ma-alert small{display:block;color:#9bb2d2;font-size:10px;margin-top:3px}",
".ma-sector-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ma-sector{overflow:hidden}",
".ma-sector-button,.ma-stock-button{display:block;width:100%;border:0;text-align:left;color:inherit;background:transparent;cursor:pointer;padding:11px}",
".ma-sector-head,.ma-stock-head{display:flex;justify-content:space-between;align-items:center;gap:7px}.ma-sector-name{font-size:12px;font-weight:850}.ma-count,.ma-tag{font-size:9px;color:#9bb2d2;white-space:nowrap}",
".ma-state{display:inline-block;font-size:9px;font-weight:800;padding:3px 6px;border-radius:5px;margin-top:7px;background:#172c49;color:#a9bfdc}.ma-state.bull{color:#20e6ac;background:#10372f}.ma-state.bear{color:#ff8795;background:#3a202c}",".ma-sector.bull{border-left:3px solid #20e6ac}.ma-sector.bear{border-left:3px solid #ff7184}.ma-sector.neutral{border-left:3px solid #8495b8}.ma-stock-row.bull{border-left:3px solid #20e6ac}.ma-stock-row.bear{border-left:3px solid #ff7184}.ma-stock-row.neutral{border-left:3px solid #8495b8}.ma-state.neutral{color:#b8c4d8;background:#263247}",
".ma-meta{display:flex;flex-wrap:wrap;gap:5px 9px;margin-top:7px;font-size:10px;color:#a9bfdc}.ma-up{color:#20e6ac}.ma-down{color:#ff7184}.ma-neutral{color:#a9bfdc}.ma-warn{color:#ffca72}",
".ma-stock-row{border-top:1px solid #1a3557}.ma-stock-button{padding:12px 10px}.ma-symbol{font-size:13px;font-weight:900;color:#6cecff}.ma-stock-meta{font-size:11px;color:#a9bfdc;line-height:1.6;margin-top:7px;overflow-wrap:anywhere}",
".ma-panel{padding:11px;margin:8px 0}.ma-panel h4{font-size:12px;margin:0 0 6px;color:#6cecff}.ma-reason{font-size:11px;line-height:1.65;color:#d5e2f3}.ma-signal{padding:10px;border-radius:8px;background:#101f39;border:1px solid #24466c;margin-top:9px;font-size:12px;line-height:1.6}",
".ma-flow{padding:10px;margin:7px 0}.ma-flow b{font-size:12px}.ma-flow small{display:block;font-size:10px;color:#9bb2d2;margin-top:4px}",
".ma-foot,.ma-empty{font-size:10px;color:#9bb2d2;line-height:1.5;margin-top:10px}",".ma-chart-preview{border:1px solid #9272d6;border-radius:10px;background:linear-gradient(145deg,#211a3b,#10172f);padding:10px;margin:8px 0 12px}.ma-chart-preview img{display:block;width:100%;height:auto;border-radius:7px;background:#07152d}.ma-chart-preview>b,.ma-chart-preview .ma-stock-head b{color:#c5a7ff}.ma-chart-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:9px}.ma-chart-link{display:inline-block;padding:9px 11px;border:1px solid #9272d6;border-radius:7px;color:#c5a7ff;text-decoration:none;font-size:11px;font-weight:800}.ma-chart-missing{font-size:11px;color:#ffca72;line-height:1.6}",
".ma-nav{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:8px;padding:8px 0 10px;background:#07152d;border-bottom:1px solid #24466c;margin-bottom:10px}",
".ma-back{border:1px solid #35709a;border-radius:8px;background:#102747;color:#6cecff;padding:9px 12px;font-size:12px;font-weight:800;cursor:pointer;white-space:nowrap}.ma-nav-title{font-size:13px;font-weight:900;color:#e7f2ff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
".ma-search{width:100%;padding:11px;border:1px solid #285078;border-radius:9px;background:#07172d;color:#e7f2ff;font-size:13px;margin:4px 0 10px}",
".ma-master{margin:8px 0}.ma-master>details{border:1px solid #1b426a;border-radius:10px;background:#0b1b33;padding:10px}.ma-master>details>summary{cursor:pointer;color:#6cecff;font-size:12px;font-weight:800}.ma-master-list details{border-top:1px solid #1a3557;padding:8px 2px}.ma-master-list summary{cursor:pointer;color:#d5e2f3;font-size:11px}",
"@media(max-width:560px){.ma-sector-grid{grid-template-columns:1fr}.ma-stat{padding:9px}.ma-sector-button{padding:10px}}",
".ma-admin-open{width:100%;padding:10px;border:1px solid #28709b;border-radius:8px;background:#102747;color:#6cecff;font-size:12px;font-weight:800;cursor:pointer}.ma-drawing-overlay{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;padding:12px;background:rgba(0,5,16,.82)}.ma-drawing-dialog{width:min(100%,520px);max-height:86vh;overflow:auto;border:1px solid #28709b;border-radius:13px;background:#07152d;box-shadow:0 18px 55px rgba(0,0,0,.55);padding:13px}.ma-drawing-dialog-head{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:13px;font-weight:900;color:#6cecff}.ma-drawing-close,.ma-drawing-action{padding:9px 11px;border:1px solid #28709b;border-radius:7px;background:#102747;color:#d9edff;font-size:11px;font-weight:800;cursor:pointer}.ma-drawing-field{display:block;margin:12px 0 5px;color:#b9c9e8;font-size:11px;font-weight:700}.ma-drawing-input{width:100%;padding:11px;border:1px solid #285078;border-radius:8px;background:#050f22;color:#e7f2ff;font-size:13px}.ma-drawing-help{font-size:10px;line-height:1.5;color:#9bb2d2;margin:7px 0}.ma-drawing-error{font-size:11px;line-height:1.5;color:#ff929e;margin:8px 0}.ma-drawing-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.ma-drawing-action.primary{background:#123b43;border-color:#1b927c;color:#75f0ca}.ma-drawing-action.danger{border-color:#a94c5a;color:#ff929e}.ma-drawing-bottom{display:flex;justify-content:flex-end;margin-top:14px;padding-top:10px;border-top:1px solid #183252}@media(max-width:560px){.ma-drawing-overlay{padding:7px}.ma-drawing-dialog{max-height:90vh;padding:11px}}"
].join("");
var st=document.createElement("style");st.textContent=css;document.head.appendChild(st);
var popupCss=document.createElement("style");popupCss.textContent=".ma-view-overlay{position:fixed;inset:0;z-index:9990;display:flex;align-items:center;justify-content:center;padding:10px;background:rgba(0,5,16,.82)}.ma-view-dialog{width:min(100%,760px);max-height:90vh;max-height:90dvh;overflow:hidden;border:1px solid #28709b;border-radius:13px;background:#07152d;box-shadow:0 18px 55px rgba(0,0,0,.55);display:flex;flex-direction:column}.ma-view-content{min-height:0;max-height:90vh;max-height:90dvh;overflow-y:auto;overscroll-behavior:contain;padding:12px;scrollbar-gutter:stable}.ma-view-content .ma-nav{position:sticky;top:-12px;margin:-12px -12px 10px;padding:10px 12px;background:#07152d;z-index:30}.ma-view-overlay .ma-drawing-overlay{z-index:100000}@media(max-width:560px){.ma-view-overlay{padding:6px;align-items:center}.ma-view-dialog{width:100%;max-height:92vh;max-height:92dvh;border-radius:11px}.ma-view-content{max-height:92vh;max-height:92dvh;padding:10px}.ma-view-content .ma-nav{top:-10px;margin:-10px -10px 10px;padding:9px 10px}}";document.head.appendChild(popupCss);
function esc(v){return String(v==null?"":v).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function n(v){return v!==null&&v!==""&&Number.isFinite(Number(v))?Number(v):null;}
function money(v){var x=n(v);return x===null?"डेटा उपलब्ध नहीं":(x>0?"+":x<0?"−":"")+"₹"+Math.abs(x).toLocaleString("en-IN",{maximumFractionDigits:1})+" Cr";}
function latestFpi(){var h=fpi&&Array.isArray(fpi.history)?fpi.history:[];return h[0]||null;}
function fpiMap(){var o={},x=latestFpi();(x&&Array.isArray(x.sectors)?x.sectors:[]).forEach(function(s){if(s&&s.name)o[s.name]=n(s.net_equity_cr);});return o;}
function quote(s){var q=marketData&&marketData.instruments?marketData.instruments[s]:null;if(q&&q.type==="stock")return q;var bulk=marketData&&marketData.market_activity_quotes&&marketData.market_activity_quotes.instruments?marketData.market_activity_quotes.instruments[s]:null;return bulk&&bulk.type==="stock"?bulk:null;}
function stockRows(sector){return Object.keys(master.stocks||{}).filter(function(s){return (master.stocks[s].sector||"सेक्टर उपलब्ध नहीं")===sector;}).sort().map(function(s){return {symbol:s,info:master.stocks[s],q:quote(s)};});}
function stats(rows){var d={up:0,down:0,flat:0,newsUp:0,newsDown:0,newsN:0};rows.forEach(function(r){var c=r.q&&n(r.q.change_pct);if(c!==null){if(c>0)d.up++;else if(c<0)d.down++;else d.flat++;}if(r.q&&(n(r.q.pos_n)!==null||n(r.q.neg_n)!==null)){d.newsN++;d.newsUp+=Number(r.q.pos_n||0);d.newsDown+=Number(r.q.neg_n||0);}});d.covered=d.up+d.down+d.flat;return d;}
function fpiDeltaMap(){var h=fpi&&Array.isArray(fpi.history)?fpi.history:[],out={};if(h.length<2)return out;var now={},prev={};(h[0].sectors||[]).forEach(function(s){if(s&&s.name)now[s.name]=n(s.net_equity_cr);});(h[1].sectors||[]).forEach(function(s){if(s&&s.name)prev[s.name]=n(s.net_equity_cr);});Object.keys(now).forEach(function(name){if(now[name]!==null&&prev[name]!==undefined&&prev[name]!==null)out[name]=now[name]-prev[name];});return out;}
function sectorOrder(s){var d=s.d;if(!d.covered)return 1;return d.up>d.down?0:d.down>d.up?2:1;}
function stockOrder(r){var c=r.q&&n(r.q.change_pct);return c===null||c===0?1:c>0?0:2;}
function compareStocks(a,b){var ga=stockOrder(a),gb=stockOrder(b);if(ga!==gb)return ga-gb;var ca=a.q&&n(a.q.change_pct),cb=b.q&&n(b.q.change_pct),va=a.q&&n(a.q.volume),vb=b.q&&n(b.q.volume);if(ga===2&&ca!==null&&cb!==null&&ca!==cb)return ca-cb;if(ga===0&&ca!==null&&cb!==null&&ca!==cb)return cb-ca;if(va!==null&&vb!==null&&va!==vb)return vb-va;if(ca!==null&&cb!==null&&Math.abs(ca)!==Math.abs(cb))return Math.abs(cb)-Math.abs(ca);return a.symbol.localeCompare(b.symbol);}
function compareSectors(a,b){var ga=sectorOrder(a),gb=sectorOrder(b);if(ga!==gb)return ga-gb;var da=a.d.up-a.d.down,db=b.d.up-b.d.down;if(ga===0)return db-da;if(ga===2)return da-db;return a.name.localeCompare(b.name);}
function allSectors(){var names={};Object.keys(master.stocks||{}).forEach(function(s){names[master.stocks[s].sector||"सेक्टर उपलब्ध नहीं"]=true;});return Object.keys(names).map(function(name){var rows=stockRows(name),d=stats(rows),fm=fpiMap();return {name:name,rows:rows,d:d,flow:fm[name]==null?null:fm[name]};}).sort(compareSectors);}
function fpiPeriod(){var x=latestFpi();return x?(x.label||((x.from_date||"")+" – "+(x.to_date||""))):"डेटा उपलब्ध नहीं";}
function sectorNews(d){return d.newsN?(d.newsUp>d.newsDown?"खबरों में तेजी":d.newsDown>d.newsUp?"खबरों में मंदी":"खबरें मिश्रित"):"खबर पुष्टि उपलब्ध नहीं";}
function sectorState(d){return !d.covered?"भाव डेटा अपर्याप्त":d.up>d.down?"उपलब्ध भावों में तेजी":d.down>d.up?"उपलब्ध भावों में मंदी":"मिश्रित हलचल";}
function freshNewsSignals(q){var p=0,b=0,hs=q&&Array.isArray(q.headlines)?q.headlines:[];hs.forEach(function(h){var age=n(h&&h.age_h),score=n(h&&h.score);if(age!==null&&age<=24&&score!==null){if(score>0)p++;else if(score<0)b++;}});return {positive:p,negative:b,total:p+b,bias:p>b?"bull":b>p?"bear":"mixed"};}
function crowdSummary(){var r=marketData&&marketData.retail_mood;if(!r)return "बाजार-स्तरीय crowd mood उपलब्ध नहीं";return "बाजार-स्तरीय "+String(r.bias||"मिश्रित")+" · CE "+(r.ce_pct==null?"—":r.ce_pct)+"% / PE "+(r.pe_pct==null?"—":r.pe_pct)+"% · "+String(r.date||"तारीख़ उपलब्ध नहीं")+" (स्टॉक-विशिष्ट नहीं)";}
function activityAlerts(){var out=[],sectors=allSectors(),delta=fpiDeltaMap();sectors.forEach(function(s){s.rows.forEach(function(r){var q=r.q,change=q&&n(q.change_pct);if(change===null)return;var news=freshNewsSignals(q),priceSignal=Math.abs(change)>=2,newsSignal=news.total>=2&&Math.abs(news.positive-news.negative)>=2,aligned=(change>0&&news.bias==="bull")||(change<0&&news.bias==="bear");if(priceSignal&&newsSignal&&aligned){out.push({kind:"high",symbol:r.symbol,sector:s.name,rank:0,activity:Math.abs(change),date:q.price_as_of||"भाव तारीख़ उपलब्ध नहीं",text:"कीमत "+(change>0?"तेजी ":"मंदी ")+Math.abs(change).toFixed(2)+"% और पिछले 24 घंटे की खबरें "+(news.bias==="bull"?"बुलिश":"बेयरिश")+" — दोनों संकेत एक दिशा में"});}else if(Math.abs(change)>=1.5||newsSignal){out.push({kind:"watch",symbol:r.symbol,sector:s.name,rank:1,activity:Math.max(Math.abs(change),Math.abs(news.positive-news.negative)),date:q.price_as_of||"भाव तारीख़ उपलब्ध नहीं",text:Math.abs(change)>=1.5?"कीमत में "+(change>0?"तेजी ":"गिरावट ")+Math.abs(change).toFixed(2)+"% — दूसरी पुष्टि बाकी":"पिछले 24 घंटे की खबरों में "+(news.bias==="bull"?"बुलिश":"बेयरिश")+" झुकाव — कीमत/अन्य पुष्टि बाकी"});}});if(delta[s.name]!==undefined&&delta[s.name]!==0){out.push({kind:"flow",sector:s.name,rank:2,activity:Math.abs(delta[s.name]),date:fpiPeriod(),text:"FPI सेक्टर नेट Equity में पिछली अवधि से "+money(delta[s.name])+" बदलाव"});}});return out.sort(function(a,b){return a.rank-b.rank||b.activity-a.activity;}).slice(0,8);}

function ensurePopup(){if(popupLayer)return;bodyOverflowBefore=document.body.style.overflow;document.body.style.overflow="hidden";popupLayer=document.createElement("div");popupLayer.className="ma-view-overlay";popupLayer.setAttribute("data-view-overlay","");popupLayer.innerHTML='<div class="ma-view-dialog" role="dialog" aria-modal="true" aria-label="Market Activity विवरण"><div class="ma-view-content" data-view-content></div></div>';root.appendChild(popupLayer);popupBody=popupLayer.querySelector("[data-view-content]");popupLayer.addEventListener("click",function(e){if(e.target===popupLayer){goBack();}});}
function closePopup(){if(popupLayer&&popupLayer.parentNode)popupLayer.parentNode.removeChild(popupLayer);popupLayer=null;popupBody=null;document.body.style.overflow=bodyOverflowBefore;}
function closeView(){stack=[{type:"home",scroll:0}];closePopup();render();}
function nav(title){var action=stack.length>1?'<button class="ma-back" type="button" data-back>← वापस</button>':'<button class="ma-back" type="button" data-close-view>✕ बंद करें</button>';return '<div class="ma-nav">'+action+'<div class="ma-nav-title">'+esc(title)+'</div></div>';}
function push(view){if(popupBody)stack[stack.length-1].scroll=popupBody.scrollTop||0;stack.push(view);history.pushState({ma:true,depth:stack.length},"","#market-activity");render();}
function goBack(){if(popupLayer&&history.state&&history.state.ma)history.back();else closeView();}
window.addEventListener("popstate",function(){if(stack.length>1){stack.pop();render();if(popupBody)popupBody.scrollTop=stack[stack.length-1].scroll||0;}else if(popupLayer){closePopup();viewRoot=root;}});
window.addEventListener("keydown",function(e){if(e.key==="Escape"&&popupLayer){goBack();}});
root.addEventListener("click",function(e){var close=e.target.closest("[data-close-view]");if(close){goBack();return;}var back=e.target.closest("[data-back]");if(back){goBack();return;}var radar=e.target.closest("[data-radar]");if(radar){push({type:"radar",kind:radar.getAttribute("data-radar"),scroll:0});return;}var sec=e.target.closest("[data-sector]");if(sec){push({type:"sector",name:sec.getAttribute("data-sector"),scroll:0});return;}var stk=e.target.closest("[data-stock]");if(stk){push({type:"stock",symbol:stk.getAttribute("data-stock"),sector:stk.getAttribute("data-sector-name")||"",scroll:0});return;}});
function renderHome(){
var sectors=allSectors(),symbols=Object.keys(master.stocks||{}),bull=sectors.filter(function(s){return sectorOrder(s)===0;}).length,bear=sectors.filter(function(s){return sectorOrder(s)===2;}).length;
var unusual=[];sectors.forEach(function(s){s.rows.forEach(function(r){var c=r.q&&n(r.q.change_pct);if(c!==null&&Math.abs(c)>=1)unusual.push({sector:s.name,row:r,change:c,date:r.q.price_as_of||"तारीख़ उपलब्ध नहीं"});});});
unusual.sort(function(a,b){return Math.abs(b.change)-Math.abs(a.change)||a.row.symbol.localeCompare(b.row.symbol);});
var fpiDelta=fpiDeltaMap(),fpiChanged=Object.keys(fpiDelta).filter(function(k){return fpiDelta[k]!==0;}).length;
var alerts=activityAlerts(),alertHtml=alerts.length?alerts.map(function(a){var tag=a.kind==="high"?"HIGH":a.kind==="watch"?"WATCH":"FLOW";var target=a.symbol?' data-stock="'+esc(a.symbol)+'" data-sector-name="'+esc(a.sector)+'"':' data-sector="'+esc(a.sector)+'"';return '<button type="button" class="ma-alert '+a.kind+'"'+target+'><span class="ma-alert-label">'+tag+'</span><b>'+esc(a.symbol||a.sector)+'</b> · '+esc(a.text)+'<small>'+esc(a.sector)+' · '+esc(a.date||"अवधि उपलब्ध नहीं")+(a.symbol?" · स्टॉक विवरण खोलें":" · सेक्टर विवरण खोलें")+'</small></button>';}).join(""):'<div class="ma-empty">अभी HIGH / WATCH / FLOW के लिए पर्याप्त सत्यापित बदलाव नहीं मिला।</div>';
var sectorHtml=sectors.map(function(s){var d=s.d,state=sectorState(d);return '<div class="ma-sector '+(sectorOrder(s)===0?"bull":sectorOrder(s)===2?"bear":"neutral")+'"><button class="ma-sector-button" type="button" data-sector="'+esc(s.name)+'"><div class="ma-sector-head"><span class="ma-sector-name">'+esc(s.name)+'</span><span class="ma-count">'+s.rows.length+' स्टॉक　›</span></div><span class="ma-state '+(sectorOrder(s)===0?"bull":sectorOrder(s)===2?"bear":"")+'">'+(sectorOrder(s)===0?"तेजी की हलचल":sectorOrder(s)===2?"मंदी की हलचल":state)+'</span><div class="ma-meta"><span>भाव उपलब्ध '+d.covered+'/'+s.rows.length+'</span><span class="ma-up">↑ '+d.up+'</span><span class="ma-neutral">सामान्य '+d.flat+'</span><span class="ma-down">↓ '+d.down+'</span></div></button></div>';}).join("");
root.innerHTML='<div class="ma-kicker">सबसे ऊपर — आज की हलचल</div><div class="ma-kicker">MARKET ACTIVITY RADAR</div><div class="ma-intro">आज बाजार में कहाँ हलचल है? · '+symbols.length+' स्टॉक · '+sectors.length+' सेक्टर · उपलब्ध सत्यापित डेटा के आधार पर</div>'+
'<div class="ma-summary">'+
'<div class="ma-stat bull"><button class="ma-stat-button" type="button" data-radar="bull"><b>'+String(bull).padStart(2,"0")+'</b><span>तेजी वाले सेक्टर<br>हलचल ऊपर की ओर</span></button></div>'+
'<div class="ma-stat bear"><button class="ma-stat-button" type="button" data-radar="bear"><b>'+String(bear).padStart(2,"0")+'</b><span>मंदी वाले सेक्टर<br>दबाव नीचे की ओर</span></button></div>'+
'<div class="ma-stat unusual"><button class="ma-stat-button" type="button" data-radar="unusual"><b>'+String(unusual.length).padStart(2,"0")+'</b><span>असामान्य स्टॉक<br>कीमत में ±1% या अधिक हलचल</span></button></div>'+
'<div class="ma-stat fpi"><button class="ma-stat-button" type="button" data-radar="fpi"><b>'+String(fpiChanged).padStart(2,"0")+'</b><span>FPI प्रवाह बदलाव<br>पिछली अवधि से तुलना</span></button></div>'+
'</div>'+
'<div class="ma-kicker">LATEST ACTIVITY ALERTS</div><div class="ma-intro">HIGH: कम-से-कम दो स्वतंत्र संकेत एक दिशा में। WATCH: एक महत्वपूर्ण संकेत, पुष्टि बाकी। FLOW: सत्यापित FPI बदलाव।</div>'+alertHtml+'<div class="ma-kicker">SECTOR ACTIVITY — '+sectors.length+' सेक्टर</div>'+'<div class="ma-intro">हलचल वाले सेक्टर ऊपर, सामान्य बीच में और मंदी वाले नीचे। सेक्टर खोलकर उसके स्टॉक देखें।</div><div class="ma-sector-grid">'+sectorHtml+'</div>'+
'<div class="ma-foot">भाव डेटा उपलब्ध '+Object.keys(marketData&&marketData.instruments||{}).filter(function(k){var q=quote(k);return q&&n(q.change_pct)!==null;}).length+' स्टॉक तक सीमित हो सकता है। बाकी स्टॉक सेक्टर सूची में रहेंगे, लेकिन बिना सत्यापित भाव के उन्हें तेजी/मंदी नहीं दिया जाएगा। असामान्य स्टॉक की गिनती कीमत बदलाव पर आधारित है; वॉल्यूम डेटा उपलब्ध नहीं है। FPI बदलाव नवीनतम दो उपलब्ध NSDL fortnightly अवधियों की तुलना है। Quote अपडेट: '+esc(marketData&&marketData.updated||"समय उपलब्ध नहीं")+' · FPI अवधि: '+esc(fpiPeriod())+'</div>';
}
function renderRadarList(kind){
var sectors=allSectors(),delta=fpiDeltaMap(),title="",body="";
if(kind==="bull"||kind==="bear"){
var chosen=sectors.filter(function(s){return sectorOrder(s)===(kind==="bull"?0:2);});
title=kind==="bull"?"तेजी वाले सेक्टर":"मंदी वाले सेक्टर";
body=chosen.length?chosen.map(function(s){return '<div class="ma-sector"><button class="ma-sector-button" type="button" data-sector="'+esc(s.name)+'"><div class="ma-sector-head"><span class="ma-sector-name">'+esc(s.name)+'</span><span class="ma-count">'+s.rows.length+' स्टॉक　›</span></div><span class="ma-state '+(kind==="bull"?"bull":"bear")+'">'+(kind==="bull"?"तेजी की हलचल":"मंदी की हलचल")+'</span><div class="ma-meta"><span>भाव उपलब्ध '+s.d.covered+'/'+s.rows.length+'</span><span class="ma-up">↑ '+s.d.up+'</span><span class="ma-down">↓ '+s.d.down+'</span></div></button></div>';}).join(""):'<div class="ma-empty">इस समय उपलब्ध सत्यापित भावों से कोई सेक्टर इस श्रेणी में नहीं है।</div>';
body='<div class="ma-sector-grid">'+body+'</div>';
}else if(kind==="unusual"){
title="असामान्य स्टॉक";
var list=[];sectors.forEach(function(s){s.rows.forEach(function(r){var c=r.q&&n(r.q.change_pct);if(c!==null&&Math.abs(c)>=1)list.push({sector:s.name,row:r,change:c});});});
list.sort(function(a,b){return Math.abs(b.change)-Math.abs(a.change)||a.row.symbol.localeCompare(b.row.symbol);});
body=list.length?list.map(function(x){return '<div class="ma-panel"><button class="ma-stock-button" type="button" data-stock="'+esc(x.row.symbol)+'" data-sector-name="'+esc(x.sector)+'"><div class="ma-stock-head"><span class="ma-symbol">'+esc(x.row.symbol)+'</span><span class="'+(x.change>0?"ma-up":"ma-down")+'">'+(x.change>0?"+":"")+x.change.toFixed(2)+'%　›</span></div><div class="ma-stock-meta">'+esc(x.sector)+' · EOD भाव तारीख़ '+esc(x.row.q.price_as_of||"उपलब्ध नहीं")+' · वॉल्यूम डेटा उपलब्ध नहीं</div></button></div>';}).join(""):'<div class="ma-empty">±1% या अधिक का कोई सत्यापित भाव बदलाव उपलब्ध नहीं।</div>';
}else{
title="FPI प्रवाह बदलाव";
var h=fpi&&Array.isArray(fpi.history)?fpi.history:[],previous=h[1]||null,latest=h[0]||null;
var rows=sectors.filter(function(s){return delta[s.name]!==undefined;}).map(function(s){return {name:s.name,delta:delta[s.name],flow:s.flow};}).sort(function(a,b){return b.flow-a.flow;});
body=latest&&previous?'<div class="ma-intro">तुलना: '+esc(latest.label||fpiPeriod())+' बनाम '+esc(previous.label||"पिछली अवधि")+'। रकम ₹ करोड़ में। किसी सेक्टर का FPI आँकड़ा उस सेक्टर के सभी स्टॉक्स का नेट निवेश है; इसे किसी एक स्टॉक की खरीदारी न समझें।</div>'+rows.map(function(x){return '<button type="button" class="ma-flow ma-flow-button" data-sector="'+esc(x.name)+'"><b>'+esc(x.name)+' · '+money(x.flow)+'　›</b><small>पिछली अवधि से बदलाव: '+money(x.delta)+' · '+(x.delta>0?"प्रवाह में सुधार":x.delta<0?"प्रवाह में गिरावट":"कोई बदलाव नहीं")+'<br>'+stockRows(x.name).length+' सेक्टर स्टॉक देखें · वर्तमान अवधि का नेट Equity प्रवाह; intraday FPI नहीं।</small></button>';}).join(""):'<div class="ma-empty">तुलना के लिए दो सत्यापित FPI अवधियाँ उपलब्ध नहीं हैं।</div>';
}
viewRoot.innerHTML=nav(title)+'<div class="ma-kicker">'+esc(title)+'</div>'+body;
}
function renderSector(name){
var s=allSectors().filter(function(x){return x.name===name;})[0];if(!s){viewRoot.innerHTML=nav("सेक्टर नहीं मिला")+'<div class="ma-empty">इस सेक्टर का डेटा उपलब्ध नहीं।</div>';return;}
var d=s.d,ordered=s.rows.slice().sort(compareStocks),rows=ordered.map(function(r){var c=r.q&&n(r.q.change_pct),group=stockOrder(r),label=c===null?"भाव उपलब्ध नहीं":c>0?"तेजी +"+c.toFixed(2)+"%":c<0?"मंदी "+c.toFixed(2)+"%":"सामान्य 0.00%";return '<div class="ma-stock-row '+(group===0?"bull":group===2?"bear":"neutral")+'"><button type="button" class="ma-stock-button" data-stock="'+esc(r.symbol)+'" data-sector-name="'+esc(name)+'"><div class="ma-stock-head"><span class="ma-symbol">'+esc(r.symbol)+'</span><span class="ma-tag '+(group===0?"ma-up":group===2?"ma-down":"")+'">'+esc(label)+'　›</span></div><div class="ma-stock-meta">'+esc(r.info.industry||"इंडस्ट्री उपलब्ध नहीं")+' · '+(r.q?"भाव "+esc(r.q.price_as_of||"तारीख़ उपलब्ध नहीं"):"भाव डेटा उपलब्ध नहीं")+'</div></button></div>';}).join("");
viewRoot.innerHTML=nav(name)+'<div class="ma-kicker">SECTOR ACTIVITY</div><div class="ma-intro">इस सेक्टर के स्टॉक: तेजी ऊपर, सामान्य/भाव अनुपलब्ध बीच में और मंदी नीचे।</div><div class="ma-summary"><div class="ma-stat"><div class="ma-stat-button"><b>'+d.up+'</b><span>तेजी वाले स्टॉक</span></div></div><div class="ma-stat"><div class="ma-stat-button"><b>'+d.flat+'</b><span>सामान्य स्टॉक</span></div></div><div class="ma-stat"><div class="ma-stat-button"><b>'+d.down+'</b><span>मंदी वाले स्टॉक</span></div></div><div class="ma-stat"><div class="ma-stat-button"><b>'+(s.rows.length-d.covered)+'</b><span>भाव उपलब्ध नहीं</span></div></div></div><div class="ma-panel"><h4>सेक्टर की स्थिति</h4><div class="ma-reason">'+esc(sectorState(d))+' · '+esc(sectorNews(d))+'<br>FPI प्रवाह: '+money(s.flow)+'<br>अवधि: '+esc(fpiPeriod())+'<br>खबरों का रुख: '+esc(sectorNews(d))+'<br>भीड़ का रुख: '+esc(crowdSummary())+'<br>FPI + खबर पुष्टि: '+(s.flow===null||!d.newsN?"मिलान संभव नहीं":((s.flow>0&&d.newsUp>d.newsDown)||(s.flow<0&&d.newsDown>d.newsUp))?"दिशा समान":"दिशा अलग/मिश्रित")+'<br><b>ध्यान दें:</b> FPI डेटा पूरे सेक्टर का fortnightly Equity है; खबरें उपलब्ध स्टॉक-स्तरीय खबरों का सेक्टर योग हैं। भीड़ बाजार-स्तरीय संदर्भ है, स्टॉक-विशिष्ट नहीं।</div></div><div class="ma-kicker">STOCK WIND — '+esc(name)+'</div>'+rows;
}

var DRAWING_API="https://trinetra-drawing-api.suncity247.workers.dev";
function drawingApiKey(symbol){return String(symbol).replace(/&/g,"_AMP_");}
function drawingSymbolFromApiKey(key){return String(key).replace(/_AMP_/g,"&");}
function drawingToken(){
  var token=sessionStorage.getItem("trinetraDrawingToken")||"";
  var expiry=Number(sessionStorage.getItem("trinetraDrawingTokenExp")||0);
  if(!token||expiry<=Date.now()){
    sessionStorage.removeItem("trinetraDrawingToken");
    sessionStorage.removeItem("trinetraDrawingTokenExp");
    return "";
  }
  return token;
}
function drawingModalHtml(symbol){
  var record=drawings&&drawings.records&&drawings.records[symbol]||{};
  return '<div class="ma-drawing-overlay" data-drawing-modal style="display:none"><div class="ma-drawing-dialog" role="dialog" aria-modal="true" aria-label="Drawing Admin">'+
    '<div class="ma-drawing-dialog-head"><span>DRAWING ADMIN · '+esc(symbol)+'</span><button type="button" class="ma-drawing-close" data-drawing-close>✕ बंद करें</button></div>'+
    '<div class="ma-drawing-error" data-drawing-error aria-live="polite"></div>'+
    '<form data-drawing-login>'+
      '<label class="ma-drawing-field">Admin Password</label><input class="ma-drawing-input" name="password" type="password" autocomplete="current-password" required maxlength="256" placeholder="अपना निजी Admin Password डालें">'+
      '<div class="ma-drawing-help">यह पासवर्ड केवल सुरक्षित Login अनुरोध में भेजा जाएगा। इसे Dashboard में सेव नहीं किया जाएगा।</div>'+
      '<div class="ma-drawing-actions"><button class="ma-drawing-action primary" type="submit">Login करें</button></div>'+
    '</form>'+
    '<form data-drawing-editor hidden>'+
      '<label class="ma-drawing-field">TradingView Snapshot URL *</label><input class="ma-drawing-input" name="snapshotUrl" type="url" required placeholder="https://www.tradingview.com/x/XXXXXXXX/">'+
      '<label class="ma-drawing-field">TradingView Chart URL (वैकल्पिक)</label><input class="ma-drawing-input" name="chartUrl" type="url" placeholder="https://www.tradingview.com/chart/CHART_ID/">'+
      '<div class="ma-drawing-help">Snapshot URL सभी दर्शकों के Preview के लिए जरूरी है। Chart URL खाली छोड़ने पर स्टॉक का सामान्य TradingView Chart खुलेगा। Login लगभग 1 घंटे तक मान्य रहेगा।</div>'+
      '<div class="ma-drawing-actions"><button class="ma-drawing-action primary" type="submit">Save Drawing</button><button class="ma-drawing-action danger" type="button" data-drawing-delete>Drawing हटाएँ</button></div>'+
    '</form>'+
    '<div class="ma-drawing-bottom"><button type="button" class="ma-drawing-close" data-drawing-close>✕ बंद करें</button></div>'+
  '</div></div>';
}
function openDrawingAdmin(symbol){
  var modal=root.querySelector("[data-drawing-modal]");
  if(!modal)return;
  modal.style.display="flex";
  var login=modal.querySelector("[data-drawing-login]");
  var editor=modal.querySelector("[data-drawing-editor]");
  var error=modal.querySelector("[data-drawing-error]");
  error.textContent="";
  if(drawingToken()){
    login.hidden=true;editor.hidden=false;
    editor.elements.snapshotUrl.value=(drawings.snapshots||{})[symbol]||"";
    editor.elements.chartUrl.value=((drawings.records||{})[symbol]||{}).chartUrl||"";
  }else{
    login.hidden=false;editor.hidden=true;
    login.elements.password.value="";
    login.elements.password.focus();
  }
}
function closeDrawingAdmin(){
  var modal=root.querySelector("[data-drawing-modal]");
  if(modal)modal.style.display="none";
}
root.addEventListener("click",function(e){
  var open=e.target.closest("[data-drawing-admin]");
  if(open){openDrawingAdmin(open.getAttribute("data-drawing-admin"));return;}
  if(e.target.closest("[data-drawing-close]")){closeDrawingAdmin();return;}
  var del=e.target.closest("[data-drawing-delete]");
  if(del){
    var modal=del.closest("[data-drawing-modal]");
    var symbol=(modal.querySelector(".ma-drawing-dialog-head span").textContent.split("·").pop()||"").trim();
    var token=drawingToken();
    if(!token){modal.querySelector("[data-drawing-error]").textContent="Login की अवधि समाप्त हो गई। दोबारा Login करें।";modal.querySelector("[data-drawing-login]").hidden=false;modal.querySelector("[data-drawing-editor]").hidden=true;return;}
    if(!confirm(symbol+" का Drawing Preview हटाएँ?"))return;
    fetch(DRAWING_API+"/api/drawings/"+encodeURIComponent(drawingApiKey(symbol)),{method:"DELETE",headers:{Authorization:"Bearer "+token}})
      .then(function(r){return r.json().then(function(d){if(!r.ok)throw Error(d.error||"Delete असफल");return d;});})
      .then(function(){delete drawings.snapshots[symbol];delete drawings.records[symbol];closeDrawingAdmin();render();})
      .catch(function(err){modal.querySelector("[data-drawing-error]").textContent=err.message||"Delete असफल";});
  }
});
root.addEventListener("submit",function(e){
  var login=e.target.closest("[data-drawing-login]");
  if(login){
    e.preventDefault();
    var modal=login.closest("[data-drawing-modal]");
    var error=modal.querySelector("[data-drawing-error]");
    var password=login.elements.password.value;
    error.textContent="Login जाँचा जा रहा है…";
    fetch(DRAWING_API+"/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:password})})
      .then(function(r){return r.json().then(function(d){if(!r.ok)throw Error(d.error||"Login असफल");return d;});})
      .then(function(d){
        sessionStorage.setItem("trinetraDrawingToken",d.token);
        sessionStorage.setItem("trinetraDrawingTokenExp",String(Date.now()+Number(d.expiresIn||3600)*1000));
        login.hidden=true;
        var editor=modal.querySelector("[data-drawing-editor]");
        editor.hidden=false;
        var symbol=(modal.querySelector(".ma-drawing-dialog-head span").textContent.split("·").pop()||"").trim();
        editor.elements.snapshotUrl.value=(drawings.snapshots||{})[symbol]||"";
        editor.elements.chartUrl.value=((drawings.records||{})[symbol]||{}).chartUrl||"";
        error.textContent="Login सफल।";
        login.elements.password.value="";
      })
      .catch(function(err){error.textContent=err.message||"Login असफल";});
    return;
  }
  var editor=e.target.closest("[data-drawing-editor]");
  if(editor){
    e.preventDefault();
    var modal=editor.closest("[data-drawing-modal]");
    var error=modal.querySelector("[data-drawing-error]");
    var symbol=(modal.querySelector(".ma-drawing-dialog-head span").textContent.split("·").pop()||"").trim();
    var token=drawingToken();
    if(!token){error.textContent="Login की अवधि समाप्त हो गई। दोबारा Login करें।";editor.hidden=true;modal.querySelector("[data-drawing-login]").hidden=false;return;}
    var snapshotUrl=editor.elements.snapshotUrl.value.trim();
    var chartUrl=editor.elements.chartUrl.value.trim();
    error.textContent="Drawing सेव हो रही है…";
    fetch(DRAWING_API+"/api/drawings/"+encodeURIComponent(drawingApiKey(symbol)),{method:"PUT",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({snapshotUrl:snapshotUrl,chartUrl:chartUrl})})
      .then(function(r){return r.json().then(function(d){if(!r.ok)throw Error(d.error||"Save असफल");return d;});})
      .then(function(d){
        drawings.records=drawings.records||{};
        drawings.snapshots=drawings.snapshots||{};
        drawings.records[symbol]=d.drawing;
        drawings.snapshots[symbol]=d.drawing.snapshotUrl;
        closeDrawingAdmin();
        render();
      })
      .catch(function(err){error.textContent=err.message||"Save असफल";});
  }
});

function renderStock(symbol,sector){
var info=master.stocks[symbol]||{},company=companyResearch&&companyResearch.stocks?companyResearch.stocks[symbol]||{}:{},q=quote(symbol),c=q?n(q.change_pct):n(company.change_pct),price=q?n(q.price):n(company.price);
var rawSnapshot=drawings&&drawings.snapshots?drawings.snapshots[symbol]:"";
var snapshotMatch=typeof rawSnapshot==="string"?rawSnapshot.match(/^https:\/\/www\.tradingview\.com\/x\/([A-Za-z0-9]+)\/?$/):null;
var snapshotId=snapshotMatch?snapshotMatch[1]:null;
var snapshotImage=snapshotId?"https://s3.tradingview.com/snapshots/"+snapshotId.charAt(0).toLowerCase()+"/"+snapshotId+".png":"";
var savedChartUrl=drawings&&drawings.records&&drawings.records[symbol]?drawings.records[symbol].chartUrl:"";
var fullChartUrl=savedChartUrl||"https://www.tradingview.com/chart/?symbol=NSE%3A"+encodeURIComponent(symbol);
var chartPreviewHtml=snapshotId?'<div class="ma-chart-preview"><div class="ma-stock-head"><b>आपकी DRAWING PREVIEW</b><span class="ma-tag">TradingView Snapshot</span></div><a href="'+esc(snapshotMatch[0])+'" target="_blank" rel="noopener"><img src="'+esc(snapshotImage)+'" alt="'+esc(symbol)+' TradingView Drawing Preview" loading="lazy"></a><div class="ma-chart-actions"><a class="ma-chart-link" href="'+esc(snapshotMatch[0])+'" target="_blank" rel="noopener">Drawing अलग से खोलें ↗</a><a class="ma-chart-link" href="'+esc(fullChartUrl)+'" target="_blank" rel="noopener">अपना TradingView Chart खोलें ↗</a></div></div>':'<div class="ma-chart-preview"><b>DRAWING PREVIEW</b><div class="ma-chart-missing">इस स्टॉक का अलग Snapshot लिंक अभी जोड़ा नहीं गया है।</div><div class="ma-chart-actions"><a class="ma-chart-link" href="'+esc(fullChartUrl)+'" target="_blank" rel="noopener">अपना TradingView Chart खोलें ↗</a></div></div>';
var drawingAdminHtml='<div class="ma-panel"><h4>DRAWING LINK MANAGEMENT</h4><button type="button" class="ma-admin-open" data-drawing-admin="'+esc(symbol)+'">Drawing लिंक जोड़ें / बदलें</button><div class="ma-drawing-help">Admin Login आवश्यक · Preview सभी दर्शकों को दिखेगा</div></div>'+drawingModalHtml(symbol);
function unavailable(v){return v===null||v===undefined||v===""?"डेटा उपलब्ध नहीं":esc(v);}
function ratio(label,value){return '<div class="ma-stock-row"><div class="ma-stock-button"><div class="ma-stock-head"><span>'+esc(label)+'</span><b>'+unavailable(value)+'</b></div></div></div>';}
var priceLabel=price===null?"कीमत उपलब्ध नहीं":"₹"+price.toLocaleString("en-IN",{maximumFractionDigits:2});
var changeLabel=c===null?"बदलाव उपलब्ध नहीं":(c>0?"+":"")+c.toFixed(2)+"%";
var changeClass=c===null?"ma-neutral":c>0?"ma-up":c<0?"ma-down":"ma-neutral";
var quoteMeta="स्रोत: "+(q&&q.price_source||company.quote_source||"स्रोत उपलब्ध नहीं")+" · भाव समय: "+(q&&q.price_as_of||company.quote_timestamp||company.checked_at||"उपलब्ध नहीं");
var sectorName=sector||info.sector||company.nse_sector||"सेक्टर उपलब्ध नहीं";
var industry=company.industry||info.industry||"इंडस्ट्री उपलब्ध नहीं";
var companyName=company.company_name||"कंपनी नाम उपलब्ध नहीं";
var sh=company.shareholding||{},financials=company.financials||{},latestFinancial=financials.latest||{},financialQuarters=Array.isArray(financials.quarters)?financials.quarters:[],integrated=company.integrated_financials||{},integratedParsed=integrated.parsed||{},integratedQuarter=integratedParsed.quarter||{},integratedBS=integratedParsed.balance_sheet||{},integratedFiling=integrated.filing||{};
function parseNsePeriod(value){var m=String(value||"").trim().match(/^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/);if(m){var months={jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11};var month=months[m[2].toLowerCase()];if(month!==undefined)return new Date(Date.UTC(Number(m[3]),month,Number(m[1])));}var iso=String(value||"").match(/^(\d{4})-(\d{2})-(\d{2})$/);return iso?new Date(Date.UTC(Number(iso[1]),Number(iso[2])-1,Number(iso[3]))):null;}
var comparisonPeriodDate=parseNsePeriod(latestFinancial.period_end),comparisonPeriodAgeDays=comparisonPeriodDate?Math.floor((Date.now()-comparisonPeriodDate.getTime())/86400000):null,comparisonPeriodFresh=comparisonPeriodAgeDays!==null&&comparisonPeriodAgeDays>=0&&comparisonPeriodAgeDays<=548;
function comparisonValue(value){if(value===null||value===undefined)return "डेटा उपलब्ध नहीं";return comparisonPeriodFresh?value:"पुराना रिकॉर्ड · "+(latestFinancial.period_end||"तारीख़ उपलब्ध नहीं");}
function pct(v,delta){if(v===null||v===undefined)return "डेटा उपलब्ध नहीं";return Number(v).toFixed(2)+"%"+(delta!==null&&delta!==undefined?" · पिछली तिमाही से "+(delta>0?"+":"")+Number(delta).toFixed(2)+" pp":"");}
var marketCap=company.market_cap_cr===null||company.market_cap_cr===undefined?"डेटा उपलब्ध नहीं":"₹"+Number(company.market_cap_cr).toLocaleString("en-IN",{maximumFractionDigits:2})+" Cr";
function financialGrowth(field){if(!comparisonPeriodFresh)return latestFinancial.period_end?"पुराना रिकॉर्ड · "+latestFinancial.period_end:"डेटा उपलब्ध नहीं";var now=n(financialQuarters[0]&&financialQuarters[0][field]),prior=n(financialQuarters[4]&&financialQuarters[4][field]);if(now===null||prior===null||prior===0)return "डेटा उपलब्ध नहीं";return ((now-prior)/Math.abs(prior)*100).toFixed(2)+"% YoY";}
function croreLabel(value){var x=n(value);return x===null?"डेटा उपलब्ध नहीं":"₹"+x.toLocaleString("en-IN",{maximumFractionDigits:2})+" Cr";}
var valuationGauge='<div class="ma-panel"><h4>Valuation Scorecard</h4><div class="ma-reason">Valuation Score: <b>डेटा उपलब्ध नहीं</b><br>आपके तय स्तर: Attractive &lt; 78 · Expensive 78–104 · Over-Priced &gt; 104</div><div style="display:grid;grid-template-columns:1fr 1fr 1fr;height:10px;border-radius:8px;overflow:hidden;margin:12px 0 5px"><span style="background:#20c997"></span><span style="background:#f0b64d"></span><span style="background:#ed6575"></span></div><div class="ma-meta"><span>Attractive</span><span>Expensive</span><span>Over-Priced</span></div><div class="ma-foot">सूचक/needle नहीं दिखाया गया क्योंकि सत्यापित valuation score और उसकी गणना उपलब्ध नहीं है।</div></div>';
viewRoot.innerHTML=nav(symbol)+
'<div class="ma-panel"><div class="ma-stock-head"><span class="ma-symbol">'+esc(symbol)+'</span><span class="ma-tag">'+esc(industry)+'</span></div><div class="ma-stock-meta">'+esc(sectorName)+' · NSE F&O सूची का सेक्टर/इंडस्ट्री वर्गीकरण</div><div class="ma-stock-head" style="margin-top:12px"><b style="font-size:24px">'+priceLabel+'</b><b class="'+changeClass+'">'+changeLabel+'</b></div><div class="ma-foot">'+esc(quoteMeta)+'</div></div>'+
'<div class="ma-panel"><h4>कंपनी का कारोबार</h4><div class="ma-reason">कंपनी: '+esc(companyName)+'<br>इंडस्ट्री: '+esc(industry)+'<br>व्यवसाय विवरण: NSE के उपलब्ध quote डेटा में विस्तृत business description नहीं मिला।</div><div class="ma-foot">कंपनी/इंडस्ट्री स्रोत: '+esc(company.quote_source||'NSE F&O Master')+' · Cache: '+esc(company.checked_at||'अभी उपलब्ध नहीं')+'</div></div>'+
'<div class="ma-panel"><h4>KNOW YOUR STOCK</h4><div class="ma-intro">कंपनी की गुणवत्ता, मूल्यांकन और वित्तीय रुझान का सारांश। स्कोर केवल सत्यापित वित्तीय डेटा और स्पष्ट गणना मिलने पर दिखेगा।</div><div class="ma-summary"><div class="ma-stat"><div class="ma-stat-button"><b>—</b><span>Good Quality<br>डेटा उपलब्ध नहीं</span></div></div><div class="ma-stat"><div class="ma-stat-button"><b>—</b><span>Valuation<br>डेटा उपलब्ध नहीं</span></div></div><div class="ma-stat"><div class="ma-stat-button"><b>—</b><span>Finance Trends<br>डेटा उपलब्ध नहीं</span></div></div><div class="ma-stat"><div class="ma-stat-button"><b>—</b><span>Overall View<br>अभी तय नहीं</span></div></div></div><div class="ma-reason">Short Term: डेटा उपलब्ध नहीं<br>Long Term: डेटा उपलब्ध नहीं</div></div>'+
'<div class="ma-panel"><h4>Market Snapshot</h4>'+ratio("Market Cap",marketCap)+ratio("1 Year Return","डेटा उपलब्ध नहीं")+ratio("Sector Return","डेटा उपलब्ध नहीं")+ratio("Market Return","डेटा उपलब्ध नहीं")+'</div>'+
'<div class="ma-panel"><h4>Shareholding Pattern · नवीनतम तिमाही</h4><div class="ma-intro">NSE Shareholding Pattern XBRL से उपलब्ध हिस्सेदारी। रिपोर्ट की तारीख़: '+unavailable(sh.as_of)+'</div>'+ratio("Promoters",pct(sh.promoter_pct,sh.promoter_change_pp))+ratio("FII",pct(sh.fii_pct,sh.fii_change_pp))+ratio("DII",pct(sh.dii_pct,sh.dii_change_pp))+ratio("Public / Others",pct(sh.public_pct,sh.public_change_pp))+ratio("Employee Trust",pct(sh.employee_trust_pct,null))+'<div class="ma-foot">स्रोत: '+unavailable(sh.source)+' · XBRL taxonomy: '+unavailable(sh.taxonomy)+'</div></div>'+
'<div class="ma-panel"><h4>Fundamental Ratios</h4>'+ratio("P/E Ratio","डेटा उपलब्ध नहीं")+ratio("P/B Ratio","डेटा उपलब्ध नहीं")+ratio("Latest Reported EPS",integratedQuarter.basic_eps!==null&&integratedQuarter.basic_eps!==undefined?"₹"+Number(integratedQuarter.basic_eps).toFixed(2)+" · Integrated XBRL · "+unavailable(integratedFiling.quarter_end):comparisonPeriodFresh&&latestFinancial.eps!==null&&latestFinancial.eps!==undefined?"₹"+Number(latestFinancial.eps).toFixed(2)+" · NSE Results · "+unavailable(latestFinancial.period_end):comparisonValue(latestFinancial.eps))+ratio("Book Value","डेटा उपलब्ध नहीं")+ratio("ROE","डेटा उपलब्ध नहीं")+ratio("ROCE","डेटा उपलब्ध नहीं")+ratio("Debt / Equity",comparisonPeriodFresh&&latestFinancial.debt_equity!==null&&latestFinancial.debt_equity!==undefined?Number(latestFinancial.debt_equity).toFixed(2)+" · NSE reported · "+unavailable(latestFinancial.period_end):comparisonValue(latestFinancial.debt_equity))+ratio("Total Debt","डेटा उपलब्ध नहीं")+ratio("Profit Growth (YoY)",financialGrowth("net_profit_cr"))+ratio("Sales / Revenue Growth (YoY)",financialGrowth("revenue_cr"))+ratio("Operating Profit Margin","डेटा उपलब्ध नहीं")+ratio("Dividend Yield","डेटा उपलब्ध नहीं")+ratio("NSE XBRL Quarter Revenue",croreLabel(integratedQuarter.revenue_cr))+ratio("NSE XBRL Quarter Net Profit",croreLabel(integratedQuarter.net_profit_cr))+ratio("NSE XBRL Basic EPS",integratedQuarter.basic_eps===null||integratedQuarter.basic_eps===undefined?"डेटा उपलब्ध नहीं":"₹"+Number(integratedQuarter.basic_eps).toFixed(2))+ratio("NSE XBRL Total Assets",croreLabel(integratedBS.total_assets_cr))+ratio("NSE XBRL Total Equity",croreLabel(integratedBS.total_equity_cr))+'<div class="ma-foot">NSE Results Comparison: '+(comparisonPeriodFresh?"ताज़ा अवधि":"पुराना रिकॉर्ड · "+unavailable(latestFinancial.period_end))+' · Revenue: '+(comparisonPeriodFresh?croreLabel(latestFinancial.revenue_cr):"डेटा पुराना") +' · Net profit: '+(comparisonPeriodFresh?croreLabel(latestFinancial.net_profit_cr):"डेटा पुराना")+'<br>Integrated XBRL filing: '+unavailable(integratedFiling.quarter_end)+' · '+unavailable(integratedFiling.consolidated)+' · '+unavailable(integratedFiling.audited)+'<br>XBRL स्रोत: '+unavailable(integratedParsed.source)+' · '+unavailable(integratedFiling.url)+'<br>स्रोत: '+unavailable(financials.source)+' · '+unavailable(financials.note)+'</div></div>'+
'<div class="ma-panel"><h4>Quality Scorecard</h4><div class="ma-reason">Quality Score: डेटा उपलब्ध नहीं<br>Financial Strength: डेटा उपलब्ध नहीं<br>Profitability: डेटा उपलब्ध नहीं<br>Management Risk: डेटा उपलब्ध नहीं<br>Company Growth: डेटा उपलब्ध नहीं</div><div class="ma-foot">Excellent / Good / Below Average रेटिंग देने के लिए सत्यापित financial statements और तय scoring formula अभी उपलब्ध नहीं हैं।</div></div>'+
valuationGauge+
'<div class="ma-panel"><h4>Insights & Sector Position</h4><div class="ma-reason">मुख्य सकारात्मक बातें: डेटा उपलब्ध नहीं<br>मुख्य जोखिम / कमजोरियाँ: डेटा उपलब्ध नहीं<br>सेक्टर में रैंक: डेटा उपलब्ध नहीं</div><div class="ma-foot">Sector rank निकालने के लिए केवल F&O सूची नहीं, पूरे सेक्टर की तुलनीय कंपनियों का verified dataset चाहिए।</div></div>'+
'<div class="ma-panel"><h4>Price & Trading Activity</h4><div class="ma-reason">उपलब्ध कीमत: '+priceLabel+'<br>दैनिक बदलाव: <span class="'+changeClass+'">'+changeLabel+'</span><br>वॉल्यूम: '+(q&&n(q.volume)!==null?Number(q.volume).toLocaleString("en-IN"):"डेटा उपलब्ध नहीं")+'<br>वॉल्यूम तारीख़: '+(q&&q.volume_as_of||"उपलब्ध नहीं")+'<br><br>स्टॉक-स्तरीय वास्तविक buy/sell या FPI order-flow डेटा उपलब्ध नहीं है। इसलिए कीमत/वॉल्यूम को institutional buying या selling नहीं कहा गया।</div></div>'+
chartPreviewHtml+ drawingAdminHtml;
}
function render(){if(!master||!master.stocks){root.innerHTML='<div class="ma-empty">NSE F&amp;O मास्टर लोड नहीं हुआ।</div>';return;}var v=stack[stack.length-1];if(v.type==="home"){closePopup();viewRoot=root;renderHome();return;}ensurePopup();viewRoot=popupBody;if(v.type==="radar")renderRadarList(v.kind);else if(v.type==="sector")renderSector(v.name);else renderStock(v.symbol,v.sector);if(popupBody&&v.scroll===0)popupBody.scrollTop=0;}
function load(){if(loading)return;loading=true;Promise.all([fetch("nse-fo-stock-sector-master.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("master");return r.json();}),fetch("fpi-sector-data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("fpi");return r.json();}),fetch("data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("data");return r.json();}),fetch("stock-chart-drawings.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("drawings");return r.json();}).catch(function(){return {snapshots:{}};}),fetch(DRAWING_API+"/api/drawings?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("drawing api");return r.json();}).catch(function(){return {}; }),fetch("stock-company-data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("company data");return r.json();}).catch(function(){return {stocks:{}};})]).then(function(v){master=v[0];fpi=v[1];marketData=v[2];drawings=v[3]||{snapshots:{}};drawings.snapshots=drawings.snapshots||{};drawings.records=v[4]||{};companyResearch=v[5]||{stocks:{}};Object.keys(drawings.records).forEach(function(k){var symbol=drawingSymbolFromApiKey(k),rec=drawings.records[k];if(symbol!==k){drawings.records[symbol]=rec;delete drawings.records[k];}if(rec&&rec.snapshotUrl)drawings.snapshots[symbol]=rec.snapshotUrl;});render();}).catch(function(){if(!master)root.innerHTML='<div class="ma-empty">Market Activity डेटा लोड नहीं हो पाया। पेज रीफ़्रेश करें।</div>';}).finally(function(){loading=false;});}
load();window.setInterval(load,5*60*1000);
})();