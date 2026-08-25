import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Landing from './pages/Landing.jsx'
import ChatPage from './pages/Chat.jsx'
import DocumentsPage from './pages/Documents.jsx'
import Observability from './pages/Observability.jsx'
import './App.css'

export default function App(){
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app" element={<ChatPage />} />
        <Route path="/app/:id" element={<ChatPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/observability" element={<Observability />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
