FROM python:3.11-slim

WORKDIR /app

# Build deps for some Python packages (sentence-transformers, chromadb)
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so the first document upload is instant
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY app/ ./app/

# Runtime data directories (mount a Railway volume at /data for persistence)
RUN mkdir -p /data/chroma_db /data/uploaded_docs

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
