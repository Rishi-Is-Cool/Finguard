"""
backend/agentic_rag.py — Day 19
Corrective RAG (CRAG) pattern:
  retrieve → grade relevance → if poor: rewrite query → retrieve again → generate

Reading: Ch. 8 pp. 255–258 (Advanced RAG Techniques)
"""
import os
import uuid
from functools import lru_cache
from typing import List
# Chroma ships usage telemetry on by default. Transaction data never goes in
# it, but a finance deployment should not phone home at all. Must be set
# before chromadb is imported.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from dotenv import load_dotenv

from langchain.schema import Document
from langchain.retrievers import EnsembleRetriever
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from sentence_transformers import CrossEncoder
from langchain.schema import BaseRetriever
from langchain.callbacks.manager import CallbackManagerForRetrieverRun

load_dotenv()

# Groq serves a moving set of models; llama-3.1-8b-instant was retired.
# Override with GROQ_MODEL in .env if this one is retired too.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

from backend.knowledge import FRAUD_RULES


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
        for score, doc in ranked[:self.top_n]:
            doc.metadata["rerank_score"] = float(score)
            results.append(doc)
        return results


class CorreciveRAG:
    """
    CRAG — Corrective RAG with self-correction loop.

    Flow:
      query → retrieve → grade each doc (1–5) → if avg score < 3:
        → rewrite query with LLM → retrieve again → generate
      else:
        → generate directly

    This ensures the context passed to the LLM is always relevant.
    """

    def __init__(self, retriever, llm, vectorstore=None):
        self.retriever   = retriever
        self.llm         = llm
        self.vectorstore = vectorstore

    def close(self):
        """Drop this run's Chroma collection. The in-process Chroma client is
        shared, so an undeleted collection leaks memory on every request."""
        if self.vectorstore is not None:
            try:
                self.vectorstore.delete_collection()
            except Exception as e:
                print(f"  [CRAG] could not drop collection: {e}")
            self.vectorstore = None

    def grade_document(self, query: str, document: str) -> float:
        """
        Grade relevance of a document for a query (1.0–5.0).
        1 = completely irrelevant, 5 = highly relevant.
        """
        prompt = f"""Rate the relevance of this document for answering the query on a scale of 1-5.
Query: {query}
Document: {document[:300]}
Respond with ONLY a single number (1, 2, 3, 4, or 5). No explanation."""

        response = self.llm.invoke([HumanMessage(content=prompt)])
        try:
            score = float(response.content.strip()[0])
            return max(1.0, min(5.0, score))
        except Exception:
            return 3.0

    def rewrite_query(self, original_query: str, context: str = "") -> str:
        """
        Rewrite a query to be more specific for fraud rule retrieval.
        """
        prompt = f"""You are helping retrieve fraud detection rules.
Rewrite this query to be more specific and retrieval-friendly.

Original query: {original_query}
Context (what we know so far): {context[:200] if context else "None"}

Write ONE improved query. No explanation, just the query:"""

        response = self.llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()

    def retrieve_with_grading(self, query: str, min_score: float = 3.0):
        """
        Retrieve docs, grade them, rewrite and re-retrieve if quality is poor.
        Returns (docs, was_rewritten, final_query)
        """
        # Step 1: Initial retrieval
        docs = self.retriever.invoke(query)
        if not docs:
            return [], False, query

        # Step 2: Grade each doc
        scores = []
        for doc in docs[:3]:  # grade top 3 for speed
            score = self.grade_document(query, doc.page_content)
            scores.append(score)
            doc.metadata["relevance_score"] = score

        avg_score = sum(scores) / len(scores)
        print(f"  [CRAG] Initial retrieval avg relevance: {avg_score:.1f}/5.0")

        # Step 3: If quality is poor, rewrite and re-retrieve
        if avg_score < min_score:
            print(f"  [CRAG] Low relevance ({avg_score:.1f}) — rewriting query...")
            new_query = self.rewrite_query(query)
            print(f"  [CRAG] Rewritten: '{new_query}'")

            docs = self.retriever.invoke(new_query)
            # Re-grade
            for doc in docs[:3]:
                score = self.grade_document(new_query, doc.page_content)
                doc.metadata["relevance_score"] = score

            return docs, True, new_query

        return docs, False, query

    def answer(self, query: str, extra_context: str = "") -> dict:
        """
        Full CRAG pipeline: retrieve → grade → maybe rewrite → generate.
        """
        docs, was_rewritten, final_query = self.retrieve_with_grading(query)

        if not docs:
            return {
                "answer": "No relevant fraud rules found for this query.",
                "sources": [],
                "was_rewritten": False,
                "final_query": query,
            }

        context = "\n".join(f"- {doc.page_content}" for doc in docs)

        prompt = f"""You are a financial fraud expert. Answer the question using the fraud rules below.
Be specific and cite the relevant rules.

Fraud Rules:
{context}

{f"Additional Context: {extra_context}" if extra_context else ""}

Question: {query}

Answer:"""

        response = self.llm.invoke([HumanMessage(content=prompt)])

        return {
            "answer":        response.content,
            "sources":       [doc.page_content for doc in docs],
            "relevance_scores": [doc.metadata.get("relevance_score", 0) for doc in docs],
            "was_rewritten": was_rewritten,
            "final_query":   final_query,
        }


@lru_cache(maxsize=1)
def get_embeddings():
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def get_reranker():
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def warm_models():
    """Load both models once at startup instead of on the first user's request."""
    get_embeddings()
    get_reranker()


def build_crag(transactions=None):
    """Build the CRAG pipeline over the fraud rules plus this upload's transactions.
    Call .close() on the result when done."""
    all_docs = [
        Document(page_content=rule, metadata={"source": "fraud_rule"})
        for rule in FRAUD_RULES
    ]

    for t in transactions or []:
        content = (
            f"Date: {t['date']} Time: {t['time']} | "
            f"Account: {t['account']} | Beneficiary: {t['beneficiary']} | "
            f"Amount: {t['amount']} | Type: {t['type']}"
        )
        all_docs.append(Document(page_content=content, metadata={"source": "transaction"}))

    # Chroma's in-process client is a singleton: with the default collection
    # name every request appends into the same collection, so one user's
    # transactions become retrievable in another user's report. One collection
    # per run, dropped in close().
    vectorstore = Chroma.from_documents(
        documents=all_docs,
        embedding=get_embeddings(),
        collection_name=f"finguard-{uuid.uuid4().hex}",
    )
    dense = vectorstore.as_retriever(search_kwargs={"k": 20})

    bm25   = BM25Retriever.from_documents(all_docs)
    bm25.k = 20

    hybrid    = EnsembleRetriever(retrievers=[bm25, dense], weights=[0.4, 0.6])
    retriever = RerankedRetriever(base_retriever=hybrid, cross_encoder=get_reranker(), top_n=5)

    llm = ChatGroq(
        model=GROQ_MODEL,
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0,
    )

    return CorreciveRAG(retriever=retriever, llm=llm, vectorstore=vectorstore)
