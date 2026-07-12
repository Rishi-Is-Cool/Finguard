"""
langsmith_test.py — Day 14
Run this AFTER setting LANGCHAIN_API_KEY in .env.
It runs a full analysis and sends traces to LangSmith.

Usage: python langsmith_test.py
Then go to smith.langchain.com to see the traces.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Verify LangSmith is configured
api_key = os.getenv("LANGCHAIN_API_KEY")
if not api_key or api_key == "your_langsmith_api_key_here":
    print("⚠️  LANGCHAIN_API_KEY not set in .env")
    print("   Get a free key at smith.langchain.com")
    print("   Tracing will be disabled for this run.\n")
else:
    print(f"✅ LangSmith configured — project: {os.getenv('LANGCHAIN_PROJECT', 'default')}")
    print("   Go to smith.langchain.com to see traces after this run.\n")

from graph import run_analysis

def run_langsmith_test():
    """
    Run a full analysis. Every LangChain/LangGraph call will be
    traced automatically in LangSmith if the API key is set.
    """
    print("Running FinGuard analysis with LangSmith tracing...\n")

    state = run_analysis(
        csv_path="transactions.csv",
        user_query="Perform a comprehensive fraud risk analysis. Flag all suspicious transactions and identify patterns.",
        thread_id="langsmith-test-1",
        auto_approve=True,  # auto approve for testing
    )

    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)
    print(f"Overall Risk:  {state.get('overall_risk')}")
    print(f"Risk Score:    {state.get('risk_score')}")
    print(f"Total Flags:   {len(state.get('risk_flags', []))}")
    print(f"Transactions:  {state.get('total_count')}")
    print(f"Date Range:    {state.get('date_range')}")

    flags = state.get("risk_flags", [])
    high  = [f for f in flags if f["severity"] == "HIGH"]
    med   = [f for f in flags if f["severity"] == "MEDIUM"]
    print(f"\nFlags:         {len(high)} HIGH, {len(med)} MEDIUM, {len(flags)-len(high)-len(med)} LOW")

    print("\n--- TOP HIGH RISK FLAGS ---")
    for f in high[:5]:
        t = f["transaction"]
        print(f"  [{f['flag_type']}] {t['date']} {t['time']} | ₹{t['amount']:,.0f} | {t['account']} → {t['beneficiary']}")
        print(f"    Reason: {f['reason']}")

    report = state.get("report", "")
    if report:
        print("\n--- REPORT PREVIEW (first 500 chars) ---")
        print(report[:500] + "...")

    if api_key and api_key != "your_langsmith_api_key_here":
        print("\n✅ Check smith.langchain.com for full traces")
        print(f"   Project: {os.getenv('LANGCHAIN_PROJECT', 'default')}")
    else:
        print("\n💡 Set LANGCHAIN_API_KEY to see traces in LangSmith")


if __name__ == "__main__":
    run_langsmith_test()
