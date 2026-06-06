import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import tomllib

# Load .env as fallback for env vars
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(env_path)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


def _load_toml() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {}


def _get(key: str, default="") -> str:
    """Lookup priority: env var > config.toml > default."""
    raw = os.environ.get(key)
    if raw:
        return raw
    cfg = _load_toml()
    # Support both flat keys and section.key notation
    if "." in key:
        section, k = key.split(".", 1)
        return str(cfg.get(section, {}).get(k, default)) if isinstance(cfg.get(section), dict) else default
    return str(cfg.get(key, default)) if isinstance(cfg, dict) and key in cfg else default


def _get_int(key: str, default: int) -> int:
    raw = _get(key, "")
    if raw and str(raw).strip():
        try:
            return int(str(raw).strip())
        except (ValueError, TypeError):
            pass
    return default


def _get_float(key: str, default: float) -> float:
    raw = _get(key, "")
    if raw and str(raw).strip():
        try:
            return float(str(raw).strip())
        except (ValueError, TypeError):
            pass
    return default


class Settings:
    # ── LLM ──
    llm_api_key: str = _get("LLM_API_KEY", "")
    llm_base_url: str = _get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    llm_model: str = _get("LLM_MODEL", "qwen-vl-max")

    # ── Embedding ──
    embedding_api_key: str = _get("EMBEDDING_API_KEY", "")
    embedding_base_url: str = _get("EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    embedding_model: str = _get("EMBEDDING_MODEL", "text-embedding-v3")
    embedding_dimensions: int = _get_int("EMBEDDING_DIMENSIONS", 1024)

    # ── Qdrant ──
    qdrant_host: str = _get("QDRANT_HOST", "localhost")
    qdrant_port: int = _get_int("QDRANT_PORT", 6333)

    # ── Data directories ──
    upload_dir: Path = Path(__file__).resolve().parent.parent / _get("UPLOAD_DIR", "uploads")
    image_dir: Path = Path(__file__).resolve().parent.parent / _get("IMAGE_DIR", "extracted_images")

    # ── Vector collection names ──
    doc_collection: str = _get("DOC_COLLECTION", "documents")
    session_collection: str = _get("SESSION_COLLECTION", "conversations")

    # ── Document chunking ──
    chunk_size: int = _get_int("CHUNK_SIZE", 500)
    chunk_overlap: int = _get_int("CHUNK_OVERLAP", 50)

    # ── RAG / context window ──
    rag_top_k: int = _get_int("RAG_TOP_K", 8)
    rag_min_score: float = _get_float("RAG_MIN_SCORE", 0.35)
    rag_max_history_rounds: int = _get_int("RAG_MAX_HISTORY_ROUNDS", 10)
    rag_max_images: int = _get_int("RAG_MAX_IMAGES", 5)
    rag_max_tokens: int = _get_int("RAG_MAX_TOKENS", 4096)

    # ── Server ──
    server_host: str = _get("SERVER_HOST", "0.0.0.0")
    server_port: int = _get_int("SERVER_PORT", 8000)


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.image_dir.mkdir(parents=True, exist_ok=True)


def dump_settings() -> dict:
    """Return current settings as a dict (for display)."""
    return {
        "LLM 模型": settings.llm_model,
        "LLM 地址": settings.llm_base_url,
        "Embedding 模型": settings.embedding_model,
        "Embedding 维度": settings.embedding_dimensions,
        "Qdrant 地址": f"{settings.qdrant_host}:{settings.qdrant_port}",
        "文档 Collection": settings.doc_collection,
        "会话 Collection": settings.session_collection,
        "上传目录": str(settings.upload_dir),
        "图片目录": str(settings.image_dir),
        "单次检索段落数": settings.rag_top_k,
        "最低相关度阈值": settings.rag_min_score,
        "历史对话轮数上限": settings.rag_max_history_rounds,
        "图片上限": settings.rag_max_images,
        "回答 token 上限": settings.rag_max_tokens,
        "文本分块大小": settings.chunk_size,
        "分块重叠": settings.chunk_overlap,
        "服务端口": f"{settings.server_host}:{settings.server_port}",
    }


if __name__ == "__main__":
    print(json.dumps(dump_settings(), ensure_ascii=False, indent=2))
