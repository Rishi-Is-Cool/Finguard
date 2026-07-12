# 🛡️ FinGuard AI — Week 2

Multi-Agent Fraud & Risk Intelligence System built with LangGraph.

## What's new in Week 2
- Full LangGraph multi-agent pipeline (5 agents)
- Human-in-the-loop review for HIGH risk cases
- SQLite memory — flagged accounts persist across sessions
- RAG + fraud rules knowledge base
- LangSmith observability + tracing

---

## File Structure
```
finguard_week2/
├── app.py              ← Streamlit frontend
├── graph.py            ← LangGraph graph (wires all agents)
├── agents.py           ← All 5 agent functions
├── state.py            ← Shared state schema (TypedDict)
├── tools.py            ← Pydantic-typed fraud detection tools
├── rag.py              ← RAG retriever (hybrid + reranker)
├── langsmith_test.py   ← LangSmith tracing test
├── requirements.txt
├── .env.example
└── README.md

# From Week 1 (copy into this folder):
└── generate_data.py    ← generates transactions.csv
```

---

## Setup

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Add GROQ_API_KEY (required)
# Add LANGCHAIN_API_KEY (optional, for tracing)

# 3. Generate data (if you don't have transactions.csv)
python generate_data.py   # copy from Week 1

# 4. Run the Streamlit app
streamlit run app.py

# 5. OR run analysis directly
python langsmith_test.py
```

---

## Agent Architecture

```
User Query
    ↓
[Supervisor Agent]  — routes to correct agent based on state
    ↓         ↓           ↓            ↓            ↓
[Extractor] [Risk      [RAG         [Human       [Report
            Classifier] Agent]       Review]      Generator]
               ↓
         [Tools called]:
         - check_structuring
         - check_late_night
         - check_beneficiary_risk
         - check_velocity
         - calculate_risk_score
```

## State flow
```
START
  → extractor  (loads CSV → transactions[])
  → risk_classifier  (calls tools → risk_flags[], risk_score)
  → rag  (retrieves fraud context → retrieved_context[])
  → human_review  (INTERRUPT if overall_risk == HIGH)
  → report  (LLM writes final report)
  → END
```

---

## Human-in-the-loop (Day 13)
Graph pauses BEFORE `human_review` node when `overall_risk == "HIGH"`.
The Streamlit UI shows the flags and waits for Approve/Reject.
On approval, graph resumes and generates the report.

## Memory (Day 11)
SQLite checkpointer (`finguard_memory.db`) persists state per `thread_id`.
Different thread IDs = different sessions.
Same thread ID = resumes from last checkpoint.

---

## Week 2 Learnings

| Day | Concept | Key file |
|-----|---------|---------|
| 8 | LangGraph state + nodes | state.py, graph.py |
| 9 | Pydantic tool schemas | tools.py |
| 10 | ReAct pattern | agents.py (risk_classifier_agent) |
| 11 | Memory + persistence | graph.py (SqliteSaver) |
| 12 | Multi-agent supervisor | agents.py (supervisor_agent) |
| 13 | Human-in-the-loop | graph.py (interrupt_before) |
| 14 | LangSmith tracing | langsmith_test.py |

---

## Week 3 (coming)
- Fine-tune Llama-3 fraud classifier on custom dataset
- Replace LLM risk classifier with fine-tuned local model
- FastAPI backend
- React frontend
