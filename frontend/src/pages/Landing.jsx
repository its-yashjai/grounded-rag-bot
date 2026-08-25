import { Link } from 'react-router-dom'

export default function Landing(){
  return (
    <div className="landing">
      <header className="landing-header">
        <div className="landing-brand">
          <span className="brand-mark"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/></svg></span>
          <span className="brand-name">Domain Knowledge Bot</span>
        </div>
        <nav className="landing-nav">
          <Link to="/documents">Documents</Link>
          <Link to="/observability">Observability</Link>
          <Link to="/app" className="landing-cta">Open App</Link>
        </nav>
      </header>

      <section className="landing-hero">
        <div className="hero-badge">Grounded · Cited · Private</div>
        <h1>Turn your documents<br/>into <em>answers.</em></h1>
        <p className="hero-sub">Upload PDFs, DOCX or TXT. Ask anything. Every answer is streamed, cited to the exact page, and stays in its own chat with a shareable URL.</p>
        <div className="hero-actions">
          <Link to="/app" className="btn-primary">Start chatting →</Link>
          <a href="#features" className="btn-ghost">See how it works</a>
        </div>
        <div className="hero-stats">
          <div className="hero-stat-card"><div className="hero-stat-num">Grounded</div><div className="hero-stat-label">Refuses rather than hallucinates</div></div>
          <div className="hero-stat-card"><div className="hero-stat-num">Cited</div><div className="hero-stat-label">Exact document & page</div></div>
          <div className="hero-stat-card"><div className="hero-stat-num">Isolated</div><div className="hero-stat-label">Each chat = unique URL</div></div>
        </div>
      </section>

      <section id="features" className="feature-grid">
        <div className="feature-card"><h3>Instant new chats</h3><p>Click New chat — it appears instantly. First question locks its URL before streaming starts. No waiting.</p></div>
        <div className="feature-card"><h3>No forked threads</h3><p>Follow-ups reuse the same conversation ID from the URL. Your context never leaks into a new chat.</p></div>
        <div className="feature-card"><h3>Hard-grounded</h3><p>Hybrid retrieval + reranker + guard. If the answer isn’t in your docs, it says so.</p></div>
      </section>

      <section className="pipeline-strip">
        <div className="pipe-step"><span className="pipe-num">01</span><h4>Upload</h4><p>PDF, DOCX, TXT indexed with BM25 + vectors</p></div>
        <div className="pipe-step"><span className="pipe-num">02</span><h4>Ask</h4><p>Streaming tokens with citations</p></div>
        <div className="pipe-step"><span className="pipe-num">03</span><h4>Share</h4><p>Copy the chat URL — isolated thread</p></div>
      </section>

      <footer className="landing-footer">
        <span>Domain Knowledge Bot · Built for private, grounded QA</span>
        <Link to="/app">Go to App →</Link>
      </footer>
    </div>
  )
}
