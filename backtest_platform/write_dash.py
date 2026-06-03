import os
BASE = os.path.dirname(os.path.abspath(__file__))
h="""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta http-equiv="Cache-Control" content="no-cache">
<title>量化回测仪表盘</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei",sans-serif;background:#0d1117;color:#c9d1d9}
.hdr{background:#161b22;border-bottom:1px solid #30363d;padding:10px 20px;display:flex;justify-content:space-between;align-items:center}
.hdr h1{color:#e94560;font-size:16px}
.hdr nav{display:flex;gap:20px}
.hdr nav a{color:#8b949e;text-decoration:none;font-size:12px}
.hdr nav a:hover{color:#58a6ff}
.ctn{max-width:1000px;margin:0 auto;padding:16px}
.row{display:flex;gap:6px;margin-bottom:8px}
.row input{flex:1;padding:7px 9px;background:#161b22;border:1px solid #30363d;border-radius:4px;color:#fff;font-size:12px}
.row select{padding:7px 9px;background:#161b22;border:1px solid #30363d;border-radius:4px;color:#fff;font-size:11px}
.row button{padding:7px 14px;border:none;border-radius:4px;cursor:pointer;font-size:11px}
.rbtn{background:#e94560;color:#fff}.rbtn:disabled{background:#555}
.sbtn{background:#ff6b6b;color:#fff;display:none}
.prog{height:3px;background:#30363d;border-radius:2px;margin-bottom:6px;overflow:hidden;display:none}
.prog div{height:100%;background:#58a6ff;width:0;transition:width 0.3s}
.err{color:#ff6b6b;font-size:10px;margin-bottom:6px;display:none}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px}
.card{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px;text-align:center}
.card .v{font-size:18px;font-weight:bold;color:#58a6ff}
.card .l{font-size:9px;color:#8b949e;margin-top:1px}
.card.g .v{color:#3fb950}
.pnlbox{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px;margin-bottom:10px;min-height:200px}
.ex{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px;margin-top:10px}
.ex h3{color:#8b949e;font-size:10px;margin-bottom:4px}
.ex code{display:inline-block;padding:2px 5px;margin:2px;color:#58a6ff;font-size:9px;cursor:pointer;background:#1c2533;border-radius:2px}
.ex code:hover{color:#e94560}
.sa{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:10px;margin-top:10px}
.sa h3{color:#f0883e;font-size:11px;margin-bottom:4px}
</style>
</head>
<body>
<div class="hdr"><h1>量化回测</h1>
<nav><a href="/dashboard">仪表盘</a><a href="/alpha_history">Alpha历史</a><a href="/compare">对比</a><a href="/correlation">相关性</a><a href="/data_fields">字段</a><a href="/operators">操作符</a><a href="/community">社区</a><a href="/learn">学习</a></nav>
<span style="font-size:11px;color:#8b949e">{{ username }} | <a href="/logout" style="color:#8b949e">退出</a></span></div>
<div class="ctn">

<div class="row"><input type="text" id="expr" placeholder="输入表达式" value="rank(ts_delta(close, 20))"><select id="neut"><option value="none">无中性化</option><option value="market_cap">市值中性化</option></select><button class="rbtn" id="btn" onclick="go()">回 测</button></div>
<div class="prog" id="prog"><div></div></div>
<div class="err" id="err"></div>

<div class="pnlbox"><canvas id="pnl"></canvas></div>

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

<div class="ex"><h3>示例</h3>
<code onclick="fg('rank(ts_delta(close, 20))')">20日动量</code>
<code onclick="fg('-rank(ts_sum(close/open-1, 5))')">5日反转</code>
<code onclick="fg('rank(ts_mean(volume, 5) / ts_mean(volume, 20))')">量比</code>
<code onclick="fg('-signed_power(close/open-1, 2) * rank(volume)')">异常量反转</code>
<code onclick="fg('rank(ts_std(close/open-1, 20))')">波动率</code>
<code onclick="fg('rank(ts_corr(close/open-1, volume, 20))')">量价相关</code>
<code onclick="fg('close / open - 1')">日内收益</code>
</div>

<div class="sa"><h3>SuperAlpha - 从Alpha历史选取组合</h3>
<div style="display:flex;gap:6px;margin-bottom:4px;font-size:10px;">
<select id="sasort" onchange="lsa()" style="padding:2px 4px;font-size:9px;"><option value="time">时间</option><option value="ic">IC</option><option value="excess">年化收益</option><option value="sharpe">Sharpe</option><option value="fitness">Fitness</option></select>
<button onclick="lsa('asc')" style="padding:2px 6px;font-size:9px;background:#1c2533;color:#8b949e;border:1px solid #30363d;border-radius:3px;" id="saord">降序</button>
<button onclick="lsa()" style="padding:2px 6px;font-size:9px;background:#1c2533;color:#58a6ff;border:1px solid #30363d;border-radius:3px;">加载历史</button>
</div>
<div id="salist" style="max-height:160px;overflow-y:auto;font-size:10px;margin-bottom:4px;"></div>
<div style="font-size:10px;color:#8b949e;">已选 <span id="sacnt">0</span> 个</div>
<button id="sago" onclick="rsa()" disabled style="padding:5px 12px;background:#f0883e;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:10px;margin-top:4px;">等权组合回测</button>
<div id="sares" style="margin-top:6px;font-size:10px;"></div></div>

</div>
<script>
var Chart=null;
(function(){var s=document.createElement("script");s.src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js";s.onload=function(){console.log("Chart OK")};s.onerror=function(){console.log("No Chart")};document.head.appendChild(s);})();

var _pc=null,_sd=null,sh=[],ss=[],sasort="time",saord="desc";
function $(id){return document.getElementById(id);}
function fg(e){$("expr").value=e;go();}
function sm(d){
 _sd=d;
 function s(id,fmt,v,m){try{$(id).textContent=fmt((v||0)*(m||1));}catch(e){}}
 s("m-excess",function(v){return v.toFixed(2)+"%";},d.annual_excess,100);
 s("m-ic",function(v){return v.toFixed(4);},d.pearson_ic,1);
 s("m-sharpe",function(v){return v.toFixed(2);},d.sharpe,1);
 s("m-fitness",function(v){return v.toFixed(2);},d.fitness,1);
 s("m-turnover",function(v){return v.toFixed(1)+"%";},d.turnover,100);
 s("m-dd",function(v){return v.toFixed(2)+"%";},d.max_drawdown,100);
 s("m-margin",function(v){return v.toFixed(1);},d.margin_bps,1);
 s("m-winrate",function(v){return v.toFixed(1)+"%";},d.win_rate,100);
 if(typeof Chart!=="undefined"&&d.pnl_series&&d.pnl_series.length){
  try{var ctx=$("pnl");if(ctx){if(_pc)_pc.destroy();_pc=new Chart(ctx.getContext("2d"),{type:"line",data:{labels:d.pnl_series.map(function(_,i){return i+1;}),datasets:[{label:"PnL",data:d.pnl_series,borderColor:"#3fb950",borderWidth:2,pointRadius:0,fill:true,backgroundColor:"rgba(63,185,80,0.1)"}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}});}}catch(e){}}
}
async function go(){
 $("err").style.display="none";
 var v=$("expr").value.trim();if(!v){$("err").textContent="请输入表达式";$("err").style.display="block";return;}
 var b=$("btn");b.textContent="回测中...";b.disabled=true;
 $("prog").style.display="block";$("prog").firstChild.style.width="30%";
 try{
  var r=await fetch("/api/backtest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expression:v,neutralize:$("neut").value})});
  $("prog").firstChild.style.width="80%";var d=await r.json();
  $("prog").style.display="none";b.textContent="回 测";b.disabled=false;
  if(d.error){$("err").textContent=d.error;$("err").style.display="block";return;}
  sm(d);
 }catch(x){$("prog").style.display="none";b.textContent="回 测";b.disabled=false;$("err").textContent="失败: "+x.message;$("err").style.display="block";}
}
async function lsa(ord){
 if(ord==="asc")saord="asc";else saord=saord==="desc"?"asc":"desc";
 $("saord").textContent=saord==="asc"?"升序":"降序";
 $("salist").innerHTML='<div style="color:#8b949e;padding:4px;">加载中...</div>';
 try{var r=await fetch("/api/alpha/history");var d=await r.json();sh=d.records||[];
  sh.sort(function(a,b){var am=a.metrics||{},bm=b.metrics||{},va,vb;var sv=$("sasort").value;
   if(sv==="ic"){va=am.pearson_ic||0;vb=bm.pearson_ic||0;}
   else if(sv==="excess"){va=am.annual_excess||0;vb=bm.annual_excess||0;}
   else if(sv==="sharpe"){va=am.sharpe||0;vb=bm.sharpe||0;}
   else if(sv==="fitness"){va=am.fitness||0;vb=bm.fitness||0;}
   else{va=a.timestamp||"";vb=b.timestamp||"";}
   return saord==="asc"?va-vb:vb-va;});
  var h="";for(var i=0;i<sh.length;i++){var a=sh[i],m=a.metrics||{};
   h+='<label style="display:flex;align-items:center;gap:4px;padding:3px 4px;cursor:pointer;border-bottom:1px solid #1c2533;font-size:9px;"><input type="checkbox" onchange="tsa('+i+',this.checked)"><span style="font-family:monospace;color:#58a6ff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+(a.name||a.expression||"").substring(0,25)+'</span><span style="color:#8b949e;">IC:'+((m.pearson_ic||0).toFixed(3))+' R:'+((m.annual_excess||0)*100).toFixed(1)+'%</span></label>';}
  $("salist").innerHTML=h||'<div style="color:#8b949e;padding:4px;">暂无</div>';}
 catch(e){$("salist").innerHTML='<div style="color:#ff6b6b;padding:4px;">失败</div>';}
}
function tsa(i,c){if(c){if(ss.length>=5){alert("最多5个");return false;}ss.push(i);}else{ss=ss.filter(function(x){return x!==i;});}$("sacnt").textContent=ss.length;$("sago").disabled=ss.length<2;}
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
  if(typeof Chart!=="undefined"&&cm.pnl_series&&cm.pnl_series.length){
   var allPnl=cm.pnl_series;var colors=["#e6b422","#58a6ff","#3fb950","#e94560","#f0883e"];
   h+='<div style="margin-top:8px;border-top:1px solid #30363d;padding-top:6px;"><canvas id="sapnl" style="height:180px;"></canvas></div>';
   $("sares").innerHTML=h;
   setTimeout(function(){var ctx=document.getElementById("sapnl");if(ctx){var ds=[{label:"Combined",data:allPnl,borderColor:"#fff",borderWidth:3,pointRadius:0}];(d.sub_alphas||d.alphas||[]).forEach(function(sa,i){if(sa.pnl_series&&sa.pnl_series.length)ds.push({label:(sa.expression||"").substring(0,15),data:sa.pnl_series,borderColor:colors[i%5],borderWidth:1,pointRadius:0});});new Chart(ctx.getContext("2d"),{type:"line",data:{labels:allPnl.map(function(_,i){return i+1;}),datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"top",labels:{color:"#8b949e",fontSize:9,boxWidth:10}}},scales:{x:{display:false},y:{grid:{color:"#30363d"}}}});}},100);return;}
  $("sares").innerHTML=h;}
 catch(e){$("sares").innerHTML='<span style="color:#ff6b6b;">失败</span>';}
}
</script>
</body></html>"""
with open(os.path.join(BASE, 'templates', 'dashboard.html'), 'w', encoding='utf-8') as f:f.write(h)
print('Dashboard written OK:',len(h),'bytes')
