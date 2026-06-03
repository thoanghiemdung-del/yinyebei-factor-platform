h=open('D:/yyb/backtest_platform/templates/dashboard_v2.html','r',encoding='utf-8').read()[:100]  # just to get the pattern
# Actually write the alpha history directly
html='''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta http-equiv="Cache-Control" content="no-cache">
<title>Alpha 历史记录</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei",sans-serif;background:#0d1117;color:#c9d1d9}
.hdr{background:#161b22;border-bottom:1px solid #30363d;padding:10px 20px;display:flex;justify-content:space-between;align-items:center}
.hdr h1{color:#e94560;font-size:16px}
.hdr nav{display:flex;gap:20px}
.hdr nav a{color:#8b949e;text-decoration:none;font-size:12px}
.hdr nav a:hover{color:#58a6ff}
.ctn{max-width:1400px;margin:0 auto;padding:16px}
.btns{margin-bottom:12px}
.btns button{padding:6px 14px;margin-right:8px;border:none;border-radius:4px;cursor:pointer;font-size:11px}
.btns .r{background:#1c2533;color:#58a6ff;border:1px solid #30363d}
.btns .d{background:#e94560;color:#fff}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:#1c2533;padding:6px 8px;text-align:left;color:#58a6ff;cursor:pointer;position:sticky;top:0}
th:hover{color:#e94560}
td{padding:5px 8px;border-bottom:1px solid #1c2533}
tr:hover{background:rgba(88,166,255,0.04)}
.nc{color:#e6b422;cursor:pointer;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nc:hover{text-decoration:underline}
.ec{font-family:monospace;color:#58a6ff;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.db{color:#ff6b6b;background:none;border:1px solid #ff6b6b;border-radius:3px;padding:2px 6px;cursor:pointer;font-size:10px}
.db:hover{background:rgba(255,107,107,0.1)}
.em{text-align:center;padding:60px;color:#484f58;font-size:13px}
</style>
</head>
<body>
<div class="hdr"><h1>Alpha 历史记录</h1>
<nav><a href="/dashboard">仪表盘</a><a href="/alpha_history">Alpha历史</a><a href="/compare">对比</a><a href="/correlation">相关性</a><a href="/data_fields">字段</a><a href="/operators">操作符</a><a href="/community">社区</a><a href="/learn">学习</a></nav>
<span style="font-size:11px;color:#8b949e">{{ username }} | <a href="/logout" style="color:#8b949e">退出</a></span></div>
<div class="ctn">
<div class="btns"><button class="r" onclick="load()">刷新</button><button class="d" onclick="clearAll()">清空全部</button></div>
<div id="c"></div></div>
<script>
var sc="time",so="desc";
async function load(col){
  if(col){if(col===sc)so=so==="desc"?"asc":"desc";else{sc=col;so="desc";}}
  document.getElementById("c").innerHTML='<div class="em">加载中...</div>';
  try{var r=await fetch("/api/alpha/history");var d=await r.json();
    var recs=d.records||[];
    if(!recs.length){document.getElementById("c").innerHTML='<div class="em">暂无记录</div>';return;}
    recs.sort(function(a,b){var am=a.metrics||{},bm=b.metrics||{},va,vb;
      if(sc==="ic"){va=am.pearson_ic||0;vb=bm.pearson_ic||0;}
      else if(sc==="excess"){va=am.annual_excess||0;vb=bm.annual_excess||0;}
      else if(sc==="sharpe"){va=am.sharpe||0;vb=bm.sharpe||0;}
      else if(sc==="fitness"){va=am.fitness||0;vb=bm.fitness||0;}
      else if(sc==="turnover"){va=am.turnover||0;vb=bm.turnover||0;}
      else if(sc==="maxdd"){va=am.max_drawdown||0;vb=bm.max_drawdown||0;}
      else{va=a.timestamp||"";vb=b.timestamp||"";}
      return so==="asc"?va-vb:vb-va;});
    var h='<table><thead><tr>';
    var ar=function(c){return sc===c?(so==="asc"?" ▲":" ▼"):"";};
    h+='<th onclick="load(\'time\')">时间'+ar("time")+'</th><th>名称</th><th>表达式</th><th>类型</th>';
    h+='<th onclick="load(\'ic\')">IC'+ar("ic")+'</th><th onclick="load(\'excess\')">年化收益'+ar("excess")+'</th>';
    h+='<th onclick="load(\'sharpe\')">Sharpe'+ar("sharpe")+'</th><th onclick="load(\'fitness\')">Fitness'+ar("fitness")+'</th>';
    h+='<th onclick="load(\'turnover\')">Turnover'+ar("turnover")+'</th><th onclick="load(\'maxdd\')">MaxDD'+ar("maxdd")+'</th><th>操作</th></tr></thead><tbody>';
    recs.forEach(function(r){var m=r.metrics||{},ts=r.timestamp||"",time=ts.length>16?ts.substring(0,10)+" "+ts.substring(11,16):ts,name=r.name||"",expr=r.expression||"";
      h+='<tr><td>'+time+'</td>';
      h+='<td><span class="nc" onclick="rn(\''+r.id+'\',\''+(name||"").replace(/'/g,"\\'")+'\')" title="点击重命名">'+esc(name||expr.substring(0,20))+'</span></td>';
      h+='<td><span class="ec" title="'+esc(expr)+'">'+esc(expr.length>50?expr.substring(0,50)+"...":expr)+'</span></td>';
      h+='<td>'+(r.type==="superalpha"?"组合":"单因子")+'</td>';
      h+='<td style="color:'+((m.pearson_ic||0)>=0?"#3fb950":"#ff6b6b")+'">'+(m.pearson_ic||0).toFixed(4)+'</td>';
      h+='<td style="color:'+((m.annual_excess||0)>=0?"#3fb950":"#ff6b6b")+'">'+((m.annual_excess||0)*100).toFixed(2)+'%</td>';
      h+='<td>'+(m.sharpe||0).toFixed(2)+'</td><td>'+(m.fitness||0).toFixed(2)+'</td>';
      h+='<td>'+((m.turnover||0)*100).toFixed(1)+'%</td><td>'+((m.max_drawdown||0)*100).toFixed(2)+'%</td>';
      h+='<td><button class="db" onclick="del(\''+r.id+'\')">删除</button></td></tr>';});
    h+='</tbody></table>';document.getElementById("c").innerHTML=h;}
  catch(e){document.getElementById("c").innerHTML='<div class="em">加载失败: '+e.message+'</div>';}
}
function esc(s){var d=document.createElement("div");d.textContent=s||"";return d.innerHTML;}
async function del(id){if(!confirm("确认删除？"))return;try{await fetch("/api/alpha/history/"+id,{method:"DELETE"});load();}catch(e){alert("失败");}}
async function rn(id,old){var nn=prompt("新名称:",old);if(!nn||nn===old)return;try{var r=await fetch("/api/alpha/history/"+id+"/rename",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:nn})});var d=await r.json();if(d.error){alert(d.error);}else{load();}}catch(e){alert("失败");}}
async function clearAll(){if(!confirm("确认清空？"))return;try{await fetch("/api/alpha/history/clear",{method:"POST"});load();}catch(e){alert("失败");}}
load();
</script>
</body></html>'''
with open('D:/yyb/backtest_platform/templates/alpha_history.html','w',encoding='utf-8') as f:f.write(html)
print('Alpha history rewritten - OK')
