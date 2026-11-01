"""Jev client against the request/response shapes in docs.typesafe.ai/api."""
import asyncio
import json

import httpx

from backend import jev

TXN = {"date": "2024-03-22", "time": "02:01", "account": "ACC001", "beneficiary": "Priya Ltd",
       "description": "EMI debit", "amount": 49800.0, "type": "debit"}

# Shaped exactly like the documented choice + noul answers.
OK_BODY = {
    "model": "jev-1.13.0",
    "answers": {
        "risk": {"type": "choice", "choice": "MEDIUM",
                 "probabilities": {"HIGH": 0.2, "MEDIUM": 0.7, "LOW": 0.1}, "confidence": 0.62},
        "legitimate_explanation": {"type": "noul", "noul": 0.81},
    },
    "usage": {"input_tokens": 512, "output_tokens": 30},
}


def run(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return asyncio.run(jev.screen_transactions([TXN], ["policy line"], client=client))[0]


def test_request_matches_documented_schema():
    body = jev.build_request(TXN, ["Structuring: ..."])
    assert body["model"] == jev.JEV_MODEL
    risk = body["questions"]["risk"]
    assert risk["type"] == "choice" and set(risk["criteria"]) == {"HIGH", "MEDIUM", "LOW"}
    assert body["questions"]["legitimate_explanation"]["type"] == "noul"
    assert body["state"]["transaction"]["amount_inr"] == 49800.0
    assert body["state"]["fraud_policy"] == ["Structuring: ..."]


def test_parses_answer():
    out = run(lambda req: httpx.Response(200, json=OK_BODY))
    assert out["risk_level"] == "MEDIUM" and out["confidence"] == 0.62
    assert out["legit_probability"] == 0.81 and out["input_tokens"] == 512
    assert out["model_used"] == "jev-1.13.0" and "latency_ms" in out


def test_retries_rate_limit_then_succeeds():
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(429, headers={"retry-after": "0"}) if len(calls) == 1 else httpx.Response(200, json=OK_BODY)

    assert run(handler)["risk_level"] == "MEDIUM" and len(calls) == 2


def test_http_error_becomes_error_item_not_exception():
    out = run(lambda req: httpx.Response(422, json={"detail": "bad question"}))
    assert out["error"].startswith("HTTP 422")


def test_malformed_body_becomes_error_item():
    assert "unexpected response shape" in run(lambda req: httpx.Response(200, json={"answers": {}}))["error"]


def test_sends_bearer_token(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    seen = {}

    async def go():
        async def handler(req):
            seen["auth"] = req.headers["authorization"]
            return httpx.Response(200, json=OK_BODY)
        orig = httpx.AsyncClient

        def patched(**kw):
            return orig(transport=httpx.MockTransport(handler), **kw)
        monkeypatch.setattr(jev.httpx, "AsyncClient", patched)
        return await jev.screen_transactions([TXN], [])

    asyncio.run(go())
    assert seen["auth"] == "Bearer sk-test"
