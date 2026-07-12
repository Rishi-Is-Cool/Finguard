"""
state.py — Day 8
Shared state schema for the FinGuard LangGraph multi-agent system.
Every agent reads from and writes to this TypedDict.
This is the single source of truth flowing through the graph.
"""
from typing import TypedDict, Annotated, List, Optional
from langgraph.graph.message import add_messages


class Transaction(TypedDict):
    date:        str
    time:        str
    account:     str
    beneficiary: str
    description: str
    amount:      float
    type:        str


class RiskFlag(TypedDict):
    transaction:  Transaction
    flag_type:    str   # "structuring" | "late_night" | "velocity" | "unknown_beneficiary"
    severity:     str   # "LOW" | "MEDIUM" | "HIGH"
    reason:       str


class FinGuardState(TypedDict):
    # ── Input ──────────────────────────────────────────────
    user_query:       str
    csv_path:         str

    # ── Extracted data ─────────────────────────────────────
    transactions:     List[Transaction]
    total_count:      int
    date_range:       str

    # ── Risk analysis ──────────────────────────────────────
    risk_flags:       List[RiskFlag]
    overall_risk:     str           # "LOW" | "MEDIUM" | "HIGH"
    risk_score:       float         # 0.0 – 1.0

    # ── RAG context ────────────────────────────────────────
    retrieved_context: List[str]

    # ── Report ─────────────────────────────────────────────
    report:           str

    # ── Control flow ───────────────────────────────────────
    next_agent:       str           # which agent supervisor picks next
    human_approved:   Optional[bool]
    error:            Optional[str]

    # ── Conversation (for multi-turn) ──────────────────────
    messages: Annotated[List, add_messages]
