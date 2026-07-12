# 🛡️ FinGuard AI — Week 1

Finance Fraud & Risk Intelligence System built with RAG + Pandas Agent + LangChain.

## What it does
- Upload bank statement CSVs
- Auto-detects fraud patterns (structuring, late-night transfers, unknown beneficiaries)
- Answers natural language questions about transactions
- Routes analytical queries to a pandas agent, semantic queries to RAG

---

## File Structure
```
finguard_ai/
├── app.py              ← Streamlit frontend (Day 7)
├── pipeline.py         ← Core RAG + agent pipeline (Days 1–6)
├── evaluate.py         ← RAGAS evaluation (Day 5)
├── generate_data.py    ← Synthetic transaction data generator
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

### 1. Clone and install
```bash
pip install -r requirements.txt
```

### 2. Set your Groq API key
```bash
cp .env.example .env
# Edit .env and paste your key from console.groq.com
```

### 3. Generate sample data
```bash
python generate_data.py
```

### 4. Run the app
```bash
streamlit run app.py
```

### 5. Run RAGAS evaluation (optional)
```bash
python evaluate.py
```

---

## Stack
| Component | Tool |
|-----------|------|
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Vector Store | ChromaDB (in-memory) |
| Retrieval | Hybrid BM25 + Dense (EnsembleRetriever) |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| LLM | Llama-3.1-8b-instant via Groq |
| Evaluation | RAGAS |
| Frontend | Streamlit |

---

## Query Routing
| Query Type | Example | Path |
|------------|---------|------|
| SEMANTIC | "Any suspicious transfers to Unknown Co?" | Hybrid RAG + reranker |
| ANALYTICAL | "Total debited from ACC001?" | Pandas agent |

---

## Week 1 Learnings

### Day 3 — RAG failure analysis
| Query Type | RAG correct? | Fix |
|------------|-------------|-----|
| Semantic search | ✅ Yes | — |
| Exact keyword | ✅ Yes (after hybrid) | BM25 |
| Count/aggregate | ❌ No | Day 6: pandas agent |
| Date arithmetic | ❌ No | Day 6: pandas agent |
| Sum/total | ❌ No | Day 6: pandas agent |

### Day 4 — Reranking
Dense search alone missed exact amount queries (e.g. "49800").
Two-stage retrieval: top-20 hybrid → cross-encoder rerank → top-5.

### Day 5 — RAGAS Scores
*(Run evaluate.py and paste your scores here)*
| Metric | Score |
|--------|-------|
| Faithfulness | — |
| Answer Relevancy | — |
| Context Precision | — |

---

## Week 2 (coming)
- LangGraph multi-agent system
- Extractor → Risk Classifier → Report Generator agents
- Human-in-the-loop fraud review
- LangSmith observability
