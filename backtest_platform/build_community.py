"""Build community.html with likes, comments, admin badge, alpha references."""
import os

DST = os.path.join(os.path.dirname(__file__), 'templates', 'community.html')

HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>社区</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.header{background:#161b22;border-bottom:1px solid #30363d;padding:12px 20px;display:flex;justify-content:center;align-items:center;gap:30px}
.header h1{color:#e94560;font-size:17px}
.header nav{display:flex;gap:24px}
.header nav a{color:#8b949e;text-decoration:none;font-size:12px}
.header nav a:hover,.header nav a.active{color:#58a6ff}
.container{max-width:900px;margin:0 auto;padding:20px}
.post-form{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:24px;position:relative}
.post-form h2{font-size:14px;color:#58a6ff;margin-bottom:16px}
.fg{margin-bottom:14px}
.fg label{display:block;font-size:11px;color:#8b949e;margin-bottom:6px}
.fg input,.fg textarea{width:100%;padding:10px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:13px;font-family:inherit;outline:none;resize:vertical}
.fg input:focus,.fg textarea:focus{border-color:#58a6ff}
.fg textarea{min-height:80px}
.fg textarea.mono{font-family:monospace;color:#58a6ff;min-height:50px}
.btn-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.submit-btn{padding:10px 24px;background:#e94560;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px}
.submit-btn:hover{background:#d63850}
.ref-btn{padding:10px 18px;background:transparent;color:#e6b422;border:1px solid #e6b422;border-radius:6px;cursor:pointer;font-size:13px}
.ref-btn:hover{background:rgba(230,180,34,0.08)}
.selected-badge{display:none;align-items:center;gap:8px;padding:6px 12px;background:rgba(230,180,34,0.06);border:1px solid rgba(230,180,34,0.2);border-radius:6px;font-size:11px}
.selected-badge.show{display:inline-flex}
.selected-badge .expr{font-family:monospace;color:#58a6ff;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.selected-badge .remove{color:#8b949e;cursor:pointer;font-size:15px;line-height:1}
.selected-badge .remove:hover{color:#ff6b6b}
.form-error{color:#ff6b6b;font-size:12px;margin-top:8px;display:none}
.alpha-picker{display:none;position:absolute;z-index:50;background:#161b22;border:1px solid #e6b422;border-radius:8px;width:440px;max-height:380px;overflow:hidden;margin-top:4px;box-shadow:0 8px 24px rgba(0,0,0,0.5)}
.alpha-picker.show{display:block}
.alpha-picker .ph{padding:10px 12px;border-bottom:1px solid #30363d}
.alpha-picker .ph input{width:100%;padding:6px 10px;background:#0d1117;border:1px solid #30363d;border-radius:4px;color:#c9d1d9;font-size:12px;outline:none}
.alpha-picker .pl{overflow-y:auto;max-height:280px}
.alpha-opt{display:flex;flex-direction:column;padding:10px 12px;cursor:pointer;border-bottom:1px solid #21262d;gap:4px}
.alpha-opt:hover{background:rgba(230,180,34,0.06)}
.alpha-opt.selected{background:rgba(230,180,34,0.10);border-left:3px solid #e6b422}
.alpha-opt .expr{font-family:monospace;font-size:11px;color:#58a6ff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.alpha-opt .meta{font-size:10px;color:#8b949e;display:flex;gap:14px}
.alpha-picker .empty{text-align:center;color:#484f58;padding:24px;font-size:12px}
.posts-header{font-size:14px;color:#8b949e;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #30363d}
.post-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:12px}
.post-meta{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:6px}
.post-meta-left{display:flex;align-items:center;gap:8px}
.post-author{font-size:13px;color:#e6b422;font-weight:600}
.admin-badge{display:inline-block;background:#e94560;color:#fff;font-size:9px;padding:1px 5px;border-radius:3px;font-weight:bold}
.post-time{font-size:11px;color:#484f58}
.post-name{font-size:12px;color:#8b949e;margin-bottom:8px}
.post-expr{background:#0d1117;border:1px solid #1c2533;border-radius:6px;padding:10px 14px;font-family:monospace;font-size:13px;color:#58a6ff;margin-bottom:8px;word-break:break-all;line-height:1.5}
.post-desc{font-size:12px;color:#8b949e;line-height:1.6;margin-bottom:8px}
.post-actions{display:flex;gap:12px;align-items:center;margin-top:8px;padding-top:8px;border-top:1px solid #1c2533}
.like-btn{background:none;border:1px solid #30363d;color:#8b949e;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px}
.like-btn:hover{border-color:#e94560;color:#e94560}
.like-btn.liked{border-color:#e94560;color:#e94560;background:rgba(233,69,96,0.1)}
.comment-toggle{background:none;border:1px solid #30363d;color:#8b949e;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:11px}
.comment-toggle:hover{border-color:#58a6ff;color:#58a6ff}
.comments-section{display:none;margin-top:8px;padding:10px;background:#0d1117;border-radius:6px}
.comments-section.open{display:block}
.comment-item{padding:6px 0;border-bottom:1px solid #1c2533;font-size:11px}
.comment-item:last-child{border-bottom:none}
.comment-author{color:#e6b422;font-weight:600}
.comment-time{color:#484f58;font-size:10px;margin-left:8px}
.comment-content{color:#c9d1d9;margin-top:2px}
.comment-form{display:flex;gap:8px;margin-top:8px}
.comment-form input{flex:1;padding:6px 10px;background:#161b22;border:1px solid #30363d;border-radius:4px;color:#fff;font-size:11px;outline:none}
.comment-form input:focus{border-color:#58a6ff}
.comment-form button{padding:6px 12px;background:#1c2533;color:#58a6ff;border:1px solid #30363d;border-radius:4px;cursor:pointer;font-size:11px}
.alpha-ref{background:#0d1117;border:1px solid #e6b422;border-radius:8px;overflow:hidden;margin:8px 0}
.alpha-ref .ref-head{background:rgba(230,180,34,0.08);padding:8px 14px;font-size:11px;color:#e6b422;font-weight:600}
.alpha-ref .ref-body{padding:12px 14px}
.alpha-ref .ref-expr{font-family:monospace;font-size:12px;color:#58a6ff;word-break:break-all;padding:8px 10px;border-radius:4px;margin-bottom:12px}
.alpha-ref table{width:100%;font-size:11px;border-collapse:collapse}
.alpha-ref th{text-align:left;color:#484f58;font-weight:normal;padding:3px 8px 3px 0;width:22%}
.alpha-ref td{color:#c9d1d9;padding:3px 0;width:28%}
.loading{text-align:center;padding:40px;color:#8b949e;font-size:13px}
.empty{text-align:center;padding:60px;color:#484f58;font-size:13px}
.delete-btn{background:none;border:1px solid #ff6b6b;color:#ff6b6b;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:10px}
</style>
</head>
<body>
<div class="header">
  <h1>社区</h1>
  <nav><a href="/dashboard">仪表盘</a><a href="/alpha_history">Alpha历史</a><a href="/data_fields">数据字段</a><a href="/operators">操作符</a><a href="/community" class="active">社区</a><a href="/learn">学习</a></nav>
  <span style="font-size:12px;color:#8b949e">{{ username }} | <a href="/logout" style="color:#8b949e">退出</a></span>
</div>
<div class="container">
  <div class="post-form">
    <h2>分享你的 Alpha 表达式</h2>
    <div class="fg"><label>表达式 <span style="color:#e94560">*</span></label><textarea id="expr-input" class="mono" placeholder="例如: rank(ts_delta(close, 20))" rows="2"></textarea></div>
    <div class="fg"><label>名称</label><input type="text" id="name-input" placeholder="给你的因子起个名字" maxlength="100"></div>
    <div class="fg"><label>说明</label><textarea id="desc-input" placeholder="描述逻辑、灵感来源或使用心得..." rows="3"></textarea></div>
    <div class="btn-row">
      <button class="submit-btn" id="submit-btn" onclick="submitPost()">发布</button>
      <button class="ref-btn" id="ref-btn" onclick="toggleAlphaPicker()">引用 Alpha</button>
      <span class="selected-badge" id="selected-badge">
        <span class="expr" id="selected-expr"></span>
        <span class="remove" onclick="removeAlphaRef(event)" title="取消引用">&times;</span>
      </span>
    </div>
    <div class="form-error" id="form-error"></div>
    <div class="alpha-picker" id="alpha-picker">
      <div class="ph"><input type="text" id="picker-search" placeholder="搜索 Alpha..." oninput="filterAlphaList()"></div>
      <div class="pl" id="picker-list"></div>
    </div>
  </div>

  <div class="posts-header" id="posts-header">加载中...</div>
  <div id="posts-container"></div>
</div>

<script>
(function loadChartJS(){if(typeof Chart!=="undefined")return;var s=document.createElement("script");s.src="/static/chart.umd.min.js";s.onerror=function(){console.warn("Chart.js unavailable");};document.head.appendChild(s);})();
function genDates(y,m,d,len){var result=[],dt=new Date(Date.UTC(y,m-1,d)),safety=0;while(result.length<len&&safety<len*3){var w=dt.getUTCDay();if(w!==0&&w!==6){result.push(dt.getUTCFullYear()+'-'+String(dt.getUTCMonth()+1).padStart(2,'0')+'-'+String(dt.getUTCDate()).padStart(2,'0'));}dt.setUTCDate(dt.getUTCDate()+1);safety++;}return result;}
function downsample(arr,targetLen){if(!arr||arr.length<=targetLen)return arr||[];var step=arr.length/targetLen,result=[];for(var j=0;j<targetLen;j++){var lo=Math.floor(j*step),hi=Math.floor((j+1)*step),s=0,n=0;for(var k=lo;k<hi&&k<arr.length;k++){if(arr[k]!=null){s+=arr[k];n++;}}result.push(n>0?s/n:null);}return result;}

var selectedAlphaId=null, selectedAlphaExpr='';
var alphaList=[];
function esc(s){var d=document.createElement("div");d.textContent=s||"";return d.innerHTML;}
function fmtTime(ts){if(!ts||ts.length<16)return ts||'';return ts.substring(0,10)+' '+ts.substring(11,16);}
function fmtNum(v,d){if(v==null||isNaN(v))return'-';return Number(v).toFixed(d||3);}
function byId(id){return document.getElementById(id);}

// Alpha Picker
async function toggleAlphaPicker(){
  var p=byId("alpha-picker");
  if(p.classList.contains("show")){p.classList.remove("show");return;}
  if(alphaList.length===0){
    try{var r=await fetch("/api/alpha/history");var d=await r.json();alphaList=d.records||[];}catch(e){alphaList=[];}
  }
  renderAlphaOptions(alphaList);
  p.classList.add("show");
  byId("picker-search").value='';
  setTimeout(function(){document.addEventListener("click",closeAlphaPicker);},0);
}
function closeAlphaPicker(e){
  var p=byId("alpha-picker"), btn=byId("ref-btn");
  if(!p.contains(e.target)&&e.target!==btn){p.classList.remove("show");document.removeEventListener("click",closeAlphaPicker);}
}
function renderAlphaOptions(list){
  var c=byId("picker-list");
  if(!list.length){c.innerHTML='<div class="empty">暂无 Alpha 历史<p style="color:#30363d;margin-top:4px">请先运行回测</p></div>';return;}
  var h='';
  list.forEach(function(a){
    var m=a.metrics||{}, sel=a.id===selectedAlphaId?' selected':'';
    h+='<div class="alpha-opt'+sel+'" onclick="selectAlpha(this)" data-id="'+a.id+'" data-expr="'+esc(a.expression).replace(/"/g,'&quot;')+'">';
    h+='<div class="expr">'+esc((a.name||a.expression||'').substring(0,80))+'</div>';
    h+='<div class="meta"><span>IC '+fmtNum(m.pearson_ic,4)+'</span><span>Sharpe '+fmtNum(m.sharpe,2)+'</span></div></div>';
  });
  c.innerHTML=h;
}
function filterAlphaList(){
  var q=(byId("picker-search").value||'').toLowerCase();
  var filtered=q?alphaList.filter(function(a){return(a.name||'').toLowerCase().indexOf(q)>=0||(a.expression||'').toLowerCase().indexOf(q)>=0;}):alphaList;
  renderAlphaOptions(filtered);
}
function selectAlpha(el){
  selectedAlphaId=el.dataset.id; selectedAlphaExpr=el.dataset.expr;
  byId("expr-input").value=selectedAlphaExpr;
  document.querySelectorAll(".alpha-opt").forEach(function(o){o.classList.remove("selected");});
  el.classList.add("selected");
  byId("selected-expr").textContent=selectedAlphaExpr.substring(0,50);
  byId("selected-badge").classList.add("show");
  byId("alpha-picker").classList.remove("show");
  document.removeEventListener("click",closeAlphaPicker);
}
function removeAlphaRef(e){if(e)e.stopPropagation();selectedAlphaId=null;selectedAlphaExpr='';byId("selected-badge").classList.remove("show");}

// Submit post
async function submitPost(){
  var expr=(byId("expr-input").value||'').trim();
  if(!expr){byId("form-error").style.display="block";byId("form-error").textContent="请输入表达式";return;}
  byId("form-error").style.display="none";
  var name=(byId("name-input").value||'').trim();
  var desc=(byId("desc-input").value||'').trim();
  var body={expression:expr,name:name,description:desc};
  if(selectedAlphaId)body.alpha_id=selectedAlphaId;
  try{
    var r=await fetch("/api/community/posts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    var d=await r.json();
    if(d.error){byId("form-error").style.display="block";byId("form-error").textContent=d.error;return;}
    byId("expr-input").value='';byId("name-input").value='';byId("desc-input").value='';
    removeAlphaRef();
    loadPosts();
  }catch(e){byId("form-error").style.display="block";byId("form-error").textContent="发布失败: "+e.message;}
}

// Load posts
async function loadPosts(){
  byId("posts-header").textContent="加载中...";
  byId("posts-container").innerHTML='<div class="loading">加载中...</div>';
  try{
    var r=await fetch("/api/community/posts");var d=await r.json();
    if(d.error){byId("posts-header").textContent="加载失败";return;}
    var posts=d.posts||[];
    byId("posts-header").textContent="全部帖子 ("+d.count+" 篇)";
    if(!posts.length){byId("posts-container").innerHTML='<div class="empty">还没有帖子<p>填写上面的表单，成为第一个分享的人</p></div>';return;}
    var isAdmin='{{ is_admin }}'==='True';
    var h='';
    posts.forEach(function(p){
      h+='<div class="post-card">';
      h+='<div class="post-meta">';
      h+='<div class="post-meta-left">';
      h+='<span class="post-author">'+esc(p.author_display||p.author||'匿名')+'</span>';
      if(p.is_admin)h+='<span class="admin-badge">管理员</span>';
      h+='<span class="post-time">'+fmtTime(p.timestamp)+'</span>';
      h+='</div>';
      if(isAdmin)h+='<button class="delete-btn" onclick="deletePost(\''+p.id+'\')">删除</button>';
      h+='</div>';
      if(p.name)h+='<div class="post-name">'+esc(p.name)+'</div>';
      h+='<div class="post-expr">'+esc(p.expression)+'</div>';
      if(p.alpha_ref&&p.alpha_ref.expression){
        var ref=p.alpha_ref, m=ref.metrics||{};
        h+='<div class="alpha-ref"><div class="ref-head">&#9733; 引用的 Alpha</div><div class="ref-body">';
        h+='<div class="ref-expr">'+esc(ref.expression)+'</div>';
        h+='<table><tr><th>IC</th><td>'+fmtNum(m.pearson_ic,4)+'</td><th>Sharpe</th><td>'+fmtNum(m.sharpe,2)+'</td></tr>';
        h+='<tr><th>年化收益</th><td>'+fmtNum((m.annual_excess||0)*100,1)+'%</td><th>Fitness</th><td>'+fmtNum(m.fitness,2)+'</td></tr></table>';
        h+='</div></div>';
        h+='<div style="margin-top:6px;"><canvas id="refpnl-'+p.id+'" style="height:160px;width:100%!important;max-width:100%"></canvas></div>';
      }
      if(p.description)h+='<div class="post-desc">'+esc(p.description).replace(/\n/g,"<br>")+'</div>';
      h+='<div class="post-actions">';
      h+='<button class="like-btn'+(p.liked_by_me?' liked':'')+'" onclick="toggleLike(\''+p.id+'\',this)">&#10084; <span>'+((p.likes||0)>0?p.likes:'点赞')+'</span></button>';
      h+='<button class="comment-toggle" onclick="toggleComments(\''+p.id+'\',this)">评论</button>';
      h+='</div>';
      h+='<div class="comments-section" id="comments-'+p.id+'"><div style="color:#8b949e;font-size:11px;">加载中...</div></div>';
      h+='</div>';
    });
    byId("posts-container").innerHTML=h;
    // Draw PnL charts for alpha refs
    if(typeof Chart!=="undefined"){setTimeout(function(){posts.forEach(function(p){if(p.alpha_ref&&p.alpha_ref.pnl_series&&p.alpha_ref.pnl_series.length){var c=document.getElementById("refpnl-"+p.id);if(c){var d=downsample(p.alpha_ref.pnl_series,200);new Chart(c.getContext("2d"),{type:"line",data:{labels:d.map(function(_,j){return j+1;}),datasets:[{label:"PnL",data:d,borderColor:"#f0883e",borderWidth:1.5,pointRadius:0,spanGaps:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{display:false},y:{grid:{color:"#21262d"}}}}});}}});},300);}
  }catch(e){byId("posts-container").innerHTML='<div class="empty">加载失败: '+e.message+'</div>';}
}

// Like
async function toggleLike(postId,btn){
  try{
    var r=await fetch("/api/community/posts/"+postId+"/like",{method:"POST"});
    var d=await r.json();
    if(d.error)return;
    if(d.liked){btn.classList.add("liked");}else{btn.classList.remove("liked");}
    btn.querySelector("span").textContent=d.likes>0?d.likes:"点赞";
  }catch(e){}
}

// Comments
var commentsCache={};
async function toggleComments(postId,btn){
  var sec=byId("comments-"+postId);
  if(sec.classList.contains("open")){sec.classList.remove("open");return;}
  sec.classList.add("open");
  sec.innerHTML='<div style="color:#8b949e;font-size:11px;">加载中...</div>';
  try{
    var r=await fetch("/api/community/posts/"+postId+"/comments");
    var d=await r.json();
    var comments=d.comments||[];
    var h='';
    comments.forEach(function(c){
      h+='<div class="comment-item">';
      h+='<span class="comment-author">'+esc(c.author_display||c.author||'匿名')+'</span>';
      if(c.is_admin)h+='<span class="admin-badge">管理员</span>';
      h+='<span class="comment-time">'+fmtTime(c.timestamp)+'</span>';
      h+='<div class="comment-content">'+esc(c.content)+'</div>';
      h+='</div>';
    });
    if(!comments.length)h+='<div style="color:#484f58;font-size:11px;padding:8px 0;">暂无评论</div>';
    h+='<div class="comment-form"><input type="text" id="cmt-'+postId+'" placeholder="写评论..."><button onclick="submitComment(\''+postId+'\')">发送</button></div>';
    sec.innerHTML=h;
  }catch(e){sec.innerHTML='<div style="color:#ff6b6b;font-size:11px;">加载失败</div>';}
}

async function submitComment(postId){
  var inp=byId("cmt-"+postId);
  var content=(inp.value||'').trim();
  if(!content)return;
  try{
    var r=await fetch("/api/community/posts/"+postId+"/comments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({content:content})});
    var d=await r.json();
    if(d.error){alert(d.error);return;}
    inp.value='';
    var sec=byId("comments-"+postId);
    var newCmt='<div class="comment-item"><span class="comment-author">'+esc(d.author_display)+'</span>';
    if(d.is_admin)newCmt+='<span class="admin-badge">管理员</span>';
    newCmt+='<span class="comment-time">'+fmtTime(d.timestamp)+'</span>';
    newCmt+='<div class="comment-content">'+esc(d.content)+'</div></div>';
    var formHtml=sec.innerHTML.substring(sec.innerHTML.lastIndexOf('<div class="comment-form">'));
    sec.innerHTML=sec.innerHTML.replace(formHtml,'')+newCmt+formHtml;
  }catch(e){alert("评论失败: "+e.message);}
}

async function deletePost(id){
  if(!confirm("确认删除？"))return;
  try{await fetch("/api/community/posts/"+id,{method:"DELETE"});loadPosts();}catch(e){}
}

loadPosts();
</script>
</body>
</html>
'''

with open(DST, 'w', encoding='utf-8') as f:
    f.write(HTML)
print('community.html written OK (' + str(len(HTML)) + ' bytes)')
