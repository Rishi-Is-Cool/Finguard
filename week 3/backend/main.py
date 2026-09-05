"""
backend/main.py — Day 20
FastAPI backend exposing FinGuard AI as a REST API.

Endpoints:
  POST /upload          — upload CSV, returns document_id
  POST /analyze         — run multi-agent analysis, returns streaming SSE
  GET  /report/{doc_id} — get final report for a document
  GET  /flags/{doc_id}  — get risk flags for a document
  GET  /health          — health check

Usage:
  uvicorn backend.main:app --reload --port 8000

Reading reference: fastapi.tiangolo.com/tutorial
"""
import os
import uuid
import json
import asyncio
import tempfile
import shutil
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

load_dotenv()

# Groq serves a moving set of models; llama-3.1-8b-instant was retired.
# Override with GROQ_MODEL in .env if this one is retired too.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

app = FastAPI(
    title="FinGuard AI",
    description="Finance Fraud & Risk Intelligence API",
    version="3.0.0",
)

# ── CORS — allow React frontend ───────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory store (use Redis/DB in production) ──────────────────────────────
UPLOAD_DIR = Path(tempfile.mkdtemp())
analysis_store: dict[str, dict] = {}  # doc_id → analysis result
status_store:   dict[str, str]  = {}  # doc_id → status


# ── Request / Response models ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    document_id: str
    query:       str = "Analyze all transactions for fraud patterns and generate a risk report."
    thread_id:   str = "default"


