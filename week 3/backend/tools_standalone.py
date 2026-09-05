"""
backend/tools_standalone.py
Pure Python versions of the fraud detection tools.
Used directly in FastAPI without LangGraph dependency.
"""
import pandas as pd


def run_structuring_check(amount: float, threshold: float = 50000) -> dict:
    margin = threshold - amount
    if 0 < margin <= 2000:
        return {"is_structuring": True, "severity": "HIGH",
                "reason": f"Amount ₹{amount:,.0f} is ₹{margin:.0f} below ₹{threshold:,.0f} threshold — classic structuring"}
    elif 0 < margin <= 5000:
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
    HIGH_RISK  = ["unknown co", "unknown", "fastcash", "quickcash", "rapidpay", "cashxpress"]
    MEDIUM_RISK = ["new payee", "first transfer", "unverified"]
    b = beneficiary.lower()
    for hr in HIGH_RISK:
        if hr in b:
            return {"risk_level": "HIGH",
                    "reason": f"'{beneficiary}' matches high-risk beneficiary pattern"}
    for mr in MEDIUM_RISK:
        if mr in b:
            return {"risk_level": "MEDIUM",
                    "reason": f"'{beneficiary}' is a new/unknown payee"}
    return {"risk_level": "LOW", "reason": f"'{beneficiary}' appears low-risk"}


def run_velocity_check(account_id: str, csv_path: str) -> dict:
    try:
        df    = pd.read_csv(csv_path)
        count = len(df[df["account"] == account_id])
        if count > 20:
            return {"is_high_velocity": True, "severity": "HIGH",
                    "transaction_count": count,
                    "reason": f"{account_id} has {count} transactions — very high velocity"}
        elif count > 10:
            return {"is_high_velocity": True, "severity": "MEDIUM",
                    "transaction_count": count,
                    "reason": f"{account_id} has {count} transactions — elevated velocity"}
        return {"is_high_velocity": False, "severity": "LOW",
                "transaction_count": count, "reason": f"Normal velocity ({count} txns)"}
    except Exception as e:
        return {"is_high_velocity": False, "severity": "LOW",
                "transaction_count": 0, "reason": str(e)}


def compute_risk_score(high: int, medium: int, low: int, total: int) -> dict:
    if total == 0:
        return {"score": 0.0, "label": "LOW", "reason": "No transactions"}
    score = min(((high * 1.0) + (medium * 0.5) + (low * 0.1)) / total, 1.0)
    label = "HIGH" if score >= 0.3 else "MEDIUM" if score >= 0.1 else "LOW"
    return {"score": round(score, 3), "label": label,
            "reason": f"{high} HIGH + {medium} MEDIUM + {low} LOW flags / {total} transactions"}
