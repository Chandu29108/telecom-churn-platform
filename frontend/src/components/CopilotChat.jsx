// Floating chat widget, mounted once in App.jsx so it's available on every
// page. Talks to /api/copilot, which answers strictly from the latest (or
// specified) analysis run's stored JSON — see backend/app/routers/copilot.py.
import { useState, useRef, useEffect } from 'react'
import { MessageCircleQuestion, X, Send, Loader2 } from 'lucide-react'
import { askCopilot } from '../api'
import { useAnalysis } from '../context/AnalysisContext'

export default function CopilotChat() {
  const { result } = useAnalysis()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, open])

  const send = async (e) => {
    e.preventDefault()
    const question = input.trim()
    if (!question || loading) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', text: question }])
    setLoading(true)
    try {
      const res = await askCopilot(question, result?.run_id)
      setMessages((m) => [...m, { role: 'assistant', text: res.data.answer }])
    } catch (err) {
      const detail = err.response?.data?.detail || 'Something went wrong reaching the copilot.'
      setMessages((m) => [...m, { role: 'assistant', text: detail, isError: true }])
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 bg-ink text-white rounded-full p-4 shadow-lg hover:bg-signal transition-colors"
        aria-label="Open churn copilot"
      >
        <MessageCircleQuestion size={22} />
      </button>
    )
  }

  return (
    <div className="fixed bottom-6 right-6 w-96 max-w-[calc(100vw-2rem)] bg-card border border-black/10 rounded-2xl shadow-2xl flex flex-col h-[28rem] overflow-hidden">
      <div className="bg-ink text-white px-4 py-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold">Churn Copilot</div>
          <div className="text-[11px] text-white/60">Ask about the current analysis · runs on local Ollama</div>
        </div>
        <button onClick={() => setOpen(false)} className="text-white/70 hover:text-white">
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 text-sm">
        {messages.length === 0 && (
          <div className="text-xs text-muted">
            Try: "Which risk tier should we target first?" or "What's driving churn the most?"
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`max-w-[85%] rounded-lg px-3 py-2 ${
            m.role === 'user'
              ? 'ml-auto bg-signal/10 text-ink'
              : m.isError ? 'bg-tier-critical/10 text-tier-critical' : 'bg-black/[0.04] text-ink'
          }`}>
            {m.text}
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-xs text-muted">
            <Loader2 className="animate-spin" size={14} /> Thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={send} className="border-t border-black/5 p-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about churn drivers, risk tiers…"
          className="flex-1 border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-signal"
        />
        <button
          type="submit" disabled={loading}
          className="bg-ink text-white rounded-lg px-3 py-2 hover:bg-signal disabled:opacity-40"
        >
          <Send size={16} />
        </button>
      </form>
    </div>
  )
}
