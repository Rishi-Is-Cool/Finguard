"""
backend/tools_standalone.py
Pure Python fraud detection rules. No LLM, no pandas — deterministic and cheap,
shared by the API pipeline, the MCP server and the tests.

The thresholds live in RULESET so every audit record can state exactly which
rule configuration produced a flag.
"""

RULESET_VERSION = "2026.09-w4"

RULESET = {
    "structuring": {
        "threshold": 50000,
        "high_margin": 2000,
        "medium_margin": 5000,
    },
    "late_night": {
        "high_hours": "23:00-03:59",
        "medium_hours": "22:00-22:59, 04:00-04:59",
    },
    "unknown_beneficiary": {
        "high_patterns": ["unknown co", "unknown", "fastcash", "quickcash", "rapidpay", "cashxpress"],
        "medium_patterns": ["new payee", "first transfer", "unverified"],
    },
    "velocity": {
        "high_over": 20,
        "medium_over": 10,
        "window": "whole upload",
    },
}


def run_structuring_check(amount: float, threshold: float = RULESET["structuring"]["threshold"]) -> dict:
    cfg = RULESET["structuring"]
    margin = threshold - amount
    if 0 < margin <= cfg["high_margin"]:
        return {"is_structuring": True, "severity": "HIGH",
                "reason": f"Amount ₹{amount:,.0f} is ₹{margin:.0f} below ₹{threshold:,.0f} threshold — classic structuring"}
    elif 0 < margin <= cfg["medium_margin"]:
        return {"is_structuring": True, "severity": "MEDIUM",
                "reason": f"Amount ₹{amount:,.0f} is moderately below threshold — possible structuring"}
    return {"is_structuring": False, "severity": "LOW",
            "reason": f"Amount ₹{amount:,.0f} does not indicate structuring"}


def run_late_night_check(time_str: str) -> dict:
    try:
        hour = int(time_str.split(":")[0])
    except Exception:
        return {"is_late_night": False, "severity": "LOW", "reason": "Could not parse time"}
    if hour >= 23 or hour <= 3:
        return {"is_late_night": True, "severity": "HIGH",
                "reason": f"Transaction at {time_str} — deep night hours are high risk"}
    elif hour >= 22 or hour == 4:
        return {"is_late_night": True, "severity": "MEDIUM",
                "reason": f"Transaction at {time_str} — late evening, warrants attention"}
    return {"is_late_night": False, "severity": "LOW", "reason": f"Normal hours ({time_str})"}


def run_beneficiary_check(beneficiary: str) -> dict:
    cfg = RULESET["unknown_beneficiary"]
    b = beneficiary.lower()
    for hr in cfg["high_patterns"]:
        if hr in b:
            return {"risk_level": "HIGH",
                    "reason": f"'{beneficiary}' matches high-risk beneficiary pattern"}
    for mr in cfg["medium_patterns"]:
        if mr in b:
            return {"risk_level": "MEDIUM",
                    "reason": f"'{beneficiary}' is a new/unknown payee"}
    return {"risk_level": "LOW", "reason": f"'{beneficiary}' appears low-risk"}


def run_velocity_check(account_id: str, transaction_count: int) -> dict:
    cfg = RULESET["velocity"]
    count = transaction_count
    if count > cfg["high_over"]:
        return {"is_high_velocity": True, "severity": "HIGH", "transaction_count": count,
                "reason": f"{account_id} has {count} transactions — very high velocity"}
    elif count > cfg["medium_over"]:
        return {"is_high_velocity": True, "severity": "MEDIUM", "transaction_count": count,
                "reason": f"{account_id} has {count} transactions — elevated velocity"}
    return {"is_high_velocity": False, "severity": "LOW", "transaction_count": count,
            "reason": f"Normal velocity ({count} txns)"}


def compute_risk_score(high: int, medium: int, low: int, total: int) -> dict:
    if total == 0:
        return {"score": 0.0, "label": "LOW", "reason": "No transactions"}
    score = min(((high * 1.0) + (medium * 0.5) + (low * 0.1)) / total, 1.0)
    label = "HIGH" if score >= 0.3 else "MEDIUM" if score >= 0.1 else "LOW"
    return {"score": round(score, 3), "label": label,
            "reason": f"{high} HIGH + {medium} MEDIUM + {low} LOW flags / {total} transactions"}
