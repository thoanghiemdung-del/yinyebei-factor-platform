import os
BASE = os.path.dirname(os.path.abspath(__file__))
"""Build full-featured dashboard from v2 base — add tabs, SA, guide."""

with open(os.path.join(BASE, 'templates', 'dashboard_v2.html'), 'r', encoding='utf-8') as f:
    base = f.read()

# Extract the JS function and CSS from v2
import re
js_match = re.search(r'<script>\s*(.*?)\s*</script>', base, re.DOTALL)
base_js = js_match.group(1)

# Build full dashboard HTML
html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<title>量化回测仪表盘</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei",sans-serif;background:#0d1117;color:#c9d1d9}
.hdr{background:#161b22;border-bottom:1px solid #30363d;padding:10px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}
.hdr h1{color:#e94560;font-size:16px}
.hdr nav{display:flex;gap:20px}
.hdr nav a{color:#8b949e;text-decoration:none;font-size:12px}
.hdr nav a:hover{color:#58a6ff}
.ctn{max-width:1200px;margin:0 auto;padding:16px}
.lay{display:flex;gap:16px}
.main{flex:1;min-width:0}
.right{width:380px;flex-shrink:0;font-size:11px;line-height:1.7}
.tabs{display:flex;gap:2px;margin-bottom:0}
.tab{padding:6px 14px;background:#161b22;border:1px solid #30363d;border-radius:6px 6px 0 0;cursor:pointer;font-size:11px;color:#8b949e}
.tab.on{background:#111820;color:#e94560;border-color:#e94560;border-bottom-color:#111820;font-weight:bold}
.pnl{background:#111820;border:1px solid #30363d;border-radius:0 6px 6px 6px;padding:12px;margin-bottom:12px;display:none}
.pnl.on{display:block}
.row{display:flex;gap:6px;margin-bottom:8px}
.row input{flex:1;padding:7px 9px;background:#161b22;border:1px solid #30363d;border-radius:4px;color:#fff;font-size:12px}
.row select{padding:7px 9px;background:#161b22;border:1px solid #30363d;border-radius:4px;color:#fff;font-size:11px}
.row .rbtn{padding:7px 14px;background:#e94560;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px}
.row .rbtn:disabled{background:#555}
.row .sbtn{padding:7px 14px;background:#ff6b6b;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;display:none}
.prog{height:3px;background:#30363d;border-radius:2px;margin-bottom:6px;overflow:hidden;display:none}
.prog div{height:100%;background:#58a6ff;width:0;transition:width 0.3s}
.err{color:#ff6b6b;font-size:10px;margin-bottom:6px;display:none}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px}
.card{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px;text-align:center}
.card .v{font-size:18px;font-weight:bold;color:#58a6ff}
.card .l{font-size:9px;color:#8b949e;margin-top:1px}
.card.g .v{color:#3fb950}
.ex{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:8px}
.ex h3{color:#8b949e;font-size:10px;margin-bottom:4px}
.ex code{display:inline-block;padding:2px 5px;margin:2px;color:#58a6ff;font-size:9px;cursor:pointer;background:#1c2533;border-radius:2px}
.ex code:hover{color:#e94560}
.sabox{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:10px;margin-top:10px}
.sabox h3{color:#f0883e;font-size:11px;margin-bottom:4px}
.guide h2{color:#e94560;font-size:12px;margin-bottom:4px;padding-bottom:2px;border-bottom:1px solid #30363d}
.guide h3{color:#f0883e;font-size:10px;margin:6px 0 3px}
.guide p,.guide li{font-size:10px;color:#8b949e;line-height:1.6}
.guide table{width:100%;border-collapse:collapse;margin:4px 0;font-size:9px}
.guide th{background:#1c2533;padding:2px 5px;text-align:left;color:#58a6ff}
.guide td{padding:2px 5px;border-bottom:1px solid #1c2533}
.guide code{background:#1c2533;padding:1px 2px;border-radius:2px;color:#58a6ff;font-size:9px}
</style>
</head>
<body>
<div class="hdr"><h1>量化回测</h1>
<nav><a href="/dashboard">仪表盘</a><a href="/alpha_history">Alpha历史</a><a href="/compare">对比</a><a href="/data_fields">字段</a><a href="/operators">操作符</a><a href="/community">社区</a><a href="/learn">学习</a></nav>
<span style="font-size:11px;color:#8b949e">{{ username }} | <a href="/logout" style="color:#8b949e">退出</a></span></div>
<div class="ctn"><div class="lay"><div class="main">

<div class="tabs">
  <div class="tab on" id="tab-0" onclick="st(0)">回测 #1</div>
  <div class="tab" id="tab-1" onclick="st(1)">回测 #2</div>
  <div class="tab" id="tab-2" onclick="st(2)">回测 #3</div>
</div>

<div class="pnl on" id="pnl-0">
  <div class="row"><input type="text" id="e-0" placeholder="输入表达式" value="rank(ts_delta(close, 20))"><select id="n-0"><option value="none">无中性化</option><option value="market_cap">市值中性化</option></select><button class="rbtn" id="b-0" onclick="go(0)">回 测</button><button class="sbtn" id="s-0" onclick="stop(0)">停止</button></div>
  <div class="prog" id="p-0"><div></div></div><div class="err" id="er-0"></div>
</div>
<div class="pnl" id="pnl-1">
  <div class="row"><input type="text" id="e-1" placeholder="输入表达式"><select id="n-1"><option value="none">无中性化</option><option value="market_cap">市值中性化</option></select><button class="rbtn" id="b-1" onclick="go(1)">回 测</button><button class="sbtn" id="s-1" onclick="stop(1)">停止</button></div>
  <div class="prog" id="p-1"><div></div></div><div class="err" id="er-1"></div>
</div>
<div class="pnl" id="pnl-2">
  <div class="row"><input type="text" id="e-2" placeholder="输入表达式"><select id="n-2"><option value="none">无中性化</option><option value="market_cap">市值中性化</option></select><button class="rbtn" id="b-2" onclick="go(2)">回 测</button><button class="sbtn" id="s-2" onclick="stop(2)">停止</button></div>
  <div class="prog" id="p-2"><div></div></div><div class="err" id="er-2"></div>
</div>

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
<code onclick="fg('ts_delta(close, 60) / (ts_std(close/open-1, 60) + 0.001)')">夏普比</code>
<code onclick="fg('close / open - 1')">日内收益</code>
</div>

<div class="sabox"><h3>SuperAlpha - 从Alpha历史选取组合</h3>
<button id="saload" onclick="lsa()" style="padding:4px 10px;background:#1c2533;color:#58a6ff;border:1px solid #30363d;border-radius:3px;cursor:pointer;font-size:10px">加载历史</button>
<div id="salist" style="margin-top:4px;max-height:150px;overflow-y:auto;font-size:10px"></div>
<div style="font-size:10px;color:#8b949e;margin-top:3px">已选 <span id="sacnt">0</span> 个</div>
<button id="sago" onclick="rsa()" disabled style="margin-top:4px;padding:5px 12px;background:#f0883e;color:#fff;border:none;border-radius:3px;cursor:pointer;font-size:10px">等权组合回测</button>
<div id="sares" style="margin-top:6px;font-size:10px"></div></div>

</div><div class="right guide">
<h2>快速上手</h2><p>输入表达式→点<b>回测</b>→等~10秒→指标更新。3个标签页可同时跑不同因子。</p>
<h2>字段</h2><table><tr><th>字段</th><th>含义</th></tr><tr><td><code>close</code></td><td>收盘价</td></tr><tr><td><code>open</code></td><td>开盘价</td></tr><tr><td><code>high/low</code></td><td>最高/最低价</td></tr><tr><td><code>volume</code></td><td>成交量</td></tr><tr><td><code>amount</code></td><td>成交额</td></tr></table>
<h2>算子</h2><table><tr><th>语法</th><th>含义</th></tr><tr><td><code>rank(x)</code></td><td>截面排名百分位</td></tr><tr><td><code>ts_delta(x,d)</code></td><td>x[t]-x[t-d]</td></tr><tr><td><code>ts_mean(x,d)</code></td><td>d日滚动均值</td></tr><tr><td><code>ts_std(x,d)</code></td><td>d日标准差</td></tr><tr><td><code>ts_corr(x,y,d)</code></td><td>x,y相关系数</td></tr><tr><td><code>signed_power(x,e)</code></td><td>sign(x)*|x|^e</td></tr><tr><td><code>-</code>负号</td><td>反转排名方向</td></tr></table>
<h2>指标</h2><table><tr><th>指标</th><th>含义/阈值</th></tr><tr><td>年化收益</td><td>Top10%-市场均值×250</td></tr><tr><td>Pearson IC</td><td>因子与收益相关 >0.03好</td></tr><tr><td>Sharpe</td><td>超额收益/波动 >1.0好</td></tr><tr><td>Fitness</td><td>综合评分(含换手)</td></tr><tr><td>Turnover</td><td>日换手率 <20%正常</td></tr><tr><td>最大回撤</td><td>累计最大跌幅 <50%</td></tr></table>
</div></div></div>

<script>
var sl=0,sd=[null,null,null],sh=[],ss=[];
function $(id){return document.getElementById(id);}
function st(i){sl=i;for(var j=0;j<3;j++){$("tab-"+j).classList.toggle("on",j===i);$("pnl-"+j).classList.toggle("on",j===i);}if(sd[i])sm(sd[i]);}
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
async function lsa(){
  $("salist").innerHTML='<div style="color:#8b949e;padding:4px;">加载中...</div>';
  try{var r=await fetch("/api/alpha/history");var d=await r.json();sh=d.records||[];var h="";
    for(var i=0;i<sh.length;i++){var a=sh[i],m=a.metrics||{};
      h+='<label style="display:flex;align-items:center;gap:4px;padding:3px 4px;cursor:pointer;border-bottom:1px solid #1c2533;font-size:9px;"><input type="checkbox" onchange="tsa('+i+',this.checked)"><span style="font-family:monospace;color:#58a6ff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+(a.name||a.expression||"").substring(0,30)+'</span><span style="color:#8b949e;">IC:'+((m.pearson_ic||0).toFixed(3))+'</span></label>';}
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
    var h='<div style="color:#3fb950;font-weight:bold;margin-bottom:2px;">组合 IC='+(cm.pearson_ic||0).toFixed(4)+" 收益="+((cm.annual_excess||0)*100).toFixed(2)+"%</div><table style=\"font-size:9px;\"><tr><th>Alpha</th><th>IC</th><th>收益</th></tr>";
    (d.sub_alphas||d.alphas||[]).forEach(function(sa,i){var m=sa.metrics||sa||{},nm=(sa.expression||"").substring(0,20);h+='<tr><td style="font-family:monospace;color:#58a6ff;">'+nm+'</td><td style="color:'+((m.pearson_ic||0)>=0?"#3fb950":"#ff6b6b")+';">'+(m.pearson_ic||0).toFixed(4)+'</td><td>'+((m.annual_excess||0)*100).toFixed(2)+"%</td></tr>";});
    h+="</table>";$("sares").innerHTML=h;}
  catch(e){$("sares").innerHTML='<span style="color:#ff6b6b;">失败</span>';}
}
</script>
</body></html>'''

with open(os.path.join(BASE, 'templates', 'dashboard.html'), 'w', encoding='utf-8') as f:
    f.write(html)

# Verify
with open(os.path.join(BASE, 'templates', 'dashboard.html'), 'r', encoding='utf-8') as f:
    c = f.read()
print(f'Dashboard: {len(c)} bytes')
print(f'  Tabs: {"tab-0" in c and "tab-1" in c}')
print(f'  SA: {"saload" in c and "rsa" in c}')
print(f'  Guide: {"快速上手" in c}')
print(f'  CDN: {"chart.js" not in c.lower()}')
