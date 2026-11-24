(function(){
"use strict";
window.__TRINETRA_MA_STARTED__=true;
var root=document.getElementById("market-activity");if(!root)return;
var master=null,fpi=null,marketData=null,drawings={snapshots:{}},searchTerm="",stack=[{type:"home",scroll:0}],loading=false,viewRoot=root,popupLayer=null,popupBody=null,bodyOverflowBefore="";
var css=[
".market-activity-box{min-width:0;color:#e7f2ff}",
".ma-kicker{font-size:10px;letter-spacing:1px;color:#6cecff;font-weight:900;margin:14px 0 6px}",
".ma-intro{font-size:11px;color:#9bb2d2;line-height:1.5;margin:5px 0 10px}",
".ma-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:9px 0 14px}",
".ma-stat,.ma-sector,.ma-flow,.ma-panel{border:1px solid #1b426a;border-radius:10px;background:linear-gradient(145deg,#102747,#0a1930);min-width:0}",
".ma-stat{padding:0;overflow:hidden}.ma-stat-button{display:block;width:100%;height:100%;padding:11px;border:0;background:transparent;color:inherit;text-align:left;cursor:pointer}.ma-stat b{display:block;font-size:22px;color:#36e7ff}.ma-stat span{font-size:10px;color:#a9bfdc;line-height:1.4}.ma-stat-button:active{background:#173453}",".ma-stat.bull{border-color:#247a5a;background:linear-gradient(145deg,#10372f,#0a241f)}.ma-stat.bull b{color:#20e6ac}.ma-stat.bear{border-color:#9a3c50;background:linear-gradient(145deg,#3a202c,#241722)}.ma-stat.bear b{color:#ff7184}.ma-stat.unusual{border-color:#a86a24;background:linear-gradient(145deg,#3a2b18,#241d14)}.ma-stat.unusual b{color:#ffbd59}.ma-stat.fpi{border-color:#286a9c;background:linear-gradient(145deg,#102d49,#0a1c32)}.ma-stat.fpi b{color:#62bfff}",
".ma-alert{display:block;width:100%;text-align:left;padding:10px;margin:7px 0;border:1px solid #24466c;border-left:3px solid #f0b64d;border-radius:9px;background:#0b1b33;color:#e7f2ff;font-size:12px;cursor:pointer}.ma-alert.high{border-left-color:#ff596e}.ma-alert.watch{border-left-color:#ffbd59}.ma-alert.flow{border-left-color:#62bfff}.ma-alert-label{font-size:10px;font-weight:900;letter-spacing:.5px;margin-right:6px}.ma-alert.high .ma-alert-label{color:#ff7184}.ma-alert.watch .ma-alert-label{color:#ffbd59}.ma-alert.flow .ma-alert-label{color:#62bfff}",
".ma-alert small{display:block;color:#9bb2d2;font-size:10px;margin-top:3px}",
".ma-sector-group{margin:10px 0 14px;padding:9px;border:1px solid #1b426a;border-radius:10px;background:#091a30}.ma-sector-group.bull{border-color:#247a5a}.ma-sector-group.bear{border-color:#9a3c50}.ma-sector-group.neutral{border-color:#52627c}.ma-sector-group-title{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px;font-weight:900;margin:0 0 8px;color:#20e6ac}.ma-sector-group.bear .ma-sector-group-title{color:#ff7184}.ma-sector-group.neutral .ma-sector-group-title{color:#b8c4d8}.ma-sector-group-title span{font-size:10px;color:#9bb2d2;font-weight:700}.ma-sector-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ma-sector{overflow:hidden}",
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
".ma-admin-open{width:100%;padding:10px;border:1px solid #28709b;border-radius:8px;background:#102747;color:#6cecff;font-size:12px;font-weight:800;cursor:pointer}.ma-drawing-overlay{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;padding:12px;background:rgba(0,5,16,.82)}.ma-drawing-dialog{width:min(100%,520px);max-height:86vh;overflow:auto;border:1px solid #28709b;border-radius:13px;background:#07152d;box-shadow:0 18px 55px rgba(0,0,0,.55);padding:13px}.ma-drawing-dialog-head{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:13px;font-weight:900;color:#6cecff}.ma-drawing-close,.ma-drawing-action{padding:9px 11px;border:1px solid #28709b;border-radius:7px;background:#102747;color:#d9edff;font-size:11px;font-weight:800;cursor:pointer}.ma-drawing-field{display:block;margin:12px 0 5px;color:#b9c9e8;font-size:11px;font-weight:700}.ma-drawing-input{width:100%;padding:11px;border:1px solid #285078;border-radius:8px;background:#050f22;color:#e7f2ff;font-size:13px}.ma-drawing-help{font-size:10px;line-height:1.5;color:#9bb2d2;margin:7px 0}.ma-drawing-error{font-size:11px;line-height:1.5;color:#ff929e;margin:8px 0}.ma-drawing-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.ma-drawing-action.primary{background:#123b43;border-color:#1b927c;color:#75f0ca}.ma-drawing-action.danger{border-color:#a94c5a;color:#ff929e}.ma-drawing-bottom{display:flex;justify-content:flex-end;margin-top:14px;padding-top:10px;border-top:1px solid #183252}@media(max-width:560px){.ma-drawing-overlay{padding:7px}.ma-drawing-dialog{max-height:90vh;padding:11px}}",
".ma-radar-hero{display:grid;grid-template-columns:52px minmax(0,1fr) 52px;align-items:center;gap:10px;padding:15px 16px;margin:0 0 13px;border:2px solid #2876c7;border-radius:17px;background:linear-gradient(115deg,#071a35,#102e52 52%,#071a35);box-shadow:0 7px 22px rgba(0,0,0,.25)}",
".ma-radar-eye,.ma-radar-chart{display:flex;align-items:center;justify-content:center;width:48px;height:48px;border:1px solid #278bd0;border-radius:14px;background:#09264a;color:#55dfff;font-size:34px;font-weight:900;line-height:1}",
".ma-radar-chart{font-size:40px;color:#25e5ae;border-color:#168d79;background:#082d35}",
".ma-radar-heading{text-align:center;min-width:0}.ma-radar-kicker{font-size:11px;font-weight:900;color:#6cecff;letter-spacing:.7px;margin-bottom:4px}.ma-radar-heading h2{margin:0;color:#f2f7ff;font-size:clamp(17px,3vw,25px);font-weight:1000;letter-spacing:.4px;line-height:1.2}.ma-radar-heading p{margin:6px 0 0;color:#a9bfdc;font-size:11px;line-height:1.5}",
".ma-summary{grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0 17px}.ma-stat{border-radius:13px;min-height:102px}.ma-stat-button{padding:12px}.ma-stat b{font-size:clamp(23px,3vw,30px)}",
".ma-two-column-sectors{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-items:start}.ma-sector-group{min-width:0}",
".ma-sector-group.bull .ma-sector-group-title{background:linear-gradient(110deg,#07533d,#06352f)}.ma-sector-group.bear .ma-sector-group-title{background:linear-gradient(110deg,#7e1831,#451629)}",
".ma-sector-grid{grid-template-columns:1fr;gap:9px}",
".ma-neutral-subgroup{margin-top:10px;padding-top:8px;border-top:1px solid #52627c}.ma-neutral-subgroup .ma-sector-group-title{color:#b8c4d8;background:#17263d;border-radius:7px;padding:7px}",
".ma-sector{border-radius:12px}.ma-sector-button{padding:12px}.ma-sector-name{font-size:14px}",
".ma-alert{line-height:1.45}",
"@media(max-width:760px){.ma-radar-hero{grid-template-columns:36px minmax(0,1fr) 36px;padding:11px 8px;gap:6px}.ma-radar-eye,.ma-radar-chart{width:34px;height:34px;border-radius:10px;font-size:25px}.ma-radar-chart{font-size:29px}.ma-radar-heading h2{font-size:clamp(14px,4vw,19px)}.ma-radar-heading p{font-size:9px}.ma-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.ma-two-column-sectors{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.ma-sector-group{padding:8px}.ma-sector-group-title{font-size:12px;padding:8px 5px}.ma-sector-name{font-size:11px}.ma-sector-button{padding:8px}.ma-meta{font-size:9px;gap:4px}}",
].join("\n");
var st=document.createElement("style");st.textContent=css;document.head.appendChild(st);
var popupCss=document.createElement("style");popupCss.textContent=".ma-view-overlay{position:fixed;inset:0;z-index:9990;display:flex;align-items:center;justify-content:center;padding:10px;background:rgba(0,5,16,.82)}.ma-view-dialog{width:min(100%,760px);max-height:90vh;max-height:90dvh;overflow:hidden;border:1px solid #28709b;border-radius:13px;background:#07152d;box-shadow:0 18px 55px rgba(0,0,0,.55);display:flex;flex-direction:column}.ma-view-content{min-height:0;max-height:90vh;max-height:90dvh;overflow-y:auto;overscroll-behavior:contain;padding:12px;scrollbar-gutter:stable}.ma-view-content .ma-nav{position:sticky;top:-12px;margin:-12px -12px 10px;padding:10px 12px;background:#07152d;z-index:30}.ma-view-overlay .ma-drawing-overlay{z-index:100000}@media(max-width:560px){.ma-view-overlay{padding:6px;align-items:center}.ma-view-dialog{width:100%;max-height:92vh;max-height:92dvh;border-radius:11px}.ma-view-content{max-height:92vh;max-height:92dvh;padding:10px}.ma-view-content .ma-nav{top:-10px;margin:-10px -10px 10px;padding:9px 10px}}";document.head.appendChild(popupCss);
function esc(v){return String(v==null?"":v).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function n(v){return v!==null&&v!==""&&Number.isFinite(Number(v))?Number(v):null;}
function money(v){var x=n(v);return x===null?"डेटा उपलब्ध नहीं":(x>0?"+":x<0?"−":"")+"₹"+Math.abs(x).toLocaleString("en-IN",{maximumFractionDigits:1})+" Cr";}
function latestFpi(){var h=fpi&&Array.isArray(fpi.history)?fpi.history:[];return h[0]||null;}
function fpiMap(){var o={},x=latestFpi();(x&&Array.isArray(x.sectors)?x.sectors:[]).forEach(function(s){if(s&&s.name)o[s.name]=n(s.net_equity_cr);});return o;}
function quote(s){var q=marketData&&marketData.instruments?marketData.instruments[s]:null;if(q&&q.type==="stock")return q;var bulk=marketData&&marketData.market_activity_quotes&&marketData.market_activity_quotes.instruments?marketData.market_activity_quotes.instruments[s]:null;return bulk&&bulk.type==="stock"?bulk:null;}
function stockRows(sector){var known=master.stocks||{},symbols=Object.keys(known);if(sector==="सेक्टर मैपिंग उपलब्ध नहीं"){var quotes=marketData&&marketData.market_activity_quotes&&marketData.market_activity_quotes.instruments||{};symbols=symbols.concat(Object.keys(quotes).filter(function(s){return !known[s];}));}return symbols.filter(function(s){var info=known[s];return (info?(info.sector||"सेक्टर उपलब्ध नहीं"):"सेक्टर मैपिंग उपलब्ध नहीं")===sector;}).sort().map(function(s){return {symbol:s,info:known[s]||{sector:"सेक्टर मैपिंग उपलब्ध नहीं",industry:"इंडस्ट्री/सेक्टर मैपिंग उपलब्ध नहीं"},q:quote(s)};});}
function stats(rows){var d={up:0,down:0,flat:0,newsUp:0,newsDown:0,newsN:0};rows.forEach(function(r){var c=r.q&&n(r.q.change_pct);if(c!==null){if(c>0)d.up++;else if(c<0)d.down++;else d.flat++;}if(r.q&&(n(r.q.pos_n)!==null||n(r.q.neg_n)!==null)){d.newsN++;d.newsUp+=Number(r.q.pos_n||0);d.newsDown+=Number(r.q.neg_n||0);}});d.covered=d.up+d.down+d.flat;return d;}
function fpiDeltaMap(){var h=fpi&&Array.isArray(fpi.history)?fpi.history:[],out={};if(h.length<2)return out;var now={},prev={};(h[0].sectors||[]).forEach(function(s){if(s&&s.name)now[s.name]=n(s.net_equity_cr);});(h[1].sectors||[]).forEach(function(s){if(s&&s.name)prev[s.name]=n(s.net_equity_cr);});Object.keys(now).forEach(function(name){if(now[name]!==null&&prev[name]!==undefined&&prev[name]!==null)out[name]=now[name]-prev[name];});return out;}
function sectorOrder(s){var d=s.d;if(!d.covered)return 1;return d.up>d.down?0:d.down>d.up?2:1;}
function stockOrder(r){var c=r.q&&n(r.q.change_pct);return c===null||c===0?1:c>0?0:2;}
function compareStocks(a,b){var ga=stockOrder(a),gb=stockOrder(b);if(ga!==gb)return ga-gb;var ca=a.q&&n(a.q.change_pct),cb=b.q&&n(b.q.change_pct);if(ca===null||cb===null)return a.symbol.localeCompare(b.symbol);return ga===2?ca-cb:ga===0?cb-ca:Math.abs(ca)-Math.abs(cb);}
function compareSectors(a,b){var ga=sectorOrder(a),gb=sectorOrder(b);if(ga!==gb)return ga-gb;var da=a.d.up-a.d.down,db=b.d.up-b.d.down;if(ga===0)return db-da;if(ga===2)return da-db;return a.name.localeCompare(b.name);}
function allSectors(){var names={},known=master.stocks||{},quotes=marketData&&marketData.market_activity_quotes&&marketData.market_activity_quotes.instruments||{};Object.keys(known).forEach(function(s){names[known[s].sector||"सेक्टर उपलब्ध नहीं"]=true;});if(Object.keys(quotes).some(function(s){return !known[s];}))names["सेक्टर मैपिंग उपलब्ध नहीं"]=true;return Object.keys(names).map(function(name){var rows=stockRows(name),d=stats(rows),fm=fpiMap();return {name:name,rows:rows,d:d,flow:fm[name]==null?null:fm[name]};}).sort(compareSectors);}
function fpiPeriod(){var x=latestFpi();return x?(x.label||((x.from_date||"")+" – "+(x.to_date||""))):"डेटा उपलब्ध नहीं";}
function radarStamp(value){if(!value)return "समय उपलब्ध नहीं";var d=new Date(value);if(!Number.isFinite(d.getTime()))return String(value);return new Intl.DateTimeFormat("en-IN",{timeZone:"Asia/Kolkata",day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:true}).format(d)+" IST";}
function radarDate(value){if(!value)return null;var m=String(value).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);if(m)return m[3]+"-"+m[2]+"-"+m[1];var d=new Date(value);return Number.isFinite(d.getTime())?new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(d):null;}
function radarFreshness(){var universe=Object.assign({},marketData&&marketData.instruments||{},marketData&&marketData.market_activity_quotes&&marketData.market_activity_quotes.instruments||{});var dates=Object.keys(universe).map(function(s){var q=universe[s];return q&&q.price_as_of?radarDate(q.price_as_of):null;}).filter(Boolean).sort();var latest=dates.length?dates[dates.length-1]:null;var today=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());var label=!latest?"भाव की तारीख़ उपलब्ध नहीं":latest===today?"आज का भाव डेटा":"पुराना भाव डेटा";return label+" · भाव तारीख़: "+(latest?latest.split("-").reverse().join("/"):"उपलब्ध नहीं")+" · स्कैन अपडेट: "+radarStamp(marketData&&marketData.updated);}
function sectorNews(d){return d.newsN?(d.newsUp>d.newsDown?"खबरों में तेजी":d.newsDown>d.newsUp?"खबरों में मंदी":"खबरें मिश्रित"):"खबर पुष्टि उपलब्ध नहीं";}
function sectorState(d){return !d.covered?"भाव डेटा अपर्याप्त":d.up>d.down?"उपलब्ध भावों में तेजी":d.down>d.up?"उपलब्ध भावों में मंदी":"मिश्रित हलचल";}
function coverageCaution(d,total){var covered=Number(d&&d.covered||0),expected=Number(total||0);if(!expected||(covered>=5&&covered/expected>=0.6))return "";return '<span class="ma-foot" style="display:block">कम नमूना/कवरेज — दिशा केवल उपलब्ध '+covered+'/'+expected+' शेयरों पर आधारित है; इसे पूरे सेक्टर का निष्कर्ष न मानें।</span>';}
function freshNewsSignals(q){var p=0,b=0,hs=q&&Array.isArray(q.headlines)?q.headlines:[];hs.forEach(function(h){var age=n(h&&h.age_h),score=n(h&&h.score);if(age!==null&&age<=24&&score!==null){if(score>0)p++;else if(score<0)b++;}});return {positive:p,negative:b,total:p+b,bias:p>b?"bull":b>p?"bear":"mixed"};}
function crowdSummary(){var r=marketData&&marketData.retail_mood;if(!r)return "बाजार-स्तरीय crowd mood उपलब्ध नहीं";return "बाजार-स्तरीय "+String(r.bias||"मिश्रित")+" · CE "+(r.ce_pct==null?"—":r.ce_pct)+"% / PE "+(r.pe_pct==null?"—":r.pe_pct)+"% · "+String(r.date||"तारीख़ उपलब्ध नहीं")+" (स्टॉक-विशिष्ट नहीं)";}
function selectActivityAlerts(out){
var sorted=out.slice().sort(function(a,b){return a.rank-b.rank||b.activity-a.activity;}),selected=[],counts={high:0,watch:0,flow:0},limits={high:3,watch:3,flow:3};
["high","watch","flow"].forEach(function(kind){sorted.forEach(function(a){if(a.kind===kind&&counts[kind]<limits[kind]&&selected.length<8){selected.push(a);counts[kind]++;}});});
sorted.forEach(function(a){if(selected.length<8&&selected.indexOf(a)<0)selected.push(a);});
return selected.slice(0,8);
}
function activityAlerts(){var out=[],sectors=allSectors().filter(function(s){return s.name!=="सेक्टर मैपिंग उपलब्ध नहीं";}),delta=fpiDeltaMap();sectors.forEach(function(s){s.rows.forEach(function(r){var q=r.q,change=q&&n(q.change_pct);if(change===null)return;var news=freshNewsSignals(q),priceSignal=Math.abs(change)>=2,newsSignal=news.total>=2&&Math.abs(news.positive-news.negative)>=2,aligned=(change>0&&news.bias==="bull")||(change<0&&news.bias==="bear");if(priceSignal&&newsSignal&&aligned){out.push({kind:"high",symbol:r.symbol,sector:s.name,rank:0,activity:Math.abs(change),date:q.price_as_of||"भाव तारीख़ उपलब्ध नहीं",text:"कीमत "+(change>0?"तेजी ":"मंदी ")+Math.abs(change).toFixed(2)+"% और पिछले 24 घंटे की खबरें "+(news.bias==="bull"?"बुलिश":"बेयरिश")+" — दोनों संकेत एक दिशा में"});}else if(Math.abs(change)>=1.5||newsSignal){out.push({kind:"watch",symbol:r.symbol,sector:s.name,rank:1,activity:Math.max(Math.abs(change),Math.abs(news.positive-news.negative)),date:q.price_as_of||"भाव तारीख़ उपलब्ध नहीं",text:Math.abs(change)>=1.5?"कीमत में "+(change>0?"तेजी ":"गिरावट ")+Math.abs(change).toFixed(2)+"% — दूसरी पुष्टि बाकी":"पिछले 24 घंटे की खबरों में "+(news.bias==="bull"?"बुलिश":"बेयरिश")+" झुकाव — कीमत/अन्य पुष्टि बाकी"});}});if(delta[s.name]!==undefined&&delta[s.name]!==0){out.push({kind:"flow",sector:s.name,rank:2,activity:Math.abs(delta[s.name]),date:fpiPeriod(),text:"FPI सेक्टर नेट Equity में पिछली अवधि से "+money(delta[s.name])+" बदलाव"});}});return selectActivityAlerts(out);}

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
var sectors=allSectors().filter(function(s){return s.name!=="सेक्टर मैपिंग उपलब्ध नहीं";}),universe=Object.assign({},master.stocks||{},marketData&&marketData.market_activity_quotes&&marketData.market_activity_quotes.instruments||{}),symbols=Object.keys(universe);
var fpiDelta=fpiDeltaMap();
var alerts=activityAlerts(),alertHtml=alerts.length?alerts.map(function(a){var tag=a.kind==="high"?"HIGH":a.kind==="watch"?"WATCH":"FLOW";var target=a.symbol?' data-stock="'+esc(a.symbol)+'" data-sector-name="'+esc(a.sector)+'"':' data-sector="'+esc(a.sector)+'"';return '<button type="button" class="ma-alert '+a.kind+'"'+target+'><span class="ma-alert-label">'+tag+'</span><b>'+esc(a.symbol||a.sector)+'</b> · '+esc(a.text)+'<small>'+esc(a.sector)+' · '+esc(a.date||"अवधि उपलब्ध नहीं")+(a.symbol?" · स्टॉक विवरण खोलें":" · सेक्टर विवरण खोलें")+'</small></button>';}).join(""):'<div class="ma-empty">अभी HIGH / WATCH / FLOW के लिए पर्याप्त सत्यापित बदलाव नहीं मिला।</div>';
var bullSectors=sectors.filter(function(s){return sectorOrder(s)===0;});
var bearSectors=sectors.filter(function(s){return sectorOrder(s)===2;});
var neutralSectors=sectors.filter(function(s){return sectorOrder(s)===1;});
function renderSectorCards(items,tone){
return items.map(function(s){var d=s.d,state=sectorState(d);return '<div class="ma-sector '+tone+'"><button class="ma-sector-button" type="button" data-sector="'+esc(s.name)+'"><div class="ma-sector-head"><span class="ma-sector-name">'+esc(s.name)+'</span><span class="ma-count">'+s.rows.length+' स्टॉक　›</span></div><span class="ma-state '+tone+'">'+(tone==="bull"?"उपलब्ध भावों में तेजी":tone==="bear"?"उपलब्ध भावों में मंदी":state)+'</span><div class="ma-meta"><span>भाव उपलब्ध '+d.covered+'/'+s.rows.length+'</span><span class="ma-up">↑ '+d.up+'</span><span class="ma-neutral">सामान्य '+d.flat+'</span><span class="ma-down">↓ '+d.down+'</span></div>'+coverageCaution(d,s.rows.length)+'</button></div>';}).join("");
}
var neutralSectorHtml=neutralSectors.length?'<div class="ma-neutral-subgroup"><div class="ma-sector-group-title">मिश्रित / डेटा कम <span>'+neutralSectors.length+' सेक्टर</span></div><div class="ma-sector-grid">'+renderSectorCards(neutralSectors,"neutral")+'</div></div>':"";
var bullSectorHtml='<section class="ma-sector-group bull"><div class="ma-sector-group-title">↗ तेजी वाले सेक्टर <span>'+bullSectors.length+' सेक्टर</span></div><div class="ma-sector-grid">'+renderSectorCards(bullSectors,"bull")+'</div>'+neutralSectorHtml+'</section>';
var bearSectorHtml='<section class="ma-sector-group bear"><div class="ma-sector-group-title">↘ मंदी वाले सेक्टर <span>'+bearSectors.length+' सेक्टर</span></div><div class="ma-sector-grid">'+renderSectorCards(bearSectors,"bear")+'</div></section>';
var sectorHtml='<div class="ma-two-column-sectors">'+bullSectorHtml+bearSectorHtml+'</div>';
root.innerHTML='<div class="ma-radar-hero"><span class="ma-radar-eye" aria-hidden="true">◉</span><div class="ma-radar-heading"><div class="ma-radar-kicker">आज की बाजार गतिविधि</div><h2>MARKET ACTIVITY RADAR</h2><p>आज बाजार में कहाँ हलचल है? · '+symbols.length+' स्टॉक · '+sectors.length+' सेक्टर · उपलब्ध सत्यापित डेटा के आधार पर</p></div><span class="ma-radar-chart" aria-hidden="true">↗</span></div>'+
'<div class="ma-kicker">LATEST ACTIVITY ALERTS</div><div class="ma-intro">HIGH: कम-से-कम दो स्वतंत्र संकेत एक दिशा में। WATCH: एक महत्वपूर्ण संकेत, पुष्टि बाकी। FLOW: सत्यापित FPI बदलाव।</div>'+alertHtml+'<div class="ma-kicker">SECTOR ACTIVITY — '+sectors.length+' सेक्टर</div>'+'<div class="ma-intro">सेक्टर की दिशा उपलब्ध सत्यापित शेयर भावों के आधार पर है। सेक्टर खोलकर उसके शेयर देखें।</div>'+sectorHtml+
'<div class="ma-foot">भाव डेटा उपलब्ध '+symbols.filter(function(k){var q=quote(k);return q&&n(q.change_pct)!==null;}).length+'/'+symbols.length+' स्टॉक। बाकी स्टॉक सेक्टर सूची में रहेंगे, लेकिन बिना सत्यापित भाव के उन्हें तेजी/मंदी नहीं दिया जाएगा। असामान्य स्टॉक की गिनती कीमत बदलाव पर आधारित है; वॉल्यूम डेटा उपलब्ध नहीं है। FPI बदलाव नवीनतम दो उपलब्ध NSDL fortnightly अवधियों की तुलना है।<br><b>'+esc(radarFreshness())+'</b> · FPI अवधि: '+esc(fpiPeriod())+'</div>';
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
var rows=sectors.filter(function(s){return delta[s.name]!==undefined;}).map(function(s){return {name:s.name,delta:delta[s.name],flow:s.flow};}).sort(function(a,b){return b.delta-a.delta;});
body=latest&&previous?'<div class="ma-intro">तुलना: '+esc(latest.label||fpiPeriod())+' बनाम '+esc(previous.label||"पिछली अवधि")+'। रकम ₹ करोड़ में।</div>'+rows.map(function(x){return '<div class="ma-flow"><b>'+esc(x.name)+' · '+money(x.flow)+'</b><small>पिछली अवधि से बदलाव: '+money(x.delta)+' · '+(x.delta>0?"प्रवाह में सुधार":x.delta<0?"प्रवाह में गिरावट":"कोई बदलाव नहीं")+'<br>वर्तमान अवधि का नेट Equity प्रवाह; यह intraday FPI नहीं है।</small></div>';}).join(""):'<div class="ma-empty">तुलना के लिए दो सत्यापित FPI अवधियाँ उपलब्ध नहीं हैं।</div>';
}
viewRoot.innerHTML=nav(title)+'<div class="ma-kicker">'+esc(title)+'</div>'+body;
}
function renderSector(name){
var s=allSectors().filter(function(x){return x.name===name;})[0];if(!s){viewRoot.innerHTML=nav("सेक्टर नहीं मिला")+'<div class="ma-empty">इस सेक्टर का डेटा उपलब्ध नहीं।</div>';return;}
var d=s.d,ordered=s.rows.slice().sort(compareStocks),rows=ordered.map(function(r){var c=r.q&&n(r.q.change_pct),group=stockOrder(r),label=c===null?"भाव उपलब्ध नहीं":c>0?"तेजी +"+c.toFixed(2)+"%":c<0?"मंदी "+c.toFixed(2)+"%":"सामान्य 0.00%";return '<div class="ma-stock-row '+(group===0?"bull":group===2?"bear":"neutral")+'"><button type="button" class="ma-stock-button" data-stock="'+esc(r.symbol)+'" data-sector-name="'+esc(name)+'"><div class="ma-stock-head"><span class="ma-symbol">'+esc(r.symbol)+'</span><span class="ma-tag '+(group===0?"ma-up":group===2?"ma-down":"")+'">'+esc(label)+'　›</span></div><div class="ma-stock-meta">'+esc(r.info.industry||"इंडस्ट्री उपलब्ध नहीं")+' · '+(r.q?"भाव "+esc(r.q.price_as_of||"तारीख़ उपलब्ध नहीं"):"भाव डेटा उपलब्ध नहीं")+'</div></button></div>';}).join("");
viewRoot.innerHTML=nav(name)+'<div class="ma-kicker">SECTOR ACTIVITY</div><div class="ma-intro">इस सेक्टर के स्टॉक: तेजी ऊपर, सामान्य/भाव अनुपलब्ध बीच में और मंदी नीचे।</div><div class="ma-summary"><div class="ma-stat"><div class="ma-stat-button"><b>'+d.up+'</b><span>तेजी वाले स्टॉक</span></div></div><div class="ma-stat"><div class="ma-stat-button"><b>'+d.flat+'</b><span>सामान्य स्टॉक</span></div></div><div class="ma-stat"><div class="ma-stat-button"><b>'+d.down+'</b><span>मंदी वाले स्टॉक</span></div></div><div class="ma-stat"><div class="ma-stat-button"><b>'+(s.rows.length-d.covered)+'</b><span>भाव उपलब्ध नहीं</span></div></div></div><div class="ma-panel"><h4>सेक्टर की स्थिति</h4><div class="ma-reason">'+esc(sectorState(d))+' · '+esc(sectorNews(d))+'<br>FPI प्रवाह: '+money(s.flow)+'<br>अवधि: '+esc(fpiPeriod())+'<br>खबरों का रुख: '+esc(sectorNews(d))+'<br>भीड़ का रुख: '+esc(crowdSummary())+'<br>FPI + खबर पुष्टि: '+(s.flow===null||!d.newsN?"मिलान संभव नहीं":((s.flow>0&&d.newsUp>d.newsDown)||(s.flow<0&&d.newsDown>d.newsUp))?"दिशा समान":"दिशा अलग/मिश्रित")+'<br><b>ध्यान दें:</b> FPI डेटा पूरे सेक्टर का fortnightly Equity है; खबरें उपलब्ध स्टॉक-स्तरीय खबरों का सेक्टर योग हैं। भीड़ बाजार-स्तरीय संदर्भ है, स्टॉक-विशिष्ट नहीं।</div></div>'+coverageCaution(d,s.rows.length)+'<div class="ma-kicker">STOCK WIND — '+esc(name)+'</div>'+rows;
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
var info=(master.stocks||{})[symbol]||{sector:"सेक्टर मैपिंग उपलब्ध नहीं",industry:"इंडस्ट्री/सेक्टर मैपिंग उपलब्ध नहीं"},q=quote(symbol),fm=fpiMap(),flow=fm[sector]==null?null:fm[sector],period=fpiPeriod(),c=q&&n(q.change_pct),headlines=q&&Array.isArray(q.headlines)?q.headlines.filter(function(h){return h&&h.title;}).slice(0,5):[];

var rawSnapshot=drawings&&drawings.snapshots?drawings.snapshots[symbol]:"";
var snapshotMatch=typeof rawSnapshot==="string"?rawSnapshot.match(/^https:\/\/www\.tradingview\.com\/x\/([A-Za-z0-9]+)\/?$/):null;
var snapshotId=snapshotMatch?snapshotMatch[1]:null;
var snapshotImage=snapshotId?"https://s3.tradingview.com/snapshots/"+snapshotId.charAt(0).toLowerCase()+"/"+snapshotId+".png":"";
var savedChartUrl=drawings&&drawings.records&&drawings.records[symbol]?drawings.records[symbol].chartUrl:"";var fullChartUrl=savedChartUrl||"https://www.tradingview.com/chart/?symbol=NSE%3A"+encodeURIComponent(symbol);
var chartPreviewHtml=snapshotId?'<div class="ma-chart-preview"><div class="ma-stock-head"><b>आपकी DRAWING PREVIEW</b><span class="ma-tag">TradingView Snapshot</span></div><a href="'+esc(snapshotMatch[0])+'" target="_blank" rel="noopener"><img src="'+esc(snapshotImage)+'" alt="'+esc(symbol)+' TradingView Drawing Preview" loading="lazy"></a><div class="ma-chart-actions"><a class="ma-chart-link" href="'+esc(snapshotMatch[0])+'" target="_blank" rel="noopener">Drawing अलग से खोलें ↗</a><a class="ma-chart-link" href="'+esc(fullChartUrl)+'" target="_blank" rel="noopener">अपना TradingView Chart खोलें ↗</a></div></div>':'<div class="ma-chart-preview"><b>DRAWING PREVIEW</b><div class="ma-chart-missing">इस स्टॉक का अलग Snapshot लिंक अभी जोड़ा नहीं गया है।</div><div class="ma-chart-actions"><a class="ma-chart-link" href="'+esc(fullChartUrl)+'" target="_blank" rel="noopener">अपना TradingView Chart खोलें ↗</a></div></div>';

var bd=q&&q.component_breakdown?q.component_breakdown:{},final=bd.final||{},components=Array.isArray(final.included_components)?final.included_components:[],pdmpScore=final.status==="available"?n(final.score):null;
var sectorRows=stockRows(sector),sectorNewsUp=0,sectorNewsDown=0,sectorNewsCount=0;
sectorRows.forEach(function(r){if(r.q&&(n(r.q.pos_n)!==null||n(r.q.neg_n)!==null)){sectorNewsUp+=Number(r.q.pos_n||0);sectorNewsDown+=Number(r.q.neg_n||0);sectorNewsCount++;}});
var sectorNewsDirection=!sectorNewsCount?"सेक्टर खबर डेटा अपर्याप्त":sectorNewsUp>sectorNewsDown?"सेक्टर खबरों का रुख बुलिश":sectorNewsDown>sectorNewsUp?"सेक्टर खबरों का रुख बेयरिश":"सेक्टर खबरें मिश्रित";
var sectorMatch=flow===null||!sectorNewsCount?"मिलान संभव नहीं":((flow>0&&sectorNewsUp>sectorNewsDown)||(flow<0&&sectorNewsDown>sectorNewsUp))?"दिशा समान":"दिशा अलग/मिश्रित";
var priceText=c===null?"कीमत की दिशा उपलब्ध नहीं":c>0?"कीमत ऊपर +"+c.toFixed(2)+"%":c<0?"कीमत नीचे "+c.toFixed(2)+"%":"कीमत लगभग स्थिर";
var stockNews=q&&(n(q.pos_n)!==null||n(q.neg_n)!==null)?"बुलिश खबरें "+Number(q.pos_n||0)+" · बेयरिश खबरें "+Number(q.neg_n||0):"इस स्टॉक की खबरों का स्कोर उपलब्ध नहीं";
var missing=[];if(!q)missing.push("इस स्टॉक का सत्यापित quote उपलब्ध नहीं");else{if(c===null)missing.push("भाव बदलाव उपलब्ध नहीं");if(q.volume==null)missing.push("वॉल्यूम और औसत वॉल्यूम उपलब्ध नहीं");if(n(q.pos_n)===null&&n(q.neg_n)===null)missing.push("स्टॉक-स्तरीय खबर उपलब्ध नहीं");}
if(!components.length)missing.push("कोई सत्यापित PDMP component Final में शामिल नहीं");else if(components.length===1&&components[0]==="news")missing.push("अभी केवल News component शामिल है; पूर्ण PDMP निष्कर्ष नहीं");
var reason=[];if(q){if(q.price!=null)reason.push("अंतिम उपलब्ध कीमत ₹"+Number(q.price).toLocaleString("en-IN",{maximumFractionDigits:2}));if(c!==null)reason.push(priceText);if(q.price_as_of)reason.push("भाव तारीख़ "+q.price_as_of);if(n(q.pos_n)!==null||n(q.neg_n)!==null)reason.push(stockNews);}
var pdmpText=pdmpScore===null?"संकेत बनाने के लिए डेटा अपर्याप्त — पर्याप्त सत्यापित PDMP डेटा उपलब्ध नहीं":components.length===1&&components[0]==="news"?"आंशिक component score "+(pdmpScore>0?"+":"")+pdmpScore.toFixed(2)+" · केवल News component; इसे ट्रेड अवसर/खतरे का पूरा PDMP संकेत न मानें":"उपलब्ध PDMP component score "+(pdmpScore>0?"+":"")+pdmpScore.toFixed(2)+" · शामिल घटक: "+components.join(", ");
var retail=marketData&&marketData.retail_mood?marketData.retail_mood:null;
var crowdText=retail?"बाजार-स्तरीय retail mood: "+esc(retail.bias||"मिश्रित")+" · CE "+esc(retail.ce_pct)+"% / PE "+esc(retail.pe_pct)+"% · तारीख़ "+esc(retail.date||"उपलब्ध नहीं"):"बाजार-स्तरीय retail mood उपलब्ध नहीं";
var headlineHtml=headlines.length?headlines.map(function(h){return '<div class="ma-stock-meta">• '+(h.link?'<a target="_blank" rel="noopener" href="'+esc(h.link)+'">':'')+esc(h.title)+(h.link?'</a>':'')+' · '+esc(h.source||"स्रोत")+(h.published_at?" · "+esc(h.published_at):"")+'</div>';}).join(""):'<div class="ma-stock-meta">इस स्टॉक की खबरें उपलब्ध नहीं।</div>';
var drawingAdminHtml='<div class="ma-panel"><h4>DRAWING LINK MANAGEMENT</h4><button type="button" class="ma-admin-open" data-drawing-admin="'+esc(symbol)+'">Drawing लिंक जोड़ें / बदलें</button><div class="ma-drawing-help">Admin Login आवश्यक · Preview सभी दर्शकों को दिखेगा</div></div>'+drawingModalHtml(symbol);
viewRoot.innerHTML=nav(symbol)+chartPreviewHtml+drawingAdminHtml+'<div class="ma-kicker">STOCK WIND · '+esc(sector)+'</div><div class="ma-panel"><div class="ma-stock-head"><span class="ma-symbol">'+esc(symbol)+'</span><span class="ma-tag">'+esc(info.industry||"इंडस्ट्री उपलब्ध नहीं")+'</span></div><div class="ma-stock-meta">Tag: '+esc(symbol)+' · सेक्टर: '+esc(sector)+'</div></div>'+
'<div class="ma-panel"><h4>1. कीमत और वॉल्यूम</h4><div class="ma-reason">'+(q&&q.price!=null?"कीमत: ₹"+Number(q.price).toLocaleString("en-IN",{maximumFractionDigits:2}):"कीमत: डेटा उपलब्ध नहीं")+'<br>भाव तारीख़: '+esc(q&&q.price_as_of||"उपलब्ध नहीं")+'<br>स्रोत: '+esc(q&&q.price_source||"स्रोत उपलब्ध नहीं")+'<br>'+esc(priceText)+'<br>वॉल्यूम: '+(q&&q.volume!=null?Number(q.volume).toLocaleString("en-IN"):"डेटा उपलब्ध नहीं")+'<br>वॉल्यूम तारीख़: '+esc(q&&q.volume_as_of||"उपलब्ध नहीं")+'<br>Delivery Quantity: '+(q&&q.delivery_qty!=null?Number(q.delivery_qty).toLocaleString("en-IN"):"डेटा उपलब्ध नहीं")+'<br>Delivery %: '+(q&&q.delivery_pct!=null?Number(q.delivery_pct).toFixed(2)+"%":"डेटा उपलब्ध नहीं")+'<br>कुल Trades: '+(q&&q.trades!=null?Number(q.trades).toLocaleString("en-IN"):"डेटा उपलब्ध नहीं")+'<br><b>वॉल्यूम पुष्टि:</b> औसत वॉल्यूम उपलब्ध नहीं, इसलिए सामान्य से ज्यादा/कम नहीं कहा जा सकता।</div></div>'+
'<div class="ma-panel"><h4>2. खबरों का रुख</h4><div class="ma-reason">'+esc(stockNews)+'</div>'+headlineHtml+'</div>'+
'<div class="ma-panel"><h4>3. भीड़ का रुख</h4><div class="ma-reason">इस स्टॉक का अलग crowd mood उपलब्ध नहीं।<br>'+crowdText+'<br>यह केवल पूरे बाजार का संदर्भ है, '+esc(symbol)+' की व्यक्तिगत भीड़ का संकेत नहीं।</div></div>'+
'<div class="ma-panel"><h4>4. PDMP संकेत और पूरा कारण</h4><div class="ma-signal"><b>'+esc(pdmpText)+'</b></div><div class="ma-reason"><b>इस स्टॉक से उपलब्ध प्रमाण:</b><br>'+(reason.length?reason.map(esc).join("<br>"):"अभी पर्याप्त सत्यापित डेटा नहीं")+'<br><br><b>कौन-सी जानकारी अनुपलब्ध है:</b><br>'+(missing.length?missing.map(esc).join("<br>"):"कोई अतिरिक्त कमी दर्ज नहीं")+'<br><br>कीमत का बदलाव अकेले reversal या trade opportunity साबित नहीं करता।</div></div>'+
'<div class="ma-panel"><h4>5. FPI FLOW + NEWS CONFIRMATION</h4><div class="ma-reason">सेक्टर FPI प्रवाह: '+money(flow)+'<br>अवधि: '+esc(period)+'<br>इसी सेक्टर की उपलब्ध स्टॉक खबरें: '+esc(sectorNewsDirection)+'<br>भीड़ का रुख: '+esc(crowdSummary())+'<br>दिशा तुलना: '+esc(sectorMatch)+'<br><br><b>क्यों?</b> तुलना इस सेक्टर के उपलब्ध quote वाले स्टॉक की कुल positive/negative news counts से की गई है; यह '+esc(symbol)+' की खबरों और FPI का सीधा मिलान नहीं है।<br><br><b>महत्वपूर्ण:</b> व्यक्तिगत स्टॉक FPI उपलब्ध नहीं; यह FPI पूरे '+esc(sector)+' सेक्टर का है।</div></div>';
}
function render(){if(!master||!master.stocks){root.innerHTML='<div class="ma-empty">NSE F&amp;O मास्टर लोड नहीं हुआ।</div>';return;}var v=stack[stack.length-1];if(v.type==="home"){closePopup();viewRoot=root;renderHome();return;}ensurePopup();viewRoot=popupBody;if(v.type==="radar")renderRadarList(v.kind);else if(v.type==="sector")renderSector(v.name);else renderStock(v.symbol,v.sector);if(popupBody&&v.scroll===0)popupBody.scrollTop=0;}
function fetchJson(url,label,timeoutMs){
return new Promise(function(resolve,reject){
var settled=false,timer=window.setTimeout(function(){if(!settled){settled=true;reject(Error(label+" timeout"));}},timeoutMs||12000);
fetch(url,{cache:"no-store"}).then(function(r){if(!r.ok)throw Error(label+" HTTP "+r.status);return r.json();}).then(function(value){if(!settled){settled=true;window.clearTimeout(timer);resolve(value);}},function(err){if(!settled){settled=true;window.clearTimeout(timer);reject(err);}});
});
}
function load(){
if(loading)return;
loading=true;
Promise.all([
fetchJson("nse-fo-stock-sector-master.json?t="+Date.now(),"NSE master",15000),
fetchJson("data.json?t="+Date.now(),"Market data",15000)
]).then(function(v){
master=v[0];marketData=v[1];fpi={history:[]};drawings={snapshots:{},records:{}};
render();
loading=false;
/* FPI and drawings are supplementary: neither may delay the sector radar. */
fetchJson("fpi-sector-data.json?t="+Date.now(),"FPI data",12000).then(function(value){fpi=value||{history:[]};if(stack[stack.length-1].type==="home")render();}).catch(function(err){if(window.console&&console.warn)console.warn("Optional FPI data unavailable",err);});
fetchJson("stock-chart-drawings.json?t="+Date.now(),"Local drawings",12000).then(function(value){drawings=value||{snapshots:{}};drawings.snapshots=drawings.snapshots||{};if(stack[stack.length-1].type==="stock")render();}).catch(function(err){if(window.console&&console.warn)console.warn("Optional local drawings unavailable",err);});
fetchJson(DRAWING_API+"/api/drawings?t="+Date.now(),"Drawing API",12000).then(function(records){
drawings.records=records||{};
Object.keys(drawings.records).forEach(function(k){var symbol=drawingSymbolFromApiKey(k),rec=drawings.records[k];if(symbol!==k){drawings.records[symbol]=rec;delete drawings.records[k];}if(rec&&rec.snapshotUrl)drawings.snapshots[symbol]=rec.snapshotUrl;});
if(stack[stack.length-1].type==="stock")render();
}).catch(function(err){if(window.console&&console.warn)console.warn("Optional Drawing API unavailable",err);});
}).catch(function(err){var message=err&&err.message?err.message:"अज्ञात त्रुटि";root.innerHTML='<div class="ma-empty">Market Activity लोड/रेंडर नहीं हो पाया। कारण: '+esc(message)+'</div>';if(window.console&&console.error)console.error("Market Activity load/render failed",err);}).finally(function(){loading=false;});
}
load();window.setInterval(load,5*60*1000);
})();