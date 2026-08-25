export function escapeHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
function renderInline(text){
  let out=text;
  out=out.replace(/`([^`]+)`/g,"<code>$1</code>");
  out=out.replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>");
  out=out.replace(/\*([^*]+)\*/g,"<em>$1</em>");
  return out;
}
export function renderMarkdown(source){
  const src=escapeHtml(source).replace(/\r\n/g,"\n");
  const parts=src.split(/```(?:[a-zA-Z0-9_-]*)\n?/);
  let html="";
  for(let i=0;i<parts.length;i++){
    if(i%2===1){ html+=`<pre><code>${parts[i].replace(/\n$/,"")}</code></pre>`; continue; }
    html+=renderBlock(parts[i]);
  }
  return html;
}
function renderBlock(text){
  const lines=text.split("\n");
  const out=[]; let list=null; let para=[];
  const flushPara=()=>{ if(para.length){ out.push(`<p>${renderInline(para.join("<br>"))}</p>`); para=[]; } };
  const flushList=()=>{ if(list){ out.push(`</${list}>`); list=null; } };
  for(const raw of lines){
    const line=raw.trimEnd();
    if(!line.trim()){ flushPara(); flushList(); continue; }
    const heading=line.match(/^(#{1,3})\s+(.*)$/);
    if(heading){ flushPara(); flushList(); const level=heading[1].length+2; out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`); continue; }
    const ul=line.match(/^\s*[-*•]\s+(.*)$/);
    if(ul){ flushPara(); if(list!=="ul"){ flushList(); out.push("<ul>"); list="ul"; } out.push(`<li>${renderInline(ul[1])}</li>`); continue; }
    const ol=line.match(/^\s*\d+[.)]\s+(.*)$/);
    if(ol){ flushPara(); if(list!=="ol"){ flushList(); out.push("<ol>"); list="ol"; } out.push(`<li>${renderInline(ol[1])}</li>`); continue; }
    para.push(line);
  }
  flushPara(); flushList();
  return out.join("");
}
