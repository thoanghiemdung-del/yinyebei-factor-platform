"""Build full dashboard: 3 tabs, tutorial sidebar, session persistence, SA, AI."""
import os
DST = os.path.join(os.path.dirname(__file__), 'templates', 'dashboard.html')

HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<title>量化回测仪表盘</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9}
.header{background:#161b22;border-bottom:1px solid #30363d;padding:8px 20px;display:flex;justify-content:center;align-items:center;position:sticky;top:0;z-index:100;gap:40px}
.header h1{color:#e94560;font-size:16px;margin-right:auto}
.header nav{display:flex;gap:20px}
.header nav a{color:#8b949e;text-decoration:none;font-size:11px;white-space:nowrap}
.header nav a:hover{color:#58a6ff}
.layout{display:flex;height:calc(100vh - 41px)}
.main{flex:1;overflow-y:auto;padding:16px;min-width:0}
.sidebar{width:340px;overflow-y:auto;padding:14px;background:#111820;border-left:1px solid #30363d;font-size:11px;line-height:1.7}
.sidebar h3{color:#f0883e;font-size:12px;margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid #30363d}
.sidebar section{margin-bottom:18px}
.sidebar p{font-size:11px;color:#8b949e;margin:4px 0}
.sidebar code{background:#1c2533;padding:1px 4px;border-radius:3px;color:#58a6ff;font-size:10px}
.sidebar .tip{background:rgba(240,136,62,0.08);border-left:3px solid #f0883e;padding:6px 10px;margin:6px 0;font-size:10px;color:#f0883e}
.tab-bar{display:flex;gap:0;margin-bottom:12px;border-bottom:1px solid #30363d}
.tab-btn{padding:8px 20px;background:none;border:none;color:#8b949e;cursor:pointer;font-size:12px;border-bottom:2px solid transparent}
.tab-btn:hover{color:#c9d1d9}
.tab-btn.active{color:#e94560;border-bottom-color:#e94560}
.tab-content{display:none}
.tab-content.active{display:block}
.input-row{display:flex;gap:8px;margin-bottom:10px;position:relative}
.input-row textarea{flex:1;padding:9px 10px;background:#161b22;border:1px solid #30363d;border-radius:6px;color:#fff;font-size:13px;resize:vertical;min-height:60px;height:60px;font-family:monospace}
.input-row select{padding:9px 10px;background:#161b22;border:1px solid #30363d;border-radius:6px;color:#fff;font-size:12px}
.input-row button{padding:9px 16px;background:#e94560;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;white-space:nowrap}
.input-row button:hover{background:#d63850}
.input-row button:disabled{background:#555}
.ac-dropdown{display:none;position:absolute;top:100%;left:0;right:0;z-index:99;background:#161b22;border:1px solid #58a6ff;border-radius:0 0 6px 6px;max-height:240px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,0.5)}
.ac-dropdown.show{display:block}
.ac-item{padding:6px 10px;cursor:pointer;font-size:11px;border-bottom:1px solid #1c2533;display:flex;justify-content:space-between}
.ac-item:hover,.ac-item.sel{background:#1c2533}
.ac-item .name{font-family:monospace;color:#58a6ff;font-size:12px}
.ac-item .desc{color:#8b949e;font-size:10px;text-align:right}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;text-align:center}
.card .val{font-size:22px;font-weight:bold;color:#58a6ff}
.card .lbl{font-size:9px;color:#8b949e;margin-top:3px}
.card.up .val{color:#e94560}
.chart-box{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px;margin-bottom:12px;overflow:hidden;min-width:0}
.chart-box h3{font-size:10px;color:#8b949e;margin-bottom:6px}
.chart-box canvas{width:100%!important;height:180px!important;max-width:100%}
.sa-section{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin-bottom:12px}
.sa-section h3{font-size:11px;color:#8b949e;margin-bottom:8px}
.sa-controls{display:flex;gap:6px;align-items:center;margin-bottom:8px;flex-wrap:wrap}
.sa-controls button{padding:5px 10px;background:#1c2533;color:#58a6ff;border:1px solid #30363d;border-radius:4px;cursor:pointer;font-size:10px}
.sa-controls button:hover{background:#30363d}
.sa-controls button.primary{background:#f0883e;color:#fff;border-color:#f0883e}
.sa-controls button.primary:disabled{background:#555;color:#888}
#sa-select-list{max-height:180px;overflow-y:auto;font-size:10px;margin-bottom:6px}
#sa-select-list label{display:flex;align-items:center;gap:6px;padding:4px 6px;cursor:pointer;border-bottom:1px solid #1c2533}
#sa-select-list label:hover{background:#1c2533}
#sa-result{margin-top:8px;font-size:10px}
.sa-sub-item{cursor:pointer;padding:6px 8px;background:#0d1117;border:1px solid #1c2533;border-radius:4px;margin:4px 0}
.sa-sub-item:hover{border-color:#58a6ff}
.sa-sub-detail{display:none;padding:8px;background:#0d1117;border:1px solid #1c2533;border-radius:4px;margin:4px 0}
.sa-sub-detail.open{display:block}
.example-box{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin-top:10px}
.example-box h3{color:#8b949e;font-size:10px;margin-bottom:6px}
.example-box code{display:inline-block;padding:2px 6px;margin:2px;color:#58a6ff;font-size:10px;cursor:pointer;background:#1c2533;border-radius:3px}
.example-box code:hover{color:#e94560}
@media(max-width:900px){.layout{flex-direction:column}.sidebar{width:100%;border-left:none;border-top:1px solid #30363d}}
.ai-float{position:fixed;bottom:20px;right:20px;z-index:999}
.ai-btn{width:48px;height:48px;border-radius:50%;background:#a855f7;color:#fff;border:none;cursor:pointer;font-size:20px;box-shadow:0 2px 12px rgba(168,85,247,0.4)}
.ai-panel{display:none;position:fixed;bottom:80px;right:20px;width:420px;min-width:300px;max-width:90vw;height:400px;min-height:250px;max-height:80vh;background:#161b22;border:1px solid #a855f7;border-radius:10px;z-index:999;flex-direction:column;overflow:hidden;resize:both}
.ai-panel.open{display:flex}
.ai-head{background:#a855f7;padding:8px 14px;color:#fff;font-size:12px;font-weight:bold;display:flex;justify-content:space-between}
.ai-head button{background:none;border:none;color:#fff;cursor:pointer;font-size:16px}
.ai-body{flex:1;overflow-y:auto;padding:10px;font-size:11px}
.ai-msg{margin-bottom:8px;padding:6px 10px;border-radius:6px;max-width:85%;white-space:pre-wrap;word-break:break-all}
.ai-msg.user{align-self:flex-end;background:#1c2533;color:#c9d1d9}
.ai-msg.bot{align-self:flex-start;background:#0d1117;color:#58a6ff;font-family:monospace;border:1px solid #30363d}
.ai-input{display:flex;border-top:1px solid #30363d}
.ai-input input{flex:1;padding:8px 12px;background:#0d1117;border:none;color:#fff;font-size:11px;outline:none}
.ai-input button{padding:8px 14px;background:#a855f7;color:#fff;border:none;cursor:pointer;font-size:11px}
</style>
</head>
<body>
<div class="header">
  <h1>量化回测</h1>
  <nav><a href="/dashboard">仪表盘</a><a href="/alpha_history">Alpha历史</a><a href="/data_fields">数据字段</a><a href="/operators">操作符</a><a href="/correlation">相关性</a><a href="/community">社区</a><a href="/learn">学习</a><a href="/logout">退出</a></nav>
</div>
<div class="layout">
<div class="main">

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab(0)">回测 1</button>
  <button class="tab-btn" onclick="switchTab(1)">回测 2</button>
  <button class="tab-btn" onclick="switchTab(2)">回测 3</button>
</div>

<div id="tabs-container"></div>

<div class="sa-section">
  <h3>SuperAlpha — 从 Alpha 历史选取等权组合</h3>
  <div class="sa-controls">
    <button onclick="loadSAHistory()">加载历史</button>
    <span style="font-size:10px;color:#8b949e">已选 <strong id="sa-count">0</strong></span>
    <select id="sa-neut"><option value="market_cap">市值中性化</option><option value="none">无中性化</option></select>
    <button onclick="loadSAHistory('excess','desc')" style="font-size:9px">收益▼</button><button onclick="loadSAHistory('excess','asc')" style="font-size:9px">收益▲</button>
    <button onclick="loadSAHistory('ic','desc')" style="font-size:9px">IC▼</button><button onclick="loadSAHistory('ic','asc')" style="font-size:9px">IC▲</button>
    <button class="primary" id="sa-run-btn" onclick="runSAFromHistory()" disabled>等权组合回测</button>
    <button class="primary" id="sa-lgb-btn" onclick="runLGB()" disabled style="background:#a855f7;border-color:#a855f7">LightGBM训练</button>
    <span style="font-size:9px;color:#484f58;white-space:nowrap">SA≈30s LGB≈60s</span>
    <button onclick="preloadMinute()" style="font-size:9px;background:#1c2533;color:#f0883e;border:1px solid #f0883e;padding:5px 8px;cursor:pointer" title="预加载分钟数据，之后所有分钟字段秒出">预载分钟</button>
  </div>
  <div id="sa-select-list"></div>
  <div id="sa-result"></div>
</div>

<div class="example-box">
  <h3>示例（点击填充到当前Tab）</h3>
  <code onclick="fillActiveTab(this)">rank(ts_delta(close,20))</code>
  <code onclick="fillActiveTab(this)">-rank(ts_sum(close/open-1,5))</code>
  <code onclick="fillActiveTab(this)">rank(ts_mean(volume,5)/ts_mean(volume,20))</code>
  <code onclick="fillActiveTab(this)">rank(ts_std(close/open-1,20))</code>
  <code onclick="fillActiveTab(this)">rank(ret_20d)</code>
  <code onclick="fillActiveTab(this)">-rank(returns)</code>
  <code onclick="fillActiveTab(this)">rank(vwap_gap)</code>
  <code onclick="fillActiveTab(this)">group_neutralize(rank(ts_delta(close,5)),market_cap)</code>
</div>

</div>

<div class="sidebar">
  <h3>量化回测平台教程</h3>
  <section>
    <p><strong style="color:#a855f7">AI助手:</strong> 右下角紫色 <code>?</code> — 表达式写法、字段选择、指标含义，不懂就问AI。支持多轮对话记忆。</p>
  </section>
  <section>
    <p><strong style="color:#58a6ff">1. 快速开始</strong></p>
    <p>输入 <code>rank(ts_delta(close,20))</code> 点回测。试试 <code>-rank(returns)</code>（反转）、<code>rank(ret_20d)</code>（动量）、<code>rank(vwap_gap)</code>（VWAP偏离）。</p>
    <p style="color:#484f58;font-size:10px;">预估: 普通~10s / SA组合~30s / LGB训练~60s。首次用分钟字段(vwap等)约3min加载数据。</p>
  </section>
  <section>
    <p><strong style="color:#58a6ff">2. 理解指标</strong></p>
    <p>IC>0.03可用 >0.05优秀 | Sharpe>1.0 | Fitness>1.0 | 回撤<5% | 胜率>51%</p>
  </section>
  <section>
    <p><strong style="color:#58a6ff">3. 122字段 / 28操作符</strong></p>
    <p>详: <a href="/operators" style="color:#58a6ff">操作符</a> | <a href="/data_fields" style="color:#58a6ff">字段百科</a> | <a href="/learn" style="color:#58a6ff">学习页</a></p>
  </section>
  <section>
    <p><strong style="color:#58a6ff">4. SuperAlpha组合</strong></p>
    <p><strong>等权:</strong> 勾选因子→zscore标准化→等权平均→PnL叠加对比各因子贡献。</p>
    <p><strong>LightGBM:</strong> 非线性集成→自动学因子交互→比赛最终因子。</p>
  </section>
  <div class="tip">CSI800 / 2020-2023 / Top10%纯多头超额 / 5日标签。多行支持: returns=close/open-1; returns+1</div>
</div>
</div>

<div class="ai-float">
  <button class="ai-btn" onclick="toggleAI()" title="AI助手">?</button>
  <div class="ai-panel" id="ai-panel">
    <div class="ai-head">平台AI助手 <button onclick="clearAI()" style="font-size:10px;margin-right:8px">清记忆</button><button onclick="toggleAI()">&times;</button></div>
    <div class="ai-body" id="ai-body"><div class="ai-msg bot">你好！可问代码、计算逻辑、字段等问题。</div></div>
    <div class="ai-input"><input type="text" id="ai-input" placeholder="输入问题..." onkeydown="if(event.key==='Enter')askAI()"><button onclick="askAI()">发送</button></div>
  </div>
</div>

<script>
(function loadChartJS(){if(typeof Chart!=="undefined")return;var s=document.createElement("script");s.src="/static/chart.umd.min.js";s.onerror=function(){console.warn("Chart.js unavailable");};document.head.appendChild(s);})();

function byId(id){return document.getElementById(id);}
function escAttr(s){return(s||"").replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

var TAB_COUNT=3,activeTab=0,tabs=[];
function initTabs(){
  var saved=null;
  try{saved=JSON.parse(localStorage.getItem("dash_tabs"));console.log("localStorage:",saved?"已恢复":"无存档");}catch(e){console.log("localStorage错误:",e);}
  for(var i=0;i<TAB_COUNT;i++){
    var hasResult=saved&&saved[i]&&saved[i].result&&saved[i].result.pearson_ic!=null;
    var t=hasResult?{expr:saved[i].expr,neut:saved[i].neut,result:saved[i].result,pnl:saved[i].pnl||[],ic:saved[i].ic||[]}:{expr:"rank(ts_delta(close, 20))",neut:"market_cap",result:null,pnl:[],ic:[]};
    t.chartPnl=null;tabs.push(t);
  }
  if(saved&&saved.activeTab!=null)activeTab=saved.activeTab;
  renderAllTabs();switchTab(activeTab);
  // Only draw chart for active tab (visible canvas)
  if(tabs[activeTab].result)setTimeout(function(){drawChartsForTab(activeTab);},300);
}
function saveTabs(){
  var data={activeTab:activeTab,tabs:[]};
  for(var i=0;i<TAB_COUNT;i++){
    var t=tabs[i];
    data.tabs.push({expr:t.expr,neut:t.neut,result:t.result?{pearson_ic:t.result.pearson_ic,annual_excess:t.result.annual_excess,returns:t.result.returns,sharpe:t.result.sharpe,fitness:t.result.fitness,turnover:t.result.turnover,max_drawdown:t.result.max_drawdown,margin_bps:t.result.margin_bps,win_rate:t.result.win_rate}:null,pnl:t.pnl,ic:t.ic});
  }
  try{localStorage.setItem("dash_tabs",JSON.stringify(data));}catch(e){console.log("saveTabs错误:",e);}
}
function renderAllTabs(){
  var h='';
  for(var i=0;i<TAB_COUNT;i++){
    var t=tabs[i];
    h+='<div class="tab-content'+(i===activeTab?' active':'')+'" id="tab-'+i+'">';
    h+='<div class="input-row">';
    h+='<textarea id="expr-'+i+'" placeholder="输入因子表达式 支持多行" oninput="acFilter('+i+',this.value)" onkeydown="acKey('+i+',event)" onfocus="acFilter('+i+',this.value)" onblur="setTimeout(function(){acHide('+i+')},200)">'+escAttr(t.expr)+'</textarea>';
    h+='<select id="neut-'+i+'"><option value="market_cap"'+(t.neut==="market_cap"?" selected":"")+'>市值中性化</option><option value="none"'+(t.neut==="none"?" selected":"")+'>无中性化</option></select>';
    h+='<button id="btn-'+i+'" onclick="go('+i+')">回 测</button>';
    h+='<span style="font-size:9px;color:#484f58;white-space:nowrap;margin-left:4px">约10s</span>';
    h+='<div class="ac-dropdown" id="ac-'+i+'"></div>';
    h+='</div>';
    h+='<div id="progress-'+i+'" style="height:3px;background:#30363d;border-radius:2px;margin-bottom:8px;overflow:hidden;display:none"><div style="height:100%;background:#58a6ff;width:0"></div></div>';
    h+='<div id="error-'+i+'" style="color:#ff6b6b;font-size:11px;margin-bottom:8px;display:none"></div>';
    h+='<div class="metrics">';
    h+='<div class="card up"><div class="val" id="ex-'+i+'">--</div><div class="lbl">年化收益</div></div>';
    h+='<div class="card"><div class="val" id="ic-'+i+'">--</div><div class="lbl">Pearson IC</div></div>';
    h+='<div class="card"><div class="val" id="sh-'+i+'">--</div><div class="lbl">Sharpe</div></div>';
    h+='<div class="card"><div class="val" id="ft-'+i+'">--</div><div class="lbl">Fitness</div></div>';
    h+='<div class="card"><div class="val" id="to-'+i+'">--</div><div class="lbl">Turnover</div></div>';
    h+='<div class="card"><div class="val" id="dd-'+i+'">--</div><div class="lbl">最大回撤</div></div>';
    h+='<div class="card"><div class="val" id="mg-'+i+'">--</div><div class="lbl">Margin(bps)</div></div>';
    h+='<div class="card"><div class="val" id="wr-'+i+'">--</div><div class="lbl">日胜率</div></div>';
    h+='</div>';
    h+='<div class="chart-box" id="chartbox-'+i+'" style="display:none"><h3>PnL 累积收益曲线</h3><canvas id="pnl-'+i+'"></canvas></div>';
    h+='</div>';
  }
  byId("tabs-container").innerHTML=h;
  for(var i=0;i<TAB_COUNT;i++){if(tabs[i].result)updateCards(i,tabs[i].result);}
}
function switchTab(i){activeTab=i;
  var btns=document.querySelectorAll(".tab-btn");for(var j=0;j<btns.length;j++)btns[j].classList.toggle("active",j===i);
  var contents=document.querySelectorAll(".tab-content");for(var j=0;j<contents.length;j++)contents[j].classList.toggle("active",j===i);
  saveTabs();
  if(tabs[i].result&&!tabs[i].chartPnl)drawChartsForTab(i);}
function fillActiveTab(el){byId("expr-"+activeTab).value=el.textContent;}

async function go(i){
  var errEl=byId("error-"+i);errEl.style.display="none";
  var v=byId("expr-"+i).value.trim();if(!v){errEl.textContent="请输入表达式";errEl.style.display="block";return;}
  tabs[i].expr=v;tabs[i].neut=byId("neut-"+i).value;
  var btn=byId("btn-"+i);btn.textContent="回测中...";btn.disabled=true;
  var prog=byId("progress-"+i);prog.style.display="block";prog.firstChild.style.width="30%";
  try{
    var r=await fetch("/api/backtest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expression:v,neutralize:tabs[i].neut})});
    prog.firstChild.style.width="80%";
    var d=await r.json();
    prog.style.display="none";btn.textContent="回 测";btn.disabled=false;
    if(d.error){errEl.textContent=d.error;errEl.style.display="block";return;}
    tabs[i].result=d;tabs[i].pnl=d.pnl_series||[];tabs[i].ic=d.ic_series||[];
    updateCards(i,d);drawChartsForTab(i);saveTabs();
  }catch(ex){prog.style.display="none";btn.textContent="回 测";btn.disabled=false;errEl.textContent="请求失败: "+ex.message;errEl.style.display="block";}
}
function updateCards(i,d){
  byId("ex-"+i).textContent=((d.returns||d.annual_excess||0)*100).toFixed(2)+"%";
  byId("ic-"+i).textContent=(d.pearson_ic||0).toFixed(4);
  byId("sh-"+i).textContent=(d.sharpe||0).toFixed(2);
  byId("ft-"+i).textContent=(d.fitness||0).toFixed(2);
  byId("to-"+i).textContent=((d.turnover||0)*100).toFixed(1)+"%";
  byId("dd-"+i).textContent=((d.max_drawdown||0)*100).toFixed(2)+"%";
  byId("mg-"+i).textContent=(d.margin_bps||0).toFixed(1);
  byId("wr-"+i).textContent=((d.win_rate||0)*100).toFixed(1)+"%";
}
function genDates(startY,startM,startD,n){
  var result=[],d=new Date(startY,startM-1,startD),safety=0;
  while(result.length<n&&safety<n*5){
    var w=d.getDay();if(w!==0&&w!==6)result.push(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'));
    d.setDate(d.getDate()+1);safety++;
  }
  return result;
}
function downsample(arr,targetLen){
  if(!arr||arr.length<=targetLen)return arr||[];
  var step=arr.length/targetLen,result=[];
  for(var j=0;j<targetLen;j++){var lo=Math.floor(j*step),hi=Math.floor((j+1)*step),s=0,n=0;
    for(var k=lo;k<hi&&k<arr.length;k++){if(arr[k]!=null){s+=arr[k];n++;}}
    result.push(n>0?s/n:null);}
  return result;
}
function drawChartsForTab(i){
  if(typeof Chart==="undefined"){setTimeout(function(){drawChartsForTab(i);},500);return;}
  var pnl=tabs[i].pnl;if(!pnl||pnl.length===0)return;
  var box=byId("chartbox-"+i);box.style.display="block";
  var canvas=byId("pnl-"+i);if(!canvas)return;
  if(tabs[i].chartPnl)tabs[i].chartPnl.destroy();
  var d=downsample(pnl,200);
  var dl=genDates(2020,1,2,d.length);
  tabs[i].chartPnl=new Chart(canvas.getContext("2d"),{type:"line",
    data:{labels:dl,datasets:[{label:"PnL",data:d,borderColor:"#f0883e",borderWidth:1.5,pointRadius:0,spanGaps:true,fill:true,backgroundColor:"rgba(240,136,62,0.06)"}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return 'PnL: '+ctx.raw.toFixed(2)+'%'},title:function(ctx){return ctx[0].label}}}},scales:{x:{ticks:{maxTicksLimit:8,color:'#484f58',font:{size:8}},grid:{display:false}},y:{grid:{color:"#21262d"}}}}});
}

var saHistory=[],saSelected=[];
async function loadSAHistory(sortBy,sortDir){
  var listEl=byId("sa-select-list");listEl.innerHTML='<div style="color:#8b949e;padding:8px;">加载中...</div>';
  try{
    var r=await fetch("/api/alpha/history");var d=await r.json();
    saHistory=(d.records||[]).filter(function(r){return r.type!=="superalpha";});
    if(!saHistory.length){listEl.innerHTML='<div style="color:#8b949e;padding:8px;">暂无记录</div>';return;}
    if(sortBy){saHistory.sort(function(a,b){var va,vb,am=a.metrics||{},bm=b.metrics||{};va=sortBy==="ic"?am.pearson_ic||0:am.annual_excess||0;vb=sortBy==="ic"?bm.pearson_ic||0:bm.annual_excess||0;return sortDir==="asc"?va-vb:vb-va;});}
    var h="";saHistory.forEach(function(a,i){var m=a.metrics||{};var ex=((m.annual_excess||0)*100).toFixed(1);h+='<label><input type="checkbox" onchange="toggleSA('+i+',this.checked)"'+(saSelected.indexOf(i)>=0?" checked":"")+'><span style="font-family:monospace;color:#58a6ff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+(a.name||a.expression||"").substring(0,45)+'</span><span style="color:#8b949e;font-size:9px;">IC:'+((m.pearson_ic||0).toFixed(3))+' Ex:'+ex+'%</span></label>';});
    listEl.innerHTML=h;
  }catch(e){listEl.innerHTML='<div style="color:#ff6b6b;padding:8px;">加载失败</div>';}
}
function toggleSA(i,checked){if(checked){if(saSelected.length>=50){alert("最多50个");return false;}saSelected.push(i);}else{saSelected=saSelected.filter(function(x){return x!==i;});}byId("sa-count").textContent=saSelected.length;byId("sa-run-btn").disabled=saSelected.length<2;byId("sa-lgb-btn").disabled=saSelected.length<2;}

async function runLGB(){
  if(saSelected.length<1){alert("至少选1个");return;}
  var exps=saSelected.map(function(i){return saHistory[i].expression;});
  var resEl=byId("sa-result");resEl.innerHTML='<div style="text-align:center;color:#8b949e;padding:12px;">LightGBM训练中...</div>';
  try{
    var resp=await fetch("/api/superalpha/lgb",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expressions:exps})});
    var data=await resp.json();
    if(data.error){resEl.innerHTML='<span style="color:#ff6b6b">'+data.error+'</span>';return;}
    var cm=data.metrics||{},fi=data.feature_importance||{},subs=data.sub_alphas||[],pnlRaw=cm.pnl_series;
    var h='<div style="color:#a855f7;font-weight:bold;margin-bottom:8px;">LightGBM 组合结果</div>';
    h+='<div class="metrics">';
    h+='<div class="card up"><div class="val">'+(((cm.returns||cm.annual_excess)||0)*100).toFixed(2)+'%</div><div class="lbl">年化收益</div></div>';
    h+='<div class="card"><div class="val">'+(cm.pearson_ic||0).toFixed(4)+'</div><div class="lbl">Pearson IC</div></div>';
    h+='<div class="card"><div class="val">'+(cm.sharpe||0).toFixed(2)+'</div><div class="lbl">Sharpe</div></div>';
    h+='<div class="card"><div class="val">'+(cm.fitness||0).toFixed(2)+'</div><div class="lbl">Fitness</div></div>';
    h+='<div class="card"><div class="val">'+((cm.turnover||0)*100).toFixed(1)+'%</div><div class="lbl">Turnover</div></div>';
    h+='<div class="card"><div class="val">'+((cm.max_drawdown||0)*100).toFixed(2)+'%</div><div class="lbl">最大回撤</div></div>';
    h+='<div class="card"><div class="val">'+(cm.margin_bps||0).toFixed(1)+'</div><div class="lbl">Margin(bps)</div></div>';
    h+='<div class="card"><div class="val">'+((cm.win_rate||0)*100).toFixed(1)+'%</div><div class="lbl">日胜率</div></div>';
    h+='</div>';
    // PnL overlay with sub-factors
    h+='<div class="chart-box"><h3>PnL 叠加对比</h3><canvas id="lgb-comb-pnl" style="height:200px!important"></canvas></div>';
    // Feature importance
    h+='<div style="font-size:10px;color:#8b949e;"><strong>特征重要性:</strong> ';
    var fis=[];Object.keys(fi).forEach(function(k){fis.push([k,fi[k]]);});fis.sort(function(a,b){return b[1]-a[1];});
    fis.forEach(function(p){h+=p[0].substring(0,20)+': '+(p[1]*100).toFixed(1)+'% ';});
    h+='</div>';
    resEl.innerHTML=h;
    // Sub-factor expandable cards
    if(subs.length>0){
      var subH='<div style="margin-top:6px;">';
      subs.forEach(function(sa,si){var m=sa.metrics||{},nm=(sa.expression||"").substring(0,30);
        subH+='<div class="sa-sub-item" onclick="this.nextElementSibling.classList.toggle(\'open\')"><span style="color:#a855f7;font-family:monospace;">'+nm+'</span> <span style="color:#8b949e;">IC:'+(m.pearson_ic||0).toFixed(4)+' Ex:'+(((m.returns||m.annual_excess)||0)*100).toFixed(1)+'% S:'+(m.sharpe||0).toFixed(2)+'</span></div>';
        subH+='<div class="sa-sub-detail"><div class="metrics">';
        subH+='<div class="card up"><div class="val">'+(((m.returns||m.annual_excess)||0)*100).toFixed(2)+'%</div><div class="lbl">年化收益</div></div>';
        subH+='<div class="card"><div class="val">'+(m.pearson_ic||0).toFixed(4)+'</div><div class="lbl">Pearson IC</div></div>';
        subH+='<div class="card"><div class="val">'+(m.sharpe||0).toFixed(2)+'</div><div class="lbl">Sharpe</div></div>';
        subH+='<div class="card"><div class="val">'+(m.fitness||0).toFixed(2)+'</div><div class="lbl">Fitness</div></div>';
        subH+='<div class="card"><div class="val">'+((m.turnover||0)*100).toFixed(1)+'%</div><div class="lbl">Turnover</div></div>';
        subH+='<div class="card"><div class="val">'+((m.max_drawdown||0)*100).toFixed(2)+'%</div><div class="lbl">最大回撤</div></div>';
        subH+='<div class="card"><div class="val">'+(m.margin_bps||0).toFixed(1)+'</div><div class="lbl">Margin(bps)</div></div>';
        subH+='<div class="card"><div class="val">'+((m.win_rate||0)*100).toFixed(1)+'%</div><div class="lbl">日胜率</div></div>';
        subH+='</div><div class="chart-box"><canvas id="lgb-sub-pnl-'+si+'" style="height:160px!important"></canvas></div></div>';
      });subH+='</div>';resEl.innerHTML+=subH;
    }
    // Draw charts
    if(typeof Chart!=="undefined")setTimeout(function(){
      var ctx=document.getElementById("lgb-comb-pnl");if(ctx){
        var ds=[{label:"LGB组合",data:downsample(pnlRaw,200),borderColor:"#a855f7",borderWidth:2,pointRadius:0}];
        subs.forEach(function(sa,si){var sp=sa.pnl_series;if(sp&&sp.length)ds.push({label:(sa.expression||"").substring(0,20),data:downsample(sp,200),borderColor:"hsla("+(si*120+30)+",70%,60%,0.6)",borderWidth:1,pointRadius:0});});
        new Chart(ctx.getContext("2d"),{type:"line",data:{labels:genDates(2020,1,2,ds[0].data.length),datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom",labels:{color:"#8b949e",font:{size:10},boxWidth:12}},tooltip:{callbacks:{label:function(ctx){return ctx.dataset.label+": "+ctx.raw.toFixed(2)+"%"}}}},scales:{x:{display:false},y:{grid:{color:"#21262d"}}}}});
      }
      subs.forEach(function(sa,si){var ctx2=document.getElementById("lgb-sub-pnl-"+si);if(ctx2&&sa.pnl_series)new Chart(ctx2.getContext("2d"),{type:"line",data:{labels:genDates(2020,1,2,downsample(sa.pnl_series,200).length),datasets:[{label:"PnL",data:downsample(sa.pnl_series,200),borderColor:"#f0883e",borderWidth:1.5,pointRadius:0,spanGaps:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return "PnL: "+ctx.raw.toFixed(2)+"%"},title:function(ctx){return ctx[0].label}}}},scales:{x:{ticks:{maxTicksLimit:8,color:"#484f58",font:{size:8}},grid:{display:false}},y:{grid:{color:"#21262d"}}}}});});
    },100);
  }catch(e){resEl.innerHTML='<span style="color:#ff6b6b">LightGBM失败: '+e.message+'</span>';}
}

async function runSAFromHistory(){
  if(saSelected.length<1){alert("至少选1个");return;}
  var ids=saSelected.map(function(i){return saHistory[i].id;});
  var neut=byId("sa-neut").value,resEl=byId("sa-result");
  resEl.innerHTML='<div style="text-align:center;color:#8b949e;padding:12px;">组合回测中...</div>';
  try{
    var resp=await fetch("/api/superalpha",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({alpha_ids:ids,neutralize:neut})});
    var data=await resp.json();
    if(data.error){resEl.innerHTML='<span style="color:#ff6b6b">'+data.error+'</span>';return;}
    var cm=data.combined_metrics||{},subs=data.sub_alphas||[];
    var h='<div style="color:#e94560;font-weight:bold;margin-bottom:8px;">组合结果</div>';
    h+='<div class="metrics">';
    h+='<div class="card up"><div class="val">'+(((cm.returns||cm.annual_excess)||0)*100).toFixed(2)+'%</div><div class="lbl">年化收益</div></div>';
    h+='<div class="card"><div class="val">'+(cm.pearson_ic||0).toFixed(4)+'</div><div class="lbl">Pearson IC</div></div>';
    h+='<div class="card"><div class="val">'+(cm.sharpe||0).toFixed(2)+'</div><div class="lbl">Sharpe</div></div>';
    h+='<div class="card"><div class="val">'+(cm.fitness||0).toFixed(2)+'</div><div class="lbl">Fitness</div></div>';
    h+='<div class="card"><div class="val">'+((cm.turnover||0)*100).toFixed(1)+'%</div><div class="lbl">Turnover</div></div>';
    h+='<div class="card"><div class="val">'+((cm.max_drawdown||0)*100).toFixed(2)+'%</div><div class="lbl">最大回撤</div></div>';
    h+='<div class="card"><div class="val">'+(cm.margin_bps||0).toFixed(1)+'</div><div class="lbl">Margin(bps)</div></div>';
    h+='<div class="card"><div class="val">'+((cm.win_rate||0)*100).toFixed(1)+'%</div><div class="lbl">日胜率</div></div>';
    h+='</div>';
    if(cm.pnl_series&&cm.pnl_series.length)h+='<div class="chart-box"><h3>PnL叠加对比</h3><canvas id="sa-pnl-canvas" style="height:200px!important"></canvas></div>';
    resEl.innerHTML=h;
    // Sub-factors
    var subH='<div style="margin-top:6px;">';
    subs.forEach(function(sa,si){var m=sa.metrics||{},nm=(sa.expression||"").substring(0,30);
      subH+='<div class="sa-sub-item" onclick="this.nextElementSibling.classList.toggle(\'open\')"><span style="color:#58a6ff;font-family:monospace;">'+nm+'</span> <span style="color:#8b949e;">IC:'+(m.pearson_ic||0).toFixed(4)+' Ex:'+(((m.returns||m.annual_excess)||0)*100).toFixed(1)+'% S:'+(m.sharpe||0).toFixed(2)+'</span></div>';
      subH+='<div class="sa-sub-detail"><div class="metrics">';
      subH+='<div class="card up"><div class="val">'+(((m.returns||m.annual_excess)||0)*100).toFixed(2)+'%</div><div class="lbl">年化收益</div></div>';
      subH+='<div class="card"><div class="val">'+(m.pearson_ic||0).toFixed(4)+'</div><div class="lbl">Pearson IC</div></div>';
      subH+='<div class="card"><div class="val">'+(m.sharpe||0).toFixed(2)+'</div><div class="lbl">Sharpe</div></div>';
      subH+='<div class="card"><div class="val">'+(m.fitness||0).toFixed(2)+'</div><div class="lbl">Fitness</div></div>';
      subH+='<div class="card"><div class="val">'+((m.turnover||0)*100).toFixed(1)+'%</div><div class="lbl">Turnover</div></div>';
      subH+='<div class="card"><div class="val">'+((m.max_drawdown||0)*100).toFixed(2)+'%</div><div class="lbl">最大回撤</div></div>';
      subH+='<div class="card"><div class="val">'+(m.margin_bps||0).toFixed(1)+'</div><div class="lbl">Margin(bps)</div></div>';
      subH+='<div class="card"><div class="val">'+((m.win_rate||0)*100).toFixed(1)+'%</div><div class="lbl">日胜率</div></div>';
      subH+='</div><div class="chart-box"><canvas id="sa-sub-pnl-'+si+'" style="height:160px!important"></canvas></div></div>';
    });subH+='</div>';resEl.innerHTML+=subH;
    if(typeof Chart!=="undefined")setTimeout(function(){
      var ctx=document.getElementById("sa-pnl-canvas");if(ctx){
        var pnlData=cm.pnl_series||[],ds=[{label:"组合",data:downsample(pnlData,200),borderColor:"#e94560",borderWidth:2,pointRadius:0}];
        subs.forEach(function(sa,si){var sp=sa.pnl_series;if(sp&&sp.length)ds.push({label:(sa.expression||"").substring(0,20),data:downsample(sp,200),borderColor:"hsla("+(si*120+30)+",70%,60%,0.6)",borderWidth:1,pointRadius:0});});
        new Chart(ctx.getContext("2d"),{type:"line",data:{labels:genDates(2020,1,2,ds[0].data.length),datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom",labels:{color:"#8b949e",font:{size:10},boxWidth:12}},tooltip:{callbacks:{label:function(ctx){return ctx.dataset.label+": "+ctx.raw.toFixed(2)+"%"}}}},scales:{x:{display:false},y:{grid:{color:"#21262d"}}}}});
      }
      subs.forEach(function(sa,si){var ctx2=document.getElementById("sa-sub-pnl-"+si);if(ctx2&&sa.pnl_series)new Chart(ctx2.getContext("2d"),{type:"line",data:{labels:genDates(2020,1,2,downsample(sa.pnl_series,200).length),datasets:[{label:"PnL",data:downsample(sa.pnl_series,200),borderColor:"#f0883e",borderWidth:1.5,pointRadius:0,spanGaps:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return "PnL: "+ctx.raw.toFixed(2)+"%"},title:function(ctx){return ctx[0].label}}}},scales:{x:{ticks:{maxTicksLimit:8,color:"#484f58",font:{size:8}},grid:{display:false}},y:{grid:{color:"#21262d"}}}}});});
    },100);
  }catch(e){resEl.innerHTML='<span style="color:#ff6b6b">请求失败: '+e.message+'</span>';}
}

async function preloadMinute(){
  var btn=event.target;btn.textContent="加载中...";btn.disabled=true;
  try{
    var r=await fetch("/api/backtest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expression:"vwap",neutralize:"none"})});
    var d=await r.json();
    if(d.error){btn.textContent="失败";}else{btn.textContent="已就绪";btn.style.color="#3fb950";btn.style.borderColor="#3fb950";}
  }catch(e){btn.textContent="失败";}
  setTimeout(function(){btn.disabled=false;},3000);
}

// Autocomplete
var fieldList=[],acIdx={},acCN={},acMode="fuzzy";
setTimeout(function(){
  fetch("/api/datafields").then(function(r){return r.json();}).then(function(d){var cats=d.categories||d;Object.keys(cats).forEach(function(cn){(cats[cn]||[]).forEach(function(f){fieldList.push(f.name);acIdx[f.name]=f.description||"";acCN[f.name]=f.chinese_name||"";});});});
},500);
function acFilter(i,v){if(!v||v.length<1){acHide(i);return;}var q=v.toLowerCase(),dd=byId("ac-"+i),isChinese=/[一-鿿]/.test(v),matches=[];fieldList.forEach(function(f){var cn=acCN[f]||"",desc=acIdx[f]||"";if(acMode==="exact"&&isChinese){if(cn.indexOf(v)>=0)matches.push(f);}else{if(f.toLowerCase().indexOf(q)>=0||cn.indexOf(v)>=0||desc.indexOf(v)>=0)matches.push(f);}});if(!matches.length){dd.classList.remove("show");return;}var h='<div style="font-size:9px;color:#8b949e;padding:2px 10px;border-bottom:1px solid #1c2533">'+(acMode==="exact"?"搜准确":"搜大概")+' ('+matches.length+') <span onclick="acToggleMode('+i+',\''+v+'\')" style="color:#58a6ff;cursor:pointer;margin-left:8px">切换</span></div>';for(var j=0;j<Math.min(matches.length,10);j++){h+='<div class="ac-item" onmousedown="acSelect('+i+',\''+matches[j]+'\')"><span class="name">'+matches[j]+'</span><span class="desc">'+(acCN[matches[j]]||"")+'</span></div>';}dd.innerHTML=h;dd.classList.add("show");dd._sel=-1;}
function acToggleMode(i,v){acMode=acMode==="exact"?"fuzzy":"exact";acFilter(i,v);}
function acKey(i,e){var dd=byId("ac-"+i);if(!dd.classList.contains("show"))return;var items=dd.querySelectorAll(".ac-item");if(!items.length)return;if(e.key==="ArrowDown"){e.preventDefault();dd._sel=Math.min((dd._sel||-1)+1,items.length-1);updateAcSel(items,dd._sel);}else if(e.key==="ArrowUp"){e.preventDefault();dd._sel=Math.max((dd._sel||1)-1,0);updateAcSel(items,dd._sel);}else if(e.key==="Enter"){e.preventDefault();if(dd._sel>=0)byId("expr-"+i).value=items[dd._sel].querySelector(".name").textContent;acHide(i);}else if(e.key==="Escape")acHide(i);}
function updateAcSel(items,sel){items.forEach(function(it,j){it.classList.toggle("sel",j===sel);});}
function acHide(i){var dd=byId("ac-"+i);if(dd)dd.classList.remove("show");}
function acSelect(i,name){byId("expr-"+i).value=name;acHide(i);}

// AI Chat
function toggleAI(){var p=byId("ai-panel");p.classList.toggle("open");if(p.classList.contains("open"))byId("ai-input").focus();}
async function clearAI(){try{await fetch("/api/ai/clear",{method:"POST"});byId("ai-body").innerHTML='<div class="ai-msg bot">记忆已清除。</div>';}catch(e){}}
async function askAI(){
  var inp=byId("ai-input");var q=inp.value.trim();if(!q)return;
  var body=byId("ai-body");body.innerHTML+='<div class="ai-msg user">'+esc(q)+'</div>';inp.value='';body.scrollTop=body.scrollHeight;
  body.innerHTML+='<div class="ai-msg bot">...</div>';
  try{var r=await fetch("/api/ai/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q})});var d=await r.json();
    body.removeChild(body.lastChild);body.innerHTML+='<div class="ai-msg bot">'+esc(d.answer||'无结果')+'</div>';}
  catch(e){body.removeChild(body.lastChild);body.innerHTML+='<div class="ai-msg bot">请求失败</div>';}
  body.scrollTop=body.scrollHeight;
}
function esc(s){var d=document.createElement("div");d.textContent=(s||"");return d.innerHTML;}

initTabs();
</script>
</body>
</html>
'''

with open(DST, 'w', encoding='utf-8') as f:
    f.write(HTML)
print('dashboard.html written OK (' + str(len(HTML)) + ' bytes)')
