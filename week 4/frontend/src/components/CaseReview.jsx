// src/components/CaseReview.jsx
// Model verdicts on every flagged transaction, how each was routed, and the
// human decision. Every decision is appended to the hash-chained audit trail.
import { useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, ShieldCheck, ShieldAlert, Download, FileJson } from 'lucide-react'
import { API } from '../hooks/useFinGuard.js'

const LEVEL = {
  HIGH:   'bg-red-500/20 text-red-300 border-red-500/40',
  MEDIUM: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
  LOW:    'bg-green-500/20 text-green-300 border-green-500/40',
}
const ROUTE = {
  auto:         { label: 'Jev auto',     cls: 'text-emerald-300 border-emerald-500/40' },
  llm:          { label: 'LLM',          cls: 'text-blue-300 border-blue-500/40' },
  human_review: { label: 'Human queue',  cls: 'text-orange-300 border-orange-500/40' },
}
const DECISIONS = [
  { key: 'confirmed_fraud',  label: 'Confirm fraud',  cls: 'hover:bg-red-600/30 border-red-500/40 text-red-300' },
  { key: 'false_positive',   label: 'False positive', cls: 'hover:bg-green-600/30 border-green-500/40 text-green-300' },
  { key: 'needs_escalation', label: 'Escalate',       cls: 'hover:bg-orange-600/30 border-orange-500/40 text-orange-300' },
]
const DECISION_LABEL = Object.fromEntries(DECISIONS.map(d => [d.key, d.label]))

function Chip({ className, children }) {
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-medium ${className}`}>{children}</span>
}

function ProbabilityBar({ probabilities }) {
  if (!probabilities) return null
  const colors = { HIGH: 'bg-red-500', MEDIUM: 'bg-yellow-500', LOW: 'bg-green-600' }
  return (
    <div className="flex h-1.5 rounded-full overflow-hidden bg-slate-700 w-24" title={
      Object.entries(probabilities).map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`).join(' · ')}>
      {['HIGH', 'MEDIUM', 'LOW'].map(k => (
        <div key={k} className={colors[k]} style={{ width: `${(probabilities[k] || 0) * 100}%` }} />
      ))}
    </div>
  )
}

function CaseRow({ c, review, reviewer, onReview }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr]   = useState(null)
  const t = c.transaction
  const route = ROUTE[c.route] || ROUTE.llm

  const decide = async (decision) => {
    setBusy(true); setErr(null)
    try {
      await onReview({ txn_id: t.txn_id, decision, note, reviewer: reviewer || 'anonymous' })
      setNote('')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="bg-slate-700/25 rounded-lg border border-slate-700/40">
      <button className="w-full text-left p-3 flex items-center gap-3" onClick={() => setOpen(o => !o)}>
        <Chip className={LEVEL[c.risk_level] || LEVEL.MEDIUM}>{c.risk_level}</Chip>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-200 truncate">
            <span className="font-mono text-slate-500 mr-1.5">{t.txn_id}</span>
            {t.account} → {t.beneficiary} · ₹{Number(t.amount).toLocaleString('en-IN')}
          </p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <Chip className={route.cls}>{route.label}</Chip>
            {c.jev?.confidence != null && (
              <span className="text-[11px] text-slate-500">conf {c.jev.confidence.toFixed(2)}</span>
            )}
            <ProbabilityBar probabilities={c.jev?.probabilities} />
            {c.disagrees_with_rules && (
              <span className="text-[11px] text-amber-400">rules said {c.rule_severity}</span>
            )}
            {review && (
              <Chip className="text-slate-200 border-slate-500/60 bg-slate-600/30">
                ✓ {DECISION_LABEL[review.decision]} · {review.reviewer}
              </Chip>
            )}
          </div>
        </div>
        {open ? <ChevronUp size={16} className="text-slate-500 shrink-0" /> : <ChevronDown size={16} className="text-slate-500 shrink-0" />}
      </button>

      {open && (
        <div className="px-3 pb-3 border-t border-slate-700/40 pt-3 space-y-3 text-xs">
          <p className="text-slate-400 leading-relaxed whitespace-pre-wrap">{c.reasoning}</p>
          <p className="text-slate-500">
            {t.date} {t.time} · {t.description} · rules: {c.rules.map(r => `${r.rule} (${r.severity})`).join(', ')}
            <span className="block mt-0.5">model: {c.model_used}</span>
          </p>
          {review?.note && <p className="text-slate-400 italic">“{review.note}” — {review.reviewer}</p>}
          <input
            value={note}
            onChange={e => setNote(e.target.value)}
            maxLength={500}
            placeholder="Reviewer note (optional)"
            className="w-full bg-slate-900/60 border border-slate-700 rounded-md px-2.5 py-1.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500"
          />
          <div className="flex gap-2 flex-wrap">
            {DECISIONS.map(d => (
              <button key={d.key} disabled={busy} onClick={() => decide(d.key)}
                className={`px-3 py-1.5 rounded-md border transition-colors disabled:opacity-40 ${d.cls}`}>
                {d.label}
              </button>
            ))}
          </div>
          {err && <p className="text-red-400">{err}</p>}
        </div>
      )}
    </div>
  )
}

