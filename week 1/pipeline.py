"""
pipeline.py
Core FinGuard AI pipeline — RAG + Pandas Agent + Router.
All Days 1-6 logic lives here. Imported by app.py.
"""
import os
import pandas as pd
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.retrievers import EnsembleRetriever
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain_core.output_parsers import StrOutputParser
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain_groq import ChatGroq
from sentence_transformers import CrossEncoder
from langchain_core.retrievers import BaseRetriever
from langchain.callbacks.manager import CallbackManagerForRetrieverRun
from typing import List

load_dotenv()

# ─────────────────────────────────────────────
# 1. Helpers
# ─────────────────────────────────────────────

def load_dataframe(csv_path: str) -> pd.DataFrame:
    """Load and enrich the transactions CSV."""
    df = pd.read_csv(csv_path)
    df["date"]    = pd.to_datetime(df["date"])
    df["hour"]    = pd.to_datetime(df["time"], format="%H:%M").dt.hour
    df["weekday"] = df["date"].dt.day_name()
    return df


def df_to_docs(df: pd.DataFrame) -> List[Document]:
    """Convert each transaction row into a LangChain Document."""
    docs = []
    for _, row in df.iterrows():
        content = (
            f"Date: {row['date'].strftime('%Y-%m-%d')} Time: {row['time']} | "
            f"Account: {row['account']} | "
            f"Beneficiary: {row['beneficiary']} | "
            f"Description: {row['description']} | "
            f"Amount: {row['amount']} | Type: {row['type']}"
        )
        docs.append(Document(
            page_content=content,
            metadata={
                "date":    str(row["date"]),
                "account": row["account"],
                "amount":  float(row["amount"]),
                "type":    row["type"],
            }
        ))
    return docs


# ─────────────────────────────────────────────
# 2. Reranker (Day 4)
# ─────────────────────────────────────────────

class RerankedRetriever(BaseRetriever):
    """Hybrid retriever + cross-encoder reranking."""

    base_retriever: EnsembleRetriever
    cross_encoder:  CrossEncoder
    top_n:          int = 5

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:
        candidates = self.base_retriever.invoke(query)
        if not candidates:
            return []
        pairs  = [[query, doc.page_content] for doc in candidates]
        scores = self.cross_encoder.predict(pairs)
        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        results = []
        for score, doc in ranked[: self.top_n]:
            doc.metadata["rerank_score"] = float(score)
            results.append(doc)
        return results


# ─────────────────────────────────────────────
# 3. Pipeline builder
# ─────────────────────────────────────────────

FRAUD_PROMPT = PromptTemplate(
    template="""You are a financial fraud analyst AI.
Use ONLY the transaction records below to answer the question.
If the answer cannot be determined from the records, say "Cannot determine from available data."
Never guess or hallucinate amounts, dates, or account numbers.

Transaction Records:
{context}

Question: {question}

Analysis:""",
    input_variables=["context", "question"],
)

ROUTER_PROMPT = PromptTemplate(
    template="""Classify this financial query into exactly one category:

ANALYTICAL — requires counting, summing, averaging, date calculations,
             sorting, ranking, or any math on data.
SEMANTIC   — requires finding patterns, describing suspicious behavior,
             qualitative analysis, or meaning-based search.

Query: {query}

Respond with exactly one word — ANALYTICAL or SEMANTIC:""",
    input_variables=["query"],
)


def build_pipeline(df: pd.DataFrame):
    """
    Build and return the full FinGuard pipeline.
    Returns: (rag_chain, pandas_agent, router_chain, reranked_retriever)
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in .env file")

    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=api_key,
        temperature=0,
    )

    # --- Documents ---
    docs = df_to_docs(df)

    # --- Embeddings + Vector store ---
    print("  Loading embedding model...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    vectorstore = Chroma.from_documents(documents=docs, embedding=embeddings)

    # --- Retrievers ---
    dense_retriever = vectorstore.as_retriever(search_kwargs={"k": 20})

    bm25_retriever   = BM25Retriever.from_documents(docs)
    bm25_retriever.k = 20

    hybrid_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, dense_retriever],
        weights=[0.4, 0.6],
    )

    # --- Cross-encoder reranker (Day 4) ---
    print("  Loading reranker model...")
    reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    reranked_retriever = RerankedRetriever(
        base_retriever=hybrid_retriever,
        cross_encoder=reranker,
        top_n=5,
    )

    # --- RAG chain ---
    rag_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=reranked_retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": FRAUD_PROMPT},
    )

    # --- Pandas agent ---
    pandas_agent = create_pandas_dataframe_agent(
        llm=llm,
        df=df,
        verbose=False,
        allow_dangerous_code=True,
        agent_type="tool-calling",
    )

    # --- Router chain ---
    router_chain = ROUTER_PROMPT | llm | StrOutputParser()

    return rag_chain, pandas_agent, router_chain, reranked_retriever


# ─────────────────────────────────────────────
# 4. Main query function
# ─────────────────────────────────────────────

def ask(query: str, rag_chain, pandas_agent, router_chain) -> dict:
    """
    Route a query and return a result dict:
    { "answer": str, "route": str, "sources": list[str] }
    """
    raw    = router_chain.invoke({"query": query}).strip().upper()
    route  = "ANALYTICAL" if "ANALYTICAL" in raw else "SEMANTIC"
    sources = []

    if route == "ANALYTICAL":
        result = pandas_agent.invoke(query)
        answer = result["output"]
    else:
        result = rag_chain.invoke({"query": query})
        answer = result["result"]
        sources = [
            doc.page_content[:150]
            for doc in result.get("source_documents", [])
        ]

    return {"answer": answer, "route": route, "sources": sources}