class HealthResponse(BaseModel):
    status:      str
    version:     str
    model:       str   # the model that will actually serve classification
    finetuned:   bool  # is that the fine-tuned local model, or the Groq fallback?
    model_note:  str   # why, when the configured model is not the one serving


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check. Reports the model that will actually serve, not the
    one that is merely configured — those differ whenever the fine-tuned
    model does not fit on this machine."""
    from backend.classifier import USE_LOCAL, LOCAL_REASON, MODEL_NAME

    return HealthResponse(
        status="ok",
        version="3.0.0",
        model=MODEL_NAME if USE_LOCAL else f"{GROQ_MODEL} (groq)",
        finetuned=USE_LOCAL,
        model_note="" if USE_LOCAL else (
            f"{MODEL_NAME} configured but not loaded: {LOCAL_REASON}"
            if MODEL_NAME else "no FINGUARD_MODEL_NAME set"
        ),
    )


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    Upload a transaction CSV.
    Returns document_id to use in subsequent /analyze calls.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    doc_id   = str(uuid.uuid4())[:8]
    save_path = UPLOAD_DIR / f"{doc_id}.csv"

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Quick validation
    try:
        df = pd.read_csv(save_path)
        required = {"date", "time", "account", "beneficiary", "description", "amount", "type"}
        missing  = required - set(df.columns)
        if missing:
            save_path.unlink()
            raise HTTPException(
                status_code=400,
                detail=f"Missing columns: {missing}"
            )
        row_count = len(df)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {e}")

    status_store[doc_id] = "uploaded"

    return {
        "document_id":  doc_id,
        "filename":     file.filename,
        "row_count":    row_count,
        "status":       "uploaded",
        "message":      f"Ready to analyze {row_count} transactions.",
    }


@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """
    Run full multi-agent analysis on an uploaded document.
    Returns Server-Sent Events (SSE) stream showing agent progress.
    """
    doc_id   = request.document_id
    csv_path = UPLOAD_DIR / f"{doc_id}.csv"

    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

    async def event_stream():
        """Generate SSE events as agents run."""

        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        try:
            yield sse("status", {"step": "starting", "message": "Starting FinGuard analysis..."})
            await asyncio.sleep(0.1)

            # ── Step 1: Load data ─────────────────────────────────────────
            yield sse("agent", {"agent": "extractor", "status": "running", "message": "Loading transaction data..."})
            await asyncio.sleep(0.1)

            df = pd.read_csv(str(csv_path))
            df["date"]    = pd.to_datetime(df["date"])
            df["hour"]    = pd.to_datetime(df["time"], format="%H:%M").dt.hour
            df["weekday"] = df["date"].dt.day_name()

            yield sse("agent", {
                "agent":   "extractor",
                "status":  "done",
                "message": f"Extracted {len(df)} transactions",
                "data":    {
                    "total_count": len(df),
                    "date_range":  f"{df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}",
                    "accounts":    df["account"].unique().tolist(),
                }
            })
            await asyncio.sleep(0.2)

            # ── Step 2: Quick rule-based pre-screening ────────────────────
            yield sse("agent", {"agent": "risk_classifier", "status": "running", "message": "Classifying transaction risk..."})
            await asyncio.sleep(0.1)

            from backend.classifier import classify_transaction
            from backend.tools_standalone import (
                run_structuring_check,
                run_late_night_check,
                run_beneficiary_check,
                run_velocity_check,
                compute_risk_score,
            )

            risk_flags = []
            # SSE payloads are json.dumps'd, so records must hold plain Python
            # types only — no pandas Timestamps, no numpy scalars.
            transactions = [
                {
                    "date":        row["date"].strftime("%Y-%m-%d"),
                    "time":        str(row["time"]),
                    "account":     str(row["account"]),
                    "beneficiary": str(row["beneficiary"]),
                    "description": str(row["description"]),
                    "amount":      float(row["amount"]),
                    "type":        str(row["type"]),
                    "hour":        int(row["hour"]),
                    "weekday":     str(row["weekday"]),
                }
                for _, row in df.iterrows()
            ]

            for txn in transactions:
                # Structuring
                if txn["type"] == "debit":
                    r = run_structuring_check(float(txn["amount"]))
                    if r["is_structuring"]:
                        risk_flags.append({
                            "transaction": txn,
                            "flag_type":   "structuring",
                            "severity":    r["severity"],
                            "reason":      r["reason"],
                        })
                # Late night
                r = run_late_night_check(str(txn["time"]))
                if r["is_late_night"]:
                    risk_flags.append({
                        "transaction": txn,
                        "flag_type":   "late_night",
                        "severity":    r["severity"],
                        "reason":      r["reason"],
                    })
                # Beneficiary
                r = run_beneficiary_check(str(txn["beneficiary"]))
                if r["risk_level"] != "LOW":
                    risk_flags.append({
                        "transaction": txn,
                        "flag_type":   "unknown_beneficiary",
                        "severity":    r["risk_level"],
                        "reason":      r["reason"],
                    })

            # Velocity per account
            for acct in df["account"].unique().tolist():
                r = run_velocity_check(acct, str(csv_path))
                if r["is_high_velocity"]:
                    risk_flags.append({
                        "transaction": transactions[0],
                        "flag_type":   "velocity",
                        "severity":    r["severity"],
                        "reason":      r["reason"],
                    })

            score_result = compute_risk_score(
                sum(1 for f in risk_flags if f["severity"] == "HIGH"),
                sum(1 for f in risk_flags if f["severity"] == "MEDIUM"),
                sum(1 for f in risk_flags if f["severity"] == "LOW"),
                len(transactions),
            )

            yield sse("agent", {
                "agent":   "risk_classifier",
                "status":  "done",
                "message": f"Found {len(risk_flags)} flags — Overall: {score_result['label']}",
                "data":    {
                    "risk_flags":   risk_flags[:20],  # first 20 for response size
                    "overall_risk": score_result["label"],
                    "risk_score":   score_result["score"],
                    "flag_counts": {
                        "HIGH":   sum(1 for f in risk_flags if f["severity"] == "HIGH"),
                        "MEDIUM": sum(1 for f in risk_flags if f["severity"] == "MEDIUM"),
                        "LOW":    sum(1 for f in risk_flags if f["severity"] == "LOW"),
                    }
                }
            })
            await asyncio.sleep(0.2)

            # ── Step 3: fine-tuned classifier on the top flags ────────────
            # Day 18. The rules above are deterministic; this asks the model
            # what it thinks about the transactions they flagged hardest.
            # Bounded to TOP_N so one upload cannot fan out into hundreds of
            # model calls, and wrapped so a classifier failure never kills the
            # run — the rest of the report is still worth having.
            yield sse("agent", {"agent": "ai_classifier", "status": "running",
                                "message": "Running fraud classifier on top flags..."})
            await asyncio.sleep(0.1)

            ai_classifications = []
            try:
                from backend.classifier import classify_transaction_batch

                top_n = int(os.getenv("FINGUARD_CLASSIFY_TOP_N", "5"))

                # Distinct transactions only — one transaction often carries
                # several flags (structuring *and* late_night, say).
                seen, to_classify = set(), []
                for f in risk_flags:
                    if f["severity"] != "HIGH":
                        continue
                    t = f["transaction"]
                    key = (t["date"], t["time"], t["account"], t["beneficiary"], t["amount"])
                    if key in seen:
                        continue
                    seen.add(key)
                    to_classify.append(t)
                    if len(to_classify) >= top_n:
                        break

                # Sync + network-bound; keep it off the event loop.
                results = await asyncio.to_thread(classify_transaction_batch, to_classify)

                for r in results:
                    ai_classifications.append({
                        "transaction":  r["transaction"],
                        "risk_level":   r["risk_level"],
                        "reasoning":    r["reasoning"],
                        "model_used":   r["model_used"],
                        "is_finetuned": r["is_finetuned"],
                    })

                agreed = sum(1 for c in ai_classifications if c["risk_level"] == "HIGH")
                model_label = ai_classifications[0]["model_used"] if ai_classifications else "n/a"
                yield sse("agent", {
                    "agent":   "ai_classifier",
                    "status":  "done",
                    "message": f"Classified {len(ai_classifications)} flags — {agreed} confirmed HIGH",
                    "data": {
                        "classifications": ai_classifications,
                        "model_used":      model_label,
                        "is_finetuned":    bool(ai_classifications and ai_classifications[0]["is_finetuned"]),
                        "agreed_high":     agreed,
                        "sampled":         len(ai_classifications),
                    },
                })
            except Exception as e:
                yield sse("agent", {
                    "agent":   "ai_classifier",
                    "status":  "error",
                    "message": f"Classifier unavailable — continuing: {str(e)[:120]}",
                })
            await asyncio.sleep(0.2)

            # ── Step 4: CRAG context retrieval ────────────────────────────
            yield sse("agent", {"agent": "rag", "status": "running", "message": "Retrieving fraud rule context..."})
            await asyncio.sleep(0.1)

            from backend.agentic_rag import build_crag

            flag_types  = list(set(f["flag_type"] for f in risk_flags))
            rag_query   = " and ".join(flag_types) + " fraud patterns and detection rules"

            crag        = build_crag(df)
            rag_result  = crag.answer(rag_query)

            yield sse("agent", {
                "agent":   "rag",
                "status":  "done",
                "message": f"Retrieved {len(rag_result['sources'])} fraud rule references",
                "data":    {
                    "sources":       rag_result["sources"],
                    "was_rewritten": rag_result["was_rewritten"],
                    "final_query":   rag_result["final_query"],
                }
            })
            await asyncio.sleep(0.2)

            # ── Step 5: Generate report ───────────────────────────────────
            yield sse("agent", {"agent": "report", "status": "running", "message": "Generating risk report..."})
            await asyncio.sleep(0.1)

            from langchain_groq import ChatGroq
            from langchain_core.messages import HumanMessage

            llm = ChatGroq(
                model=GROQ_MODEL,
                api_key=os.getenv("GROQ_API_KEY"),
                temperature=0,
            )

            high_flags = [f for f in risk_flags if f["severity"] == "HIGH"]
            med_flags  = [f for f in risk_flags if f["severity"] == "MEDIUM"]

            flags_text = ""
            for f in high_flags[:5]:
                t = f["transaction"]
                flags_text += (
                    f"\n  [HIGH] {t.get('date','')} {t.get('time','')} | "
                    f"₹{float(t.get('amount',0)):,.0f} | "
                    f"{t.get('account','')} → {t.get('beneficiary','')} | "
                    f"{f['reason']}"
                )

            context_text = "\n".join(f"- {s[:200]}" for s in rag_result["sources"][:5])

            ai_text = ""
            for c in ai_classifications:
                t = c["transaction"]
                ai_text += (
                    f"\n  [{c['risk_level']}] {t.get('account','')} -> {t.get('beneficiary','')} "
                    f"₹{float(t.get('amount', 0)):,.0f}: {c['reasoning'][:180]}"
                )

            report_prompt = f"""You are a compliance officer writing a fraud risk assessment.

