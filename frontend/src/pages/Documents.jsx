import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as API from '../api.js'
import { showToast, showErrorToast } from '../utils/toast.js'

export default function DocumentsPage(){
  const navigate = useNavigate()
  const [docs,setDocs]=useState([])
  const [dragOver,setDragOver]=useState(false)
  const refresh=async()=>setDocs(await API.listDocuments())
  useEffect(()=>{ refresh() },[])
  const handleFiles=async(files)=>{
    if(!files?.length) return
    const toast = showToast(`Uploading ${files.length} document${files.length>1?'s':''} — ${Array.from(files).map(f=>f.name).join(", ")}`, "loading")
    try{
      const res = await API.uploadDocuments(Array.from(files))
      toast.remove()
      showToast(`✓ Uploaded ${res.documents.length} document${res.documents.length>1?'s':''} — ${res.documents.map(d=>d.filename).join(", ")}`, "success")
      refresh()
    }catch(err){
      toast.remove()
      showErrorToast(err.message || "Upload failed")
    }
  }
  const handleUpload=async(e)=>{
    await handleFiles(e.target.files)
    e.target.value=""
  }
  const handleDelete=async(id)=>{
    if(!confirm("Delete document and remove it from the knowledge base?")) return
    await API.deleteDocument(id)
    showToast("Document deleted", "success")
    refresh()
  }
  const ready=docs.filter(d=>d.processing_status==="ready").length
  const chunks=docs.reduce((a,d)=>a+(d.chunk_count||0),0)
  const totalMb=(docs.reduce((a,d)=>a+d.file_size,0)/1048576).toFixed(1)

  const iconFor=(type)=>{
    const t=(type||"").toLowerCase()
    if(t.includes("pdf")) return "PDF"
    if(t.includes("docx")||t.includes("doc")) return "DOC"
    return "TXT"
  }
  const clsFor=(type)=>{
    const t=(type||"").toLowerCase()
    if(t.includes("pdf")) return "pdf"
    if(t.includes("docx")||t.includes("doc")) return "docx"
    return "txt"
  }

  return (
    <div className="page">
      <button className="back-btn" onClick={()=> window.history.length>1 ? navigate(-1) : navigate('/app')} aria-label="Go back">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
        Back
      </button>
      <header className="page-header">
        <div>
          <h1>Documents</h1>
          <div className="page-sub">Upload PDFs, DOCX or TXT — they’re chunked, embedded and cited in every answer.</div>
        </div>
        <div style={{display:'flex', gap:8}}>
          <Link to="/app" style={{padding:'7px 12px', borderRadius:999, border:'1px solid var(--border)', background:'var(--card)', fontSize:13, fontWeight:600}}>Open Chat</Link>
          <label className="upload-btn" htmlFor="docUpload" style={{background:'var(--text)', color:'var(--bg)', borderColor:'var(--text)'}}>Upload</label>
          <input id="docUpload" type="file" multiple accept=".pdf,.docx,.txt" style={{display:'none'}} onChange={handleUpload} />
        </div>
      </header>

      <div className="docs-stats">
        <div className="metric-card"><div className="metric-label">Documents</div><div className="metric-value">{docs.length}</div><div className="metric-sub">Total uploads</div></div>
        <div className="metric-card"><div className="metric-label">Ready</div><div className="metric-value">{ready}</div><div className="metric-sub">Indexed & searchable</div></div>
        <div className="metric-card"><div className="metric-label">Chunks</div><div className="metric-value">{chunks}</div><div className="metric-sub">Retrievable units</div></div>
        <div className="metric-card"><div className="metric-label">Size</div><div className="metric-value">{totalMb} MB</div><div className="metric-sub">Total storage</div></div>
      </div>

      <label
        className={`dropzone ${dragOver?'drag-over':''}`}
        htmlFor="docUpload"
        onDragEnter={e=>{e.preventDefault(); setDragOver(true)}}
        onDragOver={e=>{e.preventDefault(); setDragOver(true)}}
        onDragLeave={e=>{e.preventDefault(); setDragOver(false)}}
        onDrop={e=>{e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files)}}
      >
        <div className="dropzone-title">Drop files here or click to upload</div>
        <div className="dropzone-sub">PDF, DOCX, TXT up to 25 MB — private to your workspace</div>
      </label>

      <div className="docs-grid" style={{marginTop:16}}>
        {docs.length===0 ? <div className="docs-empty">Nothing here yet — drop a file above to build your knowledge base.</div> : docs.map(d=>(
          <div key={d.document_id} className="doc-tile">
            <div className="doc-tile-top">
              <span className={`doc-tile-icon ${clsFor(d.file_type)}`}>{iconFor(d.file_type)}</span>
              <span className="doc-tile-name" title={d.filename}>{d.filename}</span>
            </div>
            <div className="doc-tile-meta">
              <span>{d.file_type.toUpperCase()}</span> · <span>{(d.file_size/1024).toFixed(0)} KB</span> · <span>{d.page_count||0} pages</span> · <span>{d.chunk_count||0} chunks</span>
            </div>
            <span className={`doc-status ${d.processing_status==="ready"?"ready":d.processing_status==="failed"?"failed":"processing"}`}>{d.processing_status}</span>
            {d.error && <div style={{fontSize:11, color:'var(--danger)'}}>{d.error}</div>}
            <div className="doc-tile-actions">
              <button className="doc-action danger" onClick={()=>handleDelete(d.document_id)}>Delete</button>
              <Link to="/app" className="doc-action" style={{textDecoration:'none'}}>Chat with this</Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
