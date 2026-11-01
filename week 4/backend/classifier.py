"""
backend/classifier.py — Day 18, extended Week 4
Model verdicts on flagged transactions.

  Week 3: fine-tuned model (or Groq fallback) on the top-N HIGH flags.
  Week 4: confidence-gated cascade. Jev screens every flagged transaction;
          confident verdicts are accepted, uncertain ones escalate to the LLM,
          and anything past the LLM budget is queued for a human.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Groq serves a moving set of models; llama-3.1-8b-instant was retired.
# Override with GROQ_MODEL in .env if this one is retired too.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

MODEL_NAME   = os.getenv("FINGUARD_MODEL_NAME", "")

# A merged Llama-3.1-8B is ~16 GB of fp16 weights. transformers downloads the
# whole repo before it discovers it cannot fit, so blindly attempting the local
# path on an undersized box costs a 16 GB download and then an OOM. Gate it on
# a capacity check; FINGUARD_FORCE_LOCAL=1 overrides if you know better.
FORCE_LOCAL  = os.getenv("FINGUARD_FORCE_LOCAL", "").strip().lower() in ("1", "true", "yes")

# Rough floor for an 8B model in fp16, plus room for activations and KV cache.
_MIN_VRAM_GB = 18.0


def _local_model_is_viable():
    """Can this machine actually run MODEL_NAME? Returns (ok, reason)."""
    if not MODEL_NAME:
        return False, "FINGUARD_MODEL_NAME is not set"
    if FORCE_LOCAL:
        return True, "FINGUARD_FORCE_LOCAL=1 (capacity check skipped)"
    try:
        import torch
    except ImportError:
        return False, "torch is not installed — see backend/requirements.txt"
    if not torch.cuda.is_available():
        return False, ("no CUDA GPU — an 8B model needs ~16 GB of weights "
                       "resident and will not fit in CPU RAM here")
    vram = torch.cuda.get_device_properties(0).total_memory / 1e9
    if vram < _MIN_VRAM_GB:
        return False, f"GPU has {vram:.0f} GB VRAM, an 8B fp16 model needs ~{_MIN_VRAM_GB:.0f} GB"
    return True, f"CUDA GPU with {vram:.0f} GB VRAM"


USE_LOCAL, LOCAL_REASON = _local_model_is_viable()

if MODEL_NAME and not USE_LOCAL:
    print(f"[Classifier] Not loading '{MODEL_NAME}': {LOCAL_REASON}")
    print(f"[Classifier] Using Groq '{GROQ_MODEL}' for classification instead.")
elif USE_LOCAL:
    print(f"[Classifier] Local model enabled: {MODEL_NAME} ({LOCAL_REASON})")

# ── Local fine-tuned model ────────────────────────────────────────────────────
_pipeline = None

def _load_local_pipeline():
    """Load the fine-tuned model pipeline (lazy, loads once)."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    try:
        from transformers import pipeline
        import torch

        print(f"[Classifier] Loading fine-tuned model: {MODEL_NAME}")
        _pipeline = pipeline(
            "text-generation",
            model=MODEL_NAME,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        print("[Classifier] Fine-tuned model loaded.")
        return _pipeline
    except Exception as e:
        err_msg = str(e)
        print(f"[Classifier] Could not load local model: {err_msg[:200]}")
        if "model_type" in err_msg or "config.json" in err_msg:
            print("[Classifier] NOTE: that repo looks like LoRA adapters, not a merged "
                  "model. Point FINGUARD_MODEL_NAME at the merged repo.")
        print("[Classifier] Falling back to Groq LLM.")
        return None


# ── Alpaca prompt template (same as fine-tuning) ─────────────────────────────
ALPACA_TEMPLATE = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
{instruction}

### Input:
{input}

### Response:
"""

INSTRUCTION = "You are a financial fraud analyst. Classify this transaction for fraud risk and explain your reasoning."


def classify_with_local_model(transaction_text: str) -> dict:
    """Run inference with the fine-tuned local model."""
    pipe = _load_local_pipeline()
    if pipe is None:
        return None

    prompt = ALPACA_TEMPLATE.format(
        instruction=INSTRUCTION,
        input=transaction_text,
    )

    try:
        result = pipe(
            prompt,
            max_new_tokens=150,
            temperature=0.1,
            do_sample=True,
            return_full_text=False,
        )
        response = result[0]["generated_text"].strip()
        risk_level = _extract_risk_level(response)
        return {
            "risk_level":  risk_level,
            "reasoning":   response,
            "model_used":  MODEL_NAME,
            "is_finetuned": True,
        }
    except Exception as e:
        print(f"[Classifier] Local model inference failed: {e}")
        return None


def classify_with_groq(transaction_text: str) -> dict:
    """Fallback: classify using Groq LLM."""
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage

    llm = ChatGroq(
        model=GROQ_MODEL,
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0,
    )

    prompt = f"""{INSTRUCTION}

Transaction: {transaction_text}

Respond with risk level (HIGH/MEDIUM/LOW) followed by your reasoning.
Start your response with exactly: HIGH RISK, MEDIUM RISK, or LOW RISK"""

    response = llm.invoke([HumanMessage(content=prompt)])
    text = response.content.strip()
    risk_level = _extract_risk_level(text)

    return {
        "risk_level":   risk_level,
        "reasoning":    text,
        "model_used":   f"{GROQ_MODEL} (groq)",
        "is_finetuned": False,
    }


def classify_transaction(transaction_text: str) -> dict:
    """
    Main classification function.
    Tries fine-tuned model first, falls back to Groq.
    Returns: {"risk_level": str, "reasoning": str, "model_used": str, "is_finetuned": bool}
    """
    if USE_LOCAL:
        result = classify_with_local_model(transaction_text)
        if result:
            return result

    return classify_with_groq(transaction_text)


def _extract_risk_level(text: str) -> str:
    """Extract HIGH/MEDIUM/LOW from model output."""
    upper = text.upper().strip()
    if upper.startswith("HIGH"):   return "HIGH"
    if upper.startswith("MEDIUM"): return "MEDIUM"
    if upper.startswith("LOW"):    return "LOW"
    # Fallback: search in text
    if "HIGH RISK" in upper:   return "HIGH"
    if "MEDIUM RISK" in upper: return "MEDIUM"
    if "LOW RISK" in upper:    return "LOW"
    return "MEDIUM"  # conservative default


# ── Cascade ───────────────────────────────────────────────────────────────────

def transaction_text(txn: dict) -> str:
    return (
        f"₹{txn.get('amount', 0):,.0f} {txn.get('type', '')} "
        f"from {txn.get('account', '')} to {txn.get('beneficiary', '')} "
        f"at {txn.get('time', '')} on {txn.get('date', '')}. "
        f"Description: {txn.get('description', '')}."
    )


def classify_transaction_batch(transactions: list) -> list:
    results = []
    for txn in transactions:
        result = classify_transaction(transaction_text(txn))
        result["transaction"] = txn
        results.append(result)
    return results


def _jev_summary(j: dict, rules: list[dict]) -> str:
    probs = ", ".join(f"{k} {v:.2f}" for k, v in sorted(j["probabilities"].items(), key=lambda kv: -kv[1]))
    fired = ", ".join(f"{r['rule']} ({r['severity']})" for r in rules)
    legit = (f" Legitimate-purpose probability {j['legit_probability']:.2f}."
             if j.get("legit_probability") is not None else "")
    return (f"Jev verdict {j['risk_level']} at confidence {j['confidence']:.2f} "
            f"(probabilities: {probs}).{legit} Rules fired: {fired}.")


def run_cascade(candidates: list[dict], policy: list[str]) -> dict:
    """candidates: pipeline.flagged_transactions() entries, worst first.
    Returns {"classifications": [...], "stats": {...}}. Sync — call via to_thread."""
    llm_budget = int(os.getenv("FINGUARD_CLASSIFY_TOP_N", "5"))
    results, stats = [], {}

    def llm_verdict(cand, jev=None, route="llm"):
        r = classify_transaction(transaction_text(cand["transaction"]))
        return {**cand, **r, "route": route, "jev": jev}

    from backend.jev import jev_enabled, screen_transactions, PRICE_PER_MTOK_USD

    if not jev_enabled():
        # Week 3 behaviour: the LLM alone, on the worst few HIGH transactions.
        pool = [c for c in candidates if c["rule_severity"] == "HIGH"][:llm_budget]
        results = [llm_verdict(c) for c in pool]
        stats = {"mode": "llm_only", "screened": 0, "auto": 0,
                 "escalated_llm": len(results), "human_review": 0}
    else:
        threshold  = float(os.getenv("FINGUARD_JEV_CONFIDENCE", "0.8"))
        screen_max = int(os.getenv("FINGUARD_SCREEN_MAX", "300"))
        pool = candidates[:screen_max]
        screened = asyncio.run(screen_transactions([c["transaction"] for c in pool], policy))

        uncertain = []
        for cand, j in zip(pool, screened):
            if "error" in j:
                uncertain.append((cand, None, f"Jev unavailable ({j['error'][:80]})"))
            elif j["confidence"] >= threshold:
                results.append({**cand, "risk_level": j["risk_level"],
                                "reasoning": _jev_summary(j, cand["rules"]),
                                "model_used": j["model_used"], "is_finetuned": False,
                                "route": "auto", "jev": j})
            else:
                uncertain.append((cand, j, f"confidence {j['confidence']:.2f} < {threshold}"))

        escalated = 0
        for cand, j, why in uncertain:
            if escalated < llm_budget:
                r = llm_verdict(cand, jev=j, route="llm")
                r["reasoning"] = f"[Escalated: {why}] {r['reasoning']}"
                results.append(r)
                escalated += 1
            else:
                results.append({**cand,
                                "risk_level": j["risk_level"] if j else cand["rule_severity"],
                                "reasoning": f"Queued for human review: {why}, and the LLM budget "
                                             f"of {llm_budget} was spent on worse cases.",
                                "model_used": j["model_used"] if j else "rules",
                                "is_finetuned": False, "route": "human_review", "jev": j})

        tokens = sum(j.get("input_tokens", 0) for j in screened if "error" not in j)
        ok = [j for j in screened if "error" not in j]
        stats = {
            "mode": "cascade",
            "screened": len(pool),
            "screen_errors": len(pool) - len(ok),
            "auto": sum(1 for r in results if r["route"] == "auto"),
            "escalated_llm": sum(1 for r in results if r["route"] == "llm"),
            "human_review": sum(1 for r in results if r["route"] == "human_review"),
            "confidence_threshold": threshold,
            "jev_input_tokens": tokens,
            "jev_cost_usd": round(tokens * PRICE_PER_MTOK_USD / 1e6, 6),
            "jev_median_latency_ms": sorted(j["latency_ms"] for j in ok)[len(ok) // 2] if ok else None,
        }

    for r in results:
        r["disagrees_with_rules"] = r["risk_level"] != r["rule_severity"]
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    results.sort(key=lambda r: (order.get(r["risk_level"], 3), -r["transaction"]["amount"]))

    llm_models = {r["model_used"] for r in results if r["route"] == "llm"}
    stats.update({
        "classified": len(results),
        "agreed_high": sum(1 for r in results if r["risk_level"] == "HIGH"),
        "disagreements": sum(1 for r in results if r["disagrees_with_rules"]),
        "llm_model": next(iter(llm_models)) if llm_models else None,
        "is_finetuned": any(r.get("is_finetuned") for r in results),
    })
    return {"classifications": results, "stats": stats}
