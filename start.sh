#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  Product Helper - 产品文档智能问答助手"
echo "========================================="
echo ""

# ── 1. 检查配置文件 ──
if [ ! -f config.toml ]; then
    echo "[!] 未找到 config.toml"
    echo "    请先复制 config.toml.example 为 config.toml 并修改参数"
    exit 1
fi

# ── 2. 检查 Python 依赖 ──
echo "[1/3] 检查依赖..."
if ! uv sync --quiet 2>/dev/null; then
    echo "    安装依赖..."
    uv sync
fi

# ── 3. 检查 Qdrant 是否运行 ──
# 从 config.toml 读取 Qdrant 端口
QDRANT_PORT=$(grep -E '^QDRANT_PORT' config.toml 2>/dev/null | head -1 | sed 's/.*=[[:space:]]*//' | tr -d '"'"'" )
QDRANT_PORT=${QDRANT_PORT:-6333}
if ! command -v nc &>/dev/null; then
    echo "    跳过 Qdrant 连通性检查（未安装 nc）"
else
    if nc -z localhost "$QDRANT_PORT" 2>/dev/null; then
        echo "    Qdrant 服务正常 (localhost:$QDRANT_PORT)"
    else
        echo "[!] Qdrant 服务未运行 (localhost:$QDRANT_PORT)"
        echo "    请先启动 Qdrant"
        exit 1
    fi
fi

# ── 4. 读取服务端口并启动 ──
SERVER_PORT=$(grep -E '^SERVER_PORT' config.toml 2>/dev/null | head -1 | sed 's/.*=[[:space:]]*//' | tr -d '"'"'" )
SERVER_PORT=${SERVER_PORT:-8000}

echo "[2/3] 启动服务 (port $SERVER_PORT)..."
nohup uv run python -m uvicorn main:app --host 0.0.0.0 --port "$SERVER_PORT" > /tmp/product-helper.log 2>&1 &
PID=$!
echo "    PID: $PID"

# ── 5. 等待服务启动 ──
echo "[3/3] 等待服务就绪..."
for i in $(seq 1 15); do
    if command -v nc &>/dev/null; then
        if nc -z localhost "$SERVER_PORT" 2>/dev/null; then
            echo "    服务已就绪"
            break
        fi
    else
        # fallback: curl
        if curl -sS "http://localhost:$SERVER_PORT/" >/dev/null 2>&1; then
            echo "    服务已就绪"
            break
        fi
    fi
    sleep 1
done

echo ""
echo "========================================="
echo "  服务已启动"
echo "  配置文件: config.toml"
echo "  访问地址: http://localhost:$SERVER_PORT"
echo "  停止服务: ./stop.sh"
echo "========================================="
