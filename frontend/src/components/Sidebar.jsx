import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as API from '../api.js'

function groupLabel(days){
  if(days<1) return "Today";
  if(days<2) return "Yesterday";
  if(days<7) return "Previous 7 days";
  if(days<30) return "Previous 30 days";
  return "Older";
}
function daysAgo(s){
  if(!s) return 999;
  const iso=s.includes("T")?s:s.replace(" ","T");
  const d=new Date(iso);
  if(isNaN(d)) return 999;
  return (Date.now()-d)/86400000;
}

export default function Sidebar({ currentId, onNewChat }){
  const [conversations, setConversations]=useState([])
  const [q,setQ]=useState("")
  const navigate=useNavigate()

  const refresh=async()=>{
    try{
      const list=await API.listConversations()
      setConversations(list)
    }catch{}
  }
  useEffect(()=>{ refresh(); },[currentId])
  useEffect(()=>{
    const id=setTimeout(refresh, 120)
    return ()=>clearTimeout(id)
  },[q])

  const visible=conversations.filter(c=>!(c.message_count===0 && c.title==="New chat" && c.conversation_id!==currentId))
  const filtered=q?visible.filter(c=>c.title.toLowerCase().includes(q.toLowerCase())||(c.preview||"").toLowerCase().includes(q.toLowerCase())):visible

  const buckets=new Map()
  for(const c of filtered){
    const label=groupLabel(daysAgo(c.updated_at))
    if(!buckets.has(label)) buckets.set(label,[])
    buckets.get(label).push(c)
  }
  const order=["Today","Yesterday","Previous 7 days","Previous 30 days","Older"]

  const handleDelete=async(id,e)=>{
    e.stopPropagation()
    if(!confirm("Delete this chat?")) return
    await API.deleteConversation(id)
    if(id===currentId) onNewChat()
    else refresh()
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <span className="brand-mark"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/></svg></span>
          <span className="brand-name">Domain Knowledge Bot</span>
        </div>
      </div>
      <div className="sidebar-action">
        <button className="new-chat-btn" onClick={onNewChat}>
          <span className="new-chat-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg></span>
          New chat
        </button>
      </div>
      <div className="sidebar-search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.6"/><path d="M20 20l-3.5-3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
        <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search chats" />
      </div>
      <nav className="sidebar-nav">
        <div className="chat-groups">
          {visible.length===0 ? (
            <div className="chat-list-empty">No conversations yet<br/><span style={{color:'var(--text-muted)',fontSize:'11.5px'}}>Start a chat to see it here</span></div>
          ) : filtered.length===0 ? (
            <div className="chat-search-empty">No results for “{q}”</div>
          ) : order.filter(l=>buckets.has(l)).map(label=>(
            <div className="chat-group" key={label}>
              <div className="chat-group-label">{label}</div>
              <div className="chat-group-items">
                {buckets.get(label).map(c=>(
                  <div key={c.conversation_id} className={`chat-item ${c.conversation_id===currentId?'active':''}`} onClick={()=>navigate(`/app/${c.conversation_id}`)} title={c.title}>
                    <svg className="chat-item-icon" width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M4 5h16v11H8l-4 4V5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/></svg>
                    <div className="chat-item-main">
                      <span className="chat-item-title">{c.title}</span>
                      {c.preview && <span className="chat-item-preview">{c.preview}</span>}
                    </div>
                    <button className="chat-item-btn danger delete" onClick={(e)=>handleDelete(c.conversation_id,e)} aria-label="Delete">×</button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="nav-group nav-group--library">
          <div className="nav-group-label">Library</div>
          <a className="nav-item" href="/documents">Documents</a>
          <a className="nav-item" href="/observability">Observability</a>
        </div>
      </nav>
      <div className="sidebar-footer">
        <div className="sidebar-user">
          <div className="user-avatar">DK</div>
          <div className="user-meta"><div className="user-name">Workspace</div><div className="user-sub">Grounded · Private</div></div>
        </div>
      </div>
    </aside>
  )
}
