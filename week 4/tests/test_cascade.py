"""Routing: confident Jev verdicts are accepted, uncertain ones go to the LLM
up to the budget, the rest to a human queue. No network."""
import pytest

from backend import classifier, jev
from backend.pipeline import flagged_transactions, normalize_transactions, run_rules


@pytest.fixture
def candidates(make_txn):
    rows = [make_txn(time="02:00", amount=str(49000 + i)) for i in range(6)]
    return flagged_transactions(run_rules(normalize_transactions(rows))["flags"])


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def classify(text):
        calls.append(text)
        return {"risk_level": "HIGH", "reasoning": "HIGH RISK — llm", "model_used": "fake (groq)", "is_finetuned": False}
    monkeypatch.setattr(classifier, "classify_transaction", classify)
    return calls


def fake_screen(confidences, fail=()):
    async def screen(transactions, policy, **_):
        out = []
        for i, t in enumerate(transactions):
            if i in fail:
                out.append({"error": "HTTP 529"})
                continue
            out.append({"risk_level": "LOW", "confidence": confidences[i], "legit_probability": 0.9,
                        "probabilities": {"HIGH": 0.1, "MEDIUM": 0.1, "LOW": 0.8},
                        "model_used": "jev-1.13.0", "input_tokens": 1000, "latency_ms": 90})
        return out
    return screen


def test_llm_only_without_key(candidates, fake_llm, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    monkeypatch.setenv("FINGUARD_CLASSIFY_TOP_N", "2")
    out = classifier.run_cascade(candidates, [])
    assert out["stats"]["mode"] == "llm_only" and len(out["classifications"]) == 2 and len(fake_llm) == 2
    assert all(c["route"] == "llm" for c in out["classifications"])


def test_confidence_gate_budget_and_human_queue(candidates, fake_llm, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
    monkeypatch.setenv("FINGUARD_CLASSIFY_TOP_N", "2")
    monkeypatch.setenv("FINGUARD_JEV_CONFIDENCE", "0.8")
    # two confident, one failed call, three uncertain
    monkeypatch.setattr(jev, "screen_transactions", fake_screen([0.95, 0.9, 0, 0.5, 0.4, 0.3], fail={2}))
    out = classifier.run_cascade(candidates, [])
    st = out["stats"]
    assert (st["mode"], st["screened"], st["auto"], st["escalated_llm"], st["human_review"]) == ("cascade", 6, 2, 2, 2)
    assert st["screen_errors"] == 1 and len(fake_llm) == 2
    assert st["jev_input_tokens"] == 5000 and st["jev_cost_usd"] == pytest.approx(5000 * 0.042 / 1e6)

    by_route = {}
    for c in out["classifications"]:
        by_route.setdefault(c["route"], []).append(c)
    # The failed screen is escalated first — it is the worst candidate.
    assert any(c["jev"] is None for c in by_route["llm"])
    assert all(c["disagrees_with_rules"] for c in by_route["auto"])  # rules HIGH, Jev LOW
    assert all("human review" in c["reasoning"] for c in by_route["human_review"])
