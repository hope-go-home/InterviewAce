"""pytest 共享配置：优先读真实 .env，缺失项才补测试占位值 + 项目根目录入 sys.path

顺序很重要：config.py 在 import 时读环境变量，且 load_dotenv() 不会覆盖
已存在的环境变量。所以这里先手工加载 .env（拿到真实配置，集成测试才能连上库），
再对仍然缺失的项补占位值（保证纯单测在没有 .env 时也能 import）。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 1) 先加载真实 .env（不覆盖已有环境变量）
try:
    from dotenv import dotenv_values
    for k, v in (dotenv_values(ROOT / ".env") or {}).items():
        if v is not None and k not in os.environ:
            os.environ[k] = v
except Exception:
    pass

# 2) 仍然缺失的项 → 测试占位值（单测不连真实依赖时用）
_PLACEHOLDERS = {
    "QWEN_API_KEY": "test-dummy-key",
    "QWEN_BASE_URL": "https://example.com/v1",
    "QWEN_MODEL": "qwen-test",
    "QWEN_EMBEDDING_MODEL": "qwen-embedding-test",
    "MYSQL_HOST": "127.0.0.1",
    "MYSQL_PORT": "3306",
    "MYSQL_USER": "root",
    "MYSQL_PASSWORD": "test",
    "MYSQL_DATABASE": "interviewace_test",
    "MILVUS_HOST": "127.0.0.1",
    "MILVUS_PORT": "19530",
}
for k, v in _PLACEHOLDERS.items():
    os.environ.setdefault(k, v)

