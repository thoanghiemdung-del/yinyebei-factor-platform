import os
BASE = os.path.dirname(os.path.abspath(__file__))
"""Deploy bulletproof dashboard JS"""
import re
with open(os.path.join(BASE, 'templates', 'dashboard.html'), 'r', encoding='utf-8') as f:
    c=f.read()

m=re.search(r'(<script>\s*)(.*?)(\s*</script>)',c,re.DOTALL)
js='''
var pnlChart=null,activeSlot=0,slotPnlData=[null,null,null];
var saHistory=[],saSelected=[];
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
    var tab=$("bt-tab-"+i);if(tab){tab.classList.toggle("active",i===idx);}
    var panel=$("bt-panel-"+i);if(panel){panel.classList.toggle("active",i===idx);}
  }
  var saved=slotPnlData[idx];
  if(saved){try{showMetrics(saved);drawPnL(saved);}catch(e){}}
  else{clearMetrics();}
}
function clearMetrics(){
  try{$("m-excess").textContent="--";}catch(e){}
  try{$("m-ic").textContent="--";}catch(e){}
  try{$("m-sharpe").textContent="--";}catch(e){}
  try{$("m-fitness").textContent="--";}catch(e){}
  try{$("m-turnover").textContent="--";}catch(e){}
  try{$("m-dd").textContent="--";}catch(e){}
  try{$("m-margin").textContent="--";}catch(e){}
  try{$("m-winrate").textContent="--";}catch(e){}
  if(pnlChart){try{pnlChart.destroy();}catch(e){};pnlChart=null;}
}
function showMetrics(data){
  if(!data)return;
  try{$("m-excess").textContent=((data.annual_excess||0)*100).toFixed(2)+"%";}catch(e){}
  try{$("m-ic").textContent=(data.pearson_ic||0).toFixed(4);}catch(e){}
  try{$("m-sharpe").textContent=(data.sharpe||0).toFixed(2);}catch(e){}
  try{$("m-fitness").textContent=(data.fitness||0).toFixed(2);}catch(e){}
  try{$("m-turnover").textContent=((data.turnover||0)*100).toFixed(1)+"%";}catch(e){}
  try{$("m-dd").textContent=((data.max_drawdown||0)*100).toFixed(2)+"%";}catch(e){}
  try{$("m-margin").textContent=(data.margin_bps||0).toFixed(1);}catch(e){}
  try{$("m-winrate").textContent=((data.win_rate||0)*100).toFixed(1)+"%";}catch(e){}
}
function drawPnL(data){
  if(typeof Chart==="undefined")return;
  try{
    if(pnlChart){pnlChart.destroy();pnlChart=null;}
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
    else if(data.pearson_ic!==undefined){
      slotPnlData[activeSlot]=data;
      showMetrics(data);
      drawPnL(data);
    }else{showErr("回测失败");}
  }catch(e){showProg(false);btn.textContent="回 测";btn.disabled=false;showErr("请求失败: "+e.message);}
}

async function loadSAHistory(){
  var el=$("sa-select-list");if(!el)return;
  el.innerHTML='<div style="color:#8b949e;padding:8px;">加载中...</div>';
  try{
    var r=await fetch("/api/alpha/history");var d=await r.json();
    saHistory=d.records||[];var h="";
    for(var i=0;i<saHistory.length;i++){
      var a=saHistory[i],m=a.metrics||{};
      h+='<label style="display:flex;align-items:center;gap:8px;padding:6px 8px;cursor:pointer;border-bottom:1px solid #1c2533;"><input type="checkbox" onchange="toggleSA('+i+',this.checked)"><span style="font-family:monospace;color:#58a6ff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;">'+(a.name||a.expression||"").substring(0,35)+'</span><span style="color:#8b949e;font-size:10px;">IC:'+((m.pearson_ic||0).toFixed(3))+' Ex:'+((m.annual_excess||0)*100).toFixed(1)+'%</span></label>';
    }
    el.innerHTML=h||'<div style="color:#8b949e;padding:8px;">暂无</div>';
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
    showMetrics(cm);drawPnL(cm);
    var h='<div style="color:#3fb950;font-weight:bold;font-size:12px;margin-bottom:8px;">组合 IC='+(cm.pearson_ic||0).toFixed(4)+' 收益='+((cm.annual_excess||0)*100).toFixed(2)+'% Sharpe='+(cm.sharpe||0).toFixed(2)+' Fitness='+(cm.fitness||0).toFixed(2)+'</div>';
    var subs=data.sub_alphas||data.alphas||[];
    subs.forEach(function(sa,i){
      var m=sa.metrics||sa||{};
      var sid="sasub-"+i+"-"+Date.now();
      h+='<div style="border:1px solid #30363d;border-radius:4px;margin-bottom:4px;"><div onclick="document.getElementById(\\''+sid+'\\').style.display=document.getElementById(\\''+sid+'\\').style.display===\\'none\\'?\\'block\\':\\'none\\'" style="padding:6px 10px;background:#161b22;cursor:pointer;font-size:11px;display:flex;gap:10px;"><span style="color:#e94560;">&#9654;</span><span style="font-family:monospace;color:#58a6ff;flex:1;">'+(sa.expression||"").substring(0,35)+'</span><span style="color:#8b949e;">IC:'+(m.pearson_ic||0).toFixed(3)+'</span></div><div id="'+sid+'" style="display:block;padding:8px 10px;background:#0d1117;"><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;">';
      h+='<div style="text-align:center;"><div style="font-size:10px;color:#8b949e;">IC</div><div style="font-size:13px;font-weight:bold;color:'+((m.pearson_ic||0)>=0?"#3fb950":"#ff6b6b")+';">'+(m.pearson_ic||0).toFixed(4)+'</div></div>';
      h+='<div style="text-align:center;"><div style="font-size:10px;color:#8b949e;">收益</div><div style="font-size:13px;font-weight:bold;color:#58a6ff;">'+((m.annual_excess||0)*100).toFixed(2)+'%</div></div>';
      h+='<div style="text-align:center;"><div style="font-size:10px;color:#8b949e;">Sharpe</div><div style="font-size:13px;font-weight:bold;color:#58a6ff;">'+(m.sharpe||0).toFixed(2)+'</div></div>';
      h+='<div style="text-align:center;"><div style="font-size:10px;color:#8b949e;">Fitness</div><div style="font-size:13px;font-weight:bold;color:#58a6ff;">'+(m.fitness||0).toFixed(2)+'</div></div>';
      h+='<div style="text-align:center;"><div style="font-size:10px;color:#8b949e;">Turnover</div><div style="font-size:13px;font-weight:bold;color:#58a6ff;">'+((m.turnover||0)*100).toFixed(1)+'%</div></div>';
      h+='<div style="text-align:center;"><div style="font-size:10px;color:#8b949e;">回撤</div><div style="font-size:13px;font-weight:bold;color:#ff6b6b;">'+((m.max_drawdown||0)*100).toFixed(2)+'%</div></div>';
      h+='<div style="text-align:center;"><div style="font-size:10px;color:#8b949e;">Margin</div><div style="font-size:13px;font-weight:bold;color:#58a6ff;">'+(m.margin_bps||0).toFixed(1)+'</div></div>';
      h+='<div style="text-align:center;"><div style="font-size:10px;color:#8b949e;">胜率</div><div style="font-size:13px;font-weight:bold;color:#58a6ff;">'+((m.win_rate||0)*100).toFixed(1)+'%</div></div>';
      h+='</div></div></div>';
    });
    var allPnl=cm.pnl_series||[];
    if(typeof Chart!=="undefined" && allPnl.length){
      h+='<div style="margin-top:8px;border-top:1px solid #30363d;padding-top:8px;"><canvas id="sa-pnl-canvas" style="height:180px;"></canvas></div>';
    }
    if(el)el.innerHTML=h;
    if(allPnl.length){setTimeout(function(){
      var ctx=document.getElementById("sa-pnl-canvas");
      if(ctx && typeof Chart!=="undefined"){
        var colors=["#e6b422","#58a6ff","#3fb950","#e94560","#f0883e"];
        var datasets=[{label:"Combined",data:allPnl,borderColor:"#fff",borderWidth:3,pointRadius:0}];
        subs.forEach(function(sa,i){
          if(sa.pnl_series&&sa.pnl_series.length) datasets.push({label:(sa.expression||"").substring(0,20),data:sa.pnl_series,borderColor:colors[i%5],borderWidth:1,pointRadius:0});
        });
        new Chart(ctx.getContext("2d"),{type:"line",data:{labels:allPnl.map(function(_,i){return i+1;}),datasets:datasets},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"top",labels:{color:"#8b949e",fontSize:10,boxWidth:12}}},scales:{x:{display:false},y:{grid:{color:"#30363d"}}}}});
      }
    },100);}
  }catch(e){if(el)el.innerHTML='<span style="color:#ff6b6b">失败: '+e.message+'</span>';}
}
console.log("DASHBOARD OK v2");
'''

c=c[:m.start(2)]+js+c[m.end(2):]
with open(os.path.join(BASE, 'templates', 'dashboard.html'), 'w', encoding='utf-8') as f:
    f.write(c)
print("Bulletproof JS deployed")
