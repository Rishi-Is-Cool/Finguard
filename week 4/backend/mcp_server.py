"""
backend/mcp_server.py
FinGuard's fraud rules as an MCP server, so any MCP host (Claude Desktop,
Claude Code, Cursor, an agent framework) can call them as tools.

Deterministic and keyless on purpose: no LLM call and no API key, so an agent
gets the same answer every time and can cite the ruleset version it used.

Run (stdio):  python -m backend.mcp_server   (from week 4/, or with PYTHONPATH=week 4)
Host config:  see "MCP server" in week 4/README.md
"""
import os
from pathlib import Path
from typing import Literal

import pandas as pd
from mcp.server import MCPServer
from pydantic import BaseModel, Field

from backend.audit import AuditLog, valid_doc_id
from backend.knowledge import FRAUD_RULES
from backend.pipeline import flagged_transactions, normalize_transactions, run_rules
from backend.tools_standalone import (
    RULESET,
    RULESET_VERSION,
    run_beneficiary_check,
    run_late_night_check,
    run_structuring_check,
)

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = Path(os.getenv("FINGUARD_AUDIT_DIR", ROOT / "audit_logs"))
MAX_ROWS = int(os.getenv("FINGUARD_MAX_ROWS", "5000"))

mcp = MCPServer("FinGuard AI")


class Transaction(BaseModel):
    date: str = Field(description="YYYY-MM-DD")
    time: str = Field(description="HH:MM, 24-hour")
    account: str
    beneficiary: str
    description: str
    amount: float = Field(description="Amount in INR")
    type: Literal["debit", "credit"]


Severity = Literal["HIGH", "MEDIUM", "LOW"]


# Typed outputs: MCP clients receive these as a JSON schema, so an agent knows
# the exact shape of a result before it calls the tool.
class RuleHit(BaseModel):
    rule: str
    severity: Severity
    reason: str


class RuleCheck(BaseModel):
    triggered: bool
    severity: Severity
    reason: str


class CheckResult(BaseModel):
    ruleset_version: str
    worst_severity: Severity
    checks: dict[str, RuleCheck]


class FlaggedTransaction(BaseModel):
    txn_id: str
    date: str
    time: str
    account: str
    beneficiary: str
    amount: float
    worst_severity: Severity
    rules: list[RuleHit]


class AccountFlag(BaseModel):
    account: str
    rule: str
    severity: Severity
    reason: str


class ScreenResult(BaseModel):
    ruleset_version: str
    transactions: int
    overall_risk: Severity
    risk_score: float
    flag_counts: dict[str, int]
    flagged_transactions: list[FlaggedTransaction]
    account_flags: list[AccountFlag]


class AuditVerification(BaseModel):
    valid: bool
    events: int
    broken_at: int | None
    head: str | None
    event_types: list[str]
    human_reviews: dict[str, dict]


def _summarise(transactions: list[dict]) -> ScreenResult:
    run = run_rules(transactions)
    return ScreenResult(
        ruleset_version=RULESET_VERSION,
        transactions=len(transactions),
        overall_risk=run["score"]["label"],
        risk_score=run["score"]["score"],
        flag_counts=run["counts"],
        flagged_transactions=[
            FlaggedTransaction(**{k: c["transaction"][k] for k in
                                  ("txn_id", "date", "time", "account", "beneficiary", "amount")},
                               worst_severity=c["rule_severity"], rules=c["rules"])
            for c in flagged_transactions(run["flags"])
        ],
        account_flags=[
            AccountFlag(account=f["transaction"]["account"], rule=f["flag_type"],
                        severity=f["severity"], reason=f["reason"])
            for f in run["flags"] if f["scope"] == "account"
        ],
    )


@mcp.tool()
def check_transaction(transaction: Transaction) -> CheckResult:
    """Run FinGuard's per-transaction fraud rules (structuring, late-night timing,
    high-risk beneficiary) on one transaction. Returns each rule's verdict and the
    worst severity."""
    t = transaction.model_dump()
    late = run_late_night_check(t["time"])
    bene = run_beneficiary_check(t["beneficiary"])
    checks = {
        "late_night": RuleCheck(triggered=late["is_late_night"], severity=late["severity"], reason=late["reason"]),
        "unknown_beneficiary": RuleCheck(triggered=bene["risk_level"] != "LOW", severity=bene["risk_level"],
                                         reason=bene["reason"]),
    }
    if t["type"] == "debit":
        st = run_structuring_check(t["amount"])
        checks["structuring"] = RuleCheck(triggered=st["is_structuring"], severity=st["severity"], reason=st["reason"])
    severities = {c.severity for c in checks.values()}
    worst = next((s for s in ("HIGH", "MEDIUM") if s in severities), "LOW")
    return CheckResult(ruleset_version=RULESET_VERSION, worst_severity=worst, checks=checks)


@mcp.tool()
def screen_transactions(transactions: list[Transaction]) -> ScreenResult:
    """Screen a batch of transactions with every FinGuard rule, including
    account-level velocity. Returns the overall risk, flag counts, and each
    flagged transaction with the rules it tripped, worst first."""
    if len(transactions) > MAX_ROWS:
        raise ValueError(f"At most {MAX_ROWS} transactions per call.")
    return _summarise(normalize_transactions([t.model_dump() for t in transactions]))


@mcp.tool()
def screen_csv(path: str) -> ScreenResult:
    """Screen a local transaction CSV (columns: date, time, account, beneficiary,
    description, amount, type). Same output as screen_transactions."""
    p = Path(path).expanduser()
    if p.suffix.lower() != ".csv" or not p.is_file():
        raise ValueError(f"Not a CSV file: {path}")
    records = pd.read_csv(p, dtype=str, keep_default_na=False).to_dict("records")
    if len(records) > MAX_ROWS:
        raise ValueError(f"{len(records)} rows; at most {MAX_ROWS}.")
    return _summarise(normalize_transactions(records))


@mcp.tool()
def verify_audit_trail(document_id: str) -> AuditVerification:
    """Verify the hash chain of a FinGuard analysis audit trail. Reports whether
    any recorded event was altered, removed or reordered after the fact."""
    if not valid_doc_id(document_id):
        raise ValueError("document_id is 8 lowercase hex characters.")
    log = AuditLog(AUDIT_DIR)
    events = log.events(document_id)
    if not events:
        raise ValueError(f"No audit trail for {document_id} in {AUDIT_DIR}.")
    return AuditVerification(**log.verify(document_id), event_types=[e["type"] for e in events],
                             human_reviews=log.reviews(document_id))


@mcp.resource("finguard://policy")
def fraud_policy() -> str:
    """The written fraud policy and the exact rule thresholds FinGuard applies."""
    lines = [f"FinGuard fraud policy — ruleset {RULESET_VERSION}", ""]
    lines += [f"- {rule}" for rule in FRAUD_RULES]
    lines += ["", "Rule thresholds:"]
    lines += [f"- {name}: {cfg}" for name, cfg in RULESET.items()]
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
