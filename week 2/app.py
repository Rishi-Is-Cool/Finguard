"""
app.py — Day 14 (fixed v3)
Fix: SqliteSaver.from_conn_string() returns a context manager in this
langgraph version. Call .__enter__() manually to get the actual saver
object, store it in session_state so it stays open across reruns.
"""
import os
import shutil
import tempfile
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="FinGuard AI", page_icon="🛡️", layout="wide")
st.title("🛡️ FinGuard AI — v2")
st.caption("Multi-Agent Fraud & Risk Intelligence System")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 Upload Data")
    uploaded_file = st.file_uploader("Upload transaction CSV", type=["csv"])
    if uploaded_file:
        st.success(f"✅ {uploaded_file.name}")

    st.divider()
    st.markdown("**Agent Pipeline**")
    for s in ["① Supervisor", "② Extractor", "③ Risk Classifier",
              "④ RAG Agent", "⑤ Human Review (HIGH)", "⑥ Report Generator"]:
        st.caption(s)

    st.divider()
    st.markdown("**Stack**")
    st.caption("Orchestration: LangGraph")
    st.caption("Memory: SQLite (cross-session)")
    st.caption("LLM: Llama-3.1-8b via Groq")
    st.caption("Retrieval: Hybrid RAG + Reranker")

    st.divider()
    thread_id = st.text_input(
        "Session Thread ID", value="user-session-1",
        help="Change to start a fresh analysis session"
    )

# ── No file ───────────────────────────────────────────────────────────────────
if not uploaded_file:
    st.info("👆 Upload a transaction CSV to start.")
    st.dataframe(pd.DataFrame([{
        "date": "2024-01-15", "time": "23:14", "account": "ACC001",
        "beneficiary": "Unknown Co", "description": "NEFT transfer",
        "amount": 49800, "type": "debit"
    }]))
    st.info("💡 No CSV? Run `python generate_data.py` first.")
    st.stop()

# ── Save uploaded file to disk ────────────────────────────────────────────────
if "csv_path" not in st.session_state:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        uploaded_file.seek(0)
        shutil.copyfileobj(uploaded_file, tmp)
        st.session_state.csv_path = tmp.name
else:
    uploaded_file.seek(0)
    with open(st.session_state.csv_path, "wb") as f:
        shutil.copyfileobj(uploaded_file, f)

# ── Load CSV for display ──────────────────────────────────────────────────────
@st.cache_data
def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"]    = pd.to_datetime(df["date"])
    df["hour"]    = pd.to_datetime(df["time"], format="%H:%M").dt.hour
    df["weekday"] = df["date"].dt.day_name()
    return df

df = load_csv(st.session_state.csv_path)

# ── KEY FIX: manually enter the context manager, store actual saver ───────────
# SqliteSaver.from_conn_string() returns a _GeneratorContextManager.
# Calling .__enter__() gives the real SqliteSaver object with .get_next_version.
# We store it in session_state so it stays open across Streamlit reruns.
if "memory" not in st.session_state:
    from langgraph.checkpoint.sqlite import SqliteSaver
    ctx = SqliteSaver.from_conn_string("finguard_memory.db")
    st.session_state.memory     = ctx.__enter__()   # actual saver
    st.session_state.memory_ctx = ctx               # keep ctx alive (prevents GC)

if "graph" not in st.session_state:
    from graph import build_graph
    with st.spinner("🔧 Building agent graph (first load ~30s)..."):
        graph, _ = build_graph(
            st.session_state.csv_path,
            checkpointer=st.session_state.memory,
            use_memory=True,
        )
    st.session_state.graph = graph
    st.success("✅ Graph ready")

graph  = st.session_state.graph
config = {"configurable": {"thread_id": thread_id}}

# ── Metrics ───────────────────────────────────────────────────────────────────
structuring = df[df["amount"].between(49_000, 50_000)]
late_night  = df[df["hour"] >= 23]
unknown     = df[df["beneficiary"].str.lower().str.contains("unknown", na=False)]
flagged     = len(set(list(structuring.index) + list(late_night.index) + list(unknown.index)))

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Transactions",   len(df))
c2.metric("Debits",         len(df[df["type"] == "debit"]))
c3.metric("Credits",        len(df[df["type"] == "credit"]))
c4.metric("Accounts",       df["account"].nunique())
c5.metric("⚠️ Pre-flagged", flagged)
st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🤖 AI Analysis", "🔍 Quick Flags", "📊 Raw Data"])

