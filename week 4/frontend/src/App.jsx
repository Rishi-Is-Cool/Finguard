// src/App.jsx
import { useEffect, useRef, useState } from 'react'
import { Shield, RotateCcw, Github, BookOpen, Sparkles } from 'lucide-react'
import { FileUpload }    from './components/FileUpload.jsx'
import { AgentPipeline } from './components/AgentPipeline.jsx'
import { RiskReport }    from './components/RiskReport.jsx'
import { useFinGuard, API } from './hooks/useFinGuard.js'

const REPO_URL = import.meta.env.VITE_REPO_URL || 'https://github.com/Rishi-Is-Cool/Finguard'
// FastAPI serves Swagger at the server root, not under the /api mirror.
const DOCS_URL = `${API.replace(/\/api$/, '')}/docs`

export default function App() {
  const {
    documentId, uploadInfo, agentSteps, result,
    isUploading, isAnalyzing, error,
    uploadFile, analyze, submitReview, openReport, reset,
  } = useFinGuard()

  const [query, setQuery] = useState(
    'Analyze all transactions for fraud patterns and generate a compliance risk report.'
  )

  const handleUpload = async (file) => {
    const info = await uploadFile(file)
    if (info) {
      // Auto-start analysis
      await analyze(info.document_id, query)
    }
  }

  const handleReanalyze = () => {
    if (documentId) analyze(documentId, query)
  }

  // ?demo runs the bundled sample on load; ?report=<id> reopens a finished
  // analysis. Both are links you can send someone.
  const started = useRef(false)
  useEffect(() => {
    if (started.current) return
    started.current = true
    const params = new URLSearchParams(window.location.search)
    if (params.get('report')) openReport(params.get('report'))
    else if (params.has('demo')) handleUpload(null)
  }, [])

  // Keep the address bar pointing at the finished report: refresh-safe and shareable.
  useEffect(() => {
    const url = new URL(window.location.href)
    if (result?.document_id) url.search = `?report=${result.document_id}`
    else if (!isAnalyzing && !isUploading && url.searchParams.has('report')) url.search = ''
    else return
    window.history.replaceState(null, '', url)
  }, [result?.document_id])

  return (
    <div className="min-h-screen bg-slate-900">

      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-blue-500/20 p-2 rounded-lg">
              <Shield className="text-blue-400" size={20} />
            </div>
            <div>
              <h1 className="font-bold text-slate-100 text-lg leading-none">FinGuard AI</h1>
              <p className="text-xs text-slate-500 mt-0.5">Finance Fraud & Risk Intelligence</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a href={DOCS_URL} target="_blank" rel="noreferrer" title="API docs"
               className="p-2 text-slate-500 hover:text-slate-200 rounded-lg"><BookOpen size={17} /></a>
            <a href={REPO_URL} target="_blank" rel="noreferrer" title="Source on GitHub"
               className="p-2 text-slate-500 hover:text-slate-200 rounded-lg"><Github size={17} /></a>
            {(uploadInfo || result) && (
              <button
                onClick={reset}
                disabled={isAnalyzing}
                className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-600 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-40"
              >
                <RotateCcw size={14} /> New Analysis
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">

        {/* Error banner */}
        {error && (
          <div className="mb-6 bg-red-900/30 border border-red-500/40 rounded-xl p-4 text-red-300 text-sm">
            ⚠️ {error}
          </div>
        )}

        {/* Upload state */}
        {!uploadInfo ? (
          <div className="max-w-2xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-slate-100">Fraud Risk Analysis</h2>
              <p className="text-slate-400 mt-2">
                Upload a transaction CSV — 5 AI agents will analyze it for fraud patterns
                and generate a compliance report.
              </p>
            </div>

            <div className="space-y-4">
              <FileUpload
                onUpload={handleUpload}
                isUploading={isUploading}
                uploadInfo={uploadInfo}
              />

              <button
                onClick={() => handleUpload(null)}
                disabled={isUploading}
                className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg text-sm transition-colors"
              >
                <Sparkles size={15} /> Try it with sample data (200 transactions)
              </button>

              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Analysis query (optional)</label>
                <textarea
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  rows={2}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 resize-none focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            {/* Agent overview */}
            <div className="mt-8 grid grid-cols-2 sm:grid-cols-3 gap-3">
              {[
                { icon: '📥', label: 'Extractor Agent',       desc: 'Loads & structures data' },
                { icon: '🔍', label: 'Risk Classifier',       desc: 'Runs fraud detection tools' },
                { icon: '🤖', label: 'AI Screener',           desc: 'Jev triage, LLM escalation' },
                { icon: '📚', label: 'RAG Agent (CRAG)',      desc: 'Retrieves fraud rules' },
                { icon: '📝', label: 'Report Generator',      desc: 'Writes compliance report' },
                { icon: '🔏', label: 'Audit Trail',           desc: 'Hash-chained, reviewable' },
              ].map(({ icon, label, desc }) => (
                <div key={label} className="bg-slate-800/40 border border-slate-700/40 rounded-xl p-4">
                  <p className="text-lg mb-1">{icon}</p>
                  <p className="text-sm font-medium text-slate-300">{label}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                </div>
              ))}
            </div>
          </div>

        ) : (

          /* Analysis view */
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* Left: file info + agent pipeline */}
            <div className="lg:col-span-1 space-y-4">
              <FileUpload
                onUpload={handleUpload}
                isUploading={isUploading}
                uploadInfo={uploadInfo}
              />

              {(agentSteps.length > 0 || isAnalyzing) && (
                <AgentPipeline steps={agentSteps} isAnalyzing={isAnalyzing} />
              )}

              {result && !isAnalyzing && (
                <div className="space-y-2">
                  <textarea
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    rows={2}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:border-blue-500"
                  />
                  <button
                    onClick={handleReanalyze}
                    className="w-full bg-blue-600 hover:bg-blue-500 text-white font-medium py-2.5 rounded-lg text-sm transition-colors"
                  >
                    Re-analyze
                  </button>
                </div>
              )}
            </div>

            {/* Right: results */}
            <div className="lg:col-span-2">
              {isAnalyzing && !result && (
                <div className="flex flex-col items-center justify-center h-64 text-slate-500">
                  <div className="w-10 h-10 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mb-4" />
                  <p>Agents are working...</p>
                </div>
              )}
              {result && <RiskReport result={result} onReview={r => submitReview(result.document_id, r)} />}
            </div>

          </div>
        )}
      </main>
    </div>
  )
}
