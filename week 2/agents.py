"""
agents.py — Days 9–12 (fixed v2)
Fix: supervisor_agent human_review condition was looping back
to human_review even after approval. Added human_approved check.
"""
import os
import pandas as pd
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage

from state import FinGuardState, RiskFlag, Transaction
from tools import (
    check_structuring,
    check_late_night,
    check_beneficiary_risk,
    check_velocity,
    calculate_risk_score,
)

load_dotenv()


def _get_llm(temperature: float = 0) -> ChatGroq:
    return ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=temperature,
    )


# ── Agent 1: Extractor ────────────────────────────────────────────────────────
def extractor_agent(state: FinGuardState) -> dict:
    print("\n[Extractor] Loading transactions...")
    try:
        df = pd.read_csv(state["csv_path"])
        df["date"] = pd.to_datetime(df["date"])
        df["hour"] = pd.to_datetime(df["time"], format="%H:%M").dt.hour

        transactions = []
        for _, row in df.iterrows():
            transactions.append(Transaction(
                date=str(row["date"].date()),
                time=str(row["time"]),
                account=str(row["account"]),
                beneficiary=str(row["beneficiary"]),
                description=str(row["description"]),
                amount=float(row["amount"]),
                type=str(row["type"]),
            ))

        date_min = df["date"].min().strftime("%Y-%m-%d")
        date_max = df["date"].max().strftime("%Y-%m-%d")
        print(f"[Extractor] Loaded {len(transactions)} transactions.")

        return {
            "transactions": transactions,
            "total_count":  len(transactions),
            "date_range":   f"{date_min} to {date_max}",
            "next_agent":   "risk_classifier",
            "messages": [AIMessage(content=f"Extracted {len(transactions)} transactions ({date_min} to {date_max}).")],
        }
    except Exception as e:
        print(f"[Extractor] ERROR: {e}")
        return {"error": str(e), "next_agent": "END"}


# ── Agent 2: Risk Classifier ──────────────────────────────────────────────────
def risk_classifier_agent(state: FinGuardState) -> dict:
    print("\n[Risk Classifier] Analyzing transactions...")

    transactions = state.get("transactions", [])
    csv_path     = state.get("csv_path", "transactions.csv")
    risk_flags   = []

    for txn in transactions:
        if txn["type"] == "debit":
            r = check_structuring.invoke({"amount": txn["amount"], "threshold": 50000})
            if r["is_structuring"]:
                risk_flags.append(RiskFlag(
                    transaction=txn, flag_type="structuring",
                    severity=r["severity"], reason=r["reason"],
                ))

        late = check_late_night.invoke({"time_str": txn["time"]})
        if late["is_late_night"]:
            risk_flags.append(RiskFlag(
                transaction=txn, flag_type="late_night",
                severity=late["severity"], reason=late["reason"],
            ))

        bene = check_beneficiary_risk.invoke({"beneficiary": txn["beneficiary"]})
        if bene["risk_level"] != "LOW":
            risk_flags.append(RiskFlag(
                transaction=txn, flag_type="unknown_beneficiary",
                severity=bene["risk_level"], reason=bene["reason"],
            ))

    for acct in set(t["account"] for t in transactions):
        vel = check_velocity.invoke({"account_id": acct, "csv_path": csv_path})
        if vel["is_high_velocity"]:
            acct_txns = [t for t in transactions if t["account"] == acct]
            if acct_txns:
                risk_flags.append(RiskFlag(
                    transaction=acct_txns[0], flag_type="velocity",
                    severity=vel["severity"], reason=vel["reason"],
                ))

    high   = sum(1 for f in risk_flags if f["severity"] == "HIGH")
    medium = sum(1 for f in risk_flags if f["severity"] == "MEDIUM")
    low    = sum(1 for f in risk_flags if f["severity"] == "LOW")

    score_result = calculate_risk_score.invoke({
        "flag_count_high": high, "flag_count_medium": medium,
        "flag_count_low": low,   "total_transactions": len(transactions),
    })

    print(f"[Risk Classifier] {len(risk_flags)} flags — Risk: {score_result['label']}")

    return {
        "risk_flags":   risk_flags,
        "overall_risk": score_result["label"],
        "risk_score":   score_result["score"],
        "next_agent":   "rag",
        "messages": [AIMessage(content=f"Found {len(risk_flags)} flags. Overall: {score_result['label']}.")],
    }


