import { useState, useEffect } from 'react'
import { Quote } from 'lucide-react'
import { getQuote } from '../api/client'

export default function QuoteBar() {
  const [quote, setQuote] = useState('')

  useEffect(() => {
    let cancelled = false
    const fetchQuote = () => {
      getQuote()
        .then(data => { if (!cancelled) setQuote(data.quote) })
        .catch(() => {})
    }
    fetchQuote()
    const interval = setInterval(fetchQuote, 60000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  if (!quote) return null

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-500/5 to-gold/5 rounded-lg border border-purple-400/10">
      <Quote size={14} className="text-purple-400 shrink-0" />
      <p className="text-sm text-cd-text-secondary italic">{quote}</p>
    </div>
  )
}
