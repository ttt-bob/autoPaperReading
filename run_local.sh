#!/bin/bash
# ============================================================
# AutoPaperReading - 本地预览启动脚本
#
# 功能：
#   1. 创建符号链接，使 PDF 可通过 HTTP 访问
#   2. 导出最新论文数据到 docs/papers.json
#   3. 启动本地 HTTP 服务器
#   4. 自动打开浏览器预览
#
# 使用方法：
#   ./run_local.sh          # 正常启动
#   ./run_local.sh --port=9000  # 指定端口
#   ./run_local.sh --no-open      # 不自动打开浏览器
#
# 注意事项：
#   - PDF 离线阅读：确保 PDF 已下载到 data/pdfs/{category}/*.pdf
#   - 无网络时：arXiv 链接不可用，但本地 PDF 链接仍可用
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- 配置 ---
PORT=""
NO_OPEN="false"

# 解析参数
for arg in "$@"; do
    case "$arg" in
        --port=*)
            PORT="${arg#*=}"
            ;;
        --no-open)
            NO_OPEN="true"
            ;;
        --help|-h)
            echo "用法: $0 [--port=端口号] [--no-open]"
            echo "  --port=8083    指定服务端口（默认 8083）"
            echo "  --no-open      不自动打开浏览器"
            echo "  --help         显示帮助"
            exit 0
            ;;
    esac
done

# 默认端口
PORT="${PORT:-8083}"

echo ""
echo "========================================"
echo "  AutoPaperReading - 本地预览"
echo "========================================"
echo ""

# ============================================================
# 步骤 1: 创建符号链接（使本地 PDF 可通过 HTTP 访问）
# ============================================================
echo "[1/4] 检查数据目录..."

DATA_SYMLINK="$SCRIPT_DIR/docs/data"
if [ -L "$DATA_SYMLINK" ]; then
    echo "      ✅ 符号链接已存在: docs/data -> ../data"
elif [ -d "$DATA_SYMLINK" ]; then
    echo "      ⚠️  docs/data 是目录而非符号链接"
    echo "      请手动删除该目录后重新运行: rm -rf docs/data"
else
    ln -s "$SCRIPT_DIR/data" "$DATA_SYMLINK" && echo "      ✅ 创建符号链接: docs/data -> ../data"
fi

# ============================================================
# 步骤 2: 导出论文数据
# ============================================================
echo ""
echo "[2/4] 导出论文数据..."
if [ -f "papers.db" ] || [ -f "data/papers.db" ]; then
    uv run python jobs/export_papers.py
    echo "      ✅ 导出完成"
else
    echo "      ⚠️  未找到数据库，跳过导出（可能没有论文数据）"
fi

# ============================================================
# 步骤 3: 启动本地服务器
# ============================================================
echo ""
echo "[3/4] 启动本地服务器..."
echo "      📂 静态文件目录: docs/"
echo "      🌐 端口: $PORT"

# 检测端口是否被占用
if lsof -Pi ":$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "      ⚠️  端口 $PORT 已被占用，尝试端口 $((PORT+1))"
    PORT=$((PORT+1))
fi

# 启动 Python HTTP 服务器
cd "$SCRIPT_DIR/docs"
python3 -m http.server "$PORT" --bind 127.0.0.1 &
SERVER_PID=$!

cd "$SCRIPT_DIR"

# 等待服务器启动
sleep 1

# 检查服务器是否成功启动
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo ""
    echo "❌ 服务器启动失败，请检查端口是否被占用"
    exit 1
fi

echo "      ✅ 服务器已启动 (PID: $SERVER_PID)"

# ============================================================
# 步骤 4: 打开浏览器
# ============================================================
echo ""
echo "[4/4] 打开浏览器..."

if [ "$NO_OPEN" = "false" ]; then
    if command -v open >/dev/null 2>&1; then
        sleep 0.5
        open "http://localhost:$PORT"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://localhost:$PORT"
    else
        echo "      ℹ️  请手动打开浏览器访问: http://localhost:$PORT"
    fi
else
    echo "      ℹ️  已跳过自动打开浏览器"
fi

echo ""
echo "========================================"
echo "  🎉 本地预览已就绪"
echo ""
echo "  访问地址: http://localhost:$PORT"
echo "  关闭服务: kill $SERVER_PID"
echo ""
echo "  📄 PDF 离线阅读:"
echo "     - 本地 PDF 路径: data/pdfs/{category}/{paper_id}.pdf"
echo "     - 前端会自动显示「本地 PDF」链接（如果文件存在）"
echo "     - 无网络时，arXiv 链接不可用，本地 PDF 仍可用"
echo "========================================"
echo ""
echo "按 Ctrl+C 停止服务器"

# 等待信号
trap "echo ''; echo '正在停止服务器...'; kill $SERVER_PID 2>/dev/null; exit 0" INT TERM

wait $SERVER_PID
