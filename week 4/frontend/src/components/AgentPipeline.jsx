// src/components/AgentPipeline.jsx
// Shows real-time agent step progress as SSE events arrive.
import { CheckCircle, Circle, Loader, AlertTriangle } from 'lucide-react'

const AGENTS = [
  { key: 'extractor',       label: 'Extractor Agent',        desc: 'Load & structure transaction data' },
  { key: 'risk_classifier', label: 'Risk Classifier Agent',  desc: 'Detect fraud patterns with tools' },
  { key: 'ai_classifier',   label: 'AI Screener',            desc: 'Jev triage → LLM → human' },
  { key: 'rag',             label: 'RAG Agent',              desc: 'Retrieve fraud rule context' },
  { key: 'report',          label: 'Report Generator',       desc: 'Write compliance risk report' },
]

function AgentStep({ agent, step }) {
  const status = step?.status || 'waiting'

  const icon = {
    waiting: <Circle size={18} className="text-slate-600" />,
    running: <Loader size={18} className="text-blue-400 animate-spin" />,
    done:    <CheckCircle size={18} className="text-green-400" />,
    error:   <AlertTriangle size={18} className="text-red-400" />,
  }[status]

  const bg = {
    waiting: 'bg-slate-800/40 border-slate-700/40',
    running: 'bg-blue-900/30 border-blue-500/40',
    done:    'bg-green-900/20 border-green-500/30',
    error:   'bg-red-900/20 border-red-500/30',
  }[status]

  return (
    <div className={`border rounded-lg p-4 transition-all fade-in ${bg}`}>
      <div className="flex items-center gap-3">
        {icon}
        <div className="flex-1 min-w-0">
          <p className={`font-medium text-sm ${status === 'waiting' ? 'text-slate-500' : 'text-slate-200'}`}>
            {agent.label}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">
            {step?.message || agent.desc}
          </p>
        </div>
      </div>

      {/* Extra data from agent */}
      {step?.data && status === 'done' && (
        <div className="mt-3 pt-3 border-t border-slate-700/40 text-xs text-slate-400 space-y-1">
          {step.data.total_count && (
            <p>✓ {step.data.total_count.toLocaleString()} transactions extracted</p>
          )}
          {step.data.overall_risk && (
            <p>✓ Overall risk: <span className={
              step.data.overall_risk === 'HIGH'   ? 'text-red-400 font-medium' :
              step.data.overall_risk === 'MEDIUM' ? 'text-yellow-400 font-medium' :
                                                    'text-green-400 font-medium'
            }>{step.data.overall_risk}</span> (score: {step.data.risk_score?.toFixed(3)})</p>
          )}
          {step.data.flag_counts && (
            <p>✓ Flags: {step.data.flag_counts.HIGH} HIGH · {step.data.flag_counts.MEDIUM} MEDIUM · {step.data.flag_counts.LOW} LOW</p>
          )}
          {step.data.mode === 'cascade' && (
            <p>
              ✓ Jev screened {step.data.screened}:{' '}
              <span className="text-emerald-400">{step.data.auto} auto</span> ·{' '}
              <span className="text-blue-400">{step.data.escalated_llm} LLM</span> ·{' '}
              <span className="text-orange-400">{step.data.human_review} human</span>
              <span className="block text-slate-600 mt-0.5">
                ${step.data.jev_cost_usd?.toFixed(4)} · {step.data.disagreements} disagree with rules
              </span>
            </p>
          )}
          {step.data.mode === 'llm_only' && (
            <p>
              {step.data.is_finetuned ? 'Fine-tuned' : 'Fallback'} model confirmed{' '}
              <span className="text-red-400 font-medium">{step.data.agreed_high}</span>
              {' '}of {step.data.classified}
              <span className="block text-slate-600 mt-0.5 truncate">{step.data.llm_model}</span>
            </p>
          )}
          {step.data.sources && (
            <p>✓ Retrieved {step.data.sources.length} fraud rule references
              {step.data.was_rewritten && <span className="text-blue-400"> (query rewritten)</span>}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export function AgentPipeline({ steps, isAnalyzing }) {
  const stepMap = Object.fromEntries(steps.map(s => [s.agent, s]))

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-slate-400 mb-3">Agent Pipeline</h3>
      {AGENTS.map(agent => (
        <AgentStep key={agent.key} agent={agent} step={stepMap[agent.key]} />
      ))}
      {isAnalyzing && (
        <div className="text-center py-2">
          <p className="text-xs text-slate-500 animate-pulse">Analysis in progress...</p>
        </div>
      )}
    </div>
  )
}