export function CaseReview({ result, onReview }) {
  const [open, setOpen]         = useState(true)
  const [filter, setFilter]     = useState('attention')
  const [reviewer, setReviewer] = useState(() => {
    try { return localStorage.getItem('finguard.reviewer') || '' } catch { return '' }
  })
  const cases   = result.ai_classifications || []
  const stats   = result.classifier_stats || {}
  const reviews = result.reviews || {}
  const audit   = result.audit

  const needsAttention = c => c.route === 'human_review' || c.disagrees_with_rules || c.risk_level === 'HIGH'
  const shown = useMemo(() => cases.filter(c =>
    filter === 'all' ? true :
    filter === 'reviewed' ? reviews[c.transaction.txn_id] :
    needsAttention(c) && !reviews[c.transaction.txn_id]
  ), [cases, reviews, filter])

  const saveReviewer = v => {
    setReviewer(v)
    try { localStorage.setItem('finguard.reviewer', v) } catch { /* storage blocked */ }
  }

  if (!cases.length) return null
  const reviewedCount = cases.filter(c => reviews[c.transaction.txn_id]).length

  return (
    <div className="bg-slate-800/40 border border-slate-700/40 rounded-xl overflow-hidden">
      <button className="w-full flex items-center justify-between p-4 hover:bg-slate-700/20" onClick={() => setOpen(o => !o)}>
        <span className="font-medium text-slate-200 text-left">
          Case Review ({cases.length})
          <span className="ml-2 text-xs font-normal text-slate-500">
            {stats.mode === 'cascade'
              ? `Jev screened ${stats.screened} · ${stats.auto} auto · ${stats.escalated_llm} LLM · ${stats.human_review} human`
              : `LLM only · ${stats.llm_model || cases[0].model_used}`}
            {' · '}{reviewedCount} reviewed
          </span>
        </span>
        {open ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          {stats.mode === 'cascade' && (
            <p className="text-xs text-slate-500">
              Screening cost ${stats.jev_cost_usd?.toFixed(4)} for {stats.jev_input_tokens?.toLocaleString()} tokens
              {stats.jev_median_latency_ms != null && ` · median ${stats.jev_median_latency_ms} ms`}
              {' · '}confidence gate {stats.confidence_threshold}
              {stats.screen_errors > 0 && <span className="text-amber-400"> · {stats.screen_errors} screening errors escalated</span>}
            </p>
          )}
          {stats.mode === 'llm_only' && (
            <p className="text-xs text-slate-500">
              Set <span className="font-mono">TYPESAFE_API_KEY</span> to screen every flagged transaction with Jev
              instead of only the top {cases.length}.
            </p>
          )}

          <div className="flex items-center gap-2 flex-wrap">
            {[['attention', 'Needs attention'], ['reviewed', 'Reviewed'], ['all', 'All']].map(([k, label]) => (
              <button key={k} onClick={() => setFilter(k)}
                className={`text-xs px-3 py-1 rounded-full border ${filter === k
                  ? 'border-blue-500/60 text-blue-300 bg-blue-500/10' : 'border-slate-600 text-slate-400 hover:text-slate-200'}`}>
                {label}
              </button>
            ))}
            <input
              value={reviewer}
              onChange={e => saveReviewer(e.target.value)}
              maxLength={80}
              placeholder="Your name (reviewer)"
              className="ml-auto bg-slate-900/60 border border-slate-700 rounded-md px-2.5 py-1 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">
            {shown.length
              ? shown.map(c => (
                  <CaseRow key={c.transaction.txn_id} c={c} review={reviews[c.transaction.txn_id]}
                           reviewer={reviewer} onReview={onReview} />))
              : <p className="text-xs text-slate-500 py-4 text-center">Nothing here.</p>}
          </div>
        </div>
      )}

      {audit && (
        <div className="border-t border-slate-700/40 px-4 py-3 flex items-center gap-3 flex-wrap text-xs">
          {audit.valid
            ? <span className="flex items-center gap-1.5 text-emerald-300"><ShieldCheck size={15} /> Audit chain intact</span>
            : <span className="flex items-center gap-1.5 text-red-300"><ShieldAlert size={15} /> Audit chain broken at event {audit.broken_at}</span>}
          <span className="text-slate-500 font-mono" title={audit.head || ''}>
            {audit.events} events · head {audit.head?.slice(0, 12)}…
          </span>
          <span className="ml-auto flex gap-2">
            <a href={`${API}/audit/${result.document_id}/export.csv`}
               className="flex items-center gap-1 text-blue-400 hover:text-blue-300 border border-blue-500/30 px-2.5 py-1 rounded-md">
              <Download size={12} /> Case file (CSV)
            </a>
            <a href={`${API}/audit/${result.document_id}`} target="_blank" rel="noreferrer"
               className="flex items-center gap-1 text-blue-400 hover:text-blue-300 border border-blue-500/30 px-2.5 py-1 rounded-md">
              <FileJson size={12} /> Audit log
            </a>
          </span>
        </div>
      )}
    </div>
  )
}
