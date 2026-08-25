import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as API from '../api.js'
import { showToast, showErrorToast } from '../utils/toast.js'

export default function Observability(){
  const navigate = useNavigate()
  const [summary,setSummary]=useState(null)
  const [recent,setRecent]=useState([])
  const refresh=()=>{
    fetch('/api/v1/metrics/summary').then(r=>r.json()).then(setSummary).catch(()=>{})
    fetch('/api/v1/metrics').then(r=>r.json()).then(setRecent).catch(()=>{})
  }
  useEffect(()=>{ refresh(); const t=setInterval(refresh,3000); return ()=>clearInterval(t)},[])
  const handleUpload=async(e)=>{
    const files=e.target.files
    if(!files?.length) return
    const toast = showToast(`Uploading ${files.length} document${files.length>1?'s':''} — ${Array.from(files).map(f=>f.name).join(", ")}`, "loading")
    try{
      const res = await API.uploadDocuments(Array.from(files))
      toast.remove()
      showToast(`✓ Uploaded ${res.documents.length} document${res.documents.length>1?'s':''} — ${res.documents.map(d=>d.filename).join(", ")}`, "success")
    }catch(err){
      toast.remove()
      showErrorToast(err.message || "Upload failed")
    }
    e.target.value=""
  }
  if(!summary) return <div className="page"><p style={{color:'var(--text-faint)'}}>Loading metrics...</p></div>
  const hitRate = summary.cache_hit_rate ? `${(summary.cache_hit_rate*100).toFixed(1)}%` : "0%"
  return (
    <div className="page">
      <button className="back-btn" onClick={()=> window.history.length>1 ? navigate(-1) : navigate('/app')} aria-label="Go back">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
        Back
      </button>
      <header className="page-header">
        <div>
          <h1>Observability</h1>
          <div className="page-sub">Latency, cache, tokens and cost — grounded retrieval at a glance.</div>
        </div>
        <div style={{display:'flex', gap:8}}>
          <label className="upload-btn" htmlFor="obsUpload" style={{background:'var(--text)', color:'var(--bg)', borderColor:'var(--text)'}}>Upload</label>
          <input id="obsUpload" type="file" multiple accept=".pdf,.docx,.txt" style={{display:'none'}} onChange={handleUpload} />
          <Link to="/app" style={{padding:'7px 12px', borderRadius:999, border:'1px solid var(--border)', background:'var(--card)', fontSize:13, fontWeight:600}}>Open Chat</Link>
        </div>
      </header>

      <div className="metrics-grid">
        <div className="metric-card"><div className="metric-label">Documents</div><div className="metric-value">{summary.documents}</div><div className="metric-sub">{summary.chunks} chunks indexed</div></div>
        <div className="metric-card"><div className="metric-label">Questions</div><div className="metric-value">{summary.questions}</div><div className="metric-sub">Total answered</div></div>
        <div className="metric-card"><div className="metric-label">Avg latency</div><div className="metric-value">{Math.round(summary.avg_latency_ms)}<span style={{fontSize:14, fontWeight:500}}>ms</span></div><div className="metric-sub">Hit rate {hitRate}</div></div>
        <div className="metric-card"><div className="metric-label">Est. cost</div><div className="metric-value">${Number(summary.estimated_cost_usd||0).toFixed(4)}</div><div className="metric-sub">{summary.total_tokens||0} tokens</div></div>
      </div>

      <div className="metrics-table-wrap">
        <table className="metrics-table">
          <thead><tr><th>Question</th><th>Latency</th><th>Tokens</th><th>Cost</th><th>Cache</th></tr></thead>
          <tbody>
            {recent.length===0 ? <tr><td colSpan={5} style={{textAlign:'center', color:'var(--text-faint)', padding:24}}>No requests yet — ask something in chat.</td></tr> :
              recent.map((r,i)=>(
                <tr key={i}>
                  <td className="q-cell" title={r.question}>{r.question}</td>
                  <td>{Math.round(r.latency_ms)}ms</td>
                  <td>{r.tokens}</td>
                  <td>${Number(r.cost_usd||0).toFixed(6)}</td>
                  <td><span className={`cache-badge ${r.cache_hit?'hit':'miss'}`}>{r.cache_hit?"hit":"miss"}</span></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <div style={{marginTop:12, fontSize:11.5, color:'var(--text-muted)'}}>Grounded retrieval · rerank top 5 · refuses when not in docs</div>
    </div>
  )
}
