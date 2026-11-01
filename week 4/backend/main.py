"""
backend/main.py — Week 4
FinGuard AI API. Every route is served at both /x and /api/x: the Vite dev
proxy and split deployments use the bare paths, while the single-container
deployment serves the built frontend from / and the API from /api.

  POST /upload                   upload a CSV → document_id
  POST /upload/sample            load the bundled sample CSV → document_id
  GET  /sample.csv               download the sample (shows the expected format)
  POST /analyze                  run the 5-agent pipeline, streamed as SSE
  GET  /report/{doc_id}          final result
  GET  /flags/{doc_id}           rule flags, optional ?severity=
  GET  /status/{doc_id}
  GET  /audit/{doc_id}           hash-chained audit trail + chain verification
  GET  /audit/{doc_id}/verify
  GET  /audit/{doc_id}/export.csv   case file: one row per flagged transaction
  POST /review/{doc_id}          record a human decision on a transaction
  GET  /review/{doc_id}
  GET  /health

Run:  uvicorn backend.main:app --reload --port 8000
"""
import asyncio
import csv
import hashlib
import io
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.audit import AuditLog, sha256_text, valid_doc_id
from backend.pipeline import flagged_transactions, normalize_transactions, run_rules
from backend.tools_standalone import RULESET, RULESET_VERSION

load_dotenv()

VERSION     = "4.0.0"
ROOT        = Path(__file__).resolve().parent.parent
GROQ_MODEL  = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
MAX_UPLOAD  = int(float(os.getenv("FINGUARD_MAX_UPLOAD_MB", "5")) * 1024 * 1024)
MAX_ROWS    = int(os.getenv("FINGUARD_MAX_ROWS", "5000"))
RATE_LIMIT  = int(os.getenv("FINGUARD_RATE_LIMIT_PER_HOUR", "20"))  # /analyze per IP; 0 = off
SAMPLE_CSV  = ROOT / "data" / "transactions.csv"
STATIC_DIR  = Path(os.getenv("FINGUARD_STATIC_DIR", ROOT / "frontend" / "dist"))
CORS        = [o.strip() for o in os.getenv(
    "FINGUARD_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]

UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="finguard-"))
audit_log  = AuditLog(Path(os.getenv("FINGUARD_AUDIT_DIR", ROOT / "audit_logs")))

# Bounded: a public demo must not grow memory or temp disk without limit.
uploads:        "OrderedDict[str, dict]" = OrderedDict()
analysis_store: "OrderedDict[str, dict]" = OrderedDict()
status_store:   dict[str, str] = {}
_STORE_CAP = 100


def _remember(store: OrderedDict, key: str, value: dict):
    store[key] = value
    store.move_to_end(key)
    while len(store) > _STORE_CAP:
        old_key, old = store.popitem(last=False)
        if "path" in old:
            Path(old["path"]).unlink(missing_ok=True)
        status_store.pop(old_key, None)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Warm the embedding + reranker models in the background: the port opens
    # immediately (hosts health-check it) and the first analysis doesn't pay
    # the model load.
    if os.getenv("FINGUARD_SKIP_WARMUP", "").lower() not in ("1", "true", "yes"):
        def warm():
            try:
                from backend.agentic_rag import warm_models
                warm_models()
                print("[Startup] RAG models warm.")
            except Exception as e:
                print(f"[Startup] Model warm-up failed (will retry on first use): {e}")
        threading.Thread(target=warm, daemon=True).start()
    yield
    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)


app = FastAPI(title="FinGuard AI", description="Finance Fraud & Risk Intelligence API",
              version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
router = APIRouter()


# ── Rate limiting (per client IP, sliding hour) ───────────────────────────────
_hits: dict[str, deque] = defaultdict(deque)


TRUSTED_HOPS = int(os.getenv("FINGUARD_TRUSTED_PROXY_HOPS", "1"))


def _client_ip(request: Request) -> str:
    # The left of X-Forwarded-For is whatever the client typed; only entries
    # appended by our own proxies can be trusted, counted from the right.
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if TRUSTED_HOPS and len(hops) >= TRUSTED_HOPS:
        return hops[-TRUSTED_HOPS]
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request):
    if RATE_LIMIT <= 0:
        return
    now, window = time.time(), _hits[_client_ip(request)]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        retry = int(3600 - (now - window[0])) + 1
        raise HTTPException(429, f"Rate limit: {RATE_LIMIT} analyses per hour. Retry in {retry // 60 + 1} min.",
                            headers={"Retry-After": str(retry)})
    window.append(now)


