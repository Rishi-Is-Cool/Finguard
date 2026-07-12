"""
evaluate.py
Run RAGAS evaluation on the FinGuard pipeline.
Usage: python evaluate.py
"""
import os
import pandas as pd
from dotenv import load_dotenv
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from pipeline import build_pipeline, load_dataframe, ask

load_dotenv()

# ── Eval dataset (10 questions) ──────────────────────────────────────────────
EVAL_DATA = [
    {
        "question": "Which transactions involve amounts just below 50000?",
        "ground_truth": "Transactions with amounts like 49500, 49800, 49900 show structuring patterns near the reporting threshold.",
    },
    {
        "question": "Are there any late night transactions after 11pm?",
        "ground_truth": "Yes, several transactions occur at 23:xx hours across multiple accounts.",
    },
    {
        "question": "Are there transactions to Unknown Co?",
        "ground_truth": "Yes, multiple transactions show Unknown Co as the beneficiary.",
    },
    {
        "question": "Which account has suspicious activity involving FastCash?",
        "ground_truth": "Transactions to FastCash beneficiary appear across accounts in the dataset.",
    },
    {
        "question": "Are there any UPI payments made late at night?",
        "ground_truth": "Yes, UPI payments appear in late night hours in the transaction records.",
    },
    {
        "question": "Show transactions where the same beneficiary received money multiple times.",
        "ground_truth": "Multiple transactions to FastCash, Unknown Co, and Priya Ltd appear in the records.",
    },
    {
        "question": "Are there ATM withdrawals in the dataset?",
        "ground_truth": "Yes, ATM withdrawal transactions appear in the records.",
    },
    {
        "question": "What types of transactions does ACC001 have?",
        "ground_truth": "ACC001 has both debit and credit transactions including NEFT, UPI, and ATM withdrawals.",
    },
    {
        "question": "Any suspicious NEFT transfers to unknown beneficiaries?",
        "ground_truth": "Yes, NEFT transfers to Unknown Co appear in the dataset and may warrant investigation.",
    },
    {
        "question": "Which transactions look like layering fraud?",
        "ground_truth": "Transactions involving rapid movement of funds through multiple accounts or to unknown beneficiaries may indicate layering.",
    },
]


def run_evaluation():
    print("Loading data and pipeline...")
    df = load_dataframe("transactions.csv")
    rag_chain, pandas_agent, router_chain, _ = build_pipeline(df)

    print(f"\nRunning pipeline on {len(EVAL_DATA)} questions...")
    results = []
    for i, item in enumerate(EVAL_DATA):
        # Only evaluate SEMANTIC queries with RAGAS
        # (RAGAS measures RAG quality, not pandas agent quality)
        result = rag_chain.invoke({"query": item["question"]})
        results.append({
            "question":     item["question"],
            "answer":       result["result"],
            "contexts":     [doc.page_content for doc in result["source_documents"]],
            "ground_truth": item["ground_truth"],
        })
        print(f"  [{i+1}/{len(EVAL_DATA)}] Done: {item['question'][:55]}...")

    print("\nRunning RAGAS scoring...")
    dataset = Dataset.from_list(results)
    scores  = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
    )

    print("\n" + "="*50)
    print("RAGAS EVALUATION RESULTS")
    print("="*50)
    print(f"  Faithfulness      : {scores['faithfulness']:.3f}")
    print(f"  Answer Relevancy  : {scores['answer_relevancy']:.3f}")
    print(f"  Context Precision : {scores['context_precision']:.3f}")
    print("="*50)

    # Per-question breakdown
    scores_df = scores.to_pandas()
    print("\nPer-question scores:")
    cols = ["question", "faithfulness", "answer_relevancy", "context_precision"]
    print(scores_df[cols].to_string(index=False))

    # Worst 3
    worst = scores_df.nsmallest(3, "faithfulness")
    print("\n3 worst queries by faithfulness:")
    for _, row in worst.iterrows():
        print(f"\n  Q: {row['question']}")
        print(f"  Faithfulness: {row['faithfulness']:.3f}")
        if row["faithfulness"] < 0.5:
            print("  Diagnosis: LLM hallucinating — not grounded in context")
        elif row["context_precision"] < 0.5:
            print("  Diagnosis: Wrong chunks retrieved — retrieval problem")
        else:
            print("  Diagnosis: Answer relevance issue — prompt may need tuning")

    return scores


if __name__ == "__main__":
    run_evaluation()
