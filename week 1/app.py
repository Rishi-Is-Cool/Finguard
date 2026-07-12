"""
app.py
FinGuard AI — Streamlit frontend.
Usage: streamlit run app.py
"""
import os
import tempfile
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FinGuard AI",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ FinGuard AI")
st.caption("Finance Fraud & Risk Intelligence System — Week 1")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 Upload Data")
    uploaded_file = st.file_uploader(
        "Upload transaction CSV",
        type=["csv"],
        help="CSV with columns: date, time, account, beneficiary, description, amount, type",
    )

    if uploaded_file:
        st.success(f"✅ Loaded: {uploaded_file.name}")

    st.divider()
    st.markdown("**Stack**")
    st.caption("Embeddings: all-MiniLM-L6-v2")
    st.caption("Vector DB: ChromaDB")
    st.caption("Retrieval: Hybrid BM25 + Dense")
    st.caption("Reranker: ms-marco-MiniLM-L-6-v2")
    st.caption("LLM: Llama-3.1-8b via Groq")

    st.divider()
    st.markdown("**Week 1 Progress**")
    for label in [
        "✅ Day 1 — Embeddings & chunking",
        "✅ Day 2 — Hybrid search",
        "✅ Day 3 — RAG pipeline",
        "✅ Day 4 — Reranking",
        "✅ Day 5 — RAGAS evaluation",
        "✅ Day 6 — Pandas agent + router",
        "✅ Day 7 — Streamlit demo",
    ]:
        st.caption(label)

# ── No file uploaded ──────────────────────────────────────────────────────────
if not uploaded_file:
    st.info("👆 Upload a transaction CSV from the sidebar to get started.")

    st.subheader("Expected CSV format")
    sample = pd.DataFrame([
        {
            "date": "2024-01-15", "time": "23:14",
            "account": "ACC001", "beneficiary": "Unknown Co",
            "description": "NEFT transfer", "amount": 49800, "type": "debit",
        },
        {
            "date": "2024-02-03", "time": "14:30",
            "account": "ACC002", "beneficiary": "Raj Kumar",
            "description": "UPI payment", "amount": 5000, "type": "debit",
        },
    ])
    st.dataframe(sample, use_container_width=True)

    st.info("💡 No CSV? Run `python generate_data.py` to create a sample one.")
    st.stop()

# ── Load CSV ──────────────────────────────────────────────────────────────────
@st.cache_data
def load_csv(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df["date"]    = pd.to_datetime(df["date"])
    df["hour"]    = pd.to_datetime(df["time"], format="%H:%M").dt.hour
    df["weekday"] = df["date"].dt.day_name()
    return df

df = load_csv(uploaded_file)

# ── Metrics row ───────────────────────────────────────────────────────────────
structuring  = df[df["amount"].between(49_000, 50_000)]
late_night   = df[df["hour"] >= 23]
unknown_co   = df[df["beneficiary"] == "Unknown Co"]
flagged_count = len(set(
    list(structuring.index) + list(late_night.index) + list(unknown_co.index)
))

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Transactions", len(df))
col2.metric("Total Debits",       len(df[df["type"] == "debit"]))
col3.metric("Total Credits",      len(df[df["type"] == "credit"]))
col4.metric("Unique Accounts",    df["account"].nunique())
col5.metric("⚠️ Auto-flagged",    flagged_count)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["💬 Ask Questions", "🔍 Auto Flags", "📊 Raw Data"])

# ── Tab 2: Auto Flags ─────────────────────────────────────────────────────────
with tab2:
    st.subheader("Automatically Detected Patterns")

    if len(structuring):
        st.warning(f"⚠️ **Structuring** — {len(structuring)} transactions in ₹49k–50k range")
        st.dataframe(
            structuring[["date","time","account","beneficiary","amount","type"]],
            use_container_width=True
        )
    else:
        st.success("No structuring patterns detected.")

    if len(late_night):
        st.warning(f"⚠️ **Late Night Activity** — {len(late_night)} transactions after 11pm")
        st.dataframe(
            late_night[["date","time","account","beneficiary","amount","type"]],
            use_container_width=True
        )
    else:
        st.success("No late night transactions detected.")

    if len(unknown_co):
        st.warning(f"⚠️ **Unknown Beneficiary** — {len(unknown_co)} transactions to 'Unknown Co'")
        st.dataframe(
            unknown_co[["date","time","account","beneficiary","amount","type"]],
            use_container_width=True
        )
    else:
        st.success("No unknown beneficiary transactions detected.")

