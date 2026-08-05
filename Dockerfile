# AXIS Personal OS 3.0 - Docker 镜像
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . /app

# 数据卷（持久化数据库）
VOLUME ["/data"]

# 默认环境变量
ENV DB_PATH=/data/personal_os.db \
    SECRET_KEY=change-me-in-production \
    HOST=0.0.0.0 \
    PORT=5000 \
    PYTHONUNBUFFERED=1

EXPOSE 5000

# 生产环境使用 gunicorn
CMD ["sh", "-c", "exec gunicorn --bind ${HOST}:${PORT} --workers 1 --threads 4 --timeout 120 app:app"]
