"""Fix SuperAlpha: history-based selection + PnL overlay"""
with open('D:/yyb/backtest_platform/templates/dashboard.html', 'r', encoding='utf-8') as f:
    c = f.read()

# Replace SuperAlpha UI: manual input -> history selection
old_ui = '''    <!-- SuperAlpha Panel -->
    <div id="superalpha-box">
      <h3>SuperAlpha — 多因子等权组合</h3>
      <div class="sa-add">
        <input type="text" id="sa-input" class="sa-input" placeholder="输入另一个表达式">
        <button onclick="addSA()">添加</button>
      </div>
      <div id="sa-list"></div>
      <button onclick="runSA()" style="margin-top:8px;padding:8px 16px;background:#f0883e;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">组合回测</button>
      <div id="sa-result"></div>
    </div>'''

new_ui = '''    <!-- SuperAlpha Panel - select from alpha history -->
    <div id="superalpha-box">
      <h3>SuperAlpha — 从 Alpha 历史选取组合</h3>
      <button id="sa-load-btn" onclick="loadSAHistory()" style="padding:6px 12px;background:#1c2533;color:#58a6ff;border:1px solid #30363d;border-radius:4px;cursor:pointer;font-size:11px;">加载历史 Alpha</button>
      <div id="sa-select-list" style="margin-top:8px;max-height:200px;overflow-y:auto;font-size:11px;"></div>
      <div style="font-size:11px;color:#8b949e;margin-top:6px;">已选 <span id="sa-count">0</span> 个</div>
      <button id="sa-run-btn" onclick="runSAFromHistory()" disabled style="margin-top:8px;padding:8px 16px;background:#f0883e;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px;">等权组合回测</button>
      <div id="sa-result" style="margin-top:10px;"></div>
    </div>'''

if old_ui in c:
    c = c.replace(old_ui, new_ui)
    print('UI replaced')
else:
    print('UI NOT FOUND - searching...')
    idx = c.find('SuperAlpha')
    if idx > 0:
        print('Found at', idx, ':', c[idx:idx+80])

# Replace old SA JS (manual expression input) with history-based selection
old_js = '''  // SuperAlpha
  function addSA(){var v=$('sa-input').value.trim();if(v){saRecords.push(v);$('sa-input').value='';renderSA();}}
  function removeSA(i){saRecords.splice(i,1);renderSA();}
  function renderSA(){
    var h='';
    saRecords.forEach(function(e,i){
      h+='<div class=\\"sa-row\\"><span>'+e+'</span><input id=\\"saw-'+i+'\\" value=\\"1\\"><button onclick=\\"removeSA('+i+')\\">X</button></div>';
    });
    $('sa-list').innerHTML=h;
  }
  async function runSA(){'''

new_js = '''  // SuperAlpha - select from history, equal-weight combine
  var saHistory=[], saSelected=[];
  async function loadSAHistory(){
    $('sa-select-list').innerHTML='<div style="color:#8b949e;padding:8px;">加载中...</div>';
    try{
      var r=await fetch('/api/alpha/history');var d=await r.json();
      saHistory=d.records||[];
      var h='';
      saHistory.forEach(function(a,i){
        var m=a.metrics||{};
        var ex=(m.annual_excess||0)*100;
        h+='<label style="display:flex;align-items:center;gap:8px;padding:6px 8px;cursor:pointer;font-size:11px;border-bottom:1px solid #1c2533;">';
        h+='<input type="checkbox" onchange="toggleSA('+i+',this.checked)" style="cursor:pointer;">';
        h+='<span style="font-family:monospace;color:#58a6ff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+(a.name||a.expression||'').substring(0,50)+'</span>';
        h+='<span style="color:#8b949e;font-size:10px;">IC:'+((m.pearson_ic||0).toFixed(3))+' Ex:'+(ex.toFixed(1))+'%</span>';
        h+='</label>';
      });
      $('sa-select-list').innerHTML=h||'<div style="color:#8b949e;padding:8px;">暂无 Alpha，先做一次回测</div>';
    }catch(e){$('sa-select-list').innerHTML='<div style="color:#ff6b6b;padding:8px;">加载失败</div>';}
  }
  function toggleSA(i,checked){
    if(checked){if(saSelected.length>=5){alert('最多选5个');return false;}saSelected.push(i);}
    else{saSelected=saSelected.filter(function(x){return x!==i;});}
    document.getElementById('sa-count').textContent=saSelected.length;
    document.getElementById('sa-run-btn').disabled=saSelected.length<2;
  }
  async function runSAFromHistory(){'''

if old_js in c:
    c = c.replace(old_js, new_js)
    print('JS replaced 1')
else:
    print('JS old NOT found 1')

# Replace runSA body - the API call and response handling
old_body = '''  if(saRecords.length<2){showErr('至少添加2个表达式');return;}
  var ws=saRecords.map(function(_,i){var el=$('saw-'+i);return el?parseFloat(el.value)||1:1;});
  var tw=ws.reduce(function(a,b){return a+b;},0);
  var nw=ws.map(function(w){return w/tw;});
  var neutralize=$('neutralize-select').value;
  $('sa-result').style.display='block';
  $('sa-result').innerHTML='<div style="text-align:center;color:#8b949e">组合回测中...</div>';
  try{
    var resp=await fetch('/api/superalpha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expressions:saRecords,weights:nw,neutralize:neutralize})});'''

