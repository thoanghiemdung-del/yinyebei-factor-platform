"""Build data_fields.html — fetches ALL field metadata from /api/datafields API.
Single source of truth: FIELDS_METADATA in expression_parser.py.
"""
import os

DST = os.path.join(os.path.dirname(__file__), 'templates', 'data_fields.html')

HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<title>数据百科全书</title>
<style>
*, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; min-height: 100vh; }
.header { background: #161b22; border-bottom: 1px solid #30363d; padding: 12px 24px; display: flex; justify-content: center; align-items: center; gap: 30px; position: sticky; top: 0; z-index: 200; }
.header h1 { color: #e94560; font-size: 17px; }
.header nav { display: flex; gap: 20px; }
.header nav a { color: #8b949e; text-decoration: none; font-size: 12px; }
.header nav a:hover { color: #58a6ff; }
.layout { display: flex; height: calc(100vh - 49px); }
.panel-left { flex: 1; overflow-y: auto; padding: 20px 24px; min-width: 0; }
.search-wrap { position: sticky; top: 0; background: #0d1117; padding: 12px 0 16px; z-index: 10; }
.search-wrap input { width: 100%; padding: 10px 14px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; color: #c9d1d9; font-size: 14px; font-family: inherit; outline: none; }
.search-wrap input:focus { border-color: #58a6ff; }
.search-wrap input::placeholder { color: #484f58; }
.search-stats { margin-top: 8px; font-size: 11px; color: #8b949e; display: none; }
.search-stats.visible { display: block; }
.category { margin-bottom: 6px; border-radius: 8px; overflow: hidden; }
.cat-header { background: #161b22; border: 1px solid #30363d; padding: 13px 18px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
.cat-header:hover { border-color: #58a6ff; background: #1c2128; }
.cat-header h2 { font-size: 14px; color: #58a6ff; }
.cat-count { font-size: 11px; color: #8b949e; background: #1c2533; padding: 2px 8px; border-radius: 10px; }
.cat-arrow { color: #8b949e; font-size: 12px; transition: transform 0.2s; }
.cat-header.open .cat-arrow { transform: rotate(90deg); }
.cat-body { display: none; }
.cat-body.open { display: block; }
.field-row { background: #111820; border: 1px solid #30363d; border-top: none; cursor: pointer; }
.field-row:last-child { border-radius: 0 0 8px 8px; }
.field-row:hover { background: #161e2a; }
.field-summary { padding: 12px 18px 12px 30px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.field-code { font-family: monospace; font-size: 13px; font-weight: 600; color: #e94560; white-space: nowrap; }
.field-name-cn { font-size: 12px; color: #8b949e; white-space: nowrap; }
.field-one-liner { font-size: 12px; color: #6e7681; flex: 1; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.field-detail { display: none; padding: 0 18px 14px 30px; border-top: 1px solid #1c2533; }
.field-detail.open { display: block; }
.field-row.expanded { border-left: 3px solid #58a6ff; }
.detail-calc { background: #0d1117; border: 1px solid #1c2533; border-radius: 6px; padding: 12px 14px; margin-top: 10px; font-family: monospace; font-size: 12px; color: #58a6ff; line-height: 1.7; white-space: pre-wrap; word-break: break-all; }
.detail-meaning { font-size: 12px; color: #8b949e; margin-top: 10px; line-height: 1.65; }
.detail-meaning strong { color: #f0883e; }
.detail-meta { display: flex; gap: 20px; margin-top: 8px; font-size: 11px; }
.detail-meta span { color: #484f58; }
.detail-meta strong { color: #8b949e; }
.panel-right { width: 340px; overflow-y: auto; padding: 18px; background: #111820; border-left: 1px solid #30363d; font-size: 12px; line-height: 1.75; }
.panel-right h3 { color: #f0883e; font-size: 13px; margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px solid #30363d; }
.panel-right section { margin-bottom: 24px; }
.panel-right code { background: #1c2533; padding: 1px 5px; border-radius: 3px; color: #58a6ff; font-size: 11px; font-family: monospace; }
.panel-right table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 11px; }
.panel-right th { text-align: left; background: #1c2533; padding: 4px 8px; color: #58a6ff; }
.panel-right td { padding: 3px 8px; border-bottom: 1px solid #1c2533; }
.no-results { text-align: center; padding: 40px; color: #484f58; display: none; }
.no-results.show { display: block; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
</style>
</head>
<body>

<div class="header">
  <h1>数据百科全书</h1>
  <nav>
    <a href="/dashboard">仪表盘</a>
    <a href="/alpha_history">Alpha历史</a>
    <a href="/data_fields">数据字段</a>
    <a href="/operators">操作符</a>
    <a href="/correlation">相关性</a>
    <a href="/community">社区</a>
    <a href="/learn">学习</a>
    <a href="/logout">退出</a>
  </nav>
</div>

<div class="layout">
<div class="panel-left">
<div class="search-wrap">
  <input type="text" id="search-input" placeholder="搜索字段 — 支持中英文模糊匹配">
  <div class="search-stats" id="search-stats"></div>
</div>
<div id="encyclopedia">
  <div style="text-align:center;padding:60px;color:#8b949e;">加载中...</div>
</div>
<div class="no-results" id="no-results">没有匹配的字段，试试其他关键词</div>
</div>

<div class="panel-right">
<section>
  <h3>数据源说明</h3>
  <table>
    <tr><th style="width:80px">数据源</th><th>内容</th></tr>
    <tr><td>Daily .bin</td><td>日频 OHLCV + 股本，float32 (N_dates &times; N_stocks)</td></tr>
    <tr><td>Minute .mat</td><td>分钟频 OHLCV，970天 &times; 242 bar/天，用于微观结构字段</td></tr>
    <tr><td>Pre-computed</td><td>65个因子，来自 FactorComputer，含动量/反转/波动/微观结构等8大类</td></tr>
    <tr><td>Derived</td><td>运行时从原始/分钟数据实时计算，含K线形态、VWAP、量比等</td></tr>
  </table>
</section>
<section>
  <h3>字段分类速览</h3>
  <table id="toc-table"><tr><th>#</th><th>类别</th><th style="width:40px">数量</th></tr></table>
</section>
<section>
  <h3>常用算子速查</h3>
  <table>
    <tr><td><code>rank(x)</code></td><td>截面排名百分位</td></tr>
    <tr><td><code>ts_delta(x,d)</code></td><td>d日变化量</td></tr>
    <tr><td><code>ts_mean(x,d)</code></td><td>d日滚动均值</td></tr>
    <tr><td><code>ts_std(x,d)</code></td><td>d日滚动标准差</td></tr>
    <tr><td><code>ts_rank(x,d)</code></td><td>d日时序排名</td></tr>
    <tr><td><code>ts_corr(x,y,d)</code></td><td>x与y的滚动相关系数</td></tr>
    <tr><td><code>zscore(x)</code></td><td>截面标准化</td></tr>
    <tr><td><code>signed_power(x,e)</code></td><td>保号幂变换</td></tr>
    <tr><td><code>group_neutralize(x,g)</code></td><td>分组中性化</td></tr>
    <tr><td><code>trade_when(c,a,f)</code></td><td>条件因子</td></tr>
    <tr><td><code>ts_decay_linear(x,d)</code></td><td>线性衰减加权</td></tr>
    <tr><td><code>ts_regression(y,x,d)</code></td><td>滚动回归残差</td></tr>
  </table>
</section>
</div>
</div>

<script>
// ===== FETCH FROM API — single source of truth =====
var allCategories = [];
var allFieldsFlat = [];

async function loadFields(){
  try{
    var r = await fetch('/api/datafields');
    var d = await r.json();
    var cats = d.categories || d;
    allCategories = [];
    allFieldsFlat = [];
    Object.keys(cats).forEach(function(catName){
      var fields = cats[catName];
      if(!fields || fields.length===0) return;
      allCategories.push({name: catName, fields: fields});
      fields.forEach(function(f){ f._cat = catName; allFieldsFlat.push(f); });
    });
    renderAll();
  }catch(e){
    document.getElementById('encyclopedia').innerHTML = '<div style="text-align:center;padding:60px;color:#ff6b6b;">加载失败: '+e.message+'</div>';
  }
}

function renderAll(){
  var query = (document.getElementById('search-input').value || '').toLowerCase().trim();
  var filtered = allFieldsFlat;
  if(query){
    filtered = allFieldsFlat.filter(function(f){
      return (f.name||'').toLowerCase().indexOf(query)>=0 ||
             (f.description||'').toLowerCase().indexOf(query)>=0 ||
             (f.calculation||'').toLowerCase().indexOf(query)>=0 ||
             (f.category||'').toLowerCase().indexOf(query)>=0;
    });
  }

  var stats = document.getElementById('search-stats');
  if(query){
    stats.textContent = '找到 '+filtered.length+' 个匹配字段 (共 '+allFieldsFlat.length+' 个)';
    stats.classList.add('visible');
  } else {
    stats.classList.remove('visible');
  }

  var enc = document.getElementById('encyclopedia');
  if(query){
    // Flat search results
    if(filtered.length===0){
      enc.innerHTML = '';
      document.getElementById('no-results').classList.add('show');
      return;
    }
    document.getElementById('no-results').classList.remove('show');
    var h = '<div class="category"><div class="cat-header open" style="cursor:default;"><h2>搜索结果</h2><span class="cat-count">'+filtered.length+'</span></div><div class="cat-body open">';
    filtered.forEach(function(f){ h += renderFieldRow(f); });
    h += '</div></div>';
    enc.innerHTML = h;
  } else {
    document.getElementById('no-results').classList.remove('show');
    // Categorized view
    var h = '';
    allCategories.forEach(function(cat){
      h += '<div class="category"><div class="cat-header" onclick="this.classList.toggle(\'open\');this.nextElementSibling.classList.toggle(\'open\')"><h2>'+esc(cat.name)+'</h2><span class="cat-count">'+cat.fields.length+'</span><span class="cat-arrow">&#9654;</span></div><div class="cat-body">';
      cat.fields.forEach(function(f){ h += renderFieldRow(f); });
      h += '</div></div>';
    });
    enc.innerHTML = h;
  }

  // Update TOC
  var toc = document.getElementById('toc-table');
  var tocH = '<tr><th>#</th><th>类别</th><th style="width:40px">数量</th></tr>';
  allCategories.forEach(function(cat,i){
    tocH += '<tr><td>'+(i+1)+'</td><td><a href="javascript:void(0)" onclick="scrollToCat(\''+esc(cat.name)+'\')" style="color:#58a6ff;text-decoration:none;">'+esc(cat.name)+'</a></td><td>'+cat.fields.length+'</td></tr>';
  });
  toc.innerHTML = tocH;
}

function renderFieldRow(f){
  var desc = (f.description || '').substring(0, 60);
  var cn = f.chinese_name || '';
  var h = '<div class="field-row" onclick="this.classList.toggle(\'expanded\');this.querySelector(\'.field-detail\').classList.toggle(\'open\')">';
  h += '<div class="field-summary">';
  h += '<span class="field-code">'+esc(f.name)+'</span>';
  if(cn) h += '<span class="field-name-cn">'+esc(cn)+'</span>';
  h += '<span class="field-one-liner">'+esc(desc)+(desc.length>=60?'...':'')+'</span>';
  h += '</div>';
  h += '<div class="field-detail">';
  h += '<div class="detail-meaning"><strong>含义：</strong>'+esc(f.description||'')+'</div>';
  h += '<div class="detail-calc"><strong>计算公式：</strong>\n'+esc(f.calculation||'')+'</div>';
  h += '<div class="detail-meta"><span>分类: <strong>'+esc(f.category||'')+'</strong></span></div>';
  h += '</div></div>';
  return h;
}

function scrollToCat(name){
  document.getElementById('search-input').value = '';
  renderAll();
  setTimeout(function(){
    var headers = document.querySelectorAll('.cat-header h2');
    headers.forEach(function(h){
      if(h.textContent === name) h.parentElement.scrollIntoView({behavior:'smooth'});
    });
  },100);
}

function esc(s){
  var d = document.createElement('div'); d.textContent = (s||''); return d.innerHTML;
}

// Init
document.getElementById('search-input').addEventListener('input', renderAll);
loadFields();
</script>
</body>
</html>
'''

with open(DST, 'w', encoding='utf-8') as f:
    f.write(HTML)
print('data_fields.html written OK (' + str(len(HTML)) + ' bytes)')
