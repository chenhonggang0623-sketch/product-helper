import uuid
import time
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
    MatchText,
    PointStruct,
    VectorParams,
)

from app.config import settings
from app.embedder import embed_texts

_client: Optional[QdrantClient] = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _client


# ── Document Collection ──────────────────────────────────


def ensure_doc_collection():
    client = _get_client()
    collections = [c.name for c in client.get_collections().collections]
    if settings.doc_collection not in collections:
        client.create_collection(
            collection_name=settings.doc_collection,
            vectors_config=VectorParams(size=settings.embedding_dimensions, distance=Distance.COSINE),
        )


def add_document_chunks(chunks: list[dict], category: str = ""):
    """Add chunks to Qdrant. category is a virtual isolation tag (e.g. '产品A')."""
    ensure_doc_collection()
    client = _get_client()

    # Dedup: remove existing chunks from same source file within same category
    if chunks:
        base_source = chunks[0].get("source", "").split(" (p.")[0]
        if base_source:
            must_conditions = [
                FieldCondition(key="source_file", match=MatchValue(value=base_source)),
            ]
            if category:
                must_conditions.append(
                    FieldCondition(key="category", match=MatchValue(value=category))
                )
            try:
                client.delete(
                    collection_name=settings.doc_collection,
                    points_selector=Filter(must=must_conditions),
                )
            except Exception:
                pass

    texts = [c["text"] for c in chunks]
    vectors = embed_texts(texts)
    points = []
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        base_source = chunk.get("source", "").split(" (p.")[0]
        payload = {
            "text": chunk["text"],
            "source": chunk.get("source", ""),
            "source_file": base_source,
            "doc_id": chunk.get("doc_id", ""),
            "doc_type": chunk.get("doc_type", ""),
            "chunk_index": chunk.get("index", i),
            "images": chunk.get("images", []),
            "category": category,
        }
        if "page" in chunk:
            payload["page"] = chunk["page"]
        points.append(PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload))

    client.upsert(collection_name=settings.doc_collection, points=points)


def search_documents(query: str, top_k: int = 5, category: str = "") -> list[dict]:
    """Search documents, optionally filtered by category (virtual isolation)."""
    client = _get_client()
    query_vector = embed_texts([query])[0]

    query_filter = None
    if category:
        query_filter = Filter(
            must=[
                FieldCondition(key="category", match=MatchValue(value=category)),
            ]
        )

    resp = client.query_points(
        collection_name=settings.doc_collection,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    )
    return [
        {
            "text": r.payload.get("text", ""),
            "source": r.payload.get("source", ""),
            "doc_id": r.payload.get("doc_id", ""),
            "doc_type": r.payload.get("doc_type", ""),
            "images": r.payload.get("images", []),
            "score": r.score,
            "chunk_index": r.payload.get("chunk_index", 0),
            "page": r.payload.get("page"),
            "category": r.payload.get("category", ""),
        }
        for r in resp.points
    ]


def delete_category(category: str):
    """Delete all document chunks belonging to a category."""
    client = _get_client()
    try:
        client.delete(
            collection_name=settings.doc_collection,
            points_selector=Filter(
                must=[FieldCondition(key="category", match=MatchValue(value=category))]
            ),
        )
    except Exception:
        pass


def list_categories() -> list[str]:
    """Return all distinct categories stored in the document collection."""
    client = _get_client()
    try:
        results = client.scroll(
            collection_name=settings.doc_collection,
            limit=5000,
            with_payload=True,
        )
        cats = set()
        for r in results[0]:
            cat = r.payload.get("category", "")
            if cat:
                cats.add(cat)
        return sorted(cats)
    except Exception:
        return []


# ── Session / Conversation Memory ────────────────────────


def ensure_session_collection():
    client = _get_client()
    collections = [c.name for c in client.get_collections().collections]
    if settings.session_collection not in collections:
        client.create_collection(
            collection_name=settings.session_collection,
            vectors_config=VectorParams(size=settings.embedding_dimensions, distance=Distance.COSINE),
        )


def save_conversation_message(session_id: str, role: str, content: str, images: list[str] = None):
    ensure_session_collection()
    client = _get_client()
    dimension = settings.embedding_dimensions
    if content.strip():
        vector = embed_texts([content[:500]])[0]
    else:
        vector = [0.0] * dimension
    client.upsert(
        collection_name=settings.session_collection,
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "images": images or [],
                    "timestamp": time.time(),
                },
            )
        ],
    )


def get_conversation_history(session_id: str, limit: int = 20) -> list[dict]:
    client = _get_client()
    try:
        results = client.scroll(
            collection_name=settings.session_collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
            ),
            limit=100,
            with_payload=True,
        )
    except Exception:
        return []

    messages = [
        {
            "role": r.payload.get("role", ""),
            "content": r.payload.get("content", ""),
            "images": r.payload.get("images", []),
            "timestamp": r.payload.get("timestamp", 0),
        }
        for r in results[0]
    ]
    messages.sort(key=lambda x: x["timestamp"])
    return messages[-limit:]


def delete_session(session_id: str):
    """Delete all conversation messages for a session."""
    client = _get_client()
    try:
        client.delete(
            collection_name=settings.session_collection,
            points_selector=Filter(
                must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
            ),
        )
    except Exception:
        pass


def format_history_for_llm(messages: list[dict]) -> list[dict]:
    import base64

    formatted = []
    mime_map = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
    }
    for msg in messages:
        content_parts = [{"type": "text", "text": msg["content"]}]
        if msg["role"] == "user":
            for img_path in msg.get("images", []):
                try:
                    with open(img_path, "rb") as f:
                        img_bytes = f.read()
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    ext = img_path.rsplit(".", 1)[-1].lower()
                    mime = mime_map.get(ext, "image/png")
                    content_parts.append(
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                    )
                except Exception:
                    pass
        formatted.append({"role": msg["role"], "content": content_parts})
    return formatted
