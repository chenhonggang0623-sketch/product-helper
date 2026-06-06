# Product Helper — 产品文档智能问答助手

基于 RAG（检索增强生成）架构的企业级产品文档问答工具。支持上传产品手册、技术文档、Excel 参数表等多种格式，通过 LLM 进行智能问答，自动展示相关图片并标注来源。

---

## 目录

- [功能概览](#功能概览)
- [系统架构](#系统架构)
- [前置依赖](#前置依赖)
- [快速开始](#快速开始)
- [配置文件详解](#配置文件详解)
- [启动与停止](#启动与停止)
- [使用说明](#使用说明)
- [API 接口](#api-接口)
- [数据存储说明](#数据存储说明)
- [常见问题](#常见问题)

---

## 功能概览

| 功能 | 说明 |
|---|---|
| 文档上传 | 支持 `.txt`、`.md`、`.pdf`、`.docx`、`.xlsx` / `.xls` |
| 智能问答 | 基于文档上下文 + 多模态 LLM 回答，附带相关图片 |
| 多轮对话 | 每个会话独立保存对话历史，支持连续提问 |
| 知识库分类隔离 | 文档可按产品分类上传，提问时按分类过滤检索 |
| 图片识别 | PDF / Word 中的图片自动提取并发送给多模态 LLM |
| 来源标注 | 回答中包含文档名称、页码 / 片段位置 |
| 未知问题兜底 | 检索不到相关内容时回复固定提示，不编造答案 |
| 会话管理 | 新建 / 删除会话，每个会话独立存储记忆 |
| 文档管理 | 树形展示分类结构，支持删除文档（同步清理向量、文件、图片） |

---

## 系统架构

```
用户浏览器 (HTML)  ──HTTP──>  FastAPI  (Python 3.14)
                                  │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
               Qdrant 向量库    LLM (OpenAI     Embedding
               (本地 :6333)     兼容 API)        (本地调用)
                                    │
                              阿里千问 VL /
                              qwen-vl-max
```

**数据流：**

1. 上传文档 → `document_processor.py` 解析文本和图片 → `vector_store.py` 生成向量存入 Qdrant
2. 用户提问 → `llm_service.py` 搜索 Qdrant 获取相关段落和图片 → 构造 Prompt 发送给 LLM
3. LLM 返回 → 保存到会话历史 → 返回给前端展示（含图片 URL 和来源）

---

## 前置依赖

- **Python 3.14+**（项目使用 `uv` 管理虚拟环境）
- **Qdrant** 向量数据库（本地运行，默认端口 6333）
- **一个兼容 OpenAI API 的多模态 LLM**（默认使用阿里千问 VL-Max）

### 安装 Qdrant

```bash
# macOS（Homebrew）
brew install qdrant/tap/qdrant
brew services start qdrant

# Docker
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant
```

验证 Qdrant 是否运行：

```bash
curl http://localhost:6333
# 返回 {"title":"qdrant - vector search"} 表示正常
```

---

## 快速开始

### 1. 克隆 / 进入项目目录

```bash
cd product-helper
```

### 2. 安装依赖

使用 `uv` 自动创建虚拟环境并安装依赖：

```bash
uv sync
```

### 3. 修改配置

编辑项目根目录下的 `config.toml`，填写你的 LLM API Key：

```toml
LLM_API_KEY = "sk-你的key"
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = "qwen-vl-max"
```

### 4. 启动服务

```bash
./start.sh
```

### 5. 打开浏览器

访问 `http://localhost:8000`

---

## 配置文件详解

所有配置集中在项目根目录的 `config.toml` 中。支持三种配置来源（优先级从高到低）：

1. **环境变量**（如 `export LLM_API_KEY=xxx`）
2. **`config.toml`** 中的值
3. **代码中的默认值**

### 1. LLM 配置

```toml
LLM_API_KEY  = "sk-xxx"
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL    = "qwen-vl-max"
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `LLM_API_KEY` | 大语言模型的 API Key | — |
| `LLM_BASE_URL` | API 地址（兼容 OpenAI 的任意服务） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_MODEL` | 模型名称，必须支持多模态（图片识别） | `qwen-vl-max` |

**支持其他模型：**

| 服务商 | LLM_BASE_URL | 模型示例 |
|---|---|---|
| 阿里百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-max`, `qwen-vl-plus` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| 本地 ollama | `http://localhost:11434/v1` | `llava` |

### 2. Embedding 配置

```toml
EMBEDDING_API_KEY      = "sk-xxx"
EMBEDDING_BASE_URL     = "https://dashscope.aliyuncs.com/compatible-mode/v1"
EMBEDDING_MODEL        = "text-embedding-v3"
EMBEDDING_DIMENSIONS   = 1024
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `EMBEDDING_API_KEY` | 向量化模型的 API Key | 同上 |
| `EMBEDDING_BASE_URL` | 向量化 API 地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `EMBEDDING_MODEL` | 向量化模型名 | `text-embedding-v3` |
| `EMBEDDING_DIMENSIONS` | 向量维度（必须与模型一致） | `1024` |

### 3. Qdrant 配置

```toml
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `QDRANT_HOST` | Qdrant 服务地址 | `localhost` |
| `QDRANT_PORT` | Qdrant 服务端口 | `6333` |

### 4. 数据目录

```toml
UPLOAD_DIR        = "uploads"
IMAGE_DIR         = "extracted_images"
DOC_COLLECTION    = "documents"
SESSION_COLLECTION = "conversations"
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `UPLOAD_DIR` | 上传的原文档存放目录 | `uploads` |
| `IMAGE_DIR` | PDF / Word 中提取的图片存放目录 | `extracted_images` |
| `DOC_COLLECTION` | Qdrant 中文档向量的集合名称 | `documents` |
| `SESSION_COLLECTION` | Qdrant 中会话记忆的集合名称 | `conversations` |

### 5. 文档分块参数

```toml
CHUNK_SIZE    = 500
CHUNK_OVERLAP = 50
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `CHUNK_SIZE` | 文档切分的段落大小（字符数） | `500` |
| `CHUNK_OVERLAP` | 段落之间的重叠字符数（保持上下文连贯） | `50` |

### 6. RAG 上下文窗口参数

```toml
RAG_TOP_K                = 8
RAG_MIN_SCORE            = 0.35
RAG_MAX_HISTORY_ROUNDS   = 10
RAG_MAX_IMAGES           = 5
RAG_MAX_TOKENS           = 4096
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `RAG_TOP_K` | 每次检索返回的最大段落数（越多上下文越丰富，但也越占用 token） | `8` |
| `RAG_MIN_SCORE` | 最低相关度阈值。低于此值的检索结果不进入 LLM 上下文，直接回复"不清楚" | `0.35` |
| `RAG_MAX_HISTORY_ROUNDS` | 每次提问时发给 LLM 的最近 N 轮对话记录 | `10` |
| `RAG_MAX_IMAGES` | 每次提问附带的最大图片数（超过部分舍弃） | `5` |
| `RAG_MAX_TOKENS` | LLM 回答的最大 token 数 | `4096` |

**调整建议：**
- 文档内容密集时，适当降低 `CHUNK_SIZE` 和 `RAG_TOP_K`，避免超出模型上下文限制
- 图片多时降低 `RAG_MAX_IMAGES`
- 希望更严格的控制编造时，适当调高 `RAG_MIN_SCORE`（如 `0.45`）

### 7. 服务启动参数

```toml
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `SERVER_HOST` | 服务监听地址（`0.0.0.0` 允许局域网访问） | `0.0.0.0` |
| `SERVER_PORT` | 服务的 HTTP 端口 | `8000` |

---

## 启动与停止

### 启动

```bash
./start.sh
```

启动脚本会自动完成：
1. 检查 `config.toml` 是否存在
2. 执行 `uv sync` 确保依赖已安装
3. 检查 Qdrant 服务是否运行
4. 在后台启动 FastAPI 服务并等待就绪
5. 打印访问地址

### 停止

```bash
./stop.sh
```

会查找处于 `SERVER_PORT` 端口的进程并终止。

### 手动启动（调试）

```bash
uv run python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 查看当前配置

```bash
uv run python -m app.config
```

打印当前生效的全部配置项（含默认值）。

---

## 使用说明

### 文档上传

1. 打开页面右侧的 **上传文档** 区域
2. 选择文件（支持 `.txt` / `.md` / `.pdf` / `.docx` / `.xlsx` / `.xls`）
3. 在分类下拉中选择所属产品分类（或选择"不指定分类"归入"未分类"）
4. 单击 **上传并处理**
5. 上传成功后，右侧文档树会自动更新，顶部过滤下拉也会刷新

### 创建分类

- 在分类下拉中选择 **+ 新增分类**，输入名称即可创建一个空的分类
- 分类数据保存在 `uploads/docs_index.json` 中，可被所有用户共享

### 智能问答

1. 在页面顶部的 **知识库过滤** 下拉选择目标产品分类（或"全部知识库"）
2. 在输入框中输入问题，按 Enter 或点击发送
3. 系统自动检索相关文档段落和图片，生成图文回答
4. 回答底部标注信息来源（文档名称 + 页码 / 片段位置）

### 会话管理

- **新建会话**：点击顶部的 `+` 按钮
- **切换会话**：点击对应的会话标签页
- **删除会话**：点击当前会话标签的 `×` 按钮或 `🗑 删除` 按钮
- 每个会话的对话历史存储在 Qdrant 中，删除时同步清理

### 删除文档

- 在右侧文档树中，点击文档后面的 `✕` 按钮
- 系统会同步删除：Qdrant 向量数据 → 本地上传文件 → 提取的图片 → JSON 索引

### 删除分类

- 在右侧文档树中，点击分类名后的 `🗑` 按钮
- 会删除该分类下的所有文档向量和索引（原始文件需要单独删除）

---

## API 接口

| 方法 | 路由 | 说明 |
|---|---|---|
| `GET` | `/` | 返回前端页面 |
| `GET` | `/api/session` | 创建新会话，返回 `session_id` |
| `DELETE` | `/api/session/{id}` | 删除指定会话的聊天记录 |
| `GET` | `/api/docs-tree` | 返回文档分类树（带文件列表） |
| `GET` | `/api/categories` | 返回所有分类名称列表 |
| `POST` | `/api/category` | 新增空分类，参数 `category`（FormData） |
| `DELETE` | `/api/category/{name}` | 删除分类及所有文档向量 |
| `POST` | `/api/upload` | 上传文档，参数 `file` + `category`（可选） |
| `DELETE` | `/api/document/{filename}` | 删除文档（向量 + 文件 + 图片 + 索引） |
| `POST` | `/api/chat` | 聊天请求，Body: `{"session_id","message","category"}` |

### 聊天请求示例

```bash
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": "xxx-xxx-xxx",
    "message": "如何发布需求？",
    "category": "产品A"
  }'
```

---

## 数据存储说明

| 数据 | 存储位置 | 持久化方式 |
|---|---|---|
| 上传的原始文档 | `uploads/` 目录 | 磁盘文件 |
| 抽取的文档图片 | `extracted_images/` 目录 | 磁盘文件 |
| 文档向量 | Qdrant `documents` collection | Qdrant 数据库 |
| 会话记忆 | Qdrant `conversations` collection | Qdrant 数据库 |
| 分类和文档索引 | `uploads/docs_index.json` | JSON 文件 |
| 文档图片索引 | `uploads/images_index.json` | JSON 文件 |
| LLM API Key | `config.toml` | 配置文件 |

**Qdrant 中的数据：**
- 每次启动时自动创建需要的 collection
- 删除文档时同步清理向量数据
- 会话删除时同步清理记忆数据
- 同名文档重新上传时自动替换旧向量（按文件名 + 分类匹配）

---

## 常见问题

**Q: 启动提示 Qdrant 未运行？**  
A: 执行 `brew services start qdrant` 或 `docker start qdrant` 启动 Qdrant，再重新运行 `./start.sh`。

**Q: 同名文档上传多次会怎样？**  
A: 每次上传同名文档时自动删除旧的向量数据再入库，只保留最新版本。本地的 `uploads/` 文件会被覆盖。

**Q: 多人使用能隔离吗？**  
A: 会话按 `session_id` 隔离，每人有自己的聊天窗口；文档知识库默认共享。上传时按**分类**隔离，不同产品分类之间的文档互不可见。

**Q: 为什么问的问题总回复"不清楚"？**  
A: 可能有几种原因：① 未上传相关文档；② 提问时知识库过滤选错了分类；③ 检索结果的相关度低于 `RAG_MIN_SCORE`；④ 文档内容与问题不匹配。

**Q: 如何查看当前全部配置？**  
A: 执行 `uv run python -m app.config`。

**Q: 如何清空知识库重新开始？**  
A: 执行以下命令清空 Qdrant 和本地文件：
```bash
curl -X DELETE http://localhost:6333/collections/documents
curl -X DELETE http://localhost:6333/collections/conversations
rm -f uploads/* extracted_images/* uploads/docs_index.json uploads/images_index.json
```
然后重启服务。

**Q: 如何修改端口？**  
A: 修改 `config.toml` 中的 `SERVER_PORT = 8000`，然后 `./stop.sh && ./start.sh` 重启。

---

## 项目结构

```
product-helper/
├── config.toml         # 主配置文件（用户修改）
├── start.sh            # 启动脚本
├── stop.sh             # 停止脚本
├── pyproject.toml      # Python 依赖声明
├── main.py             # FastAPI 服务入口 + API 路由
├── app/
│   ├── config.py       # 配置读取层（支持 config.toml / 环境变量）
│   ├── llm_service.py  # LLM 调用 + Prompt 组装 + 未知问题兜底
│   ├── vector_store.py # Qdrant 读写 + 文档/会话管理
│   ├── docs_index.py   # JSON 文件管理的分类和图片索引
│   ├── document_processor.py  # 文档解析（txt/md/pdf/docx/xlsx）
│   ├── chunker.py      # 文本分块 + 图片关联
│   ├── embedder.py     # Embedding 调用
├── static/
│   └── index.html      # 前端页面
├── uploads/            # 上传的文档存放目录
├── extracted_images/   # 从文档中提取的图片存放目录
├── scripts/            # 辅助脚本
```