with tab2:
    st.subheader("Rule-Based Pre-Screening")
    if len(structuring):
        st.warning(f"⚠️ **Structuring** — {len(structuring)} transactions in ₹49k–50k range")
        st.dataframe(structuring[["date","time","account","beneficiary","amount","type"]], use_container_width=True)
    if len(late_night):
        st.warning(f"⚠️ **Late Night** — {len(late_night)} transactions after 11pm")
        st.dataframe(late_night[["date","time","account","beneficiary","amount","type"]], use_container_width=True)
    if len(unknown):
        st.warning(f"⚠️ **Unknown Beneficiary** — {len(unknown)} transactions")
        st.dataframe(unknown[["date","time","account","beneficiary","amount","type"]], use_container_width=True)
    if not len(structuring) and not len(late_night) and not len(unknown):
        st.success("No obvious patterns detected.")

with tab3:
    st.subheader("All Transactions")
    a_f = st.multiselect("Account", df["account"].unique())
    t_f = st.multiselect("Type",    df["type"].unique())
    filt = df.copy()
    if a_f: filt = filt[filt["account"].isin(a_f)]
    if t_f: filt = filt[filt["type"].isin(t_f)]
    st.dataframe(filt[["date","time","account","beneficiary","description","amount","type"]], use_container_width=True)

