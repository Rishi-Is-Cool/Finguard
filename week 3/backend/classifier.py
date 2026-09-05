"""
backend/classifier.py — Day 18
Fraud classifier that uses your fine-tuned model for inference.
Falls back to Groq LLM if local model is not available.

After fine-tuning on Colab, set FINGUARD_MODEL_NAME in .env:
  FINGUARD_MODEL_NAME=your-username/finguard-fraud-classifier
"""
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


# ── Batch classification for the risk classifier agent ───────────────────────

def classify_transaction_batch(transactions: list) -> list:
    """
    Classify a list of transactions.
    Returns list of classification results.
    """
    results = []
    for txn in transactions:
        text = (
            f"₹{txn.get('amount', 0):,.0f} {txn.get('type', '')} "
            f"from {txn.get('account', '')} to {txn.get('beneficiary', '')} "
            f"at {txn.get('time', '')} on {txn.get('date', '')}. "
            f"Description: {txn.get('description', '')}."
        )
        result = classify_transaction(text)
        result["transaction"] = txn
        results.append(result)
    return results
