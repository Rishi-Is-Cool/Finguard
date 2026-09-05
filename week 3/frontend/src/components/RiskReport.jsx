// src/components/RiskReport.jsx
import { useState } from 'react'
import { Download, ChevronDown, ChevronUp, AlertTriangle, CheckCircle, Info } from 'lucide-react'

function RiskBadge({ level }) {
  const styles = {
    HIGH:    'bg-red-500/20 text-red-300 border-red-500/40',
    MEDIUM:  'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
    LOW:     'bg-green-500/20 text-green-300 border-green-500/40',
    UNKNOWN: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
  }
  const icons = {
    HIGH: <AlertTriangle size={14} />,
    MEDIUM: <Info size={14} />,
    LOW: <CheckCircle size={14} />,
  }
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-sm font-medium ${styles[level] || styles.UNKNOWN}`}>
      {icons[level]}
      {level}
    </span>
  )
}

function FlagRow({ flag, index }) {
  const [open, setOpen] = useState(false)
  const t = flag.transaction || {}
  const color = {
    HIGH:   'border-red-500/30 bg-red-900/10',
    MEDIUM: 'border-yellow-500/30 bg-yellow-900/10',
    LOW:    'border-slate-600/30 bg-slate-800/20',
  }[flag.severity] || ''

  return (
    <div className={`border rounded-lg overflow-hidden ${color}`}>
      <button
        className="w-full text-left p-3 flex items-center gap-3"
        onClick={() => setOpen(o => !o)}
      >
        <RiskBadge level={flag.severity} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-200 truncate">
            {flag.flag_type?.replace('_', ' ').toUpperCase()} · ₹{parseFloat(t.amount || 0).toLocaleString('en-IN')}
          </p>
          <p className="text-xs text-slate-400 mt-0.5 truncate">
            {t.account} → {t.beneficiary} · {t.date} {t.time}
          </p>
        </div>
        {open ? <ChevronUp size={16} className="text-slate-500 shrink-0" /> : <ChevronDown size={16} className="text-slate-500 shrink-0" />}
      </button>
      {open && (
        <div className="px-3 pb-3 pt-0 border-t border-slate-700/30 text-sm text-slate-400 mt-1">
          <p><span className="text-slate-300">Reason:</span> {flag.reason}</p>
          <p className="mt-1"><span className="text-slate-300">Description:</span> {t.description}</p>
        </div>
      )}
    </div>
  )
}

export function RiskReport({ result }) {
  const [showFlags,   setShowFlags]   = useState(true)
  const [showSources, setShowSources] = useState(false)
  const [showReport,  setShowReport]  = useState(true)
  const [showAi,      setShowAi]      = useState(true)

  if (!result) return null

  const flags   = result.risk_flags || []
  const high    = flags.filter(f => f.severity === 'HIGH')
  const medium  = flags.filter(f => f.severity === 'MEDIUM')
  const low     = flags.filter(f => f.severity === 'LOW')
  const sources = result.rag_sources || []
  const aiClass = result.ai_classifications || []

  const downloadReport = () => {
    const blob = new Blob([result.report || ''], { type: 'text/plain' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `finguard-report-${result.document_id}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4 fade-in">

      {/* Summary metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Overall Risk',    value: <RiskBadge level={result.overall_risk} /> },
          { label: 'Risk Score',      value: result.risk_score?.toFixed(3) },
          { label: 'Total Flags',     value: flags.length },
          { label: 'Transactions',    value: result.total_count?.toLocaleString() },
        ].map(({ label, value }) => (
          <div key={label} className="bg-slate-800/60 border border-slate-700/40 rounded-xl p-4">
            <p className="text-xs text-slate-500 mb-1">{label}</p>
            <p className="text-lg font-semibold text-slate-100">{value}</p>
          </div>
        ))}
      </div>

      {/* Flag breakdown bar */}
      {flags.length > 0 && (
        <div className="bg-slate-800/40 border border-slate-700/40 rounded-xl p-4">
          <p className="text-xs text-slate-400 mb-2">Flag Distribution</p>
          <div className="flex rounded-full overflow-hidden h-3">
            {high.length   > 0 && <div className="bg-red-500"    style={{ width: `${100*high.length/flags.length}%` }} title={`${high.length} HIGH`} />}
            {medium.length > 0 && <div className="bg-yellow-500" style={{ width: `${100*medium.length/flags.length}%` }} title={`${medium.length} MEDIUM`} />}
            {low.length    > 0 && <div className="bg-green-600"  style={{ width: `${100*low.length/flags.length}%` }} title={`${low.length} LOW`} />}
          </div>
          <div className="flex gap-4 mt-2 text-xs text-slate-500">
            <span className="text-red-400">{high.length} HIGH</span>
            <span className="text-yellow-400">{medium.length} MEDIUM</span>
            <span className="text-green-400">{low.length} LOW</span>
          </div>
        </div>
      )}

      {/* Risk Flags */}
      {flags.length > 0 && (
        <div className="bg-slate-800/40 border border-slate-700/40 rounded-xl overflow-hidden">
          <button
            className="w-full flex items-center justify-between p-4 hover:bg-slate-700/20"
            onClick={() => setShowFlags(o => !o)}
          >
            <span className="font-medium text-slate-200">Risk Flags ({flags.length})</span>
            {showFlags ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
          </button>
          {showFlags && (
            <div className="px-4 pb-4 space-y-2 max-h-80 overflow-y-auto">
              {[...flags]
                .sort((a, b) => ({ HIGH: 0, MEDIUM: 1, LOW: 2 }[a.severity] - { HIGH: 0, MEDIUM: 1, LOW: 2 }[b.severity]))
                .map((flag, i) => <FlagRow key={i} flag={flag} index={i} />)
              }
            </div>
          )}
        </div>
      )}

      {/* Model classification of the top flags */}
      {aiClass.length > 0 && (
        <div className="bg-slate-800/40 border border-slate-700/40 rounded-xl overflow-hidden">
          <button
            className="w-full flex items-center justify-between p-4 hover:bg-slate-700/20"
            onClick={() => setShowAi(o => !o)}
          >
            <span className="font-medium text-slate-200">
              Model Classification ({aiClass.length})
              <span className="ml-2 text-xs font-normal text-slate-500">
                {aiClass[0].is_finetuned ? 'fine-tuned' : 'Groq fallback'} · {aiClass[0].model_used}
              </span>
            </span>
            {showAi ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
          </button>
          {showAi && (
            <div className="px-4 pb-4 space-y-2">
              {aiClass.map((c, i) => {
                const t = c.transaction || {}
                return (
                  <div key={i} className="bg-slate-700/25 rounded-lg p-3">
                    <div className="flex items-center gap-2.5 mb-1.5">
                      <RiskBadge level={c.risk_level} />
                      <span className="text-sm text-slate-300 truncate">
                        {t.account} → {t.beneficiary} · ₹{parseFloat(t.amount || 0).toLocaleString('en-IN')}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed whitespace-pre-wrap">{c.reasoning}</p>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* RAG Sources */}
      {sources.length > 0 && (
        <div className="bg-slate-800/40 border border-slate-700/40 rounded-xl overflow-hidden">
          <button
            className="w-full flex items-center justify-between p-4 hover:bg-slate-700/20"
            onClick={() => setShowSources(o => !o)}
          >
            <span className="font-medium text-slate-200">Fraud Rules Referenced ({sources.length})</span>
            {showSources ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
          </button>
          {showSources && (
            <div className="px-4 pb-4 space-y-2">
              {sources.map((src, i) => (
                <div key={i} className="bg-slate-700/30 rounded-lg p-3 text-sm text-slate-400">
                  <span className="text-slate-500 text-xs font-mono">[{i+1}]</span> {src.slice(0, 200)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Full Report */}
      {result.report && (
        <div className="bg-slate-800/40 border border-slate-700/40 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between p-4">
            <button
              className="font-medium text-slate-200 flex items-center gap-2"
              onClick={() => setShowReport(o => !o)}
            >
              📋 Risk Assessment Report
              {showReport ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
            </button>
            <button
              onClick={downloadReport}
              className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 border border-blue-500/30 hover:border-blue-400/50 px-3 py-1.5 rounded-lg transition-colors"
            >
              <Download size={13} /> Download
            </button>
          </div>
          {showReport && (
            <div className="px-4 pb-4">
              <div className="bg-slate-900/60 rounded-lg p-4 text-sm text-slate-300 whitespace-pre-wrap leading-relaxed font-mono max-h-96 overflow-y-auto">
                {result.report}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
