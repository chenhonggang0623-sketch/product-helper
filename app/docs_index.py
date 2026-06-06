"""docs_index.py — 文档分类索引 + 图片路径索引（使用 JSON 文件）"""

import json
from pathlib import Path

from app.config import settings

INDEX_FILE: Path = settings.upload_dir / "docs_index.json"
IMAGES_INDEX_FILE: Path = settings.upload_dir / "images_index.json"


# ── 分类索引 ──


def _load() -> dict[str, list[str]]:
    if INDEX_FILE.exists():
        try:
            data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _save(data: dict[str, list[str]]):
    INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_doc(filename: str, category: str = ""):
    data = _load()
    if category:
        if category not in data:
            data[category] = []
        if filename not in data[category]:
            data[category].append(filename)
    else:
        uncat = "未分类"
        if uncat not in data:
            data[uncat] = []
        if filename not in data[uncat]:
            data[uncat].append(filename)
    _save(data)


def remove_doc(filename: str):
    data = _load()
    for cat in list(data.keys()):
        data[cat] = [f for f in data[cat] if f != filename]
        if not data[cat]:
            del data[cat]
    _save(data)


def remove_category(category: str):
    data = _load()
    data.pop(category, None)
    _save(data)


def get_tree() -> list[dict]:
    data = _load()
    tree = []
    for cat in sorted(data.keys()):
        files = sorted(data[cat])
        tree.append({"label": cat, "children": [{"label": f} for f in files]})
    return tree


def get_categories() -> list[str]:
    return sorted(_load().keys())


def add_category(category: str):
    data = _load()
    if category not in data:
        data[category] = []
    _save(data)


def sync_from_upload_dir():
    data = _load()
    changed = False
    actual_files = {f.name for f in settings.upload_dir.iterdir()
                    if f.is_file() and f.name != ".gitkeep" and f.name != "docs_index.json" and f.name != "images_index.json"}
    for cat in list(data.keys()):
        before = len(data[cat])
        data[cat] = [f for f in data[cat] if f in actual_files]
        if len(data[cat]) != before:
            changed = True
        if not data[cat]:
            del data[cat]
            changed = True
    indexed_files = set()
    for flist in data.values():
        indexed_files.update(flist)
    for f in actual_files:
        if f not in indexed_files:
            uncat = "未分类"
            if uncat not in data:
                data[uncat] = []
            data[uncat].append(f)
            changed = True
    if changed:
        _save(data)


# ── 图片路径索引 ──


def _load_images_index() -> dict[str, list[str]]:
    if IMAGES_INDEX_FILE.exists():
        try:
            data = json.loads(IMAGES_INDEX_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _save_images_index(data: dict[str, list[str]]):
    IMAGES_INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_images_for_doc(source_file: str, image_paths: list[str]):
    """保存某个源文档对应的所有抽取图片路径（用于删除时清理）。"""
    data = _load_images_index()
    # 只存 basename，因为 extracted_images 是单个平面目录
    basenames = sorted(set(p.name for p in [Path(x) for x in image_paths]))
    if basenames:
        data[source_file] = basenames
    _save_images_index(data)


# ── 完整删除 ──


def delete_document_completely(filename: str) -> dict:
    """删除文档：Qdrant 向量 → 上传文件 → 抽取图片 → JSON 索引"""
    from qdrant_client.models import Filter as QFilter, FieldCondition, MatchValue
    from app.vector_store import _get_client
    import os

    results = {}
    errors = []

    client = _get_client()

    # 1. 先查图片索引（必须在删向量之前获取）
    images_to_delete = []
    images_index = _load_images_index()
    if filename in images_index and isinstance(images_index.get(filename), list):
        images_to_delete = images_index.pop(filename)
        _save_images_index(images_index)
    else:
        # fallback: 从 Qdrant 的 payload images 字段获取
        try:
            scroll_resp = client.scroll(
                collection_name=settings.doc_collection,
                scroll_filter=QFilter(
                    must=[FieldCondition(key="source_file", match=MatchValue(value=filename))]
                ),
                limit=5000,
                with_payload=True,
            )
            seen = set()
            for r in scroll_resp[0]:
                for img_path in r.payload.get("images", []):
                    bn = Path(img_path).name
                    if bn not in seen:
                        seen.add(bn)
                        images_to_delete.append(bn)
        except Exception:
            pass

    # 2. 删除 Qdrant 向量
    try:
        client.delete(
            collection_name=settings.doc_collection,
            points_selector=QFilter(
                must=[FieldCondition(key="source_file", match=MatchValue(value=filename))]
            ),
        )
        results["qdrant"] = "deleted"
    except Exception as e:
        errors.append(f"qdrant: {e}")
        results["qdrant"] = f"error: {e}"

    # 3. 删除上传文件
    fp = settings.upload_dir / filename
    if fp.exists():
        try:
            fp.unlink()
            results["file"] = "deleted"
        except Exception as e:
            errors.append(f"file: {e}")
            results["file"] = f"error: {e}"
    else:
        results["file"] = "not_found"

    # 4. 删除抽取图片
    deleted_count = 0
    if images_to_delete and settings.image_dir.exists():
        for bn in images_to_delete:
            img_path = settings.image_dir / bn
            if img_path.exists():
                try:
                    img_path.unlink()
                    deleted_count += 1
                except Exception as e:
                    errors.append(f"image {bn}: {e}")
    results["images_deleted"] = deleted_count

    # 5. 更新 JSON 索引
    remove_doc(filename)
    results["index"] = "updated"

    return {"status": "ok" if not errors else "partial", "errors": errors, "details": results}
