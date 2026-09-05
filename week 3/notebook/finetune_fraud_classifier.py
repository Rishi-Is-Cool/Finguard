"""
notebooks/finetune_fraud_classifier.py — Days 15–17
Copy this entire file into a Google Colab notebook (T4 GPU).

Steps:
  1. Go to colab.research.google.com
  2. Runtime → Change runtime type → T4 GPU
  3. Paste this code cell by cell (each section is one cell)
  4. Run top to bottom

At the end you will have a fine-tuned Llama-3 fraud classifier
pushed to your HuggingFace Hub.

Reading reference:
  - Ch. 12 pp. 355–373 (PEFT + QLoRA + SFT + Training + Merge)
"""

# ═══════════════════════════════════════════════════════════════════════════
# CELL 1 — Install (run once, then restart runtime)
# ═══════════════════════════════════════════════════════════════════════════
CELL_1 = """
!pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
!pip install --no-deps "xformers<0.0.27" "trl<0.9.0" peft accelerate bitsandbytes
!pip install datasets huggingface_hub
"""

# ═══════════════════════════════════════════════════════════════════════════
# CELL 2 — Load base model with QLoRA (4-bit quantization)
# ═══════════════════════════════════════════════════════════════════════════
CELL_2 = """
from unsloth import FastLanguageModel
import torch

# ── Model config ──────────────────────────────────────────────────────────
MAX_SEQ_LENGTH = 512   # fraud examples are short, 512 is enough
DTYPE          = None  # auto-detect (float16 on T4)
LOAD_IN_4BIT   = True  # QLoRA — quantize base model to 4-bit

# Load Llama-3.1-8B in 4-bit (fits on free T4 GPU)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name      = "unsloth/Meta-Llama-3.1-8B-Instruct",
    max_seq_length  = MAX_SEQ_LENGTH,
    dtype           = DTYPE,
    load_in_4bit    = LOAD_IN_4BIT,
)

print("Base model loaded.")
print(f"Model params: {model.num_parameters()/1e9:.1f}B")
"""

# ═══════════════════════════════════════════════════════════════════════════
# CELL 3 — Add LoRA adapters (Day 15 concept: LoRA rank and alpha)
# ═══════════════════════════════════════════════════════════════════════════
CELL_3 = """
# ── LoRA config ───────────────────────────────────────────────────────────
# rank (r): size of the low-rank matrices. Higher = more capacity but slower.
#   Start with 16. If the model underfits, try 32.
# alpha: scaling factor. Usually 2x rank.
# target_modules: which layers to add LoRA to.
#   q_proj, k_proj, v_proj, o_proj = attention layers
#   gate_proj, up_proj, down_proj = feed-forward layers

model = FastLanguageModel.get_peft_model(
    model,
    r              = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"],
    lora_alpha     = 32,
    lora_dropout   = 0.05,
    bias           = "none",
    use_gradient_checkpointing = "unsloth",
    random_state   = 42,
)

# Count trainable parameters (should be ~1-2% of total)
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total     = sum(p.numel() for p in model.parameters())
print(f"Trainable params: {trainable/1e6:.1f}M / {total/1e9:.1f}B ({100*trainable/total:.2f}%)")
"""

# ═══════════════════════════════════════════════════════════════════════════
# CELL 4 — Load and format the dataset (Day 16 concept: instruction templating)
# ═══════════════════════════════════════════════════════════════════════════
CELL_4 = """
import json
from datasets import Dataset

# ── Load your dataset ─────────────────────────────────────────────────────
# Option A: Upload fraud_dataset_train.json to Colab Files, then:
with open("fraud_dataset_train.json") as f:
    raw_data = json.load(f)

# Option B: If you pushed to HuggingFace Hub:
# from datasets import load_dataset
# dataset = load_dataset("your-username/finguard-fraud-dataset")

# ── Alpaca prompt template ────────────────────────────────────────────────
ALPACA_TEMPLATE = \"\"\"Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}\"\"\"

EOS_TOKEN = tokenizer.eos_token  # must add EOS at end

def format_examples(examples):
    texts = []
    for instruction, inp, output in zip(
        examples["instruction"], examples["input"], examples["output"]
    ):
        text = ALPACA_TEMPLATE.format(
            instruction=instruction,
            input=inp,
            output=output,
        ) + EOS_TOKEN
        texts.append(text)
    return {"text": texts}

# Convert to HuggingFace Dataset
hf_dataset = Dataset.from_list(raw_data)
hf_dataset = hf_dataset.map(format_examples, batched=True)

print(f"Dataset: {len(hf_dataset)} examples")
print("\\nSample formatted example:")
print(hf_dataset[0]["text"][:400])
"""

# ═══════════════════════════════════════════════════════════════════════════
# CELL 5 — Fine-tune with SFTTrainer (Day 17)
# ═══════════════════════════════════════════════════════════════════════════
CELL_5 = """
from trl import SFTTrainer
from transformers import TrainingArguments
from unsloth import is_bfloat16_supported

trainer = SFTTrainer(
    model         = model,
    tokenizer     = tokenizer,
    train_dataset = hf_dataset,
    dataset_text_field = "text",
    max_seq_length     = MAX_SEQ_LENGTH,
    dataset_num_proc   = 2,
    args = TrainingArguments(
        per_device_train_batch_size = 4,
        gradient_accumulation_steps = 4,   # effective batch = 16
        warmup_steps      = 10,
        num_train_epochs  = 3,
        learning_rate     = 2e-4,
        fp16              = not is_bfloat16_supported(),
        bf16              = is_bfloat16_supported(),
        logging_steps     = 10,
        optim             = "adamw_8bit",
        weight_decay      = 0.01,
        lr_scheduler_type = "cosine",
        seed              = 42,
        output_dir        = "./finguard-outputs",
    ),
)

print("Starting fine-tuning...")
print(f"Estimated time on T4: ~15-25 minutes for 510 examples x 3 epochs")

trainer_stats = trainer.train()

print(f"\\nTraining complete!")
print(f"  Train loss: {trainer_stats.training_loss:.4f}")
print(f"  Time: {trainer_stats.metrics['train_runtime']:.0f}s")
"""

