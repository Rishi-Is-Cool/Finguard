"""
tools.py — Day 9
Pydantic-typed tools for FinGuard agents.
Each tool is a function the LLM can call with structured inputs.
"""
from pydantic import BaseModel, Field
from langchain_core.tools import tool
import pandas as pd
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Tool input schemas (Pydantic) — these make LLM tool calls reliable
# ─────────────────────────────────────────────────────────────────────────────

class StructuringCheckInput(BaseModel):
    amount: float = Field(description="Transaction amount to check for structuring")
    threshold: float = Field(default=50000, description="Reporting threshold (default 50000)")


class VelocityCheckInput(BaseModel):
    account_id: str  = Field(description="Account ID to check")
    hours:      int  = Field(default=24, description="Time window in hours")
    csv_path:   str  = Field(description="Path to transactions CSV")


class BeneficiaryRiskInput(BaseModel):
    beneficiary: str = Field(description="Beneficiary name to assess risk")


class LateNightCheckInput(BaseModel):
    time_str: str = Field(description="Transaction time in HH:MM format")


class RiskScoreInput(BaseModel):
    flag_count_high:   int   = Field(description="Number of HIGH severity flags")
    flag_count_medium: int   = Field(description="Number of MEDIUM severity flags")
    flag_count_low:    int   = Field(description="Number of LOW severity flags")
    total_transactions: int  = Field(description="Total transactions in dataset")


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────

@tool("check_structuring", args_schema=StructuringCheckInput)
def check_structuring(amount: float, threshold: float = 50000) -> dict:
    """
    Check if a transaction amount shows structuring pattern —
    deliberately kept just below a reporting threshold to avoid detection.
    Returns severity and reason.
    """
    margin = threshold - amount
    if 0 < margin <= 2000:
        return {
            "is_structuring": True,
            "severity": "HIGH",
            "reason": f"Amount ₹{amount} is ₹{margin:.0f} below ₹{threshold} reporting threshold — classic structuring pattern",
        }
    elif 0 < margin <= 5000:
        return {
            "is_structuring": True,
            "severity": "MEDIUM",
            "reason": f"Amount ₹{amount} is moderately below ₹{threshold} threshold — possible structuring",
        }
    return {
        "is_structuring": False,
        "severity": "LOW",
        "reason": f"Amount ₹{amount} does not indicate structuring",
    }


@tool("check_late_night", args_schema=LateNightCheckInput)
def check_late_night(time_str: str) -> dict:
    """
    Check if a transaction occurred during suspicious late night hours (11pm–4am).
    Returns severity and reason.
    """
    try:
        hour = int(time_str.split(":")[0])
    except Exception:
        return {"is_late_night": False, "severity": "LOW", "reason": "Could not parse time"}

    if hour >= 23 or hour <= 3:
        return {
            "is_late_night": True,
            "severity": "HIGH",
            "reason": f"Transaction at {time_str} — deep night hours (11pm–4am) are high-risk",
        }
    elif hour >= 22 or hour == 4:
        return {
            "is_late_night": True,
            "severity": "MEDIUM",
            "reason": f"Transaction at {time_str} — late evening, warrants attention",
        }
    return {
        "is_late_night": False,
        "severity": "LOW",
        "reason": f"Transaction at {time_str} — normal hours",
    }


@tool("check_beneficiary_risk", args_schema=BeneficiaryRiskInput)
def check_beneficiary_risk(beneficiary: str) -> dict:
    """
    Assess risk level of a beneficiary based on known patterns.
    Returns risk level and reason.
    """
    HIGH_RISK  = ["unknown co", "unknown", "fastcash", "quickcash", "rapidpay"]
    MEDIUM_RISK = ["new payee", "first transfer"]

    b_lower = beneficiary.lower()

    for hr in HIGH_RISK:
        if hr in b_lower:
            return {
                "risk_level": "HIGH",
                "reason": f"'{beneficiary}' matches high-risk beneficiary pattern — often associated with money mules",
            }
    for mr in MEDIUM_RISK:
        if mr in b_lower:
            return {
                "risk_level": "MEDIUM",
                "reason": f"'{beneficiary}' is a new/unknown payee — requires verification",
            }
    return {
        "risk_level": "LOW",
        "reason": f"'{beneficiary}' appears to be a known, low-risk beneficiary",
    }


@tool("check_velocity", args_schema=VelocityCheckInput)
def check_velocity(account_id: str, hours: int = 24, csv_path: str = "transactions.csv") -> dict:
    """
    Check transaction velocity for an account — too many transactions
    in a short window is a fraud indicator.
    """
    try:
        df = pd.read_csv(csv_path)
        df["date"] = pd.to_datetime(df["date"])
        account_txns = df[df["account"] == account_id]
        count = len(account_txns)

        if count > 20:
            return {
                "is_high_velocity": True,
                "severity": "HIGH",
                "transaction_count": count,
                "reason": f"Account {account_id} has {count} transactions — very high velocity",
            }
        elif count > 10:
            return {
                "is_high_velocity": True,
                "severity": "MEDIUM",
                "transaction_count": count,
                "reason": f"Account {account_id} has {count} transactions — elevated velocity",
            }
        return {
            "is_high_velocity": False,
            "severity": "LOW",
            "transaction_count": count,
            "reason": f"Account {account_id} has {count} transactions — normal velocity",
        }
    except Exception as e:
        return {"is_high_velocity": False, "severity": "LOW",
                "transaction_count": 0, "reason": f"Error: {e}"}


@tool("calculate_risk_score", args_schema=RiskScoreInput)
def calculate_risk_score(
    flag_count_high: int,
    flag_count_medium: int,
    flag_count_low: int,
    total_transactions: int,
) -> dict:
    """
    Calculate an overall risk score (0.0–1.0) and label from flag counts.
    """
    if total_transactions == 0:
        return {"score": 0.0, "label": "LOW", "reason": "No transactions to analyze"}

    score = (
        (flag_count_high * 1.0) +
        (flag_count_medium * 0.5) +
        (flag_count_low * 0.1)
    ) / total_transactions

    score = min(score, 1.0)

    if score >= 0.3:
        label = "HIGH"
    elif score >= 0.1:
        label = "MEDIUM"
    else:
        label = "LOW"

    return {
        "score": round(score, 3),
        "label": label,
        "reason": (
            f"{flag_count_high} HIGH + {flag_count_medium} MEDIUM + "
            f"{flag_count_low} LOW flags across {total_transactions} transactions"
        ),
    }


# Convenience list for agent binding
ALL_TOOLS = [
    check_structuring,
    check_late_night,
    check_beneficiary_risk,
    check_velocity,
    calculate_risk_score,
]
