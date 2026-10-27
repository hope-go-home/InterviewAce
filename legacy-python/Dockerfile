# 后端镜像：FastAPI + 检索链路（bge-m3 / bge-reranker 在运行时从 HF 缓存加载）
FROM python:3.11-slim

WORKDIR /app

# 基础依赖（PyMuPDF 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgl1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 先装依赖（利用层缓存）；测试依赖在 requirements 里，镜像里不装
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pytest httpx

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fs http://localhost:8002/health || exit 1

# 单 worker：本地重排模型较重，多 worker 会重复占用内存
CMD ["uvicorn", "interviewace.backend.main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