def _require_doc(doc_id: str):
    if not valid_doc_id(doc_id):
        raise HTTPException(404, "Document not found.")


# ── Models ────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    document_id: str
    query:       str = Field("Analyze all transactions for fraud patterns and generate a risk report.",
                             max_length=1000)
    thread_id:   str = "default"


class ReviewRequest(BaseModel):
    txn_id:   str = Field(pattern=r"^T\d{4,}$")
    decision: Literal["confirmed_fraud", "false_positive", "needs_escalation"]
    note:     str = Field("", max_length=500)
    reviewer: str = Field("anonymous", min_length=1, max_length=80)


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    """Reports the models that will actually serve — not merely the ones configured."""
    from backend.classifier import USE_LOCAL, LOCAL_REASON, MODEL_NAME
    from backend.jev import JEV_MODEL, jev_enabled

    return {
        "status":     "ok",
        "version":    VERSION,
        "model":      MODEL_NAME if USE_LOCAL else f"{GROQ_MODEL} (groq)",
        "finetuned":  USE_LOCAL,
        "model_note": "" if USE_LOCAL else (
            f"{MODEL_NAME} configured but not loaded: {LOCAL_REASON}" if MODEL_NAME
            else "no FINGUARD_MODEL_NAME set"),
        "screener":   JEV_MODEL if jev_enabled() else None,
        "classifier_mode": "cascade" if jev_enabled() else "llm_only",
        "ruleset":    RULESET_VERSION,
    }


# ── Upload ────────────────────────────────────────────────────────────────────

def _register_upload(raw: bytes, filename: str) -> dict:
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD // (1024 * 1024)} MB.")
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
        transactions = normalize_transactions(df.to_dict("records"))
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        raise HTTPException(400, f"Invalid CSV: {e}")
    if len(transactions) > MAX_ROWS:
        raise HTTPException(413, f"{len(transactions)} rows; this deployment accepts up to {MAX_ROWS}.")

    doc_id = uuid.uuid4().hex[:8]
    path = UPLOAD_DIR / f"{doc_id}.csv"
    path.write_bytes(raw)
    meta = {"filename": filename, "rows": len(transactions), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "path": str(path)}
    _remember(uploads, doc_id, meta)
    status_store[doc_id] = "uploaded"
    audit_log.append(doc_id, "input_received", {k: v for k, v in meta.items() if k != "path"})
    return {"document_id": doc_id, "filename": filename, "row_count": len(transactions),
            "status": "uploaded", "message": f"Ready to analyze {len(transactions)} transactions."}


@router.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are supported.")
    return _register_upload(await file.read(MAX_UPLOAD + 1), file.filename)


@router.post("/upload/sample")
async def upload_sample():
    return _register_upload(SAMPLE_CSV.read_bytes(), "sample_transactions.csv")


@router.get("/sample.csv")
async def sample_csv():
    return FileResponse(SAMPLE_CSV, media_type="text/csv", filename="finguard_sample_transactions.csv")


# ── Analysis ──────────────────────────────────────────────────────────────────

