"""
Lightweight RAG retriever — no Chroma/hnswlib dependency (avoids C++ build tools
requirement on Windows). Uses sentence-transformers for embeddings and plain numpy
cosine similarity for retrieval. Fine for a few hundred to a few thousand chunks,
which comfortably covers a hotel FAQ knowledge base.
"""
import os
import pickle
import glob

import numpy as np
from sentence_transformers import SentenceTransformer

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "rag_index.pkl")

_model = None
_index = None  # dict: {"chunks": [...], "embeddings": np.ndarray}


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Simple sliding-window chunker (character-based, no external splitter needed)."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]


def build_index() -> None:
    """Run once (or whenever data/ changes) to (re)build the local index from data/*.txt."""
    model = _get_model()
    all_chunks: list[str] = []

    for filepath in glob.glob(os.path.join(DATA_DIR, "**", "*.txt"), recursive=True):
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        all_chunks.extend(_chunk_text(text))

    if not all_chunks:
        print(f"No .txt files found in {DATA_DIR} — index will be empty.")
        embeddings = np.zeros((0, model.get_sentence_embedding_dimension()))
    else:
        embeddings = model.encode(all_chunks, convert_to_numpy=True, normalize_embeddings=True)

    with open(INDEX_PATH, "wb") as f:
        pickle.dump({"chunks": all_chunks, "embeddings": embeddings}, f)

    print(f"Indexed {len(all_chunks)} chunks -> {INDEX_PATH}")


def _load_index() -> dict:
    global _index
    if _index is None:
        if not os.path.exists(INDEX_PATH):
            raise FileNotFoundError(
                "No RAG index found. Run `python -m scripts.seed` first to build it."
            )
        with open(INDEX_PATH, "rb") as f:
            _index = pickle.load(f)
    return _index


def retrieve_context(query: str, k: int = 4) -> str:
    index = _load_index()
    if len(index["chunks"]) == 0:
        return ""

    model = _get_model()
    query_emb = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]

    # cosine similarity == dot product since embeddings are normalized
    scores = index["embeddings"] @ query_emb
    top_k_idx = np.argsort(scores)[::-1][:k]

    return "\n\n".join(index["chunks"][i] for i in top_k_idx)
