(function(){
"use strict";
var root=document.getElementById("market-activity");if(!root)return;
var master=null,fpi=null,marketData=null,searchTerm="";
var css=[
".market-activity-box{min-width:0;color:#e7f2ff}",
".ma-kicker{font-size:10px;letter-spacing:1px;color:#6cecff;font-weight:900;margin:14px 0 6px}",
".ma-intro{font-size:11px;color:#9bb2d2;line-height:1.5;margin:5px 0 10px}",
".ma-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:9px 0 14px}",
".ma-stat,.ma-sector,.ma-flow{border:1px solid #1b426a;border-radius:10px;background:linear-gradient(145deg,#102747,#0a1930);min-width:0}",
".ma-stat{padding:10px}.ma-stat b{display:block;font-size:21px;color:#36e7ff}.ma-stat span{font-size:10px;color:#a9bfdc}",
".ma-alert{display:block;padding:10px;margin:7px 0;border:1px solid #24466c;border-left:3px solid #f0b64d;border-radius:9px;background:#0b1b33;color:#e7f2ff;text-decoration:none;font-size:12px}.ma-alert small{display:block;color:#9bb2d2;font-size:10px;margin-top:3px}",
".ma-search{width:100%;padding:11px;border:1px solid #285078;border-radius:9px;background:#07172d;color:#e7f2ff;font-size:13px;margin:4px 0 10px}",
".ma-sector-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ma-sector{overflow:hidden}",
".ma-sector>summary{padding:11px;cursor:pointer;list-style:none}.ma-sector>summary::-webkit-details-marker,.ma-stock>summary::-webkit-details-marker{display:none}",
".ma-sector-head,.ma-stock-head{display:flex;justify-content:space-between;align-items:center;gap:7px}.ma-sector-name{font-size:12px;font-weight:850}.ma-count,.ma-tag{font-size:9px;color:#9bb2d2;white-space:nowrap}",
".ma-state{display:inline-block;font-size:9px;font-weight:800;padding:3px 6px;border-radius:5px;margin-top:7px;background:#172c49;color:#a9bfdc}.ma-state.bull{color:#20e6ac;background:#10372f}.ma-state.bear{color:#ff8795;background:#3a202c}",
".ma-meta{display:flex;flex-wrap:wrap;gap:5px 9px;margin-top:7px;font-size:10px;color:#a9bfdc}.ma-up{color:#20e6ac}.ma-down{color:#ff7184}.ma-neutral{color:#a9bfdc}.ma-warn{color:#ffca72}",
".ma-sector-body{padding:0 9px 9px}.ma-stock{border-top:1px solid #1a3557;padding:8px 2px}.ma-stock>summary{display:flex;justify-content:space-between;gap:8px;cursor:pointer;list-style:none;padding:4px 0}",
".ma-symbol{font-size:12px;font-weight:900;color:#6cecff}.ma-stock-meta{font-size:10px;color:#a9bfdc;line-height:1.55;margin-top:5px;overflow-wrap:anywhere}.ma-stock-signal{font-size:10px;margin-top:7px;padding:7px;border-radius:7px;background:#101f39;line-height:1.45}",
".ma-flow{padding:10px;margin:7px 0}.ma-flow b{font-size:12px}.ma-flow small{display:block;font-size:10px;color:#9bb2d2;margin-top:4px}",
".ma-master details{border-top:1px solid #1a3557;padding:7px 2px}.ma-master summary{cursor:pointer;color:#6cecff;font-size:11px}.ma-foot,.ma-empty{font-size:10px;color:#9bb2d2;line-height:1.5;margin-top:10px}",
"@media(max-width:560px){.ma-sector-grid{grid-template-columns:1fr}.ma-stat{padding:9px}.ma-sector>summary{padding:10px}}"
].join("");var st=document.createElement("style");st.textContent=css;document.head.appendChild(st);
function esc(v){return String(v==null?"":v).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function n(v){return v!==null&&v!==""&&Number.isFinite(Number(v))?Number(v):null;}
function money(v){var x=n(v);return x===null?"डेटा उपलब्ध नहीं":(x>0?"+":x<0?"−":"")+"₹"+Math.abs(x).toLocaleString("en-IN",{maximumFractionDigits:1})+" Cr";}
function latestFpi(){var h=fpi&&Array.isArray(fpi.history)?fpi.history:[];return h[0]||null;}
function fpiMap(){var o={},x=latestFpi();(x&&Array.isArray(x.sectors)?x.sectors:[]).forEach(function(s){if(s&&s.name)o[s.name]=n(s.net_equity_cr);});return o;}
function quote(s){var q=marketData&&marketData.instruments?marketData.instruments[s]:null;return q&&q.type==="stock"?q:null;}
function buildRows(arr){return arr.map(function(x){return {symbol:x.symbol,info:x.info,q:quote(x.symbol)};});}
function stats(rows){var d={up:0,down:0,flat:0,newsUp:0,newsDown:0,newsN:0};rows.forEach(function(r){var c=r.q&&n(r.q.change_pct);if(c!==null){if(c>0)d.up++;else if(c<0)d.down++;else d.flat++;}if(r.q&&(n(r.q.pos_n)!==null||n(r.q.neg_n)!==null)){d.newsN++;d.newsUp+=Number(r.q.pos_n||0);d.newsDown+=Number(r.q.neg_n||0);}});d.covered=d.up+d.down+d.flat;return d;}
function stockBody(r,flow,period){
var q=r.q;if(!q)return '<div class="ma-stock-meta">कीमत: डेटा उपलब्ध नहीं · वॉल्यूम: डेटा उपलब्ध नहीं · खबरें: स्टॉक-स्तरीय खबर उपलब्ध नहीं · भीड़: डेटा उपलब्ध नहीं</div><div class="ma-stock-signal ma-warn">PDMP संकेत: पर्याप्त सत्यापित डेटा उपलब्ध नहीं।</div>';
var c=n(q.change_pct),score=n(q.score),dir=c===null?"दिशा उपलब्ध नहीं":c>0?"नीचे से ऊपर ↑":c<0?"नीचे ↓":"स्थिर";
var headlines=Array.isArray(q.headlines)?q.headlines.filter(function(h){return h&&h.title;}).slice(0,3):[];
var hhtml=headlines.length?headlines.map(function(h){return '<div class="ma-stock-meta">• '+(h.link?'<a target="_blank" rel="noopener" href="'+esc(h.link)+'">':'')+esc(h.title)+(h.link?'</a>':'')+' · '+esc(h.source||"स्रोत")+'</div>';}).join(""):'<div class="ma-stock-meta">स्टॉक-स्तरीय खबर उपलब्ध नहीं</div>';
var signal=score!==null&&c!==null?((c>0&&score<0)?"कीमत ऊपर, PDMP स्कोर मंदी — संभावित तेजी का अंतर जाँचें":(c<0&&score>0)?"कीमत नीचे, PDMP स्कोर तेजी — संभावित मंदी का अंतर जाँचें":"कीमत और PDMP स्कोर का मिलान करें"):"पर्याप्त PDMP/कीमत डेटा उपलब्ध नहीं";
return '<div class="ma-stock-meta">कीमत: '+(q.price==null?"डेटा उपलब्ध नहीं":"₹"+Number(q.price).toLocaleString("en-IN",{maximumFractionDigits:2}))+' · '+esc(q.price_as_of||"तारीख़ उपलब्ध नहीं")+'<br><span class="'+(c>0?"ma-up":c<0?"ma-down":"ma-neutral")+'">'+(c===null?"दिशा उपलब्ध नहीं":(c>0?"ऊपर ↑ ":"नीचे ↓ ")+(c>0?"+":"")+c.toFixed(2)+"%")+'</span><br>वॉल्यूम: '+(q.volume==null?"डेटा उपलब्ध नहीं":Number(q.volume).toLocaleString("en-IN"))+'</div>'+
'<div class="ma-stock-meta">खबरों का रुख: '+((q.pos_n||q.neg_n)?"तेजी "+Number(q.pos_n||0)+" · मंदी "+Number(q.neg_n||0):"डेटा उपलब्ध नहीं")+'<br>भीड़ का रुख: डेटा उपलब्ध नहीं<br>PDMP स्कोर: '+(score===null?"डेटा उपलब्ध नहीं":(score>0?"+":"")+score.toFixed(2))+'</div>'+
'<div class="ma-stock-signal ma-warn"><b>PDMP संकेत</b><br>'+signal+'</div><div class="ma-stock-meta">FPI सेक्टर प्रवाह: '+money(flow)+' · अवधि: '+esc(period)+' · व्यक्तिगत स्टॉक FPI उपलब्ध नहीं</div><b class="ma-stock-meta">ताज़ा स्टॉक खबरें</b>'+hhtml;
}
function render(){
if(!master||!master.stocks){root.innerHTML='<div class="ma-empty">NSE F&amp;O मास्टर लोड नहीं हुआ।</div>';return;}
var map=master.stocks,symbols=Object.keys(map).sort(),sectors={};symbols.forEach(function(s){var i=map[s]||{},k=i.sector||"सेक्टर उपलब्ध नहीं";(sectors[k]||(sectors[k]=[])).push({symbol:s,info:i});});
var fm=fpiMap(),lf=latestFpi(),period=lf?(lf.label||((lf.from_date||"")+" – "+(lf.to_date||""))):"डेटा उपलब्ध नहीं";
var sr=Object.keys(sectors).sort().map(function(k){var rows=buildRows(sectors[k]),d=stats(rows);return {name:k,rows:rows,d:d,flow:fm[k]};});
var coverage=symbols.filter(function(s){var q=quote(s);return q&&n(q.change_pct)!==null;}).length;
var bull=sr.filter(function(s){return s.d.covered&&s.d.up>s.d.down;}).length,bear=sr.filter(function(s){return s.d.covered&&s.d.down>s.d.up;}).length;
var alerts=[];sr.forEach(function(s){s.rows.forEach(function(r){var c=r.q&&n(r.q.change_pct);if(c!==null&&Math.abs(c)>=1)alerts.push({s:s.name,r:r,c:c});});});alerts.sort(function(a,b){return Math.abs(b.c)-Math.abs(a.c);});
var ah=alerts.length?alerts.slice(0,6).map(function(a){return '<a class="ma-alert" href="#ma-stock-'+esc(a.r.symbol)+'" data-stock="'+esc(a.r.symbol)+'"><b>'+esc(a.r.symbol)+' · <span class="'+(a.c>0?"ma-up":"ma-down")+'">'+(a.c>0?"तेजी +":"मंदी ")+a.c.toFixed(2)+'%</span></b><small>'+esc(a.s)+' · भाव तारीख़ '+esc(a.r.q.price_as_of||"उपलब्ध नहीं")+' · उपलब्ध quote snapshot</small></a>';}).join(""):'<div class="ma-empty">उपलब्ध भावों में ±1% या अधिक की सत्यापित हलचल नहीं मिली।</div>';
var sh=sr.map(function(s){var d=s.d,state=!d.covered?"डेटा अपर्याप्त":d.up>d.down?"उपलब्ध भावों में तेजी":d.down>d.up?"उपलब्ध भावों में मंदी":"मिश्रित";
var stocks=s.rows.map(function(r){var c=r.q&&n(r.q.change_pct);return '<details class="ma-stock" id="ma-stock-'+esc(r.symbol)+'"><summary><span class="ma-symbol">'+esc(r.symbol)+'</span><span class="ma-tag">'+(c===null?"भाव नहीं":(c>0?"तेजी ":c<0?"मंदी ":"स्थिर ")+(c>0?"+":"")+(c===null?"":c.toFixed(2)+"%"))+'　＋</span></summary><div class="ma-stock-meta">TAG · '+esc(r.symbol)+' · '+esc(r.info.sector)+' · '+esc(r.info.industry)+'</div>'+stockBody(r,s.flow,period)+'</details>';}).join("");
var news=d.newsN?(d.newsUp>d.newsDown?"खबरें तेजी":d.newsDown>d.newsUp?"खबरें मंदी":"खबरें मिश्रित"):"खबर पुष्टि उपलब्ध नहीं";
return '<details class="ma-sector"><summary><div class="ma-sector-head"><span class="ma-sector-name">'+esc(s.name)+'</span><span class="ma-count">'+s.rows.length+' स्टॉक　＋</span></div><span class="ma-state '+(state.indexOf("तेजी")>=0?"bull":state.indexOf("मंदी")>=0?"bear":"")+'">'+state+'</span><div class="ma-meta"><span>भाव '+d.covered+'/'+s.rows.length+'</span><span class="ma-up">↑ '+d.up+'</span><span class="ma-down">↓ '+d.down+'</span><span>स्थिर '+d.flat+'</span></div><div class="ma-meta"><span>FPI '+money(s.flow)+'</span><span>'+news+'</span></div></summary><div class="ma-sector-body"><div class="ma-intro">उपलब्ध भावों का कवरेज '+d.covered+'/'+s.rows.length+' · स्टॉक खोलने के लिए टैप करें।</div>'+stocks+'</div></details>';
}).join("");
var fh=sr.filter(function(s){return s.flow!==null;}).map(function(s){var d=s.d,news=d.newsN?(d.newsUp>d.newsDown?"खबरें तेजी":d.newsDown>d.newsUp?"खबरें मंदी":"खबरें मिश्रित"):"खबर पुष्टि उपलब्ध नहीं";var match=d.newsN&&((s.flow>0&&d.newsUp>d.newsDown)||(s.flow<0&&d.newsDown>d.newsUp));return '<div class="ma-flow"><b>'+esc(s.name)+' · '+money(s.flow)+'</b><small>अवधि: '+esc(period)+' · '+(s.flow>0?"शुद्ध खरीद":s.flow<0?"शुद्ध बिकवाली":"लगभग संतुलित")+' · '+news+' · '+(d.newsN?(match?"दिशा समान":"दिशा अलग/मिश्रित"):"मिलान संभव नहीं")+'</small></div>';}).join("");
var masterList=symbols.map(function(s){var i=map[s],q=quote(s),c=q&&n(q.change_pct);return '<details><summary>'+esc(s)+' · '+esc(i.sector)+' · '+(c===null?"भाव अनुपलब्ध":(c>0?"+":"")+c.toFixed(2)+"%")+'</summary><div class="ma-stock-meta">Tag: '+esc(s)+' · इंडस्ट्री: '+esc(i.industry)+'</div></details>';}).join("");
root.innerHTML='<div class="ma-kicker">MARKET ACTIVITY RADAR</div><div class="ma-intro">आज बाजार में कहाँ हलचल है? · 218 स्टॉक · 18 सेक्टर · केवल उपलब्ध सत्यापित डेटा</div>'+
'<div class="ma-kicker">आज की हलचल का सारांश</div><div class="ma-summary"><div class="ma-stat"><b>'+String(bull).padStart(2,"0")+'</b><span>उपलब्ध भावों में तेजी वाले सेक्टर</span></div><div class="ma-stat"><b>'+String(bear).padStart(2,"0")+'</b><span>उपलब्ध भावों में मंदी वाले सेक्टर</span></div><div class="ma-stat"><b>'+alerts.length+'</b><span>±1% से अधिक स्टॉक हलचल</span></div><div class="ma-stat"><b>'+coverage+'/218</b><span>भाव डेटा उपलब्ध</span></div></div>'+
'<div class="ma-kicker">LATEST ACTIVITY ALERTS</div><div class="ma-intro">सबसे बड़ा प्रतिशत बदलाव पहले · उपलब्ध quote snapshot, intraday live feed नहीं।</div>'+ah+
'<div class="ma-kicker">SECTOR ACTIVITY — 18 सेक्टर</div><div class="ma-intro">सेक्टर खोलें, फिर हर स्टॉक पर टैप करके STOCK WIND देखें।</div><div class="ma-sector-grid">'+sh+'</div>'+
'<div class="ma-kicker">FPI FLOW + NEWS CONFIRMATION</div><div class="ma-intro">NSDL का सेक्टर-स्तरीय Equity flow और उपलब्ध स्टॉक खबरों का मिलान।</div>'+(fh||'<div class="ma-empty">FPI डेटा उपलब्ध नहीं।</div>')+
'<div class="ma-kicker">218 STOCK MASTER LIST</div><input class="ma-search" id="ma-search" type="search" placeholder="स्टॉक / Tag / सेक्टर / इंडस्ट्री खोजें…" value="'+esc(searchTerm)+'"><div class="ma-master" id="ma-master">'+masterList+'</div>'+
'<div class="ma-foot">डेटा फ़ाइल अपडेट: '+esc(marketData&&marketData.updated||"समय उपलब्ध नहीं")+' · सेक्टर मास्टर: '+esc(master.as_of||"तारीख़ उपलब्ध नहीं")+' · FPI अवधि: '+esc(period)+'. वॉल्यूम और crowd mood feed में उपलब्ध नहीं, इसलिए अनुमान नहीं लगाया गया। FPI केवल सेक्टर स्तर का है।</div>';
document.querySelectorAll(".ma-alert").forEach(function(a){a.addEventListener("click",function(e){e.preventDefault();var id="ma-stock-"+a.getAttribute("data-stock"),el=document.getElementById(id);if(el){var sector=el.closest(".ma-sector");if(sector)sector.open=true;el.open=true;el.scrollIntoView({behavior:"smooth",block:"center"});}});});
var inp=document.getElementById("ma-search");if(inp)inp.addEventListener("input",function(e){searchTerm=String(e.target.value||"").trim().toLowerCase();document.querySelectorAll("#ma-master details").forEach(function(el){el.hidden=!!searchTerm&&el.textContent.toLowerCase().indexOf(searchTerm)<0;});document.querySelectorAll(".ma-sector").forEach(function(el){var ok=!searchTerm||el.textContent.toLowerCase().indexOf(searchTerm)>=0;el.hidden=!ok;if(searchTerm&&ok)el.open=true;});});
}
function load(){Promise.all([fetch("nse-fo-stock-sector-master.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("master");return r.json();}),fetch("fpi-sector-data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("fpi");return r.json();}),fetch("data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw Error("data");return r.json();})]).then(function(v){master=v[0];fpi=v[1];marketData=v[2];render();}).catch(function(){if(!master)root.innerHTML='<div class="ma-empty">Market Activity डेटा लोड नहीं हो पाया। पेज रीफ़्रेश करें।</div>';});}
load();window.setInterval(load,5*60*1000);
})();