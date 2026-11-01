"""
backend/jev.py
Client for Jev, TypeSafe's "System One" model (docs.typesafe.ai/api).

Jev does not write text. Given a state and typed questions it returns a
choice, a probability per option and a calibrated confidence, in ~70-500 ms,
billed on input tokens only. That makes it a cheap first-pass screener: it
triages every flagged transaction, and only the uncertain ones go on to an LLM.
Plain httpx rather than the SDK, so the request shape is visible here.
"""
import asyncio
import os
import time

import httpx

JEV_URL   = os.getenv("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.getenv("TYPESAFE_MODEL", "jev-latest")

# docs.typesafe.ai/models — jev-1.13: $0.042 per million input tokens, output free.
PRICE_PER_MTOK_USD = 0.042

_RETRYABLE = {429, 529}

RISK_CRITERIA = {
    "HIGH": ("Strong fraud or money-laundering indicators under `fraud_policy` — e.g. an "
             "amount just under the ₹50,000 reporting threshold, a vague or high-risk "
             "beneficiary, deep-night timing — with no convincing legitimate explanation."),
    "MEDIUM": ("Some indicators are present but a plausible legitimate explanation exists, "
               "or the evidence is ambiguous. Worth a human look."),
    "LOW": "Consistent with ordinary legitimate activity. No meaningful fraud indicators.",
}


def jev_enabled() -> bool:
    return bool(os.getenv("TYPESAFE_API_KEY", "").strip())


def build_request(txn: dict, policy: list[str]) -> dict:
    """One state (the transaction + the written policy), two questions asked in
    the same pass: a risk Choice and a legitimacy Noul."""
    return {
        "model": JEV_MODEL,
        "state": {
            "transaction": {
                "date":        txn["date"],
                "time":        txn["time"],
                "account":     txn["account"],
                "beneficiary": txn["beneficiary"],
                "description": txn["description"],
                "amount_inr":  txn["amount"],
                "direction":   txn["type"],
            },
            "fraud_policy": policy,
        },
        "questions": {
            "risk": {
                "type": "choice",
                "instructions": "Under `fraud_policy`, what is the fraud risk level of `transaction`?",
                "criteria": RISK_CRITERIA,
            },
            "legitimate_explanation": {
                "type": "noul",
                "instructions": ("Does the `transaction` description give a plausible legitimate "
                                 "reason for this payment, such as salary, an EMI, rent, "
                                 "utilities or an ordinary merchant purchase?"),
            },
        },
    }


def parse_response(data: dict) -> dict:
    risk  = data["answers"]["risk"]
    legit = data["answers"].get("legitimate_explanation", {})
    return {
        "risk_level":        risk["choice"],
        "confidence":        float(risk["confidence"]),
        "probabilities":     {k: float(v) for k, v in risk["probabilities"].items()},
        "legit_probability": float(legit["noul"]) if "noul" in legit else None,
        "model_used":        data.get("model", JEV_MODEL),
        "input_tokens":      int(data.get("usage", {}).get("input_tokens", 0)),
    }


async def _screen_one(client: httpx.AsyncClient, txn: dict, policy: list[str],
                      sem: asyncio.Semaphore, attempts: int = 3) -> dict:
    body = build_request(txn, policy)
    async with sem:
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                resp = await client.post(JEV_URL, json=body)
            except httpx.HTTPError as e:
                if attempt == attempts - 1:
                    return {"error": f"connection: {e}"}
                await asyncio.sleep(0.5 * 2 ** attempt)
                continue
            if resp.status_code in _RETRYABLE and attempt < attempts - 1:
                try:
                    wait = min(float(resp.headers.get("retry-after", "")), 10.0)
                except ValueError:  # absent, or an HTTP-date
                    wait = 0.5 * 2 ** attempt
                await asyncio.sleep(wait)
                continue
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
            try:
                out = parse_response(resp.json())
            except (KeyError, TypeError, ValueError) as e:
                return {"error": f"unexpected response shape: {e}"}
            out["latency_ms"] = round((time.perf_counter() - started) * 1000)
            return out
    return {"error": "retries exhausted"}


async def screen_transactions(transactions: list[dict], policy: list[str],
                              concurrency: int = 8,
                              client: httpx.AsyncClient | None = None) -> list[dict]:
    """Screen every transaction concurrently. A failed item comes back as
    {"error": ...} rather than raising, so the caller can escalate it."""
    sem = asyncio.Semaphore(concurrency)
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            headers={"Authorization": f"Bearer {os.getenv('TYPESAFE_API_KEY', '').strip()}"},
        )
    try:
        return await asyncio.gather(*(_screen_one(client, t, policy, sem) for t in transactions))
    finally:
        if owns_client:
            await client.aclose()
