import json
import os
import re
import time

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.path.join(BASE, "data", "rag_index")
CHUNKS_FILE = os.path.join(INDEX_DIR, "chunks.json")
VECTORS_FILE = os.path.join(INDEX_DIR, "vectors.npy")
META_FILE = os.path.join(INDEX_DIR, "meta.json")

_ALLOWED_EXT = {
    ".py", ".md", ".json", ".yml", ".yaml", ".service", ".txt",
    ".toml", ".ini", ".sh", ".sql",
}
_ALLOWED_NAMES = {"dockerfile", "makefile", "requirements.txt", "readme"}
_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    "data", "dist", "build", ".mypy_cache", ".pytest_cache",
}
_SKIP_FILES = {".env", ".env.local", ".env.production"}
_MAX_FILE = 200_000
_CHUNK = 800
_OVERLAP = 100


def _cfg(ai_cfg):
    return ai_cfg or {}


def _roots(ai_cfg):
    return [os.path.realpath(p) for p in _cfg(ai_cfg).get("rag_paths", []) if os.path.isdir(p)]


def _allowed_file(path):
    base = os.path.basename(path).lower()
    if base in _SKIP_FILES or base.startswith(".env"):
        return False
    if base in _ALLOWED_NAMES:
        return True
    return os.path.splitext(base)[1] in _ALLOWED_EXT


def _in_roots(path, roots):
    real = os.path.realpath(path)
    return any(real == r or real.startswith(r + os.sep) for r in roots)


def _chunk_text(text, source):
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    out = []
    step = max(1, _CHUNK - _OVERLAP)
    for i in range(0, len(text), step):
        part = text[i : i + _CHUNK].strip()
        if part:
            out.append({"source": source, "text": part})
        if i + _CHUNK >= len(text):
            break
    return out


def collect_chunks(ai_cfg):
    roots = _roots(ai_cfg)
    chunks = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if not _allowed_file(fpath):
                    continue
                try:
                    if os.path.getsize(fpath) > _MAX_FILE:
                        continue
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                except Exception:
                    continue
                rel = os.path.relpath(fpath, root)
                source = f"{root}/{rel}"
                chunks.extend(_chunk_text(text, source))
    return chunks


def _embed_client(ai_cfg):
    key = os.getenv("NVIDIA_API_KEY", "")
    if not key:
        return None
    try:
        from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
    except ImportError:
        return None
    model = _cfg(ai_cfg).get("embedding_model", "nvidia/nv-embedqa-e5-v5")
    return NVIDIAEmbeddings(model=model, api_key=key, truncate="END")


def _embed_batch(client, texts):
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)
    vecs = client.embed_documents(texts)
    arr = np.array(vecs, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def _keyword_search(chunks, query, k=5):
    words = [w.lower() for w in re.findall(r"\w{3,}", query)]
    if not words:
        return []
    scored = []
    for i, ch in enumerate(chunks):
        blob = (ch.get("source", "") + " " + ch.get("text", "")).lower()
        score = sum(blob.count(w) for w in words)
        if score:
            scored.append((score, i))
    scored.sort(reverse=True)
    return [chunks[i] for _, i in scored[:k]]


def index_age_hours():
    if not os.path.exists(META_FILE):
        return 1e9
    try:
        with open(META_FILE) as f:
            meta = json.load(f)
        return (time.time() - meta.get("built_at", 0)) / 3600.0
    except Exception:
        return 1e9


def rebuild_index(ai_cfg, force=False):
    os.makedirs(INDEX_DIR, exist_ok=True)
    max_age = float(_cfg(ai_cfg).get("rag_rebuild_hours", 24))
    if not force and index_age_hours() < max_age and os.path.exists(CHUNKS_FILE):
        return load_index()

    chunks = collect_chunks(ai_cfg)
    client = _embed_client(ai_cfg)
    vectors = None
    if client and chunks:
        batch = 32
        parts = []
        for i in range(0, len(chunks), batch):
            texts = [c["text"] for c in chunks[i : i + batch]]
            parts.append(_embed_batch(client, texts))
        vectors = np.vstack(parts) if parts else np.zeros((0, 1), dtype=np.float32)
    else:
        vectors = np.zeros((len(chunks), 1), dtype=np.float32)

    with open(CHUNKS_FILE, "w") as f:
        json.dump(chunks, f)
    np.save(VECTORS_FILE, vectors)
    with open(META_FILE, "w") as f:
        json.dump({"built_at": time.time(), "count": len(chunks)}, f)
    return chunks, vectors


def load_index():
    if not os.path.exists(CHUNKS_FILE):
        return [], np.zeros((0, 1), dtype=np.float32)
    with open(CHUNKS_FILE) as f:
        chunks = json.load(f)
    vectors = np.load(VECTORS_FILE) if os.path.exists(VECTORS_FILE) else np.zeros((0, 1))
    return chunks, vectors


def search(query, ai_cfg, k=5):
    chunks, vectors = load_index()
    if not chunks:
        chunks, vectors = rebuild_index(ai_cfg)

    client = _embed_client(ai_cfg)
    if client is not None and len(vectors) and vectors.shape[1] > 1:
        try:
            qv = np.array(client.embed_query(query), dtype=np.float32)
            norm = np.linalg.norm(qv)
            if norm > 0:
                qv = qv / norm
            scores = vectors @ qv
            idx = np.argsort(scores)[::-1][:k]
            return [chunks[int(i)] for i in idx if scores[int(i)] > 0.05]
        except Exception:
            pass
    return _keyword_search(chunks, query, k=k)


def safe_path(path, ai_cfg):
    roots = _roots(ai_cfg)
    if not roots:
        return None
    real = os.path.realpath(os.path.expanduser(path))
    if not _in_roots(real, roots):
        return None
    if os.path.basename(real).lower() in _SKIP_FILES:
        return None
    return real