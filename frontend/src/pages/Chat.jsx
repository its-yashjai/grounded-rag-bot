import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import * as API from '../api.js'
import { renderMarkdown, escapeHtml } from '../utils/markdown.js'
import Sidebar from '../components/Sidebar.jsx'
import Topbar from '../components/Topbar.jsx'
import { showToast, showErrorToast } from '../utils/toast.js'

export default function ChatPage(){
  const { id } = useParams()
  const navigate = useNavigate()
  const currentId = id || null
  const [messages, setMessages] = useState([])
  const [title, setTitle] = useState("New chat")
  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const [citations, setCitations] = useState([])
  const scrollRef = useRef(null)
  const controllerRef = useRef(null)
  const [docs, setDocs] = useState([])
  const [docCount, setDocCount] = useState(0)
  const [sourcesModal, setSourcesModal] = useState(null) // {citations, meta} or null

  // load docs
  const refreshDocs = async ()=>{
    try{
      const list = await API.listDocuments()
      setDocs(list)
      setDocCount(list.filter(d=>d.processing_status==="ready").length)
    }catch{}
  }
  useEffect(()=>{ refreshDocs(); const t=setInterval(refreshDocs,3000); return ()=>clearInterval(t)},[])

  const justCreatedRef = useRef(null)
  // load conversation when id changes
  useEffect(()=>{
    if(!currentId){
      setMessages([])
      setTitle("New chat")
      return
    }
    // If we just created this chat via stream, keep local messages (already have user+assistant)
    // and only fetch if we don't already have messages for this id or if navigating to an old chat
    if(justCreatedRef.current === currentId && messages.length>0){
      justCreatedRef.current = null
      API.getConversation(currentId).then(conv=>{
        if(conv) setTitle(conv.title)
      })
      return
    }
    justCreatedRef.current = null
    API.getConversation(currentId).then(conv=>{
      if(conv){
        setMessages(conv.messages||[])
        setTitle(conv.title)
      } else {
        navigate('/app', {replace:true})
      }
    })
  },[currentId])

  const scrollToBottom=()=>{
    const el=scrollRef.current
    if(el) el.scrollTop=el.scrollHeight
  }
  useEffect(()=>{ scrollToBottom() },[messages])
  // close sources modal on Escape
  useEffect(()=>{
    const onKey=(e)=>{ if(e.key==="Escape") setSourcesModal(null) }
    window.addEventListener("keydown", onKey)
    return ()=>window.removeEventListener("keydown", onKey)
  },[])

  const handleNewChat=()=>{
    if(streaming && controllerRef.current) controllerRef.current.abort()
    navigate('/app')
  }

  const send = async (textOverride)=>{
    const text = (textOverride ?? input).trim()
    if(!text || streaming) return
    if(docCount===0){
      alert("Upload at least one document first.")
      return
    }
    const userMsg={role:"user", content:text}
    setMessages(prev=>[...prev, userMsg])
    setInput("")
    // placeholder assistant
    const placeholder={role:"assistant", content:"", citations:[], streaming:true}
    setMessages(prev=>[...prev, placeholder])
    setStreaming(true)

    const docIds = docs.filter(d=>d.processing_status==="ready").map(d=>d.document_id)
    const convId = currentId // null for new chat -> backend will create, instant
    const controller=new AbortController()
    controllerRef.current=controller

    let answerText=""
    let currentCitations=[]

    await API.streamChat(text, docIds, convId, {
      signal: controller.signal,
      onConversation: (newId)=>{
        if(newId && newId!==currentId){
          // instant URL update — new chat gets unique URL without waiting for full answer
          justCreatedRef.current = newId
          navigate(`/app/${newId}`, {replace:true})
          // chat name = single first query only, never overwrite with follow-ups
          setTitle(prev => (prev === "New chat" || !prev) ? text.slice(0,60) : prev)
        }
      },
      onCitations: (data)=>{
        currentCitations=data
        setCitations(data)
        setMessages(prev=>{
          const copy=[...prev]
          const last=copy[copy.length-1]
          if(last && last.role==="assistant") last.citations=data
          return copy
        })
      },
      onToken: (delta)=>{
        answerText+=delta
        setMessages(prev=>{
          const copy=[...prev]
          const last=copy[copy.length-1]
          if(last && last.role==="assistant") last.content=answerText
          return [...copy]
        })
        // scroll
        setTimeout(scrollToBottom,0)
      },
      onDone: (info)=>{
        setMessages(prev=>{
          const copy=[...prev]
          const last=copy[copy.length-1]
          if(last && last.role==="assistant"){
            last.content=answerText
            last.citations=currentCitations
            last.streaming=false
            last.meta=info
          }
          return [...copy]
        })
        setStreaming(false)
        controllerRef.current=null
        // refresh sidebar will happen via navigation
      },
      onError: (err)=>{
        if(err?.name==="AbortError"){
          setMessages(prev=>{
            const copy=[...prev]
            const last=copy[copy.length-1]
            if(last) last.content = (last.content||"")+" …"
            return copy
          })
        } else {
          setMessages(prev=>{
            const copy=[...prev]
            const last=copy[copy.length-1]
            if(last) last.content="Something went wrong. Please try again."
            return copy
          })
        }
        setStreaming(false)
        controllerRef.current=null
      }
    })
  }

  const handleUpload=async(e)=>{
    const files=e.target.files
    if(!files?.length) return
    const toast = showToast(`Uploading ${files.length} document${files.length>1?'s':''} — ${Array.from(files).map(f=>f.name).join(", ")}`, "loading")
    try{
      const res = await API.uploadDocuments(Array.from(files))
      toast.remove()
      showToast(`✓ Uploaded ${res.documents.length} document${res.documents.length>1?'s':''} — ${res.documents.map(d=>d.filename).join(", ")}`, "success")
      refreshDocs()
    }catch(err){
      toast.remove()
      showErrorToast(err.message || "Upload failed")
    }
    e.target.value=""
  }

  const hasMessages = messages.length>0

  return (
    <>
      <div className="app-shell">
        <Sidebar currentId={currentId} onNewChat={handleNewChat} />
        <div className="sidebar-overlay" id="sidebarOverlay"></div>
        <main className="main-area">
        <Topbar title={title} conversationId={currentId} onUpload={handleUpload} />
        <section className="chat-main">
          {!hasMessages ? (
            <div className="greet-state">
              <div className="landing-hero">
                <div className="greet-mark"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/></svg></div>
                <h1>Ask your documents <em>anything.</em></h1>
                <p>Each chat is a isolated workspace with its own URL. Grounded, cited, private. {docCount===0 ? "Start by adding documents." : `${docCount} document${docCount>1?'s':''} indexed — ready to chat.`}</p>
                <div className="hero-stats">
                  <div className="hero-stat"><span className="hero-stat-num">{docCount}</span><span className="hero-stat-label">Documents ready</span></div>
                  <div className="hero-stat"><span className="hero-stat-num">∞</span><span className="hero-stat-label">Chats · unique URLs</span></div>
                  <div className="hero-stat"><span className="hero-stat-num">Cited</span><span className="hero-stat-label">Every answer</span></div>
                </div>
                <div className="suggestion-row">
                  <button className="suggestion-chip" onClick={()=>send("Summarize the key findings across all documents.")}>Summarize key findings</button>
                  <button className="suggestion-chip" onClick={()=>send("What are the main costs and how can they be reduced?")}>Costs & savings</button>
                  <button className="suggestion-chip" onClick={()=>send("Compare the approaches described in the documents.")}>Compare approaches</button>
                  <button className="suggestion-chip" onClick={()=>send("What does the subsidy scheme cover and who is eligible?")}>Subsidy details</button>
                </div>
                {docCount===0 && (
                  <label className="hero-upload" htmlFor="fileInput">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 16V4M7 9l5-5 5 5M4 20h16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    Upload documents to begin
                  </label>
                )}
                <div className="feature-grid">
                  <div className="feature-card"><h4>Grounded</h4><p>Answers only from your uploads — refuses rather than hallucinates.</p></div>
                  <div className="feature-card"><h4>Cited</h4><p>Every claim links to exact document & page.</p></div>
                  <div className="feature-card"><h4>Private</h4><p>Chats are isolated, shareable via unique URL.</p></div>
                </div>
              </div>
            </div>
          ) : (
            <div className="chat-scroll" ref={scrollRef}>
              <div className="thread-col">
                {messages.map((m,i)=>{
                  if(m.role==="user"){
                    return <div key={i} className="msg user"><div className="msg-bubble">{m.content}</div></div>
                  }
                  const isStreaming = m.streaming
                  return (
                    <div key={i} className="msg assistant">
                      <div className="msg-row">
                        <span className="assistant-mark"><svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/></svg></span>
                        <div
                          className="msg-bubble md"
                          onClick={(e)=>{
                            const t=e.target
                            if(t.classList && t.classList.contains('src-ref')){
                              setSourcesModal({citations: m.citations || [], meta: m.meta})
                            }
                          }}
                          dangerouslySetInnerHTML={{__html: m.content ? renderMarkdown(m.content).replace(/\[Source (\d+)\]/g,'<sup class="src-ref" data-idx="$1">[$1]</sup>') : isStreaming ? '<span class="pipeline-state">Searching your documents... <span class="typing-dot"><span></span><span></span><span></span></span></span>' : ''}} />
                      </div>
                      {/* Response first, then View Sources button (sources only in modal until clicked) and metrics */}
                      {m.citations?.length>0 && (
                        <button className="view-sources-btn" onClick={()=>setSourcesModal({citations: m.citations, meta: m.meta})}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M4 4h11l5 5v11a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.6"/><path d="M15 4v5h5" stroke="currentColor" strokeWidth="1.3"/></svg>
                          View Sources ({m.citations.length})
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" style={{marginLeft:4}}><path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        </button>
                      )}
                      {m.meta && (
                        <div className="msg-meta">
                          {m.meta.latency_ms && `${Math.round(m.meta.latency_ms)}ms · `}
                          {m.meta.cache_hit!==undefined && (m.meta.cache_hit ? "Cached" : "Fresh retrieval") + " · "}
                          {m.meta.estimated_cost_usd!==undefined && `$${Number(m.meta.estimated_cost_usd).toFixed(6)} · `}
                          {m.meta.model && <span className="model-badge">{m.meta.model}</span>}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          <div className="composer">
            <div className="composer-wrap">
              <label className="composer-attach" htmlFor="fileInput" title="Upload documents">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M16.5 13.5L9 21a3 3 0 01-4.24-4.24l9-9a2 2 0 012.83 2.83L8.5 18.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </label>
              <textarea
                value={input}
                onChange={e=>setInput(e.target.value)}
                onKeyDown={e=>{ if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); send(); }}}
                placeholder="Ask anything about your documents..."
                rows={1}
                style={{height:'auto'}}
                onInput={e=>{ e.target.style.height='auto'; e.target.style.height=Math.min(e.target.scrollHeight,160)+'px'}}
              />
              <button className={`send-btn ${streaming?'stop':''}`} onClick={()=> streaming ? (controllerRef.current?.abort()) : send()} aria-label={streaming?"Stop":"Send"}>
                {streaming ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M6 6h12v12H6z" fill="currentColor"/></svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                )}
              </button>
            </div>
            <div className="composer-meta">
              <span className="composer-hint"><kbd>↵</kbd> send · <kbd>⇧↵</kbd> new line</span>
              <span className="composer-note">Each chat keeps its own URL — follow-ups stay here.</span>
            </div>
          </div>
        </section>
        </main>
      </div>
      {/* Sources modal — in front of chat with blur bg, shows cached + cost */}
      {sourcesModal && (
        <div className="sources-modal-overlay" onClick={()=>setSourcesModal(null)}>
          <div className="sources-modal" onClick={e=>e.stopPropagation()}>
            <div className="sources-modal-header">
              <div>
                <div className="sources-modal-title">Sources — grounded in your documents</div>
                <div className="sources-modal-sub">
                  {sourcesModal.citations.length} document{sourcesModal.citations.length>1?'s':''}
                  {sourcesModal.meta?.cache_hit!==undefined && ` · ${sourcesModal.meta.cache_hit ? "Cached" : "Fresh retrieval"}`}
                  {sourcesModal.meta?.estimated_cost_usd!==undefined && ` · $${Number(sourcesModal.meta.estimated_cost_usd).toFixed(6)}`}
                  {sourcesModal.meta?.model && ` · ${sourcesModal.meta.model}`}
                  {sourcesModal.meta?.latency_ms && ` · ${Math.round(sourcesModal.meta.latency_ms)}ms`}
                </div>
              </div>
              <button className="sources-modal-close" onClick={()=>setSourcesModal(null)} aria-label="Close">×</button>
            </div>
            <div className="sources-modal-body">
              {sourcesModal.citations.map((c,idx)=>(
                <div key={idx} className="source-card" style={{marginBottom: idx===sourcesModal.citations.length-1?0:12}}>
                  <div className="source-card-header">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" style={{flexShrink:0}}><path d="M4 4h11l5 5v11a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.6"/><path d="M15 4v5h5" stroke="currentColor" strokeWidth="1.3"/></svg>
                    <span className="source-filename">{c.filename}</span>
                    {c.page_number && <span className="source-page">p. {c.page_number}</span>}
                    {c.section && <span className="source-page">{c.section}</span>}
                  </div>
                  <div className="source-excerpt">{c.excerpt}</div>
                  {c.score!==undefined && <div className="source-score">Relevance {(c.score*100).toFixed(1)}%</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
