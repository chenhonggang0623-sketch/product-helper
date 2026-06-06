import uuid
import os
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import settings
from app.document_processor import process_document
from app.vector_store import (
    add_document_chunks,
    ensure_doc_collection,
    ensure_session_collection,
    delete_category as delete_category_from_qdrant,
)
from app.llm_service import UNKNOWN_ANSWER, ask
from app.docs_index import (
    add_doc as index_add_doc,
    remove_doc as index_remove_doc,
    remove_category as index_remove_category,
    get_tree,
    get_categories,
    add_category as index_add_category,
    sync_from_upload_dir,
    record_images_for_doc,
)


# ─── Lifespan ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_doc_collection()
    ensure_session_collection()
    sync_from_upload_dir()  # 启动时同步 JSON 索引与实际文件
    yield


app = FastAPI(title="Product Document QA", lifespan=lifespan)


# ─── Static files ──────────────────────────────────────

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

IMAGE_DIR = settings.image_dir
IMAGE_DIR.mkdir(parents=True, exist_ok=True)


# ─── Pydantic models ───────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str
    category: str = ""


# ─── API Routes ────────────────────────────────────────


@app.get("/api/session")
def create_session():
    return {"session_id": str(uuid.uuid4())}


@app.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    from app.vector_store import delete_session as delete_from_store
    try:
        delete_from_store(session_id)
    except Exception:
        pass
    return {"status": "ok"}


@app.get("/api/docs-tree")
def docs_tree():
    """返回文档分类树（基于 JSON 索引）"""
    return {"tree": get_tree()}


@app.get("/api/categories")
def get_categories_api():
    """返回所有分类列表（基于 JSON 索引）"""
    cats = get_categories()
    return {"categories": cats}


@app.post("/api/category")
def add_category_api(category: str = Form(default="")):
    """新增一个空分类"""
    name = category.strip()
    if not name:
        return JSONResponse(status_code=400, content={"status": "error", "message": "分类名称不能为空"})
    index_add_category(name)
    return {"status": "ok", "message": f"分类 '{name}' 已新增", "categories": get_categories()}


@app.delete("/api/category/{category}")
def remove_category_api(category: str):
    """删除一个分类（仅索引，不删文件）"""
    index_remove_category(category)
    delete_category_from_qdrant(category)
    return {"status": "ok", "message": f"分类 '{category}' 已删除", "tree": get_tree()}


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(default=""),
):
    if not file.filename:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "没有选择文件"},
        )

    filename = file.filename
    dest = settings.upload_dir / filename
    content = await file.read()
    dest.write_bytes(content)

    try:
        chunks = process_document(str(dest))
        add_document_chunks(chunks, category=category)
        # 写入 JSON 索引
        index_add_doc(filename, category)
        # 记录抽取的图片路径
        all_images = list(set(
            img for c in chunks for img in c.get("images", [])
        ))
        if all_images:
            record_images_for_doc(filename, all_images)
        cat_label = f"（分类：{category}）" if category else "（未分类）"
        return {
            "status": "ok",
            "message": f"文档 '{filename}' 处理成功，共 {len(chunks)} 个片段已入库{cat_label}",
            "tree": get_tree(),
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"处理失败：{str(e)}",
                "tree": get_tree(),
            },
        )


@app.delete("/api/document/{filename}")
def delete_document(filename: str):
    """删除文档：Qdrant 向量 + 上传文件 + 抽取图片 + JSON 索引"""
    from urllib.parse import unquote
    fname = unquote(filename)
    import sys
    from app.docs_index import delete_document_completely
    result = delete_document_completely(fname)
    if result.get("status") == "ok" or result.get("status") == "partial":
        return {"status": "ok", "message": f"文档 '{fname}' 已删除", "tree": get_tree()}
    else:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"删除失败：{', '.join(result.get('errors',[]))}",
                "tree": get_tree(),
            }
        )


@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        result = ask(req.session_id, req.message, category=req.category)
        image_urls = []
        for img_path in result.get("images", []):
            try:
                filename = os.path.basename(img_path)
                image_urls.append(f"/images/{filename}")
            except Exception:
                pass
        return {
            "answer": result.get("answer", ""),
            "images": image_urls,
            "sources": result.get("sources", []),
            "has_images": result.get("has_images", False),
        }
    except Exception:
        return {
            "answer": UNKNOWN_ANSWER,
            "images": [],
            "sources": [],
            "has_images": False,
        }


# ─── Serve extracted images ────────────────────────────

app.mount("/images", StaticFiles(directory=str(IMAGE_DIR)), name="images")


# ─── Serve frontend ────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend not found</h1>")


# ─── Entry point ───────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=False,
    )
