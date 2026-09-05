// src/hooks/useFinGuard.js
// Custom hook handling upload, streaming analysis, and result storage.
import { useState, useCallback } from 'react'

const API = '/api'

export function useFinGuard() {
  const [documentId,   setDocumentId]   = useState(null)
  const [uploadInfo,   setUploadInfo]   = useState(null)
  const [agentSteps,   setAgentSteps]   = useState([])
  const [result,       setResult]       = useState(null)
  const [isUploading,  setIsUploading]  = useState(false)
  const [isAnalyzing,  setIsAnalyzing]  = useState(false)
  const [error,        setError]        = useState(null)

  // ── Upload CSV ─────────────────────────────────────────────────────────────
  const uploadFile = useCallback(async (file) => {
    setIsUploading(true)
    setError(null)
    setResult(null)
    setAgentSteps([])

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${API}/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Upload failed')
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
        const err = await res.json()
        throw new Error(err.detail || 'Analysis failed')
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
              setResult(data)
              setIsAnalyzing(false)
            } else if (currentEvent === 'error') {
              throw new Error(data.message)
            }
            currentEvent = null
          }
        }
      }
    } catch (e) {
      setError(e.message)
      setIsAnalyzing(false)
    }
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
    uploadFile, analyze, reset,
  }
}
