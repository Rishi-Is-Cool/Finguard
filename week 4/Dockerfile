# FinGuard AI — one container: FastAPI serves the API under /api and the built
# React app under /. Runs on Hugging Face Spaces (port 7860, uid 1000) and on
# any host that sets $PORT (Render, Fly.io, Railway, Cloud Run).

# ── 1. Build the frontend ─────────────────────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VITE_REPO_URL=https://github.com/Rishi-Is-Cool/Finguard
ENV VITE_REPO_URL=${VITE_REPO_URL}
RUN npm run build

# ── 2. API + static frontend ──────────────────────────────────────────────────
FROM python:3.11-slim

# Hugging Face Spaces runs containers as uid 1000; own everything as that user.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/user/.cache/huggingface \
    FINGUARD_AUDIT_DIR=/home/user/app/audit_logs \
    PORT=7860
WORKDIR /home/user/app

# CPU torch first — otherwise sentence-transformers pulls the ~2.5 GB CUDA build.
COPY --chown=user backend/requirements.txt backend/requirements.txt
RUN pip install --user torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --user -r backend/requirements.txt

# Bake the embedding + reranker weights in: no model download on cold start.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

COPY --chown=user backend/ backend/
COPY --chown=user data/transactions.csv data/transactions.csv
COPY --from=frontend --chown=user /build/dist frontend/dist

EXPOSE 7860
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