def _report_prompt(transactions, run, cascade, rag_result, query) -> str:
    flags = run["flags"]
    high  = [f for f in flags if f["severity"] == "HIGH"]
    dates = sorted(t["date"] for t in transactions)

    flags_text = "".join(
        f"\n  [HIGH] {f['transaction'].get('date', '')} {f['transaction'].get('time', '')} | "
        f"₹{float(f['transaction'].get('amount', 0)):,.0f} | {f['transaction'].get('account', '')} → "
        f"{f['transaction'].get('beneficiary', 'account-level')} | {f['reason']}"
        for f in high[:5])
    context_text = "\n".join(f"- {s[:200]}" for s in rag_result["sources"][:5])

    cls = cascade["classifications"]
    stats = cascade["stats"]
    worst = [c for c in cls if c["risk_level"] == "HIGH"][:5] or cls[:5]
    ai_text = "".join(
        f"\n  [{c['risk_level']} via {c['route']}] {c['transaction']['account']} -> "
        f"{c['transaction']['beneficiary']} ₹{c['transaction']['amount']:,.0f}: {c['reasoning'][:180]}"
        for c in worst)
    if stats.get("mode") == "cascade":
        ai_text += (f"\n  Screening: {stats['screened']} flagged transactions screened by Jev; "
                    f"{stats['auto']} resolved automatically, {stats['escalated_llm']} escalated to the LLM, "
                    f"{stats['human_review']} queued for human review; "
                    f"{stats['disagreements']} model verdicts disagree with the rule severity.")

    return f"""You are a compliance officer writing a fraud risk assessment.

DATASET: {len(transactions)} transactions | {dates[0]} to {dates[-1]}
OVERALL RISK: {run['score']['label']} (score: {run['score']['score']:.3f})
TOTAL FLAGS: {len(flags)} ({run['counts']['HIGH']} HIGH, {run['counts']['MEDIUM']} MEDIUM) — these are rule hits, not transactions
FLAGGED TRANSACTIONS: {len({f['transaction'].get('txn_id') for f in flags if f['scope'] == 'transaction'})} of {len(transactions)} (one transaction can trip several rules)
RULESET: {RULESET_VERSION}

KEY FINDINGS:
{flags_text or "No high-severity flags."}

FRAUD RULE CONTEXT:
{context_text}

MODEL CLASSIFICATION OF FLAGGED TRANSACTIONS:
{ai_text or "Not available for this run."}

USER QUERY: {query}

Write a professional fraud risk report with:
1. Executive Summary
2. Key Risk Findings (most severe first)
3. Pattern Analysis — note where the model verdicts disagree with the rules
4. Recommended Actions
5. Risk Rating: {run['score']['label']}"""


def _run_rag(transactions, query):
    from backend.agentic_rag import build_crag
    crag = build_crag(transactions)
    try:
        return crag.answer(query)
    finally:
        crag.close()


def _write_report(prompt: str) -> str:
    from langchain_core.messages import HumanMessage
    from langchain_groq import ChatGroq
    llm = ChatGroq(model=GROQ_MODEL, api_key=os.getenv("GROQ_API_KEY"), temperature=0)
    return llm.invoke([HumanMessage(content=prompt)]).content


