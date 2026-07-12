"""
rag.py
Week 1 RAG pipeline repackaged as a clean module for Week 2 agents.
The RAG Extractor Agent uses this to retrieve fraud rule context.
"""
import os
import pandas as pd
from typing import List

from langchain.schema import Document
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.retrievers import EnsembleRetriever
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.retrievers import BM25Retriever
from sentence_transformers import CrossEncoder
from langchain.schema import BaseRetriever
from langchain.callbacks.manager import CallbackManagerForRetrieverRun


# ── Fraud rules knowledge base ────────────────────────────────────────────────
# In a real system this would be RBI guidelines, FinCEN SAR patterns, etc.
FRAUD_RULES = [
    "Structuring: Deliberately breaking large transactions into smaller ones below ₹50,000 to avoid reporting. Also called smurfing.",
    "Layering: Moving money through multiple accounts rapidly to obscure the source. Look for circular transfers.",
    "Late night transactions: Legitimate businesses rarely transact between 11pm and 4am. These warrant investigation.",
    "Round number transactions: Fraudsters often use round numbers like ₹10,000, ₹50,000, ₹1,00,000.",
    "New beneficiary + high amount: Adding a new payee and immediately sending a large amount is high risk.",
    "Transaction velocity: More than 10 transactions per account per day is unusual for retail customers.",
    "Unknown beneficiaries: Transfers to businesses with vague names like 'Unknown Co' or 'FastCash' are red flags.",
    "Rapid fund movement: Funds credited then immediately debited (within hours) suggests layering.",
    "Threshold avoidance: Amounts just below ₹50,000 (like ₹49,800 or ₹49,500) indicate awareness of reporting thresholds.",
    "Mule accounts: Accounts receiving money from many sources and forwarding to one destination are likely money mules.",
    "Geographic anomaly: Transactions from unusual locations or IP addresses outside normal patterns.",
    "Time clustering: Multiple transactions within minutes of each other from the same account.",
    "Hawala indicators: Cash-equivalent transfers without clear business purpose to informal networks.",
    "Invoice fraud: Duplicate invoices or invoices with slight variations to same beneficiary.",
    "Salary fraud: Unusual salary credits outside normal pay cycles or amounts.",
]


class RerankedRetriever(BaseRetriever):
    base_retriever: EnsembleRetriever
    cross_encoder:  CrossEncoder
    top_n:          int = 5

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
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


def build_rag_retriever(df: pd.DataFrame):
    """
    Build the hybrid + reranked retriever over:
    1. Transaction documents (from CSV)
    2. Fraud rules knowledge base
    Returns the retriever ready for use in agents.
    """
    # Transaction docs
    txn_docs = []
    for _, row in df.iterrows():
        content = (
            f"Date: {row['date']} Time: {row['time']} | "
            f"Account: {row['account']} | "
            f"Beneficiary: {row['beneficiary']} | "
            f"Description: {row['description']} | "
            f"Amount: {row['amount']} | Type: {row['type']}"
        )
        txn_docs.append(Document(
            page_content=content,
            metadata={"source": "transaction", "account": row["account"],
                      "amount": float(row["amount"])}
        ))

    # Fraud rule docs
    rule_docs = [
        Document(page_content=rule, metadata={"source": "fraud_rule"})
        for rule in FRAUD_RULES
    ]

    all_docs = txn_docs + rule_docs

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    vectorstore = Chroma.from_documents(documents=all_docs, embedding=embeddings)

    dense_retriever  = vectorstore.as_retriever(search_kwargs={"k": 20})
    bm25_retriever   = BM25Retriever.from_documents(all_docs)
    bm25_retriever.k = 20

    hybrid_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, dense_retriever],
        weights=[0.4, 0.6],
    )

    reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return RerankedRetriever(
        base_retriever=hybrid_retriever,
        cross_encoder=reranker,
        top_n=5,
    )


def retrieve_fraud_context(query: str, retriever) -> List[str]:
    """Retrieve relevant fraud rules and transaction context for a query."""
    docs = retriever.invoke(query)
    return [doc.page_content for doc in docs]