# ═══════════════════════════════════════════════════════════════════════════
# CELL 6 — Evaluate on test set (Day 18)
# ═══════════════════════════════════════════════════════════════════════════
CELL_6 = """
import json

# Load test set
with open("fraud_dataset_test.json") as f:
    test_data = json.load(f)

# Switch to inference mode (faster)
FastLanguageModel.for_inference(model)

def classify_transaction(transaction_text: str) -> str:
    prompt = ALPACA_TEMPLATE.format(
        instruction="You are a financial fraud analyst. Classify this transaction for fraud risk and explain your reasoning.",
        input=transaction_text,
        output="",  # empty — model will fill this
    )
    inputs = tokenizer([prompt], return_tensors="pt").to("cuda")
    outputs = model.generate(
        **inputs,
        max_new_tokens   = 150,
        temperature      = 0.1,
        do_sample        = True,
        use_cache        = True,
    )
    generated = tokenizer.batch_decode(outputs)[0]
    # Extract response after ### Response:
    response = generated.split("### Response:")[-1].strip()
    return response.split(EOS_TOKEN)[0].strip()


def extract_risk_level(output: str) -> str:
    out_upper = output.upper()
    if out_upper.startswith("HIGH"):   return "HIGH"
    if out_upper.startswith("MEDIUM"): return "MEDIUM"
    if out_upper.startswith("LOW"):    return "LOW"
    return "UNKNOWN"

# Run on first 50 test examples
print("Evaluating on 50 test examples...")
results = []
for i, example in enumerate(test_data[:50]):
    prediction = classify_transaction(example["input"])
    pred_level = extract_risk_level(prediction)
    true_level = example["risk_level"]
    results.append({
        "true":       true_level,
        "predicted":  pred_level,
        "correct":    pred_level == true_level,
        "input":      example["input"][:80],
        "prediction": prediction[:100],
    })
    if i % 10 == 0:
        print(f"  {i}/50 done...")

# Metrics
correct = sum(1 for r in results if r["correct"])
print(f"\\nAccuracy: {correct}/50 = {100*correct/50:.1f}%")

# Per-class accuracy
for level in ["HIGH", "MEDIUM", "LOW"]:
    class_results = [r for r in results if r["true"] == level]
    if class_results:
        acc = sum(1 for r in class_results if r["correct"]) / len(class_results)
        print(f"  {level}: {acc:.1%} ({len(class_results)} examples)")

# Show worst predictions
print("\\nMissed predictions:")
for r in results:
    if not r["correct"]:
        print(f"  True: {r['true']:6} | Pred: {r['predicted']:6} | {r['input'][:60]}...")
"""

# ═══════════════════════════════════════════════════════════════════════════
# CELL 7 — Save and push to HuggingFace Hub
# ═══════════════════════════════════════════════════════════════════════════
CELL_7 = """
from huggingface_hub import login

# Login to HuggingFace (get token from huggingface.co/settings/tokens)
login(token="your_hf_token_here")  # replace with your token

HF_USERNAME  = "your-username"     # replace with your HuggingFace username
MODEL_NAME   = f"{HF_USERNAME}/finguard-fraud-classifier"

# Save LoRA adapters only (small — a few hundred MB)
model.save_pretrained("finguard-fraud-lora")
tokenizer.save_pretrained("finguard-fraud-lora")

# Push to Hub
model.push_to_hub(MODEL_NAME, token="your_hf_token_here")
tokenizer.push_to_hub(MODEL_NAME, token="your_hf_token_here")

print(f"Model pushed to: https://huggingface.co/{MODEL_NAME}")
print("Use this model name in your FastAPI backend.")

# Also merge weights for standalone inference (larger but self-contained)
merged_model = model.merge_and_unload()
merged_model.save_pretrained("finguard-fraud-merged")
print("Merged model saved to ./finguard-fraud-merged")
"""

# Print instructions when run directly
if __name__ == "__main__":
    print("="*60)
    print("FinGuard Fine-tuning — Colab Instructions")
    print("="*60)
    print("""
1. Go to colab.research.google.com
2. Runtime → Change runtime type → T4 GPU
3. Create cells and paste each CELL_N content above
4. Run in order: Cell 1 → restart runtime → Cell 2 → ... → Cell 7

Required files to upload to Colab:
  - data/fraud_dataset_train.json  (from running build_dataset.py)
  - data/fraud_dataset_test.json

Required accounts:
  - HuggingFace account (huggingface.co) — for pushing the model
  - Get HF token from: huggingface.co/settings/tokens

After Cell 7, paste your model name into backend/classifier.py
""")
    print("CELL_1 (install):")
    print(CELL_1)
    print("\nCELL_2 (load model):")
    print(CELL_2)
    print("\n... (see file for all cells)")
