#!/bin/bash
# Personal OS V2.0 启动脚本
cd "$(dirname "$0")"

# 配置（可通过环境变量覆盖）
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5000}"
MODE="${MODE:-dev}"  # dev 或 prod

echo "================================"
echo "  Personal OS V2.0 启动中..."
echo "  模式: $MODE"
echo "================================"

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3"
    exit 1
fi

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创��虚拟环境..."
    python3 -m venv venv
fi

# 安装依赖
echo "📦 安装依赖..."
./venv/bin/pip install -q flask gunicorn

# 初始化数据库
echo "🗄️  初始化数据库..."
./venv/bin/python models.py

# 启动应用
echo "🚀 启动应用..."
echo "================================"
echo "  访问地址: http://127.0.0.1:$PORT"
echo "  局域网:   http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'your-ip'):$PORT"
echo "  按 Ctrl+C 停止"
echo "================================"

if [ "$MODE" = "prod" ]; then
    # 生产模式：Gunicorn
    ./venv/bin/gunicorn -w 4 -b "$HOST:$PORT" app:app
else
    # 开发模式：Flask debug
    ./venv/bin/python app.py
fi
