import { showToast } from '../utils/toast.js'

export default function Topbar({ title, conversationId, onUpload }){
  const path = conversationId ? `/app/${conversationId}` : "/app"
  const copy = async () => {
    const url = window.location.href
    const doCopy = async (text) => {
      // Try modern clipboard first (requires secure context), fallback to execCommand for http://0.0.0.0:8000
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
        return true
      }
      // Fallback for http
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      ta.style.top = '0'
      document.body.appendChild(ta)
      ta.focus()
      ta.select()
      let ok = false
      try { ok = document.execCommand('copy') } catch {}
      ta.remove()
      return ok
    }
    try {
      const ok = await doCopy(url)
      if (!ok) throw new Error('copy failed')
      const btn=document.getElementById("copyLinkBtn")
      if(btn){ btn.textContent="Copied!"; btn.classList.add("copied"); setTimeout(()=>{btn.textContent="Copy link"; btn.classList.remove("copied")},1500) }
      showToast("Link copied — share this chat URL", "success")
    } catch {
      showToast("Could not copy link. Copy manually: " + url, "error")
      // As last resort, prompt with URL
      window.prompt("Copy this link:", url)
    }
  }
  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-title">{title || "New chat"}</div>
        <div className="topbar-url-row" title={window.location.origin+path}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
          <a className="topbar-url" href={path} onClick={(e)=>{ e.preventDefault(); copy(); }}>{path}</a>
          <button id="copyLinkBtn" className="topbar-copy" onClick={copy}>Copy link</button>
        </div>
      </div>
      <div className="topbar-actions">
        <span className="topbar-model">gpt-oss · routed</span>
        <label className="upload-btn" htmlFor="fileInput">Upload</label>
        <input type="file" id="fileInput" multiple accept=".pdf,.docx,.txt" style={{position:'absolute',width:1,height:1,opacity:0}} onChange={onUpload} />
      </div>
    </header>
  )
}
