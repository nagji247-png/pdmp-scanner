(function(){
"use strict";
var root=document.getElementById("market-activity");if(!root)return;
var master=null,fpi=null,marketData=null,searchTerm="",stack=[{type:"home",scroll:0}],loading=false;
var css=[
".market-activity-box{min-width:0;color:#e7f2ff}",
".ma-kicker{font-size:10px;letter-spacing:1px;color:#6cecff;font-weight:900;margin:14px 0 6px}",
".ma-intro{font-size:11px;color:#9bb2d2;line-height:1.5;margin:5px 0 10px}",
".ma-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:9px 0 14px}",
".ma-stat,.ma-sector,.ma-flow,.ma-panel{border:1px solid #1b426a;border-radius:10px;background:linear-gradient(145deg,#102747,#0a1930);min-width:0}",
".ma-stat{padding:10px}.ma-stat b{display:block;font-size:21px;color:#36e7ff}.ma-stat span{font-size:10px;color:#a9bfdc}",
".ma-alert{display:block;width:100%;text-align:left;padding:10px;margin:7px 0;border:1px solid #24466c;border-left:3px solid #f0b64d;border-radius:9px;background:#0b1b33;color:#e7f2ff;font-size:12px;cursor:pointer}",
".ma-alert small{display:block;color:#9bb2d2;font-size:10px;margin-top:3px}",
".ma-sector-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.ma-sector{overflow:hidden}",
".ma-sector-button,.ma-stock-button{display:block;width:100%;border:0;text-align:left;color:inherit;background:transparent;cursor:pointer;padding:11px}",
".ma-sector-head,.ma-stock-head{display:flex;justify-content:space-between;align-items:center;gap:7px}.ma-sector-name{font-size:12px;font-weight:850}.ma-count,.ma-tag{font-size:9px;color:#9bb2d2;white-space:nowrap}",
".ma-state{display:inline-block;font-size:9px;font-weight:800;padding:3px 6px;border-radius:5px;margin-top:7px;background:#172c49;color:#a9bfdc}.ma-state.bull{color:#20e6ac;background:#10372f}.ma-state.bear{color:#ff8795;background:#3a202c}",
".ma-meta{display:flex;flex-wrap:wrap;gap:5px 9px;margin-top:7px;font-size:10px;color:#a9bfdc}.ma-up{color:#20e6ac}.ma-down{color:#ff7184}.ma-neutral{color:#a9bfdc}.ma-warn{color:#ffca72}",
".ma-stock-row{border-top:1px solid #1a3557}.ma-stock-button{padding:12px 10px}.ma-symbol{font-size:13px;font-weight:900;color:#6cecff}.ma-stock-meta{font-size:11px;color:#a9bfdc;line-height:1.6;margin-top:7px;overflow-wrap:anywhere}",
".ma-panel{padding:11px;margin:8px 0}.ma-panel h4{font-size:12px;margin:0 0 6px;color:#6cecff}.ma-reason{font-size:11px;line-height:1.65;color:#d5e2f3}.ma-signal{padding:10px;border-radius:8px;background:#101f39;border:1px solid #24466c;margin-top:9px;font-size:12px;line-height:1.6}",
".ma-flow{padding:10px;margin:7px 0}.ma-flow b{font-size:12px}.ma-flow small{display:block;font-size:10px;color:#9bb2d2;margin-top:4px}",
".ma-foot,.ma-empty{font-size:10px;color:#9bb2d2;line-height:1.5;margin-top:10px}",
".ma-nav{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:8px;padding:8px 0 10px;background:#07152d;border-bottom:1px solid #24466c;margin-bottom:10px}",
".ma-back{border:1px solid #35709a;border-radius:8px;background:#102747;color:#6cecff;padding:9px 12px;font-size:12px;font-weight:800;cursor:pointer;white-space:nowrap}.ma-nav-title{font-size:13px;font-weight:900;color:#e7f2ff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
".ma-search{width:100%;padding:11px;border:1px solid #285078;border-radius:9px;background:#07172d;color:#e7f2ff;font-size:13px;margin:4px 0 10px}",
".ma-master{margin:8px 0}.ma-master>details{border:1px solid #1b426a;border-radius:10px;background:#0b1b33;padding:10px}.ma-master>details>summary{cursor:pointer;color:#6cecff;font-size:12px;font-weight:800}.ma-master-list details{border-top:1px solid #1a3557;padding:8px 2px}.ma-master-list summary{cursor:pointer;color:#d5e2f3;font-size:11px}",
"@media(max-width:560px){.ma-sector-grid{grid-template-columns:1fr}.ma-stat{padding:9px}.ma-sector-button{padding:10px}}"
].join("");
var st=document.createElement("style");st.textContent=css;document.head.appendChild(st);
function esc(v){return String(v==null?"":v).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function n(v){return v!==null&&v!==""&&Number.isFinite(Number(v))?Number(v):null;}
function money(v){var x=n(v);return x===null?"डेटा उपलब्ध नहीं":(x>0?"+":x<0?"−":"")+"₹"+Math.abs(x).toLocaleString("en-IN",{maximumFractionDigits:1})+" Cr";}
function latestFpi(){var h=fpi&&Array.isArray(fpi.history)?fpi.history:[];return h[0]||null;}
function fpiMap(){var o={},x=latestFpi();(x&&Array.isArray(x.sectors)?x.sectors:[]).forEach(function(s){if(s&&s.name)o[s.name]=n(s.net_equity_cr);});return o;}
function quote(s){var q=marketData&&marketData.instruments?marketData.instruments[s]:null;return q&&q.type==="stock"?q:null;}
function stockRows(sector){return Object.keys(master.stocks||{}).filter(function(s){return (master.stocks[s].sector||"सेक्टर उपलब्ध नहीं")===sector;}).sort().map(function(s){return {symbol:s,info:master.stocks[s],q:quote(s)};});}
function stats(rows){var d={up:0,down:0,flat:0,newsUp:0,newsDown:0,newsN:0};rows.forEach(function(r){var c=r.q&&n(r.q.change_pct);if(c!==null){if(c>0)d.up++;else if(c<0)d.down++;else d.flat++;}if(r.q&&(n(r.q.pos_n)!==null||n(r.q.neg_n)!==null)){d.newsN++;d.newsUp+=Number(r.q.pos_n||0);d.newsDown+=Number(r.q.neg_n||0);}});d.covered=d.up+d.down+d.flat;return d;}
function allSectors(){var names={};Object.keys(master.stocks||{}).forEach(function(s){names[master.stocks[s].sector||"सेक्टर उपलब्ध नहीं"]=true;});return Object.keys(names).sort().map(function(name){var rows=stockRows(name),d=stats(rows);var fm=fpiMap();return {name:name,rows:rows,d:d,flow:fm[name]==null?null:fm[name]};});}
function fpiPeriod(){var x=latestFpi();return x?(x.label||((x.from_date||"")+" – "+(x.to_date||""))):"डेटा उपलब्ध नहीं";}
function sectorNews(d){return d.newsN?(d.newsUp>d.newsDown?"खबरों में तेजी":d.newsDown>d.newsUp?"खबरों में मंदी":"खबरें मिश्रित"):"खबर पुष्टि उपलब्ध नहीं";}
function sectorState(d){return !d.covered?"भाव डेटा अपर्याप्त":d.up>d.down?"उपलब्ध भावों में तेजी":d.down>d.up?"उपलब्ध भावों में मंदी":"मिश्रित हलचल";}
function nav(title){return '<div class="ma-nav"><button class="ma-back" type="button" data-back>← वापस</button><div class="ma-nav-title">'+esc(title)+'</div></div>';}
function push(view){stack[stack.length-1].scroll=window.scrollY||0;stack.push(view);history.pushState({ma:true,depth:stack.length},"","#market-activity");render();window.scrollTo(0,0);}
function goBack(){if(stack.length>1)history.back();}
window.addEventListener("popstate",function(){if(stack.length>1){stack.pop();render();requestAnimationFrame(function(){window.scrollTo(0,stack[stack.length-1].scroll||0);});}});
root.addEventListener("click",function(e){var back=e.target.closest("[data-back]");if(back){goBack();return;}var sec=e.target.closest("[data-sector]");if(sec){push({type:"sector",name:sec.getAttribute("data-sector"),scroll:0});return;}var stk=e.target.closest("[data-stock]");if(stk){push({type:"stock",symbol:stk.getAttribute("data-stock"),sector:stk.getAttribute("data-sector-name")||""});return;}});
function renderHome(){
var sectors=allSectors(),symbols=Object.keys(master.stocks||{}),coverage=symbols.filter(function(s){var q=quote(s);return q&&n(q.change_pct)!==null;}).length;
var bull=sectors.filter(function(s){return s.d.covered&&s.d.up>s.d.down;}).length,bear=sectors.filter(function(s){return s.d.covered&&s.d.down>s.d.up;}).length;
var alerts=[];sectors.forEach(function(s){s.rows.forEach(function(r){var c=r.q&&n(r.q.change_pct);if(c!==null&&Math.abs(c)>=1)alerts.push({sector:s.name,row:r,change:c,date:r.q.price_as_of||"तारीख़ उपलब्ध नहीं"});});});
alerts.sort(function(a,b){var da=a.date.split("/").reverse().join("-"),db=b.date.split("/").reverse().join("-");return db.localeCompare(da)||Math.abs(b.change)-Math.abs(a.change);});
var fpiPositive=sectors.filter(function(s){return s.flow!==null&&s.flow>0;}).length,fpiNegative=sectors.filter(function(s){return s.flow!==null&&s.flow<0;}).length,fpiKnown=fpiPositive+fpiNegative;
var alertGuide='<div class="ma-meta"><span class="ma-state">HIGH · पुष्टि डेटा नहीं</span><span class="ma-state">WATCH · सत्यापित भाव बदलाव</span><span class="ma-state">FLOW · पिछली अवधि तुलना नहीं</span></div>';
var alertHtml=alerts.length?alerts.slice(0,8).map(function(a){return '<button class="ma-alert" type="button" data-stock="'+esc(a.row.symbol)+'" data-sector-name="'+esc(a.sector)+'"><span class="ma-state">WATCH</span><b> '+esc(a.row.symbol)+' · <span class="'+(a.change>0?"ma-up":"ma-down")+'">'+(a.change>0?"भाव ऊपर +":"भाव नीचे ")+a.change.toFixed(2)+'%</span></b><small>'+esc(a.sector)+' · EOD भाव तारीख़ '+esc(a.date)+' · वॉल्यूम पुष्टि उपलब्ध नहीं</small></button>';}).join(""):'<div class="ma-empty">अभी कोई सत्यापित WATCH अलर्ट नहीं। HIGH अलर्ट के लिए कीमत के साथ वॉल्यूम/अन्य पुष्टि भी आवश्यक है।</div>';