# ── Tab 3: Raw Data ───────────────────────────────────────────────────────────
with tab3:
    st.subheader("All Transactions")
    
    # Filters
    fc1, fc2, fc3 = st.columns(3)
    acct_filter = fc1.multiselect("Account", options=df["account"].unique())
    type_filter = fc2.multiselect("Type",    options=df["type"].unique())
    bene_filter = fc3.multiselect("Beneficiary", options=df["beneficiary"].unique())

    filtered = df.copy()
    if acct_filter: filtered = filtered[filtered["account"].isin(acct_filter)]
    if type_filter: filtered = filtered[filtered["type"].isin(type_filter)]
    if bene_filter: filtered = filtered[filtered["beneficiary"].isin(bene_filter)]

    st.dataframe(
        filtered[["date","time","account","beneficiary","description","amount","type"]],
        use_container_width=True
    )

# ── Tab 1: Chat ───────────────────────────────────────────────────────────────
with tab1:

    # Load pipeline (cached so it only builds once)
    @st.cache_resource
    def load_pipeline(_df):
        """Build the full pipeline. Underscore prefix stops Streamlit hashing df."""
        from pipeline import build_pipeline
        print("Building FinGuard pipeline...")
        return build_pipeline(_df)

    with st.spinner("🔧 Loading AI pipeline (first load takes ~30s)..."):
        rag_chain, pandas_agent, router_chain, _ = load_pipeline(df)

    st.success("✅ Pipeline ready")

    # Chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg.get("route"):
                st.caption(f"Route: `{msg['route']}`")
            if msg.get("sources"):
                with st.expander(f"📄 Sources ({len(msg['sources'])} chunks)"):
                    for src in msg["sources"]:
                        st.caption(f"• {src}")

    # Sample question buttons
    st.markdown("**Try these:**")
    sq_cols = st.columns(2)
    sample_questions = [
        "Which transactions look like structuring?",
        "How many transactions happened on weekends?",
        "Any suspicious activity with Unknown Co?",
        "What is the total amount debited from ACC001?",
        "Show late night transfers after 11pm",
        "Which beneficiary received the most money?",
    ]
    for i, q in enumerate(sample_questions):
        if sq_cols[i % 2].button(q, use_container_width=True, key=f"sq_{i}"):
            st.session_state.messages.append({"role": "user", "content": q})
            st.rerun()

    st.divider()

    # Chat input
    if query := st.chat_input("Ask anything about your transactions..."):
        st.session_state.messages.append({"role": "user", "content": query})
        st.rerun()

    # Process last unanswered message
    if (
        st.session_state.messages
        and st.session_state.messages[-1]["role"] == "user"
        and (
            len(st.session_state.messages) == 1
            or st.session_state.messages[-2]["role"] != "assistant"
            or st.session_state.messages[-2].get("answered_idx") != len(st.session_state.messages) - 1
        )
    ):
        query = st.session_state.messages[-1]["content"]

        with st.chat_message("user"):
            st.write(query)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                from pipeline import ask as finguard_ask
                result = finguard_ask(query, rag_chain, pandas_agent, router_chain)

            st.write(result["answer"])
            st.caption(f"Route: `{result['route']}`")

            if result["sources"]:
                with st.expander(f"📄 Sources ({len(result['sources'])} chunks)"):
                    for src in result["sources"]:
                        st.caption(f"• {src}")

        st.session_state.messages.append({
            "role":        "assistant",
            "content":     result["answer"],
            "route":       result["route"],
            "sources":     result["sources"],
            "answered_idx": len(st.session_state.messages) - 1,
        })
        st.rerun()
