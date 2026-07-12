"""
graph.py — Days 8–13 (fixed v3)
"""
import functools
import pandas as pd
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.sqlite import SqliteSaver

from state import FinGuardState
from agents import (
    extractor_agent,
    risk_classifier_agent,
    rag_agent,
    report_agent,
    supervisor_agent,
    route_from_supervisor,
)
from rag import build_rag_retriever

load_dotenv()


def human_review_node(state: FinGuardState) -> dict:
    print("\n[Human Review] ⚠️  HIGH RISK — paused for human input.")
    print(f"  Risk: {state.get('overall_risk')} | Score: {state.get('risk_score')}")
    return {"human_approved": state.get("human_approved"),}


def build_graph(csv_path: str, checkpointer=None, use_memory: bool = True):
    """
    Build and compile the FinGuard agent graph.
    checkpointer must be an already-entered SqliteSaver (not a context manager).
    """
    print("Building FinGuard AI graph...")
    print("  Loading RAG retriever...")
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    retriever = build_rag_retriever(df)
    print("  RAG retriever ready.")

    rag_with_retriever = functools.partial(rag_agent, retriever=retriever)

    builder = StateGraph(FinGuardState)
    builder.add_node("supervisor",       supervisor_agent)
    builder.add_node("extractor",        extractor_agent)
    builder.add_node("risk_classifier",  risk_classifier_agent)
    builder.add_node("rag",              rag_with_retriever)
    builder.add_node("human_review",     human_review_node)
    builder.add_node("report_generator", report_agent)

    builder.add_edge(START, "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "extractor":        "extractor",
            "risk_classifier":  "risk_classifier",
            "rag":              "rag",
            "human_review":     "human_review",
            "report_generator": "report_generator",
            "END":              END,
        },
    )

    for node in ["extractor", "risk_classifier", "rag", "human_review", "report_generator"]:
        builder.add_edge(node, "supervisor")

    if use_memory and checkpointer is not None:
        graph = builder.compile(
            checkpointer=checkpointer,
            interrupt_before=["human_review"],
        )
        print("  Graph compiled with memory + interrupt.")
    else:
        graph = builder.compile()
        print("  Graph compiled (no memory).")

    return graph, retriever


def run_analysis(
    csv_path: str,
    user_query: str = "Analyze these transactions for fraud",
    thread_id: str  = "default",
    auto_approve:   bool = False,
) -> dict:
    """
    CLI / langsmith_test.py entry point.
    Manually enters the SqliteSaver context manager.
    """
    from langchain_core.messages import HumanMessage

    # __enter__() gives the actual saver, not the context manager wrapper
    ctx    = SqliteSaver.from_conn_string("finguard_memory.db")
    memory = ctx.__enter__()

    try:
        graph, _ = build_graph(csv_path, checkpointer=memory, use_memory=True)
        config   = {"configurable": {"thread_id": thread_id}}

        initial_state = FinGuardState(
            user_query=user_query, csv_path=csv_path,
            transactions=[], total_count=0, date_range="",
            risk_flags=[], overall_risk="", risk_score=0.0,
            retrieved_context=[], report="",
            next_agent="", human_approved=None, error=None,
            messages=[HumanMessage(content=user_query)],
        )

        print(f"\n{'='*60}\nFinGuard AI — Thread: {thread_id}\nQuery: {user_query}\n{'='*60}")

        state    = graph.invoke(initial_state, config)
        snapshot = graph.get_state(config)

        if snapshot.next and "human_review" in snapshot.next:
            print(f"\n⚠️  PAUSED — Risk: {state.get('overall_risk')}")
            if auto_approve:
                print("Auto-approving...")
                graph.update_state(config, {"human_approved": True})
                state = graph.invoke(None, config)
            else:
                print("Resume: graph.update_state(config, {'human_approved': True})")
                return state

        print(f"\n{'='*60}\nCOMPLETE — Risk: {state.get('overall_risk')}\n{'='*60}")
        return state

    finally:
        ctx.__exit__(None, None, None)