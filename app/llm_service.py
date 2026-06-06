import base64
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.vector_store import (
    format_history_for_llm,
    get_conversation_history,
    save_conversation_message,
    search_documents,
)


UNKNOWN_ANSWER = "抱歉我的朋友，我还不是很不清楚，请询问相关人员，并让其完善知识库"
_MIN_RELEVANCE_SCORE = settings.rag_min_score
_MAX_CONTEXT_IMAGES = settings.rag_max_images
_TOP_K = settings.rag_top_k
_MAX_HISTORY = settings.rag_max_history_rounds
_MAX_TOKENS = settings.rag_max_tokens

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    return _client


SYSTEM_PROMPT = f"""\
你是专业的企业产品文档问答助手。

硬性规则：
1. 只能基于提供的文档上下文和图片回答，不允许编造、推测或使用外部常识补全产品流程。
2. 如果文档上下文不能明确回答用户问题，只回复：{UNKNOWN_ANSWER}
3. 如果你无法判断答案是否来自文档，只回复：{UNKNOWN_ANSWER}
4. 当回复"不清楚"时，不要解释原因，不要补充来源，不要添加其它文字。
5. 当文档中有相关图片时，结合图片内容说明，并在答案中指出图片对应的文档和页码/片段。
6. 当没有相关图片时，在答案中标明信息来自哪个文档、哪一页或哪个片段。
7. 正常回答时使用中文，语言清晰、直接。"""

UNCERTAINTY_MARKERS = (
    "不确定", "无法确定", "无法判断", "没有足够", "未提供", "没有提供",
    "上下文不足", "资料不足", "文档中未", "根据提供的信息无法",
    "抱歉", "sorry", "i don't know", "cannot determine", "not enough information",
)


def _unknown_result() -> dict:
    return {"answer": UNKNOWN_ANSWER, "images": [], "sources": [], "has_images": False}


def _filter_relevant_docs(docs: list[dict]) -> list[dict]:
    return [doc for doc in docs if float(doc.get("score") or 0) >= _MIN_RELEVANCE_SCORE]


def _build_context(docs: list[dict]) -> tuple[str, list[str]]:
    context_parts = []
    all_images = []
    for doc in docs:
        source = doc.get("source") or "Unknown"
        page = doc.get("page")
        chunk_index = doc.get("chunk_index", 0)
        score = doc.get("score", 0)
        location = f"page {page}" if page else f"chunk {chunk_index}"
        cat = doc.get("category", "")
        text = doc.get("text", "")
        cat_label = f" [分类: {cat}]" if cat else ""
        context_parts.append(f"[Source: {source}{cat_label} | {location} | score: {score:.4f}]\n{text}")
        for img_path in doc.get("images", []):
            if Path(img_path).exists() and img_path not in all_images:
                all_images.append(img_path)
    return "\n\n---\n\n".join(context_parts), all_images


def _image_to_content_part(img_path: str) -> dict:
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
    try:
        with open(img_path, "rb") as f:
            img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        ext = img_path.rsplit(".", 1)[-1].lower()
        mime = mime_map.get(ext, "image/png")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
    except Exception:
        return {"type": "text", "text": "[Image failed to load]"}


def _looks_unknown(answer: str) -> bool:
    a = answer.strip().lower()
    if not a or a == UNKNOWN_ANSWER:
        return True
    return any(marker in a for marker in UNCERTAINTY_MARKERS)


def ask(session_id: str, user_message: str, category: str = "") -> dict:
    """Ask a question within an optional product category (virtual isolation)."""
    # Step 1: search documents within the selected category
    try:
        relevant_docs = _filter_relevant_docs(
            search_documents(user_message, top_k=_TOP_K, category=category)
        )
    except Exception:
        save_conversation_message(session_id, "user", user_message)
        save_conversation_message(session_id, "assistant", UNKNOWN_ANSWER)
        return _unknown_result()

    if not relevant_docs:
        save_conversation_message(session_id, "user", user_message)
        save_conversation_message(session_id, "assistant", UNKNOWN_ANSWER)
        return _unknown_result()

    context_text, context_images = _build_context(relevant_docs)
    if not context_text.strip():
        save_conversation_message(session_id, "user", user_message)
        save_conversation_message(session_id, "assistant", UNKNOWN_ANSWER)
        return _unknown_result()

    # Step 2: build session history
    history = get_conversation_history(session_id, limit=_MAX_HISTORY)
    llm_history = format_history_for_llm(history)

    messages = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        *llm_history,
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "请只根据下面的文档上下文回答用户问题。\n"
                        f"如果不能明确回答，只回复：{UNKNOWN_ANSWER}\n\n"
                        f"文档上下文：\n{context_text}\n\n"
                        f"用户问题：{user_message}"
                    ),
                },
                *[_image_to_content_part(p) for p in context_images[:_MAX_CONTEXT_IMAGES]],
            ],
        },
    ]

    # Step 3: call LLM
    try:
        resp = _get_client().chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.1,
            max_tokens=_MAX_TOKENS,
        )
        answer = (resp.choices[0].message.content or "").strip()
    except Exception:
        save_conversation_message(session_id, "user", user_message)
        save_conversation_message(session_id, "assistant", UNKNOWN_ANSWER)
        return _unknown_result()

    save_conversation_message(session_id, "user", user_message)

    if _looks_unknown(answer):
        save_conversation_message(session_id, "assistant", UNKNOWN_ANSWER)
        return _unknown_result()

    result_images = context_images[:_MAX_CONTEXT_IMAGES]
    save_conversation_message(session_id, "assistant", answer, result_images)

    return {
        "answer": answer,
        "images": result_images,
        "sources": [doc.get("source", "") for doc in relevant_docs],
        "has_images": bool(result_images),
    }
