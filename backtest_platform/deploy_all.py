import os
import os, json

T = os.path.join(BASE, 'templates')
NAV = '<a href="/dashboard">仪表盘</a><a href="/alpha_history">Alpha历史</a><a href="/compare">对比</a><a href="/correlation">相关性</a><a href="/data_fields">字段</a><a href="/operators">操作符</a><a href="/community">社区</a><a href="/learn">学习</a>'
USER = '{{ username }} | <a href="/logout" style="color:#8b949e">退出</a>'
CHART_JS = '<script>var Chart=null;var s=document.createElement("script");s.src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js";s.onload=function(){console.log("Chart loaded")};s.onerror=function(){console.log("Chart unavailable")};document.head.appendChild(s);</script>'
CACHE = '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">'

def page(title, body, extra_head=''):
    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">{CACHE}{extra_head}<title>{title}</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:"Microsoft YaHei",sans-serif;background:#0d1117;color:#c9d1d9}}
.hdr{{background:#161b22;border-bottom:1px solid #30363d;padding:10px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}}
.hdr h1{{color:#e94560;font-size:16px}}.hdr nav{{display:flex;gap:20px}}.hdr nav a{{color:#8b949e;text-decoration:none;font-size:12px}}.hdr nav a:hover{{color:#58a6ff}}
.ctn{{max-width:1200px;margin:0 auto;padding:16px}}table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{background:#1c2533;padding:5px 7px;text-align:left;color:#58a6ff}}td{{padding:4px 7px;border-bottom:1px solid #1c2533}}
tr:hover{{background:rgba(88,166,255,0.03)}}button{{cursor:pointer}}input,select,textarea{{background:#161b22;border:1px solid #30363d;border-radius:4px;color:#fff;font-size:12px;padding:7px 9px}}
</style></head><body>
<div class="hdr"><h1>{title}</h1><nav>{NAV}</nav><span style="font-size:11px;color:#8b949e">{USER}</span></div>
<div class="ctn">{body}</div></body></html>'''

# ============================================================
# 1. DASHBOARD (full features)
# ============================================================
dash_css = '''
.tabs{{display:flex;gap:2px;margin-bottom:0}}.tb{{padding:6px 14px;background:#161b22;border:1px solid #30363d;border-radius:6px 6px 0 0;cursor:pointer;font-size:11px;color:#8b949e}}
.tb.on{{background:#111820;color:#e94560;border-color:#e94560;border-bottom-color:#111820;font-weight:bold}}
.pn{{background:#111820;border:1px solid #30363d;border-radius:0 6px 6px 6px;padding:12px;margin-bottom:12px;display:none}}.pn.on{{display:block}}
.row{{display:flex;gap:6px;margin-bottom:8px}}.row input{{flex:1}}.row select{{font-size:11px}}
.row .rbtn{{padding:7px 14px;background:#e94560;color:#fff;border:none;border-radius:4px;font-size:11px}}
.row .rbtn:disabled{{background:#555}}.row .sbtn{{padding:7px 14px;background:#ff6b6b;color:#fff;border:none;border-radius:4px;font-size:11px;display:none}}
.prog{{height:3px;background:#30363d;border-radius:2px;margin-bottom:6px;overflow:hidden;display:none}}
.prog div{{height:100%;background:#58a6ff;width:0;transition:width 0.3s}}.err{{color:#ff6b6b;font-size:10px;margin-bottom:6px;display:none}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px;text-align:center}}
.card .v{{font-size:18px;font-weight:bold;color:#58a6ff}}.card .l{{font-size:9px;color:#8b949e;margin-top:1px}}.card.g .v{{color:#3fb950}}
.ex{{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px}}.ex h3{{color:#8b949e;font-size:10px;margin-bottom:4px}}
.ex code{{display:inline-block;padding:2px 5px;margin:2px;color:#58a6ff;font-size:9px;cursor:pointer;background:#1c2533;border-radius:2px}}.ex code:hover{{color:#e94560}}
.sa{{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:10px;margin-top:10px}}.sa h3{{color:#f0883e;font-size:11px;margin-bottom:4px}}
'''

dash_body = '''
<div class="tabs">
<div class="tb on" id="tab-0" onclick="st(0)">回测 #1</div>
<div class="tb" id="tab-1" onclick="st(1)">回测 #2</div>
<div class="tb" id="tab-2" onclick="st(2)">回测 #3</div>
</div>
''' + ''.join([f'''
<div class="pn {"on" if i==0 else ""}" id="pn-{i}">
<div class="row"><input type="text" id="e-{i}" placeholder="输入表达式" value="{('rank(ts_delta(close, 20))' if i==0 else '')}"><select id="n-{i}"><option value="none">无中性化</option><option value="market_cap">市值中性化</option></select><button class="rbtn" id="b-{i}" onclick="go({i})">回 测</button><button class="sbtn" id="s-{i}" onclick="stop({i})">停止</button></div>
<div class="prog" id="p-{i}"><div></div></div><div class="err" id="er-{i}"></div>
</div>''' for i in range(3)]) + f'''
<div style="background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px;margin-bottom:10px;min-height:200px;"><canvas id="pnl-chart"></canvas></div>
<div class="cards">
<div class="card g"><div class="v" id="m-excess">--</div><div class="l">年化收益(Returns)</div></div>
<div class="card"><div class="v" id="m-ic">--</div><div class="l">Pearson IC</div></div>
<div class="card"><div class="v" id="m-sharpe">--</div><div class="l">Sharpe</div></div>
<div class="card"><div class="v" id="m-fitness">--</div><div class="l">Fitness</div></div>
<div class="card"><div class="v" id="m-turnover">--</div><div class="l">Turnover</div></div>
<div class="card"><div class="v" id="m-dd">--</div><div class="l">最大回撤</div></div>
<div class="card"><div class="v" id="m-margin">--</div><div class="l">Margin(bps)</div></div>
<div class="card"><div class="v" id="m-winrate">--</div><div class="l">日胜率</div></div>
</div>
<div class="ex"><h3>示例（点击填充当前标签页并回测）</h3>
<code onclick="fg('rank(ts_delta(close, 20))')">20日动量</code>
<code onclick="fg('-rank(ts_sum(close/open-1, 5))')">5日反转</code>
<code onclick="fg('rank(ts_mean(volume, 5) / ts_mean(volume, 20))')">量比</code>
<code onclick="fg('-signed_power(close/open-1, 2) * rank(volume)')">异常量反转</code>
<code onclick="fg('rank(ts_std(close/open-1, 20))')">波动率</code>
<code onclick="fg('rank(ts_corr(close/open-1, volume, 20))')">量价相关</code>
<code onclick="fg('close / open - 1')">日内收益</code>
</div>
<div class="sa"><h3>SuperAlpha - 从Alpha历史选取组合</h3>
<div style="display:flex;gap:8px;margin-bottom:4px;font-size:10px;">
<select id="sasort" onchange="lsa()" style="padding:2px 4px;font-size:9px;"><option value="time">时间</option><option value="ic">IC</option><option value="excess">年化收益</option><option value="sharpe">Sharpe</option><option value="fitness">Fitness</option></select>
<button onclick="lsa('asc')" style="padding:2px 6px;font-size:9px;background:#1c2533;color:#8b949e;border:1px solid #30363d;border-radius:3px;" id="saord">降序</button>
<button onclick="lsa()" style="padding:2px 6px;font-size:9px;background:#1c2533;color:#58a6ff;border:1px solid #30363d;border-radius:3px;">加载历史</button>
</div>
<div id="salist" style="max-height:160px;overflow-y:auto;font-size:10px;margin-bottom:4px;"></div>
<div style="font-size:10px;color:#8b949e;">已选 <span id="sacnt">0</span> 个</div>
<button id="sago" onclick="rsa()" disabled style="padding:5px 12px;background:#f0883e;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:10px;margin-top:4px;">等权组合回测</button>
<div id="sares" style="margin-top:6px;font-size:10px;"></div></div>
'''

dash_js = '''<script>''' + CHART_JS + '''
var sl=0,sd=[null,null,null],sh=[],ss=[],sasort="time",saord="desc",_pc=null;
function $(id){return document.getElementById(id);}
function st(i){sl=i;for(var j=0;j<3;j++){$("tab-"+j).classList.toggle("on",j===i);$("pn-"+j).classList.toggle("on",j===i);}if(sd[i])sm(sd[i]);}
function fg(e){var inp=$("e-"+sl);if(inp)inp.value=e;go(sl);}
function sm(d){
 function s(id,fmt,val,m){try{$(id).textContent=fmt((val||0)*(m||1));}catch(e){}}
 s("m-excess",function(v){return v.toFixed(2)+"%";},d.annual_excess,100);
 s("m-ic",function(v){return v.toFixed(4);},d.pearson_ic,1);
 s("m-sharpe",function(v){return v.toFixed(2);},d.sharpe,1);
 s("m-fitness",function(v){return v.toFixed(2);},d.fitness,1);
 s("m-turnover",function(v){return v.toFixed(1)+"%";},d.turnover,100);
 s("m-dd",function(v){return v.toFixed(2)+"%";},d.max_drawdown,100);
 s("m-margin",function(v){return v.toFixed(1);},d.margin_bps,1);
 s("m-winrate",function(v){return v.toFixed(1)+"%";},d.win_rate,100);
 if(typeof Chart!=="undefined"&&d.pnl_series&&d.pnl_series.length){
  try{var ctx=$("pnl-chart");if(ctx){
   if(_pc)_pc.destroy();
   _pc=new Chart(ctx.getContext("2d"),{type:"line",data:{labels:d.pnl_series.map(function(_,i){return i+1;}),datasets:[{label:"PnL",data:d.pnl_series,borderColor:"#3fb950",borderWidth:2,pointRadius:0,fill:true,backgroundColor:"rgba(63,185,80,0.1)"}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}});
  }}catch(e){}}
}
async function go(i){
 var er=$("er-"+i);er.style.display="none";
 var v=$("e-"+i).value.trim();if(!v){er.textContent="请输入表达式";er.style.display="block";return;}
 var b=$("b-"+i),st=$("s-"+i);b.textContent="回测中...";b.disabled=true;st.style.display="inline-block";
 var p=$("p-"+i);p.style.display="block";p.firstChild.style.width="30%";
 try{
  var r=await fetch("/api/backtest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expression:v,neutralize:$("n-"+i).value})});
  p.firstChild.style.width="80%";var d=await r.json();
  p.style.display="none";b.textContent="回 测";b.disabled=false;st.style.display="none";
  if(d.error){er.textContent=d.error;er.style.display="block";return;}
  sd[i]=d;sm(d);
 }catch(x){p.style.display="none";b.textContent="回 测";b.disabled=false;st.style.display="none";er.textContent="失败: "+x.message;er.style.display="block";}
}
function stop(i){sd[i]=null;}
async function lsa(ord){
 if(ord)sasort=ord==="asc"?"asc":"desc";else saord=saord==="desc"?"asc":"desc";
 $("saord").textContent=saord==="asc"?"升序":"降序";
 $("salist").innerHTML='<div style="color:#8b949e;padding:4px;">加载中...</div>';
 try{var r=await fetch("/api/alpha/history");var d=await r.json();sh=d.records||[];
  sh.sort(function(a,b){var am=a.metrics||{},bm=b.metrics||{},va,vb;
   var sv=$("sasort").value;
   if(sv==="ic"){va=am.pearson_ic||0;vb=bm.pearson_ic||0;}
   else if(sv==="excess"){va=am.annual_excess||0;vb=bm.annual_excess||0;}
   else if(sv==="sharpe"){va=am.sharpe||0;vb=bm.sharpe||0;}
   else if(sv==="fitness"){va=am.fitness||0;vb=bm.fitness||0;}
   else{va=a.timestamp||"";vb=b.timestamp||"";}
   return saord==="asc"?va-vb:vb-va;});
  var h="";
  for(var i=0;i<sh.length;i++){var a=sh[i],m=a.metrics||{};
   h+='<label style="display:flex;align-items:center;gap:4px;padding:3px 4px;cursor:pointer;border-bottom:1px solid #1c2533;font-size:9px;"><input type="checkbox" onchange="tsa('+i+',this.checked)"><span style="font-family:monospace;color:#58a6ff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+(a.name||a.expression||"").substring(0,25)+'</span><span style="color:#8b949e;">IC:'+((m.pearson_ic||0).toFixed(3))+' R:'+((m.annual_excess||0)*100).toFixed(1)+'%</span></label>';}
  $("salist").innerHTML=h||'<div style="color:#8b949e;padding:4px;">暂无</div>';}
 catch(e){$("salist").innerHTML='<div style="color:#ff6b6b;padding:4px;">失败</div>';}
}
function tsa(i,c){
 if(c){if(ss.length>=5){alert("最多5个");return false;}ss.push(i);}
 else{ss=ss.filter(function(x){return x!==i;});}
 $("sacnt").textContent=ss.length;$("sago").disabled=ss.length<2;
}
async function rsa(){
 var ids=ss.map(function(i){return sh[i].id;});
 $("sares").innerHTML='<div style="color:#8b949e;">回测中...</div>';
 try{var r=await fetch("/api/superalpha",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({alpha_ids:ids})});var d=await r.json();
  if(d.error){$("sares").innerHTML='<span style="color:#ff6b6b;">'+d.error+"</span>";return;}
  var cm=d.combined_metrics||d.combined||d||{};sm(cm);
  var h='<div style="color:#3fb950;font-weight:bold;margin-bottom:4px;">组合 IC='+(cm.pearson_ic||0).toFixed(4)+" 收益="+((cm.annual_excess||0)*100).toFixed(2)+"% Sharpe="+(cm.sharpe||0).toFixed(2)+"</div>";
  h+='<table style="font-size:9px;"><tr><th>Alpha</th><th>IC</th><th>收益</th><th>Sharpe</th></tr>';
  (d.sub_alphas||d.alphas||[]).forEach(function(sa,i){var m=sa.metrics||sa||{},nm=(sa.expression||"").substring(0,20);h+='<tr><td style="font-family:monospace;color:#58a6ff;">'+nm+'</td><td>'+((m.pearson_ic||0).toFixed(4))+'</td><td>'+((m.annual_excess||0)*100).toFixed(2)+'%</td><td>'+((m.sharpe||0).toFixed(2))+'</td></tr>';});
  h+="</table>";
  // Overlaid PnL
  if(typeof Chart!=="undefined"&&cm.pnl_series&&cm.pnl_series.length){
   var allPnl=cm.pnl_series;var colors=["#e6b422","#58a6ff","#3fb950","#e94560","#f0883e"];
   h+='<div style="margin-top:8px;border-top:1px solid #30363d;padding-top:8px;"><canvas id="sapnl" style="height:180px;"></canvas></div>';
   $("sares").innerHTML=h;
   setTimeout(function(){var ctx=document.getElementById("sapnl");if(ctx){var ds=[{label:"Combined",data:allPnl,borderColor:"#fff",borderWidth:3,pointRadius:0}];(d.sub_alphas||d.alphas||[]).forEach(function(sa,i){if(sa.pnl_series&&sa.pnl_series.length)ds.push({label:(sa.expression||"").substring(0,15),data:sa.pnl_series,borderColor:colors[i%5],borderWidth:1,pointRadius:0});});new Chart(ctx.getContext("2d"),{type:"line",data:{labels:allPnl.map(function(_,i){return i+1;}),datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"top",labels:{color:"#8b949e",fontSize:9,boxWidth:10}}},scales:{x:{display:false},y:{grid:{color:"#30363d"}}}}});}},100);return;}
  $("sares").innerHTML=h;}
 catch(e){$("sares").innerHTML='<span style="color:#ff6b6b;">失败</span>';}
}
</script>'''

dash_html = page('量化回测仪表盘', dash_body, CHART_JS + '<style>'+dash_css+'</style>')
dash_html = dash_html.replace('</body>', dash_js + '\n</body>')

# ============================================================
# 2. ALPHA HISTORY
# ============================================================
ah_body = '''<div style="margin-bottom:12px;"><button onclick="load()" style="padding:6px 14px;background:#1c2533;color:#58a6ff;border:1px solid #30363d;border-radius:4px;font-size:11px;margin-right:8px;">刷新</button><button onclick="clearAll()" style="padding:6px 14px;background:#e94560;color:#fff;border:none;border-radius:4px;font-size:11px;">清空全部</button></div><div id="c"></div>'''
ah_js = '''<script>
var sc="time",so="desc";
async function load(col){
 if(col){if(col===sc)so=so==="desc"?"asc":"desc";else{sc=col;so="desc";}}
 document.getElementById("c").innerHTML='<div style="text-align:center;padding:40px;color:#8b949e;">加载中...</div>';
 try{var r=await fetch("/api/alpha/history");var d=await r.json();var recs=d.records||[];
  if(!recs.length){document.getElementById("c").innerHTML='<div style="text-align:center;padding:60px;color:#484f58;">暂无记录</div>';return;}
  recs.sort(function(a,b){var am=a.metrics||{},bm=b.metrics||{},va,vb;
   if(sc==="ic"){va=am.pearson_ic||0;vb=bm.pearson_ic||0;}
   else if(sc==="excess"){va=am.annual_excess||0;vb=bm.annual_excess||0;}
   else if(sc==="sharpe"){va=am.sharpe||0;vb=bm.sharpe||0;}
   else if(sc==="fitness"){va=am.fitness||0;vb=bm.fitness||0;}
   else if(sc==="turnover"){va=am.turnover||0;vb=bm.turnover||0;}
   else if(sc==="maxdd"){va=am.max_drawdown||0;vb=bm.max_drawdown||0;}
   else{va=a.timestamp||"";vb=b.timestamp||"";}
   return so==="asc"?va-vb:vb-va;});
  var ar=function(c){return sc===c?(so==="asc"?" ▲":" ▼"):"";};
  var h='<table><thead><tr><th onclick="load(\'time\')">时间'+ar("time")+'</th><th>名称</th><th>表达式</th><th>类型</th><th onclick="load(\'ic\')">IC'+ar("ic")+'</th><th onclick="load(\'excess\')">年化收益'+ar("excess")+'</th><th onclick="load(\'sharpe\')">Sharpe'+ar("sharpe")+'</th><th onclick="load(\'fitness\')">Fitness'+ar("fitness")+'</th><th onclick="load(\'turnover\')">Turnover'+ar("turnover")+'</th><th onclick="load(\'maxdd\')">MaxDD'+ar("maxdd")+'</th><th>操作</th></tr></thead><tbody>';
  recs.forEach(function(r){var m=r.metrics||{},ts=r.timestamp||"",time=ts.length>16?ts.substring(0,10)+" "+ts.substring(11,16):ts,name=r.name||"",expr=r.expression||"";
   h+='<tr><td>'+time+'</td>';
   h+='<td><span style="color:#e6b422;cursor:pointer;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;" onclick="rn(\''+r.id+'\',\''+(name||"").replace(/'/g,"\\\\'")+'\')" title="点击重命名">'+esc(name||expr.substring(0,20))+'</span></td>';
   h+='<td><span style="font-family:monospace;color:#58a6ff;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;" title="'+esc(expr)+'">'+esc(expr.length>50?expr.substring(0,50)+"...":expr)+'</span></td>';
   h+='<td>'+(r.type==="superalpha"?"组合":"单因子")+'</td>';
   h+='<td style="color:'+((m.pearson_ic||0)>=0?"#3fb950":"#ff6b6b")+'">'+(m.pearson_ic||0).toFixed(4)+'</td>';
   h+='<td style="color:'+((m.annual_excess||0)>=0?"#3fb950":"#ff6b6b")+'">'+((m.annual_excess||0)*100).toFixed(2)+'%</td>';
   h+='<td>'+(m.sharpe||0).toFixed(2)+'</td><td>'+(m.fitness||0).toFixed(2)+'</td>';
   h+='<td>'+((m.turnover||0)*100).toFixed(1)+'%</td><td>'+((m.max_drawdown||0)*100).toFixed(2)+'%</td>';
   h+='<td><button onclick="del(\''+r.id+'\')" style="color:#ff6b6b;background:none;border:1px solid #ff6b6b;border-radius:3px;padding:2px 6px;font-size:10px;">删除</button></td></tr>';});
  h+='</tbody></table>';document.getElementById("c").innerHTML=h;}
 catch(e){document.getElementById("c").innerHTML='<div style="text-align:center;padding:40px;color:#ff6b6b;">加载失败: '+e.message+'</div>';}
}
function esc(s){var d=document.createElement("div");d.textContent=s||"";return d.innerHTML;}
async function del(id){if(!confirm("确认删除？"))return;try{await fetch("/api/alpha/history/"+id,{method:"DELETE"});load();}catch(e){}}
async function rn(id,old){var nn=prompt("新名称:",old);if(!nn||nn===old)return;try{var r=await fetch("/api/alpha/history/"+id+"/rename",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:nn})});if(!(await r.json()).error)load();}catch(e){}}
async function clearAll(){if(!confirm("确认清空？"))return;try{await fetch("/api/alpha/history/clear",{method:"POST"});load();}catch(e){}}
load();
</script>'''
ah_html = page('Alpha 历史记录', ah_body).replace('</body>', ah_js + '\n</body>')

# ============================================================
# WRITE ALL FILES
# ============================================================
files = {
    'dashboard.html': dash_html,
    'alpha_history.html': ah_html,
}
for name, content in files.items():
    path = os.path.join(T, name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  {name}: {len(content)} bytes - OK')

print(f'\nDEPLOY COMPLETE: {len(files)} files written')