DATASET: {len(transactions)} transactions | {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}
OVERALL RISK: {score_result['label']} (score: {score_result['score']:.3f})
TOTAL FLAGS: {len(risk_flags)} ({len(high_flags)} HIGH, {len(med_flags)} MEDIUM)

KEY FINDINGS:
{flags_text if flags_text else "No high-severity flags."}

FRAUD RULE CONTEXT:
{context_text}

MODEL CLASSIFICATION OF TOP FLAGS:
{ai_text if ai_text else "Not available for this run."}

USER QUERY: {request.query}

Write a professional fraud risk report with:
1. Executive Summary
2. Key Risk Findings (most severe first)
3. Pattern Analysis
4. Recommended Actions
5. Risk Rating: {score_result['label']}"""

            response = llm.invoke([HumanMessage(content=report_prompt)])
            report   = response.content

            yield sse("agent", {
                "agent":   "report",
                "status":  "done",
                "message": "Risk report generated",
            })
            await asyncio.sleep(0.1)

            # ── Final result ──────────────────────────────────────────────
            final = {
                "document_id":   doc_id,
                "total_count":   len(transactions),
                "date_range":    f"{df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}",
                "overall_risk":  score_result["label"],
                "risk_score":    score_result["score"],
                "risk_flags":    risk_flags,
                "report":        report,
                "rag_sources":   rag_result["sources"],
                "ai_classifications": ai_classifications,
            }
            analysis_store[doc_id] = final
            status_store[doc_id]   = "complete"

            # Send the same shape /report/{doc_id} returns. RiskReport.jsx
            # reads risk_flags, total_count and rag_sources off this payload —
            # a trimmed version renders "0 flags" for a HIGH-risk report.
            yield sse("complete", {**final, "total_flags": len(risk_flags)})

        except Exception as e:
            status_store[doc_id] = "error"
            yield sse("error", {"message": str(e), "document_id": doc_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/report/{doc_id}")
async def get_report(doc_id: str):
    """Get the stored analysis result for a document."""
    if doc_id not in analysis_store:
        status = status_store.get(doc_id, "not_found")
        raise HTTPException(
            status_code=404 if status == "not_found" else 202,
            detail=f"Analysis {status}. Try again after /analyze completes."
        )
    return analysis_store[doc_id]


@app.get("/flags/{doc_id}")
async def get_flags(doc_id: str, severity: Optional[str] = None):
    """Get risk flags for a document, optionally filtered by severity."""
    if doc_id not in analysis_store:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    flags = analysis_store[doc_id].get("risk_flags", [])
    if severity:
        flags = [f for f in flags if f["severity"] == severity.upper()]

    return {
        "document_id": doc_id,
        "total":       len(flags),
        "flags":       flags,
    }


@app.get("/status/{doc_id}")
async def get_status(doc_id: str):
    """Get analysis status."""
    return {
        "document_id": doc_id,
        "status":      status_store.get(doc_id, "not_found"),
    }
