"""Replace dashboard JS with minimal working version"""
import re
with open('D:/yyb/backtest_platform/templates/dashboard.html','r',encoding='utf-8') as f:
    c=f.read()

m=re.search(r'(<script>\s*)(.*?)(\s*</script>)',c,re.DOTALL)
if not m: print('No script found!'); exit(1)

new_js = '''
let pnlChart=null,icChart=null,pollTimer=null,pollStart=null;
const TIMEOUT=180000;
let saHistory=[],saSelected=[];

function $(id){return document.getElementById(id);}
function showErr(m){var e=$('error-msg-0'); if(e){e.textContent=m;e.style.display='block';}}
function hideErr(){var e=$('error-msg-0'); if(e) e.style.display='none';}
function fillRun(expr){var inp=$('expr-input-0'); if(inp)inp.value=expr;runBT();}
function showProg(show){
  var w=$('progress-bar-wrap-0'); if(w) w.classList.toggle('show',show);
  var t=$('progress-text-0'); if(t) t.style.display=show?'block':'none';
  if(show){var b=$('progress-bar-0'); if(b) b.style.width='0%'; if(t) t.textContent='回测中 0%';}
}

function displayResult(data){
  if(!data)return;
  try{$('m-excess').textContent=((data.annual_excess||0)*100).toFixed(2)+'%';}catch(e){}
  try{$('m-ic').textContent=(data.pearson_ic||0).toFixed(4);}catch(e){}
  try{$('m-sharpe').textContent=(data.sharpe||0).toFixed(2);}catch(e){}
  try{$('m-fitness').textContent=(data.fitness||0).toFixed(2);}catch(e){}
  try{$('m-turnover').textContent=((data.turnover||0)*100).toFixed(1)+'%';}catch(e){}
  try{$('m-dd').textContent=((data.max_drawdown||0)*100).toFixed(2)+'%';}catch(e){}
  try{$('m-margin').textContent=(data.margin_bps||0).toFixed(1);}catch(e){}
  try{$('m-winrate').textContent=((data.win_rate||0)*100).toFixed(1)+'%';}catch(e){}
  if(typeof Chart==='undefined') return;
  try{
    if(pnlChart)pnlChart.destroy();
    var ctx=$('pnl-chart'); if(!ctx) return;
    pnlChart=new Chart(ctx.getContext('2d'),{type:'line',data:{labels:(data.pnl_series||[]).map(function(_,i){return i+1;}),datasets:[{label:'PnL',data:data.pnl_series||[],borderColor:'#3fb950',borderWidth:2,pointRadius:0}]},options:{responsive:true,plugins:{legend:{display:false}}}});
  }catch(e){console.error(e);}
  try{
    if(icChart)icChart.destroy();
    var ctx=$('ic-chart'); if(!ctx) return;
    icChart=new Chart(ctx.getContext('2d'),{type:'line',data:{labels:(data.ic_series||[]).map(function(_,i){return i+1;}),datasets:[{label:'IC',data:data.ic_series||[],borderColor:'#58a6ff',borderWidth:1,pointRadius:0}]},options:{responsive:true,plugins:{legend:{display:false}}}});
  }catch(e){console.error(e);}
}

async function runBT(){
  hideErr();
  var expr=$('expr-input-0').value.trim();
  if(!expr){showErr('请输入因子表达式');return;}
  var btn=$('btn-backtest-0');btn.textContent='回测中...';btn.disabled=true;showProg(true);
  var neutralize=$('neutralize-select-0').value;
  if(pollTimer)clearInterval(pollTimer);
  try{
    var sr=await fetch('/api/backtest/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expression:expr,neutralize:neutralize})});
    var sj=await sr.json();
    if(!sj.task_id)throw new Error('No task_id');
    sessionStorage.setItem('activeTask',JSON.stringify({taskId:sj.task_id,time:Date.now()}));
    pollStart=Date.now();
    pollTimer=setInterval(async function(){
      try{
        var pr=await fetch('/api/backtest/status/'+sj.task_id);
        var pd=await pr.json();
        if(!pd) return;
        var pct=pd.progress||0;
        var bar=$('progress-bar-0'); if(bar) bar.style.width=pct+'%';
        var txt=$('progress-text-0'); if(txt) txt.textContent='回测中 '+pct+'%';
        if(pd.status==='done'){
          clearInterval(pollTimer);pollTimer=null;
          sessionStorage.removeItem('activeTask');
          showProg(false);btn.textContent='回 测';btn.disabled=false;
          if(pd.result){displayResult(pd.result);}else{showErr('无数据');}
        }else if(pd.status==='error'){
          clearInterval(pollTimer);pollTimer=null;
          sessionStorage.removeItem('activeTask');
          showProg(false);btn.textContent='回 测';btn.disabled=false;
          showErr(pd.error||'失败');
        }else if(Date.now()-pollStart>TIMEOUT){
          clearInterval(pollTimer);pollTimer=null;
          sessionStorage.removeItem('activeTask');
          showProg(false);btn.textContent='回 测';btn.disabled=false;
          showErr('超时');
        }
      }catch(e){}
    },300);
  }catch(e){showProg(false);btn.textContent='回 测';btn.disabled=false;showErr('请求失败: '+e.message);}
}

// SessionStorage resume on page load
(function(){
  var saved=sessionStorage.getItem('activeTask');
  if(saved){
    try{
      var t=JSON.parse(saved);
      if(Date.now()-t.time<180000){
        showProg(true);
        var btn=$('btn-backtest-0');btn.textContent='回测中...';btn.disabled=true;
        pollStart=Date.now();
        pollTimer=setInterval(async function(){
          try{
            var pr=await fetch('/api/backtest/status/'+t.taskId);
            var pd=await pr.json();
            if(!pd) return;
            var pct=pd.progress||0;
            var bar=$('progress-bar-0'); if(bar) bar.style.width=pct+'%';
            var txt=$('progress-text-0'); if(txt) txt.textContent='回测中 '+pct+'%';
            if(pd.status==='done'){
              clearInterval(pollTimer);pollTimer=null;
              sessionStorage.removeItem('activeTask');
              showProg(false);btn.textContent='回 测';btn.disabled=false;
              if(pd.result)displayResult(pd.result);
            }else if(pd.status==='error'){
              clearInterval(pollTimer);pollTimer=null;
              sessionStorage.removeItem('activeTask');
              showProg(false);btn.textContent='回 测';btn.disabled=false;
            }
          }catch(e){}
        },500);
      }else{sessionStorage.removeItem('activeTask');}
    }catch(e){}
  }
})();

// SuperAlpha (history-based, minimal)
async function loadSAHistory(){
  var el=$('sa-select-list'); if(!el) return;
  el.innerHTML='<div style="color:#8b949e;padding:8px;">加载中...</div>';
  try{
    var r=await fetch('/api/alpha/history');var d=await r.json();
    saHistory=d.records||[];
    var h='';
    for(var i=0;i<saHistory.length;i++){
      var a=saHistory[i],m=a.metrics||{};
      h+='<label style="display:flex;align-items:center;gap:8px;padding:6px 8px;cursor:pointer;border-bottom:1px solid #1c2533;">';
      h+='<input type="checkbox" onchange="toggleSA('+i+',this.checked)" style="cursor:pointer;">';
      h+='<span style="font-family:monospace;color:#58a6ff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;">'+(a.name||a.expression||'').substring(0,50)+'</span>';
      h+='</label>';
    }
    el.innerHTML=h||'<div style="color:#8b949e;padding:8px;">暂无 Alpha</div>';
  }catch(e){el.innerHTML='<div style="color:#ff6b6b;padding:8px;">加载失败</div>';}
}
function toggleSA(i,checked){
  if(checked){if(saSelected.length>=5){alert('最多5个');return false;}saSelected.push(i);}
  else{saSelected=saSelected.filter(function(x){return x!==i;});}
  var cnt=document.getElementById('sa-count'); if(cnt) cnt.textContent=saSelected.length;
  var btn=document.getElementById('sa-run-btn'); if(btn) btn.disabled=saSelected.length<2;
}
async function runSAFromHistory(){
  if(saSelected.length<2){alert('至少选2个');return;}
  var ids=saSelected.map(function(i){return saHistory[i].id;});
  var el=$('sa-result'); if(el){el.style.display='block';el.innerHTML='<div style="text-align:center;color:#8b949e">组合回测中...</div>';}
  try{
    var resp=await fetch('/api/superalpha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alpha_ids:ids})});
    var data=await resp.json();
    if(data.error){if(el)el.innerHTML='<span style="color:#ff6b6b">'+data.error+'</span>';return;}
    var cm=data.combined_metrics||data.combined||data||{};
    var h='<div style="color:#3fb950;font-weight:bold;">组合 IC='+(cm.pearson_ic||0).toFixed(4)+' 收益='+((cm.annual_excess||0)*100).toFixed(2)+'% Sharpe='+(cm.sharpe||0).toFixed(2)+'</div>';
    if(el)el.innerHTML=h;
  }catch(e){if(el)el.innerHTML='<span style="color:#ff6b6b">失败</span>';}
}
console.log('DASHBOARD INIT OK');
'''

c=c[:m.start(2)]+new_js+c[m.end(2):]
with open('D:/yyb/backtest_platform/templates/dashboard.html','w',encoding='utf-8') as f:
    f.write(c)
print('JS replaced OK')