# ── Agent 3: RAG Agent ────────────────────────────────────────────────────────
def rag_agent(state: FinGuardState, retriever=None) -> dict:
    print("\n[RAG Agent] Retrieving fraud context...")

    if retriever is None:
        return {"retrieved_context": [], "next_agent": "report_generator"}

    risk_flags = state.get("risk_flags", [])
    if not risk_flags:
        return {"retrieved_context": [], "next_agent": "report_generator"}

    flag_types  = set(f["flag_type"] for f in risk_flags)
    query_parts = []
    if "structuring"         in flag_types: query_parts.append("structuring transactions below reporting threshold")
    if "late_night"          in flag_types: query_parts.append("late night suspicious transactions")
    if "unknown_beneficiary" in flag_types: query_parts.append("unknown beneficiary money transfer risk")
    if "velocity"            in flag_types: query_parts.append("high velocity transaction fraud pattern")

    query = " AND ".join(query_parts) if query_parts else "fraud detection patterns"

    from rag import retrieve_fraud_context
    context = retrieve_fraud_context(query, retriever)
    print(f"[RAG Agent] Retrieved {len(context)} chunks.")

    return {
        "retrieved_context": context,
        "next_agent": "report_generator",
        "messages": [AIMessage(content=f"Retrieved {len(context)} fraud rule references.")],
    }


# ── Agent 4: Report Generator ─────────────────────────────────────────────────
def report_agent(state: FinGuardState) -> dict:
    print("\n[Report Agent] Generating report...")

    llm        = _get_llm(temperature=0)
    risk_flags = state.get("risk_flags", [])
    context    = state.get("retrieved_context", [])
    overall    = state.get("overall_risk", "UNKNOWN")
    score      = state.get("risk_score", 0.0)
    total      = state.get("total_count", 0)
    date_range = state.get("date_range", "unknown")
    user_query = state.get("user_query", "Analyze transactions for fraud")

    high_flags = [f for f in risk_flags if f["severity"] == "HIGH"]
    med_flags  = [f for f in risk_flags if f["severity"] == "MEDIUM"]

    flags_text = ""
    for f in high_flags[:5]:
        t = f["transaction"]
        flags_text += (
            f"\n  [HIGH] {t['date']} {t['time']} | ₹{t['amount']:,.0f} | "
            f"{t['account']} → {t['beneficiary']} | {f['reason']}"
        )
    for f in med_flags[:3]:
        t = f["transaction"]
        flags_text += (
            f"\n  [MEDIUM] {t['date']} {t['time']} | ₹{t['amount']:,.0f} | "
            f"{t['account']} → {t['beneficiary']} | {f['reason']}"
        )

    context_text = "\n".join(f"- {c[:200]}" for c in context[:5])

    prompt = f"""You are a compliance officer writing a fraud risk assessment report.

DATASET SUMMARY:
- Total transactions: {total}
- Date range: {date_range}
- Overall risk: {overall} (score: {score:.3f})
- Total flags: {len(risk_flags)} ({len(high_flags)} HIGH, {len(med_flags)} MEDIUM)

KEY FLAGS:
{flags_text or "No significant flags."}

FRAUD RULE CONTEXT:
{context_text or "No additional context."}

USER QUERY: {user_query}

Write a professional fraud risk report with:
1. Executive Summary (2-3 sentences)
2. Key Risk Findings (bullet points, severity order)
3. Pattern Analysis (what fraud patterns are present)
4. Recommended Actions (3-5 specific actions)
5. Risk Rating: {overall}

Be specific with amounts, accounts, dates. Professional compliance tone."""

    response = llm.invoke([HumanMessage(content=prompt)])
    print("[Report Agent] Done.")

    return {
        "report":     response.content,
        "next_agent": "END",
        "messages": [AIMessage(content="Risk report generated.")],
    }


# ── Agent 5: Supervisor ───────────────────────────────────────────────────────
def supervisor_agent(state: FinGuardState) -> dict:
    # Error → stop
    if state.get("error"):
        return {"next_agent": "END"}

    # Step 1: extract
    if not state.get("transactions"):
        return {"next_agent": "extractor"}

    # Step 2: classify risk
    if not state.get("risk_flags"):
        return {"next_agent": "risk_classifier"}

    # Step 3: RAG context
    if state.get("retrieved_context") is None or len(state.get("retrieved_context", [])) == 0:
        # only go to RAG if we haven't been there yet
        if "rag_done" not in str(state.get("messages", "")):
            return {"next_agent": "rag"}

    # Step 4: human review — ONLY if not yet approved/rejected
    if (
        state.get("overall_risk") == "HIGH"
        and state.get("human_approved") is None
        and not state.get("report")
    ):
        return {"next_agent": "human_review"}

    # Step 5: generate report
    if not state.get("report"):
        return {"next_agent": "report_generator"}

    # Done
    return {"next_agent": "END"}


def route_from_supervisor(state: FinGuardState) -> str:
    return state.get("next_agent", "END")