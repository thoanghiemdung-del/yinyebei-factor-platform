"""Build alpha_history.html: sortable, multi-select, PnL, type filter, dedup."""
import os
DST = os.path.join(os.path.dirname(__file__), 'templates', 'alpha_history.html')
HTML = r'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"><title>Alpha 历史记录</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:"Microsoft YaHei",sans-serif;background:#0d1117;color:#c9d1d9}
.hdr{background:#161b22;border-bottom:1px solid #30363d;padding:10px 20px;display:flex;justify-content:center;align-items:center;gap:30px;position:sticky;top:0;z-index:100}
.hdr h1{color:#e94560;font-size:16px}.hdr nav{display:flex;gap:20px}.hdr nav a{color:#8b949e;text-decoration:none;font-size:12px}.hdr nav a:hover{color:#58a6ff}
.ctn{max-width:1200px;margin:0 auto;padding:16px}table{width:100%;border-collapse:collapse;font-size:11px}
th{background:#1c2533;padding:5px 7px;text-align:left;color:#58a6ff}td{padding:4px 7px;border-bottom:1px solid #1c2533}
tr:hover{background:rgba(88,166,255,0.03)}button{cursor:pointer}input,select,textarea{background:#161b22;border:1px solid #30363d;border-radius:4px;color:#fff;font-size:12px;padding:7px 9px}
.pnl-chart-wrap{margin-top:6px;background:#0d1117;border:1px solid #1c2533;border-radius:6px;padding:8px;display:block;width:100%}
.pnl-chart-wrap h4{font-size:10px;color:#8b949e;margin-bottom:4px}
.pnl-chart-wrap canvas{width:100%!important;height:200px!important}
.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.toolbar button{padding:6px 14px;background:#1c2533;color:#58a6ff;border:1px solid #30363d;border-radius:4px;font-size:11px}
.toolbar button.danger{background:#e94560;color:#fff;border:none}
.toolbar button:disabled{opacity:0.4}
</style></head><body>
<div class="hdr"><h1>Alpha 历史记录</h1><nav><a href="/dashboard">仪表盘</a><a href="/alpha_history">Alpha历史</a><a href="/data_fields">数据字段</a><a href="/operators">操作符</a><a href="/correlation">相关性</a><a href="/community">社区</a><a href="/learn">学习</a><a href="/logout">退出</a></nav></div>
<div class="ctn">
<div class="toolbar">
  <button onclick="setFilter('all')">全部</button>
  <button onclick="setFilter('alpha')" style="color:#58a6ff;border-color:#58a6ff">单因子</button>
  <button onclick="setFilter('sa')" style="color:#f0883e;border-color:#f0883e">等权组合</button>
  <button onclick="setFilter('lgb')" style="color:#a855f7;border-color:#a855f7">LGB</button>
  <span style="width:8px"></span>
  <button id="selAllBtn" onclick="toggleSelectAll()">全选</button>
  <button class="danger" id="delSelBtn" onclick="deleteSelected()" disabled>删除选中(0)</button>
  <button class="danger" onclick="clearAll()">清空全部</button>
  <button onclick="dedupAll()" style="color:#f0883e;border-color:#f0883e">一键去重</button>
</div>
<div id="c"></div></div>
<script>
(function loadChartJS(){if(typeof Chart!=="undefined")return;var s=document.createElement("script");s.src="/static/chart.umd.min.js";s.onerror=function(){console.warn("Chart.js unavailable");};document.head.appendChild(s);})();
function byId(id){return document.getElementById(id);}
function downsample(arr,tL){if(!arr||arr.length<=tL)return arr||[];var step=arr.length/tL,result=[];for(var j=0;j<tL;j++){var lo=Math.floor(j*step),hi=Math.floor((j+1)*step),s=0,n=0;for(var k=lo;k<hi&&k<arr.length;k++){if(arr[k]!=null){s+=arr[k];n++;}}result.push(n>0?s/n:null);}return result;}
var sc="time",so="desc",selectedRows={},allIds=[],chartsCache={},typeFilter="all";
function setFilter(t){typeFilter=t;load();}
function toggleSelectAll(){var all=Object.keys(selectedRows).length<allIds.length;if(all){allIds.forEach(function(id){selectedRows[id]=true;});}else{selectedRows={};}updateSelUI();renderCheckboxes();}
function updateSelUI(){var n=Object.keys(selectedRows).length;byId("delSelBtn").textContent="删除选中("+n+")";byId("delSelBtn").disabled=n===0;byId("selAllBtn").textContent=n===allIds.length?"取消全选":"全选";}
function renderCheckboxes(){allIds.forEach(function(id){var cb=document.querySelector(".cb-"+id.replace(/[^a-f0-9]/g,""));if(cb)cb.checked=!!selectedRows[id];});}
async function deleteSelected(){var ids=Object.keys(selectedRows);if(!ids.length)return;if(!confirm("确认删除 "+ids.length+" 条？"))return;for(var i=0;i<ids.length;i++){try{await fetch("/api/alpha/history/"+ids[i],{method:"DELETE"});}catch(e){}}selectedRows={};load();}
async function dedupAll(){if(!confirm("一键去重：保留每个表达式最新的一条。确认？"))return;try{var r=await fetch("/api/alpha/history/dedup",{method:"POST"});var d=await r.json();alert("已删除 "+d.deleted+" 条重复，保留 "+d.kept+" 条唯一因子");load();}catch(e){alert("去重失败: "+e.message);}}
async function clearAll(){if(!confirm("确认清空？"))return;try{await fetch("/api/alpha/history/clear",{method:"POST"});selectedRows={};load();}catch(e){}}
function toggleExpand(id){var row=byId("exp-"+id);if(!row)return;var opening=row.style.display==="none";row.style.display=opening?"":"none";if(!opening){if(chartsCache[id]){chartsCache[id].destroy();delete chartsCache[id];}return;}var cached=window["_pnl_"+id];if(cached){renderChart(id,cached);return;}fetch("/api/alpha/history/"+id+"/pnl").then(function(r){return r.json();}).then(function(d){window["_pnl_"+id]=d.pnl_series||[];renderChart(id,window["_pnl_"+id]);});}
function renderChart(id,pnl){if(!pnl||!pnl.length)return;if(typeof Chart==="undefined"){setTimeout(function(){renderChart(id,pnl);},100);return;}if(chartsCache[id])chartsCache[id].destroy();var d=downsample(pnl,200);var pnlMin=Math.min.apply(null,pnl.filter(function(x){return x!=null;}));var pnlMax=Math.max.apply(null,pnl.filter(function(x){return x!=null;}));var summary=byId("pnl-summary-"+id);if(summary){summary.innerHTML='PnL: 起始 <span style="color:'+(pnl[0]>=0?'#e94560':'#3fb950')+';">'+pnl[0].toFixed(2)+'%</span> - 最低 <span style="color:#3fb950;">'+pnlMin.toFixed(2)+'%</span> - 最高 <span style="color:#e94560;">'+pnlMax.toFixed(2)+'%</span> - 最终 <span style="color:'+(pnl[pnl.length-1]>=0?'#e94560':'#3fb950')+';">'+pnl[pnl.length-1].toFixed(2)+'%</span> ('+pnl.length+'天)';summary.style.display='block';}var wrap=document.querySelector('#exp-'+id+' .pnl-chart-wrap');if(wrap)wrap.style.display='block';var canvas=byId("pnl-c-"+id);if(!canvas)return;chartsCache[id]=new Chart(canvas.getContext("2d"),{type:"line",data:{labels:d.map(function(_,j){return j+1;}),datasets:[{label:"PnL",data:d,borderColor:"#f0883e",borderWidth:1.5,pointRadius:0,spanGaps:true,fill:true,backgroundColor:"rgba(240,136,62,0.06)"}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{display:false},y:{grid:{color:"#21262d"}}}}});}
async function load(col){if(col){if(col===sc)so=so==="desc"?"asc":"desc";else{sc=col;so="desc";}}byId("c").innerHTML='<div style="text-align:center;padding:40px;color:#8b949e;">加载中...</div>';Object.keys(chartsCache).forEach(function(k){if(chartsCache[k])chartsCache[k].destroy();delete chartsCache[k];});try{var r=await fetch("/api/alpha/history");var d=await r.json();var recs=d.records||[];
 if(typeFilter==="alpha")recs=recs.filter(function(r){return r.type==="alpha";});
 else if(typeFilter==="sa")recs=recs.filter(function(r){return r.type==="superalpha"&&r.expression.indexOf("lgb(")!==0;});
 else if(typeFilter==="lgb")recs=recs.filter(function(r){return r.type==="superalpha"&&r.expression.indexOf("lgb(")===0;});
 if(!recs.length){byId("c").innerHTML='<div style="text-align:center;padding:60px;color:#484f58;">暂无记录</div>';return;}
 allIds=recs.map(function(r){return r.id;});
 recs.sort(function(a,b){var am=a.metrics||{},bm=b.metrics||{},va,vb;if(sc==="ic"){va=am.pearson_ic||0;vb=bm.pearson_ic||0;}else if(sc==="excess"){va=(am.returns||am.annual_excess)||0;vb=(bm.returns||bm.annual_excess)||0;}else if(sc==="sharpe"){va=am.sharpe||0;vb=bm.sharpe||0;}else if(sc==="fitness"){va=am.fitness||0;vb=bm.fitness||0;}else if(sc==="turnover"){va=am.turnover||0;vb=bm.turnover||0;}else if(sc==="maxdd"){va=am.max_drawdown||0;vb=bm.max_drawdown||0;}else{va=a.timestamp||"";vb=b.timestamp||"";}return so==="asc"?va-vb:vb-va;});
 var ar=function(c){return sc===c?(so==="asc"?" ▲":" ▼"):"";};
 var h='<table><thead><tr><th style="width:30px"><input type="checkbox" id="cb-all" onchange="toggleAllCb(this)"></th><th onclick="load(\'time\')">时间'+ar("time")+'</th><th>名称</th><th>表达式</th><th>类型</th><th onclick="load(\'ic\')">IC'+ar("ic")+'</th><th onclick="load(\'excess\')">年化收益'+ar("excess")+'</th><th onclick="load(\'sharpe\')">Sharpe'+ar("sharpe")+'</th><th onclick="load(\'fitness\')">Fitness'+ar("fitness")+'</th><th onclick="load(\'turnover\')">Turnover'+ar("turnover")+'</th><th onclick="load(\'maxdd\')">MaxDD'+ar("maxdd")+'</th><th>操作</th></tr></thead><tbody>';
 recs.forEach(function(r){var m=r.metrics||{},ts=r.timestamp||"",time=ts.length>16?ts.substring(0,10)+" "+ts.substring(11,16):ts,name=r.name||"",expr=r.expression||"",cid=r.id.replace(/[^a-f0-9]/g,"");
  h+='<tr><td><input type="checkbox" class="cb-'+cid+'" onchange="toggleRow(\''+r.id+'\',this.checked)"'+(selectedRows[r.id]?" checked":"")+'></td>';
  h+='<td>'+time+'</td>';
  h+='<td><span style="color:#e6b422;cursor:pointer;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;" onclick="rn(\''+r.id+'\',\''+(name||"").replace(/'/g,"\\'")+'\')" title="点击重命名">'+esc(name||expr.substring(0,20))+'</span></td>';
  h+='<td><span style="font-family:monospace;color:#58a6ff;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;" title="'+esc(expr)+'">'+esc(expr.length>50?expr.substring(0,50)+"...":expr)+'</span></td>';
  h+='<td>'+(r.type==="superalpha"?(expr.indexOf("lgb(")===0?"LGB":"组合"):"单因子")+'</td>';
  h+='<td style="color:'+((m.pearson_ic||0)>=0?"#e94560":"#3fb950")+'">'+(m.pearson_ic||0).toFixed(4)+'</td>';
  h+='<td style="color:'+(((m.returns||m.annual_excess)||0)>=0?"#e94560":"#3fb950")+'">'+(((m.returns||m.annual_excess)||0)*100).toFixed(2)+'%</td>';
  h+='<td>'+(m.sharpe||0).toFixed(2)+'</td><td>'+(m.fitness||0).toFixed(2)+'</td>';
  h+='<td>'+((m.turnover||0)*100).toFixed(1)+'%</td><td>'+((m.max_drawdown||0)*100).toFixed(2)+'%</td>';
  h+='<td><button onclick="del(\''+r.id+'\')" style="color:#ff6b6b;background:none;border:1px solid #ff6b6b;border-radius:3px;padding:2px 6px;font-size:10px;">删除</button> <button onclick="toggleExpand(\''+r.id+'\')" style="color:#58a6ff;background:none;border:1px solid #58a6ff;border-radius:3px;padding:2px 6px;font-size:10px;">图表</button></td></tr>';
  h+='<tr id="exp-'+r.id+'" style="display:none;"><td colspan="12"><div style="padding:10px 12px;">';
  h+='<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:4px 16px;margin-bottom:8px;">';
  [['Rank IC',m.rank_ic,''],['ICIR',m.icir,''],['IC>0',m.ic_positive_ratio,'%'],['Sortino',m.sortino,''],['Margin',m.margin_bps,'bps'],['日胜率',m.win_rate,'%'],['天数',m.n_days,'天'],['Returns',m.returns,'']].forEach(function(item){var v=item[1],u=item[2];if(v==null){h+='<div style="font-size:10px;"><span style="color:#484f58;">'+item[0]+'</span><br><span style="color:#6e7681;">--</span></div>';}else if(u=='%'){h+='<div style="font-size:10px;"><span style="color:#484f58;">'+item[0]+'</span><br><span style="color:#c9d1d9;">'+(v*100).toFixed(1)+'%</span></div>';}else if(u=='bps'){h+='<div style="font-size:10px;"><span style="color:#484f58;">'+item[0]+'</span><br><span style="color:#c9d1d9;">'+v.toFixed(1)+'</span></div>';}else if(u=='天'){h+='<div style="font-size:10px;"><span style="color:#484f58;">'+item[0]+'</span><br><span style="color:#c9d1d9;">'+v+'</span></div>';}else{h+='<div style="font-size:10px;"><span style="color:#484f58;">'+item[0]+'</span><br><span style="color:#c9d1d9;">'+v.toFixed(3)+'</span></div>';}});
  h+='</div>';
  h+='<div id="pnl-summary-'+r.id+'" style="font-size:10px;color:#8b949e;margin-bottom:4px;display:none"></div>';
  h+='<div class="pnl-chart-wrap" style="display:none"><h4>PnL 累积收益</h4><canvas id="pnl-c-'+r.id+'"></canvas></div>';
  h+='</div></td></tr>';});
 h+='</tbody></table>';byId("c").innerHTML=h;updateSelUI();}
 catch(e){byId("c").innerHTML='<div style="text-align:center;padding:40px;color:#ff6b6b;">加载失败: '+e.message+'</div>';}}
function toggleAllCb(cb){if(cb.checked){allIds.forEach(function(id){selectedRows[id]=true;});}else{selectedRows={};}updateSelUI();load();}
function toggleRow(id,checked){if(checked)selectedRows[id]=true;else delete selectedRows[id];updateSelUI();}
function esc(s){var d=document.createElement("div");d.textContent=s||"";return d.innerHTML;}
async function del(id){if(!confirm("确认删除？"))return;try{await fetch("/api/alpha/history/"+id,{method:"DELETE"});delete selectedRows[id];load();}catch(e){}}
async function rn(id,old){var nn=prompt("新名称:",old);if(!nn||nn===old)return;try{var r=await fetch("/api/alpha/history/"+id+"/rename",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:nn})});if(!(await r.json()).error)load();}catch(e){}}
load();
</script></body></html>
'''
with open(DST, 'w', encoding='utf-8') as f:
    f.write(HTML)
print('alpha_history.html written OK (' + str(len(HTML)) + ' bytes)')