# ── Tab 1: AI Analysis ────────────────────────────────────────────────────────
with tab1:
    st.subheader("Multi-Agent Fraud Analysis")

    user_query = st.text_area(
        "Analysis query",
        value="Analyze all transactions for fraud patterns, identify high-risk activity, and generate a compliance report.",
        height=80,
    )

    col_run, col_reset = st.columns([3, 1])
    run_btn   = col_run.button("🚀 Run Full Analysis", type="primary", use_container_width=True)
    reset_btn = col_reset.button("🔄 Reset Session", use_container_width=True)

    if reset_btn:
        for key in ["analysis_state", "analysis_done", "awaiting_approval", "graph_config"]:
            st.session_state.pop(key, None)
        st.rerun()

    # ── Run ───────────────────────────────────────────────────────────────────
    if run_btn:
        for key in ["analysis_state", "analysis_done", "awaiting_approval"]:
            st.session_state.pop(key, None)

        st.markdown("### Agent Pipeline")
        labels = {
            "supervisor":       "🔵 Supervisor",
            "extractor":        "📥 Extractor",
            "risk_classifier":  "🔍 Risk Classifier",
            "rag":              "📚 RAG Agent",
            "report_generator": "📝 Report Generator",
        }
        ph = {k: st.empty() for k in labels}
        for k, lbl in labels.items():
            ph[k].info(f"{lbl} — waiting...")

        progress = st.progress(0, text="Starting...")

        with st.spinner("Running multi-agent analysis..."):
            from state import FinGuardState
            from langchain_core.messages import HumanMessage

            initial_state = FinGuardState(
                user_query=user_query,
                csv_path=st.session_state.csv_path,
                transactions=[], total_count=0, date_range="",
                risk_flags=[], overall_risk="", risk_score=0.0,
                retrieved_context=[], report="",
                next_agent="", human_approved=None, error=None,
                messages=[HumanMessage(content=user_query)],
            )

            ph["supervisor"].success("🔵 Supervisor — routing...")
            progress.progress(15, text="Supervisor routing...")
            ph["extractor"].success("📥 Extractor — loading...")
            progress.progress(30, text="Extracting transactions...")

            state = graph.invoke(initial_state, config)

            ph["extractor"].success("📥 Extractor — ✅ done")
            ph["risk_classifier"].success("🔍 Risk Classifier — ✅ done")
            progress.progress(55, text="Risk classification done...")
            ph["rag"].success("📚 RAG Agent — ✅ done")
            progress.progress(75, text="RAG context retrieved...")

            snapshot = graph.get_state(config)
            if snapshot.next and "human_review" in snapshot.next:
                progress.progress(80, text="⚠️ Awaiting human review...")
                st.session_state.analysis_state    = state
                st.session_state.awaiting_approval = True
                st.session_state.graph_config      = config
                st.rerun()
            else:
                ph["report_generator"].success("📝 Report Generator — ✅ done")
                progress.progress(100, text="Analysis complete!")
                st.session_state.analysis_state = state
                st.session_state.analysis_done  = True
                st.rerun()

    # ── Human Review ──────────────────────────────────────────────────────────
    if st.session_state.get("awaiting_approval"):
        state  = st.session_state.analysis_state
        config = st.session_state.get("graph_config", config)

        st.error("⚠️ HIGH RISK DETECTED — Human Review Required")
        r1, r2, r3 = st.columns(3)
        r1.metric("Risk Level",  state.get("overall_risk", "—"))
        r2.metric("Risk Score",  f"{state.get('risk_score', 0):.3f}")
        r3.metric("Total Flags", len(state.get("risk_flags", [])))

        high_flags = [f for f in state.get("risk_flags", []) if f["severity"] == "HIGH"]
        if high_flags:
            st.subheader("HIGH Risk Transactions")
            rows = []
            for f in high_flags[:10]:
                t = f["transaction"]
                rows.append({
                    "Date": t["date"], "Time": t["time"],
                    "Account": t["account"], "Beneficiary": t["beneficiary"],
                    "Amount (₹)": f"{t['amount']:,.0f}",
                    "Flag": f["flag_type"], "Reason": f["reason"][:80],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

        st.markdown("**Approve generating the risk report?**")
        a1, a2 = st.columns(2)

        if a1.button("✅ Approve — Generate Report", type="primary", use_container_width=True):
            graph.update_state(config, {"human_approved": True})
            with st.spinner("Generating report..."):
                final_state = graph.invoke(None, config)
            st.session_state.analysis_state    = final_state
            st.session_state.analysis_done     = True
            st.session_state.awaiting_approval = False
            st.rerun()

        if a2.button("❌ Reject — Flag for Manual Review", use_container_width=True):
            graph.update_state(config, {
                "human_approved": False,
                "report": "REJECTED — flagged for manual compliance review.",
            })
            st.session_state.analysis_done     = True
            st.session_state.awaiting_approval = False
            st.warning("Rejected. Flagged for manual review.")
            st.rerun()

    # ── Results ───────────────────────────────────────────────────────────────
    if st.session_state.get("analysis_done") and st.session_state.get("analysis_state"):
        state = st.session_state.analysis_state

        risk  = state.get("overall_risk", "UNKNOWN")
        score = state.get("risk_score", 0.0)
        if risk == "HIGH":
            st.error(f"🔴 Overall Risk: {risk}  |  Score: {score:.3f}")
        elif risk == "MEDIUM":
            st.warning(f"🟡 Overall Risk: {risk}  |  Score: {score:.3f}")
        else:
            st.success(f"🟢 Overall Risk: {risk}  |  Score: {score:.3f}")

        flags = state.get("risk_flags", [])
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Transactions Analyzed", state.get("total_count", 0))
        m2.metric("Total Flags",           len(flags))
        m3.metric("HIGH Flags",            sum(1 for f in flags if f["severity"] == "HIGH"))
        m4.metric("Date Range",            state.get("date_range", "—"))

        if flags:
            st.subheader("Risk Flags")
            rows = []
            for f in sorted(flags, key=lambda x: {"HIGH":0,"MEDIUM":1,"LOW":2}[x["severity"]]):
                t = f["transaction"]
                rows.append({
                    "Severity":    f["severity"],
                    "Date":        t["date"],
                    "Time":        t["time"],
                    "Account":     t["account"],
                    "Beneficiary": t["beneficiary"],
                    "Amount (₹)":  f"{t['amount']:,.0f}",
                    "Flag Type":   f["flag_type"],
                    "Reason":      f["reason"][:100],
                })
            fdf = pd.DataFrame(rows)

            def color_sev(val):
                if val == "HIGH":   return "background-color: #ffcccc"
                if val == "MEDIUM": return "background-color: #fff3cc"
                return ""

            st.dataframe(
                fdf.style.applymap(color_sev, subset=["Severity"]),
                use_container_width=True,
            )

        context = state.get("retrieved_context", [])
        if context:
            with st.expander(f"📚 Fraud Rules Context ({len(context)} refs)"):
                for i, c in enumerate(context, 1):
                    st.caption(f"[{i}] {c[:200]}")

        report = state.get("report", "")
        if report:
            st.subheader("📋 Risk Assessment Report")
            st.markdown(report)
            st.download_button(
                "📥 Download Report", data=report,
                file_name=f"finguard_report_{thread_id}.txt",
                mime="text/plain",
            )

        messages = state.get("messages", [])
        if messages:
            with st.expander(f"🤖 Agent Log ({len(messages)} messages)"):
                for msg in messages:
                    st.caption(f"🤖 {msg.content[:200]}")