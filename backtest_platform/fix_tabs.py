"""Fix: 3 working tabs, SuperAlpha full metrics, remove IC chart"""
with open('D:/yyb/backtest_platform/templates/dashboard.html','r',encoding='utf-8') as f:
    c=f.read()
import re

# 1. Remove IC chart HTML (keep only PnL)
c=c.replace('''      <div class="chart-box"><h3>Rank IC 时序 (近60日)</h3><canvas id="ic-chart"></canvas></div>
''','')

# 2. Replace tab switching CSS/JS - make all 3 tabs work
# First, replace the entire JS section
m=re.search(r'(<script>\s*)(.*?)(\s*</script>)',c,re.DOTALL)
new_js='''
let pnlChart=null,activeSlot=0;
let saHistory=[],saSelected=[];
function $(id){return document.getElementById(id);}
function showErr(m){var e=$("error-msg-"+activeSlot);if(e){e.textContent=m;e.style.display="block";}}
function hideErr(){var e=$("error-msg-"+activeSlot);if(e)e.style.display="none";}
function fillRun(expr){var inp=$("expr-input-"+activeSlot);if(inp)inp.value=expr;runBT();}
function showProg(show){
  var w=$("progress-bar-wrap-"+activeSlot);if(w)w.classList.toggle("show",show);
  var t=$("progress-text-"+activeSlot);if(t){t.style.display=show?"block":"none";if(show)t.textContent="回测中...";}
}

function switchTab(idx){
  activeSlot=idx;
  for(var i=0;i<3;i++){
    var tab=$("bt-tab-"+i); if(tab) tab.style.borderColor=(i===idx)?"#58a6ff":"#30363d";
    var panel=$("bt-panel-"+i); if(panel) panel.style.display=(i===idx)?"block":"none";
  }
}

function displayResult(data){
  if(!data)return;
  try{$("m-excess").textContent=((data.annual_excess||0)*100).toFixed(2)+"%";}catch(e){}
  try{$("m-ic").textContent=(data.pearson_ic||0).toFixed(4);}catch(e){}
  try{$("m-sharpe").textContent=(data.sharpe||0).toFixed(2);}catch(e){}
  try{$("m-fitness").textContent=(data.fitness||0).toFixed(2);}catch(e){}
  try{$("m-turnover").textContent=((data.turnover||0)*100).toFixed(1)+"%";}catch(e){}
  try{$("m-dd").textContent=((data.max_drawdown||0)*100).toFixed(2)+"%";}catch(e){}
  try{$("m-margin").textContent=(data.margin_bps||0).toFixed(1);}catch(e){}
  try{$("m-winrate").textContent=((data.win_rate||0)*100).toFixed(1)+"%";}catch(e){}
  if(typeof Chart==="undefined")return;
  try{
    if(pnlChart)pnlChart.destroy();
    var ctx=$("pnl-chart");if(!ctx)return;
    pnlChart=new Chart(ctx.getContext("2d"),{type:"line",data:{labels:(data.pnl_series||[]).map(function(_,i){return i+1;}),datasets:[{label:"PnL",data:data.pnl_series||[],borderColor:"#3fb950",borderWidth:2,pointRadius:0,fill:true,backgroundColor:"rgba(63,185,80,0.1)"}]},options:{responsive:true,plugins:{legend:{display:false}}}});
  }catch(e){}
}

async function runBT(){
  hideErr();
  var expr=$("expr-input-"+activeSlot).value.trim();
  if(!expr){showErr("请输入因子表达式");return;}
  var btn=$("btn-backtest-"+activeSlot);btn.textContent="回测中...";btn.disabled=true;showProg(true);
  var neutralize=$("neutralize-select-"+activeSlot).value;
  try{
    var resp=await fetch("/api/backtest",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expression:expr,neutralize:neutralize})});
    var data=await resp.json();
    showProg(false);btn.textContent="回 测";btn.disabled=false;
    if(data.error){showErr(data.error);}
    else if(data.pearson_ic!==undefined){displayResult(data);}
    else{showErr("回测失败");}
  }catch(e){showProg(false);btn.textContent="回 测";btn.disabled=false;showErr("请求失败: "+e.message);}
}

// SuperAlpha
async function loadSAHistory(){
  var el=$("sa-select-list");if(!el)return;
  el.innerHTML='<div style="color:#8b949e;padding:8px;">加载中...</div>';
  try{
    var r=await fetch("/api/alpha/history");var d=await r.json();
    saHistory=d.records||[];
    var h="";
    for(var i=0;i<saHistory.length;i++){
      var a=saHistory[i],m=a.metrics||{};
      h+='<label style="display:flex;align-items:center;gap:8px;padding:6px 8px;cursor:pointer;border-bottom:1px solid #1c2533;"><input type="checkbox" onchange="toggleSA('+i+',this.checked)"><span style="font-family:monospace;color:#58a6ff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;">'+(a.name||a.expression||"").substring(0,50)+'</span></label>';
    }
    el.innerHTML=h||'<div style="color:#8b949e;padding:8px;">暂无 Alpha</div>';
  }catch(e){el.innerHTML='<div style="color:#ff6b6b;padding:8px;">加载失败</div>';}
}
function toggleSA(i,checked){
  if(checked){if(saSelected.length>=5){alert("最多5个");return false;}saSelected.push(i);}
  else{saSelected=saSelected.filter(function(x){return x!==i;});}
  var cnt=document.getElementById("sa-count");if(cnt)cnt.textContent=saSelected.length;
  var btn=document.getElementById("sa-run-btn");if(btn)btn.disabled=saSelected.length<2;
}
async function runSAFromHistory(){
  if(saSelected.length<2){alert("至少选2个");return;}
  var ids=saSelected.map(function(i){return saHistory[i].id;});
  var el=$("sa-result");if(el){el.style.display="block";el.innerHTML='<div style="text-align:center;color:#8b949e">组合回测中...</div>';}
  try{
    var resp=await fetch("/api/superalpha",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({alpha_ids:ids})});
    var data=await resp.json();
    if(data.error){if(el)el.innerHTML='<span style="color:#ff6b6b">'+data.error+"</span>";return;}
    var cm=data.combined_metrics||data.combined||data||{};
    // Full metrics like regular alpha
    displayResult(cm);
    // Also show sub-alpha table + combined header
    var h='<div style="color:#3fb950;font-weight:bold;margin-bottom:6px;">组合 IC='+(cm.pearson_ic||0).toFixed(4)+' 收益='+((cm.annual_excess||0)*100).toFixed(2)+'% Sharpe='+(cm.sharpe||0).toFixed(2)+' Fitness='+(cm.fitness||0).toFixed(2)+'</div>';
    h+='<table style="font-size:11px;"><tr><th>Alpha</th><th>IC</th><th>收益</th><th>Sharpe</th></tr>';
    var subs=data.sub_alphas||data.alphas||[];
    subs.forEach(function(sa,i){
      var nm=(sa.name||sa.expression||"").substring(0,30);
      h+='<tr><td style="font-family:monospace;font-size:10px;color:#58a6ff;">'+nm+'</td><td style="color:'+((sa.pearson_ic||0)>=0?"#3fb950":"#ff6b6b")+';">'+(sa.pearson_ic||0).toFixed(4)+'</td><td>'+((sa.annual_excess||0)*100).toFixed(2)+'%</td><td>'+((sa.sharpe||0).toFixed(2))+'</td></tr>';
    });
    h+="</table>";
    if(el)el.innerHTML=h;
  }catch(e){if(el)el.innerHTML='<span style="color:#ff6b6b">失败</span>';}
}
console.log("DASHBOARD OK "+new Date().toISOString());
'''

c=c[:m.start(2)]+new_js+c[m.end(2):]
with open('D:/yyb/backtest_platform/templates/dashboard.html','w',encoding='utf-8') as f:
    f.write(c)
print('Done: 3 tabs, SA full metrics, IC chart removed')
