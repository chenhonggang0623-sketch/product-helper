#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 读取端口
SERVER_PORT=$(grep -E '^SERVER_PORT' config.toml 2>/dev/null | head -1 | sed 's/.*=[[:space:]]*//' | tr -d '"'"'" )
SERVER_PORT=${SERVER_PORT:-8000}

PID=$(lsof -ti:"$SERVER_PORT" 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "正在停止服务 (PID: $PID) on port $SERVER_PORT..."
    kill "$PID" 2>/dev/null || true
    sleep 1
    echo "服务已停止"
else
    echo "端口 $SERVER_PORT 上无运行中的服务"
fi