new_body = '''  if(saSelected.length<2){showErrSlot(activeSlot,'至少选2个');return;}
  var ids=saSelected.map(function(i){return saHistory[i].id;});
  var neutralize=$('neutralize-select-'+activeSlot).value;
  $('sa-result').style.display='block';
  $('sa-result').innerHTML='<div style="text-align:center;color:#8b949e">组合回测中...</div>';
  try{
    var resp=await fetch('/api/superalpha',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alpha_ids:ids,neutralize:neutralize})});'''

if old_body in c:
    c = c.replace(old_body, new_body)
    print('JS replaced 2')
else:
    print('JS old NOT found 2 - searching...')
    idx = c.find("saRecords.length<2")
    if idx > 0:
        print('Found near:', c[idx:idx+100])

# Replace response handling
old_resp = '''    var data=await resp.json();
    if(data.error){$('sa-result').innerHTML='<span style="color:#ff6b6b">'+data.error+'</span>';return;}
    var h='<div style="color:#3fb950;font-weight:bold">组合 PearsonIC='+data.combined.pearson_ic.toFixed(4)+' 超额='+(data.combined.annual_excess*100).toFixed(2)+'% Sharpe='+data.combined.sharpe.toFixed(2)+' Fitness='+data.combined.fitness.toFixed(2)+'</div>';
    h+='<table><tr><th>表达式</th><th>权重</th><th>IC</th><th>超额</th><th>Sharpe</th></tr>';
    (data.sub_alphas||[]).forEach(function(sa,i){
      h+='<tr><td style="font-family:monospace;font-size:10px;color:#58a6ff">'+(saRecords[i]||'')+'</td><td>'+(nw[i]*100).toFixed(0)+'%</td><td style="color:'+(sa.pearson_ic>=0?'#3fb950':'#ff6b6b')+'">'+sa.pearson_ic.toFixed(4)+'</td><td>'+(sa.annual_excess*100).toFixed(2)+'%</td><td>'+sa.sharpe.toFixed(2)+'</td></tr>';
    });
    h+='</table>';$('sa-result').innerHTML=h;
  }catch(e){$('sa-result').innerHTML='<span style="color:#ff6b6b">请求失败</span>';}'''

new_resp = '''    var data=await resp.json();
    if(data.error){$('sa-result').innerHTML='<span style="color:#ff6b6b">'+data.error+'</span>';return;}
    var cm=data.combined||data||{};
    var h='<div style="color:#3fb950;font-weight:bold;margin-bottom:6px;">组合: PearsonIC='+(cm.pearson_ic||0).toFixed(4)+' 年化收益='+((cm.annual_excess||0)*100).toFixed(2)+'% Sharpe='+(cm.sharpe||0).toFixed(2)+' Fitness='+(cm.fitness||0).toFixed(2)+'</div>';
    h+='<table style="font-size:11px;"><tr><th>Alpha</th><th>IC</th><th>年化收益</th><th>Sharpe</th></tr>';
    var subs=data.sub_alphas||data.alphas||[];
    subs.forEach(function(sa,i){
      var nm=(sa.name||sa.expression||'').substring(0,30);
      h+='<tr><td style="font-family:monospace;font-size:10px;color:#58a6ff;">'+nm+'</td><td style="color:'+((sa.pearson_ic||0)>=0?'#3fb950':'#ff6b6b')+';">'+(sa.pearson_ic||0).toFixed(4)+'</td><td>'+((sa.annual_excess||0)*100).toFixed(2)+'%</td><td>'+((sa.sharpe||0).toFixed(2))+'</td></tr>';
    });
    h+='</table>';
    if(typeof Chart!=='undefined' && cm.pnl_series && cm.pnl_series.length){
      h+='<div style="margin-top:10px;"><canvas id="sa-pnl-canvas" style="height:200px;"></canvas></div>';
    }
    $('sa-result').innerHTML=h;
    if(cm.pnl_series && cm.pnl_series.length){
      setTimeout(function(){
        var ctx=document.getElementById('sa-pnl-canvas');
        if(ctx && typeof Chart!=='undefined'){
          new Chart(ctx.getContext('2d'),{type:'line',data:{labels:cm.pnl_series.map(function(_,i){return i+1;}),datasets:[{label:'Combined PnL',data:cm.pnl_series,borderColor:'#3fb950',borderWidth:2,pointRadius:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{display:false}}}});
        }
      },100);
    }
  }catch(e){$('sa-result').innerHTML='<span style="color:#ff6b6b">请求失败: '+e.message+'</span>';}'''

if old_resp in c:
    c = c.replace(old_resp, new_resp)
    print('JS replaced 3')
else:
    print('JS old NOT found 3')

# Show/hide sa-count correctly
c = c.replace('sa-count','sa-count')

with open('D:/yyb/backtest_platform/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(c)
print('Done - restart server to apply')
