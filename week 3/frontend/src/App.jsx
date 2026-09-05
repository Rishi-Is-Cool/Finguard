// src/App.jsx
import { useState } from 'react'
import { Shield, RotateCcw } from 'lucide-react'
import { FileUpload }    from './components/FileUpload.jsx'
import { AgentPipeline } from './components/AgentPipeline.jsx'
import { RiskReport }    from './components/RiskReport.jsx'
import { useFinGuard }   from './hooks/useFinGuard.js'

export default function App() {
  const {
    documentId, uploadInfo, agentSteps, result,
    isUploading, isAnalyzing, error,
    uploadFile, analyze, reset,
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
          {(uploadInfo || result) && (
            <button
              onClick={reset}
              className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-600 px-3 py-1.5 rounded-lg transition-colors"
            >
              <RotateCcw size={14} /> New Analysis
            </button>
          )}
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
            <div className="mt-8 grid grid-cols-2 gap-3">
              {[
                { icon: '📥', label: 'Extractor Agent',       desc: 'Loads & structures data' },
                { icon: '🔍', label: 'Risk Classifier',       desc: 'Runs fraud detection tools' },
                { icon: '🤖', label: 'AI Classifier',         desc: 'Model verdict on top flags' },
                { icon: '📚', label: 'RAG Agent (CRAG)',      desc: 'Retrieves fraud rules' },
                { icon: '📝', label: 'Report Generator',      desc: 'Writes compliance report' },
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
              {result && <RiskReport result={result} />}
            </div>

          </div>
        )}
      </main>
    </div>
  )
}
