"""
backend/pipeline.py
The deterministic half of FinGuard: normalise transactions and run the rules.
Plain Python in, plain Python out, so SSE payloads, audit records and MCP tool
results can all json.dumps it without pandas types leaking through.
"""
from collections import Counter
from datetime import datetime

from backend.tools_standalone import (
    run_structuring_check,
    run_late_night_check,
    run_beneficiary_check,
    run_velocity_check,
    compute_risk_score,
)

REQUIRED_COLUMNS = {"date", "time", "account", "beneficiary", "description", "amount", "type"}
SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def normalize_transactions(records: list[dict]) -> list[dict]:
    """Validate raw rows (CSV or JSON) into typed transaction dicts with stable ids."""
    if not records:
        raise ValueError("No transactions supplied.")
    missing = REQUIRED_COLUMNS - set(records[0])
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    out = []
    for i, r in enumerate(records):
        try:
            date = datetime.strptime(str(r["date"]).strip()[:10], "%Y-%m-%d")
            time = str(r["time"]).strip()
            hour = int(time.split(":")[0])
            amount = float(r["amount"])
        except (ValueError, TypeError) as e:
            raise ValueError(f"Row {i + 1}: {e}") from e
        out.append({
            "txn_id":      f"T{i + 1:04d}",
            "date":        date.strftime("%Y-%m-%d"),
            "time":        time,
            "account":     str(r["account"]).strip(),
            "beneficiary": str(r["beneficiary"]).strip(),
            "description": str(r["description"]).strip(),
            "amount":      amount,
            "type":        str(r["type"]).strip().lower(),
            "hour":        hour,
            "weekday":     date.strftime("%A"),
        })
    return out


def run_rules(transactions: list[dict]) -> dict:
    """Apply every rule. Returns flags (with ids) plus the aggregate score."""
    flags = []

    def add(rule, severity, reason, txn=None, account=None, evidence=None):
        flags.append({
            "flag_id":     f"F{len(flags) + 1:04d}",
            "flag_type":   rule,
            "severity":    severity,
            "reason":      reason,
            "scope":       "transaction" if txn else "account",
            "transaction": txn if txn else {"account": account},
            "evidence":    evidence or {},
        })

    for txn in transactions:
        if txn["type"] == "debit":
            r = run_structuring_check(txn["amount"])
            if r["is_structuring"]:
                add("structuring", r["severity"], r["reason"], txn,
                    evidence={"amount": txn["amount"]})
        r = run_late_night_check(txn["time"])
        if r["is_late_night"]:
            add("late_night", r["severity"], r["reason"], txn, evidence={"hour": txn["hour"]})
        r = run_beneficiary_check(txn["beneficiary"])
        if r["risk_level"] != "LOW":
            add("unknown_beneficiary", r["risk_level"], r["reason"], txn,
                evidence={"beneficiary": txn["beneficiary"]})

    # Velocity is a property of the account, not of any one transaction.
    for account, count in sorted(Counter(t["account"] for t in transactions).items()):
        r = run_velocity_check(account, count)
        if r["is_high_velocity"]:
            add("velocity", r["severity"], r["reason"], account=account,
                evidence={"transaction_count": count})

    counts = {s: sum(1 for f in flags if f["severity"] == s) for s in SEVERITY_ORDER}
    score = compute_risk_score(counts["HIGH"], counts["MEDIUM"], counts["LOW"], len(transactions))
    return {"flags": flags, "counts": counts, "score": score}


def flagged_transactions(flags: list[dict]) -> list[dict]:
    """Distinct flagged transactions, each with its worst rule severity and every
    rule that fired on it — worst first. One transaction often trips several rules."""
    by_id: dict[str, dict] = {}
    for f in flags:
        if f["scope"] != "transaction":
            continue
        t = f["transaction"]
        entry = by_id.setdefault(t["txn_id"], {"transaction": t, "rule_severity": "LOW", "rules": []})
        entry["rules"].append({"rule": f["flag_type"], "severity": f["severity"], "reason": f["reason"]})
        if SEVERITY_ORDER[f["severity"]] < SEVERITY_ORDER[entry["rule_severity"]]:
            entry["rule_severity"] = f["severity"]
    return sorted(by_id.values(),
                  key=lambda e: (SEVERITY_ORDER[e["rule_severity"]], -len(e["rules"]), -e["transaction"]["amount"]))