@router.post("/analyze")
async def analyze(body: AnalyzeRequest, request: Request):
    doc_id = body.document_id
    _require_doc(doc_id)
    if doc_id not in uploads:
        raise HTTPException(404, f"Document {doc_id} not found.")
    _check_rate_limit(request)
    csv_path = Path(uploads[doc_id]["path"])

    async def event_stream():
        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        try:
            status_store[doc_id] = "running"
            yield sse("status", {"step": "starting", "message": "Starting FinGuard analysis..."})

            # ── 1. Extract ────────────────────────────────────────────────
            yield sse("agent", {"agent": "extractor", "status": "running", "message": "Loading transaction data..."})
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
            transactions = normalize_transactions(df.to_dict("records"))
            dates = sorted(t["date"] for t in transactions)
            date_range = f"{dates[0]} to {dates[-1]}"
            yield sse("agent", {"agent": "extractor", "status": "done",
                                "message": f"Extracted {len(transactions)} transactions",
                                "data": {"total_count": len(transactions), "date_range": date_range,
                                         "accounts": sorted({t["account"] for t in transactions})}})

            # ── 2. Rules ──────────────────────────────────────────────────
            yield sse("agent", {"agent": "risk_classifier", "status": "running", "message": "Classifying transaction risk..."})
            run = run_rules(transactions)
            flags, score = run["flags"], run["score"]
            candidates = flagged_transactions(flags)
            audit_log.append(doc_id, "rules_applied", {
                "ruleset_version": RULESET_VERSION,
                "ruleset": RULESET,
                "counts": run["counts"],
                "score": score,
                "flags": [{"flag_id": f["flag_id"], "rule": f["flag_type"], "severity": f["severity"],
                           "scope": f["scope"], "txn_id": f["transaction"].get("txn_id"),
                           "account": f["transaction"]["account"], "reason": f["reason"]} for f in flags],
                "flagged_transactions": [
                    {k: c["transaction"][k] for k in
                     ("txn_id", "date", "time", "account", "beneficiary", "description", "amount", "type")}
                    for c in candidates],
            })
            yield sse("agent", {"agent": "risk_classifier", "status": "done",
                                "message": f"Found {len(flags)} flags on {len(candidates)} transactions — Overall: {score['label']}",
                                "data": {"risk_flags": flags[:20], "overall_risk": score["label"],
                                         "risk_score": score["score"], "flag_counts": run["counts"]}})

            # ── 3. Model screening (Jev cascade, or LLM only) ─────────────
            yield sse("agent", {"agent": "ai_classifier", "status": "running",
                                "message": "Screening flagged transactions..."})
            cascade = {"classifications": [], "stats": {"mode": "unavailable"}}
            try:
                from backend.classifier import run_cascade
                from backend.knowledge import FRAUD_RULES
                cascade = await asyncio.to_thread(run_cascade, candidates, FRAUD_RULES)
                st = cascade["stats"]
                msg = (f"Jev screened {st['screened']}: {st['auto']} auto · {st['escalated_llm']} to LLM · "
                       f"{st['human_review']} to human" if st["mode"] == "cascade"
                       else f"Classified {st['classified']} — {st['agreed_high']} confirmed HIGH")
                yield sse("agent", {"agent": "ai_classifier", "status": "done", "message": msg,
                                    "data": {"classifications": cascade["classifications"][:20], **st}})
            except Exception as e:
                yield sse("agent", {"agent": "ai_classifier", "status": "error",
                                    "message": f"Classifier unavailable — continuing: {str(e)[:120]}"})
            audit_log.append(doc_id, "model_screening", {
                "stats": cascade["stats"],
                "verdicts": [{"txn_id": c["transaction"]["txn_id"], "rule_severity": c["rule_severity"],
                              "risk_level": c["risk_level"], "route": c["route"], "model_used": c["model_used"],
                              "confidence": (c.get("jev") or {}).get("confidence"),
                              "probabilities": (c.get("jev") or {}).get("probabilities"),
                              "legit_probability": (c.get("jev") or {}).get("legit_probability"),
                              "disagrees_with_rules": c["disagrees_with_rules"],
                              "reasoning": c["reasoning"]} for c in cascade["classifications"]],
            })

            # ── 4. CRAG ───────────────────────────────────────────────────
            yield sse("agent", {"agent": "rag", "status": "running", "message": "Retrieving fraud rule context..."})
            flag_types = sorted({f["flag_type"] for f in flags})
            rag_query  = " and ".join(flag_types) + " fraud patterns and detection rules"
            rag_result = await asyncio.to_thread(_run_rag, transactions, rag_query)
            audit_log.append(doc_id, "context_retrieved", {
                "query": rag_query, "final_query": rag_result["final_query"],
                "was_rewritten": rag_result["was_rewritten"], "sources": rag_result["sources"]})
            yield sse("agent", {"agent": "rag", "status": "done",
                                "message": f"Retrieved {len(rag_result['sources'])} fraud rule references",
                                "data": {"sources": rag_result["sources"], "was_rewritten": rag_result["was_rewritten"],
                                         "final_query": rag_result["final_query"]}})

            # ── 5. Report ─────────────────────────────────────────────────
            yield sse("agent", {"agent": "report", "status": "running", "message": "Generating risk report..."})
            prompt = _report_prompt(transactions, run, cascade, rag_result, body.query)
            report = await asyncio.to_thread(_write_report, prompt)
            audit_log.append(doc_id, "report_generated", {
                "model": f"{GROQ_MODEL} (groq)", "prompt_sha256": sha256_text(prompt),
                "report_sha256": sha256_text(report), "report": report})
            yield sse("agent", {"agent": "report", "status": "done", "message": "Risk report generated"})

            final = {
                "document_id":        doc_id,
                "total_count":        len(transactions),
                "date_range":         date_range,
                "overall_risk":       score["label"],
                "risk_score":         score["score"],
                "risk_flags":         flags,
                "report":             report,
                "rag_sources":        rag_result["sources"],
                "ai_classifications": cascade["classifications"],
                "classifier_stats":   cascade["stats"],
                "ruleset_version":    RULESET_VERSION,
                "audit":              audit_log.verify(doc_id),
            }
            _remember(analysis_store, doc_id, final)
            status_store[doc_id] = "complete"
            yield sse("complete", {**final, "total_flags": len(flags)})

        except Exception as e:
            status_store[doc_id] = "error"
            yield sse("error", {"message": str(e), "document_id": doc_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/report/{doc_id}")
async def get_report(doc_id: str):
    _require_doc(doc_id)
    if doc_id not in analysis_store:
        status = status_store.get(doc_id, "not_found")
        raise HTTPException(404 if status == "not_found" else 409,
                            f"Analysis {status}. Try again after /analyze completes.")
    return analysis_store[doc_id]


@router.get("/flags/{doc_id}")
async def get_flags(doc_id: str, severity: Optional[str] = None):
    _require_doc(doc_id)
    if doc_id not in analysis_store:
        raise HTTPException(404, "Analysis not found.")
    flags = analysis_store[doc_id]["risk_flags"]
    if severity:
        flags = [f for f in flags if f["severity"] == severity.upper()]
    return {"document_id": doc_id, "total": len(flags), "flags": flags}


@router.get("/status/{doc_id}")
async def get_status(doc_id: str):
    return {"document_id": doc_id, "status": status_store.get(doc_id, "not_found")}


# ── Audit trail + human review ────────────────────────────────────────────────

def _events_or_404(doc_id: str) -> list[dict]:
    _require_doc(doc_id)
    events = audit_log.events(doc_id)
    if not events:
        raise HTTPException(404, "No audit trail for this document.")
    return events


@router.get("/audit/{doc_id}")
async def get_audit(doc_id: str):
    events = _events_or_404(doc_id)
    return {"document_id": doc_id, "chain": audit_log.verify(doc_id), "events": events}


@router.get("/audit/{doc_id}/verify")
async def verify_audit(doc_id: str):
    _events_or_404(doc_id)
    return audit_log.verify(doc_id)


@router.get("/audit/{doc_id}/export.csv")
async def export_audit_csv(doc_id: str):
    """The case file a reviewer hands to an examiner — rebuilt purely from the
    audit log, so it survives a restart and matches what was recorded."""
    events = _events_or_404(doc_id)
    latest = {}
    for e in events:
        latest[e["type"]] = e["payload"]
    rules = latest.get("rules_applied")
    if not rules:
        raise HTTPException(409, "Analysis has not run for this document yet.")
    fired = defaultdict(list)
    for f in rules["flags"]:
        if f["txn_id"]:
            fired[f["txn_id"]].append(f"{f['rule']}:{f['severity']}")
    verdicts = {v["txn_id"]: v for v in latest.get("model_screening", {}).get("verdicts", [])}
    reviews = audit_log.reviews(doc_id)
    chain = audit_log.verify(doc_id)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["txn_id", "date", "time", "account", "beneficiary", "amount_inr", "type", "description",
                "rules_fired", "rule_severity", "model_verdict", "route", "model", "confidence",
                "disagrees_with_rules", "human_decision", "reviewer", "review_note", "reviewed_at",
                "ruleset_version", "audit_chain_head"])
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    for t in rules["flagged_transactions"]:
        sevs = [s.split(":")[1] for s in fired[t["txn_id"]]]
        v, r = verdicts.get(t["txn_id"], {}), reviews.get(t["txn_id"], {})
        w.writerow([t["txn_id"], t["date"], t["time"], t["account"], t["beneficiary"], t["amount"], t["type"],
                    t["description"], "; ".join(fired[t["txn_id"]]), min(sevs, key=order.get) if sevs else "",
                    v.get("risk_level", ""), v.get("route", "not_screened"), v.get("model_used", ""),
                    "" if v.get("confidence") is None else f"{v['confidence']:.3f}",
                    v.get("disagrees_with_rules", ""), r.get("decision", ""), r.get("reviewer", ""),
                    r.get("note", ""), r.get("ts", ""), rules["ruleset_version"], chain["head"] or ""])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="finguard-case-file-{doc_id}.csv"'})


@router.post("/review/{doc_id}")
async def post_review(doc_id: str, body: ReviewRequest):
    events = _events_or_404(doc_id)
    known = {t["txn_id"] for e in events if e["type"] == "rules_applied"
             for t in e["payload"]["flagged_transactions"]}
    if body.txn_id not in known:
        raise HTTPException(404, f"{body.txn_id} is not a flagged transaction in {doc_id}.")
    event = audit_log.append(doc_id, "human_review",
                             {"txn_id": body.txn_id, "decision": body.decision, "note": body.note},
                             actor=body.reviewer.strip())
    return {"event": event, "chain": audit_log.verify(doc_id), "reviews": audit_log.reviews(doc_id)}


@router.get("/review/{doc_id}")
async def get_reviews(doc_id: str):
    _events_or_404(doc_id)
    return {"document_id": doc_id, "reviews": audit_log.reviews(doc_id)}


app.include_router(router)
app.include_router(router, prefix="/api", include_in_schema=False)

# Single-container deployment: the built React app is served from /. Mounted
# last so it never shadows an API route.
if (STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
