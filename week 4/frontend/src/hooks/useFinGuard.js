// src/hooks/useFinGuard.js
// Custom hook handling upload, streaming analysis, and result storage.
import { useState, useCallback } from 'react'

export const API = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

export function useFinGuard() {
  const [documentId,   setDocumentId]   = useState(null)
  const [uploadInfo,   setUploadInfo]   = useState(null)
  const [agentSteps,   setAgentSteps]   = useState([])
  const [result,       setResult]       = useState(null)
  const [isUploading,  setIsUploading]  = useState(false)
  const [isAnalyzing,  setIsAnalyzing]  = useState(false)
  const [error,        setError]        = useState(null)

  // ── Upload CSV (or the bundled sample) ─────────────────────────────────────
  const uploadFile = useCallback(async (file) => {
    setIsUploading(true)
    setError(null)
    setResult(null)
    setAgentSteps([])

    try {
      let res
      if (file) {
        const formData = new FormData()
        formData.append('file', file)
        res = await fetch(`${API}/upload`, { method: 'POST', body: formData })
      } else {
        res = await fetch(`${API}/upload/sample`, { method: 'POST' })
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Upload failed (HTTP ${res.status})`)
      }
      const data = await res.json()
      setDocumentId(data.document_id)
      setUploadInfo(data)
      return data
    } catch (e) {
      setError(e.message)
      return null
    } finally {
      setIsUploading(false)
    }
  }, [])

  // ── Stream analysis via SSE ────────────────────────────────────────────────
  const analyze = useCallback(async (docId, query = '') => {
    if (!docId) return
    setIsAnalyzing(true)
    setError(null)
    setAgentSteps([])
    setResult(null)

    try {
      // SSE via fetch (EventSource doesn't support POST)
      const res = await fetch(`${API}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_id: docId,
          query: query || 'Analyze all transactions for fraud patterns and generate a risk report.',
          thread_id: `session-${docId}`,
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Analysis failed (HTTP ${res.status})`)
      }

      // Read SSE stream
      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''
      // Must live outside the read loop: a large `complete` payload spans
      // several chunks, so its "event:" line and its "data:" line arrive in
      // different reads. Scoped per-chunk, the event name was forgotten and
      // the result silently dropped.
      let   currentEvent = null
      let   completed    = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep incomplete last line

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ') && currentEvent) {
            // Only JSON.parse is guarded here. Handling the events inside the
            // same try meant an `error` event's throw was caught right below
            // and downgraded to a console warning — the spinner then spun
            // forever with no banner. Let it reach the outer catch.
            let data
            try {
              data = JSON.parse(line.slice(6))
            } catch (parseErr) {
              console.warn('SSE parse error:', parseErr, line)
              currentEvent = null
              continue
            }

            if (currentEvent === 'agent') {
              setAgentSteps(prev => {
                // Update existing step or add new one
                const exists = prev.findIndex(s => s.agent === data.agent)
                if (exists >= 0) {
                  const next = [...prev]
                  next[exists] = data
                  return next
                }
                return [...prev, data]
              })
            } else if (currentEvent === 'complete') {
              completed = true
              setResult(data)
              setIsAnalyzing(false)
            } else if (currentEvent === 'error') {
              throw new Error(data.message)
            }
            currentEvent = null
          }
        }
      }
      if (!completed) throw new Error('The analysis stream ended before a result arrived. Please retry.')
      setIsAnalyzing(false)
    } catch (e) {
      setError(e.message)
      setIsAnalyzing(false)
    }
  }, [])

  // ── Reopen a finished analysis (shareable ?report=<id> links) ──────────────
  const openReport = useCallback(async (docId) => {
    setError(null)
    try {
      const [rep, rev, chain] = await Promise.all([
        fetch(`${API}/report/${docId}`),
        fetch(`${API}/review/${docId}`),
        fetch(`${API}/audit/${docId}/verify`),
      ])
      if (!rep.ok) {
        const err = await rep.json().catch(() => ({}))
        throw new Error(err.detail || `Report ${docId} not found — it may have expired.`)
      }
      const data = await rep.json()
      setDocumentId(docId)
      setUploadInfo({ filename: 'Saved analysis', row_count: data.total_count, document_id: docId })
      setResult({
        ...data,
        reviews: rev.ok ? (await rev.json()).reviews : {},
        audit:   chain.ok ? await chain.json() : data.audit,
      })
    } catch (e) {
      setError(e.message)
    }
  }, [])

  // ── Human review (appends to the audit chain) ──────────────────────────────
  const submitReview = useCallback(async (docId, review) => {
    const res = await fetch(`${API}/review/${docId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(review),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const detail = Array.isArray(data.detail) ? data.detail.map(d => d.msg).join('; ') : data.detail
      throw new Error(detail || `Review failed (HTTP ${res.status})`)
    }
    setResult(prev => prev && { ...prev, audit: data.chain, reviews: data.reviews })
    return data
  }, [])

  const reset = useCallback(() => {
    setDocumentId(null)
    setUploadInfo(null)
    setAgentSteps([])
    setResult(null)
    setError(null)
    setIsUploading(false)
    setIsAnalyzing(false)
  }, [])

  return {
    documentId, uploadInfo, agentSteps, result,
    isUploading, isAnalyzing, error,
    uploadFile, analyze, submitReview, openReport, reset,
  }
}
