"""pytest 共享配置：注入测试环境变量 + 项目根目录入 sys.path

config.py 在 import 时读环境变量（MYSQL_PORT 等缺失会直接抛错），
所以必须在任何 interviewace 模块 import 之前设置。
"""
import os
import sys
from pathlib import Path

# 项目根目录入 sys.path（interviewace 包与 data_pipeline 包都可 import）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 测试环境变量（dummy 值，单测不连真实依赖）
os.environ.setdefault("QWEN_API_KEY", "test-dummy-key")
os.environ.setdefault("QWEN_BASE_URL", "https://example.com/v1")
os.environ.setdefault("QWEN_MODEL", "qwen-test")
os.environ.setdefault("QWEN_EMBEDDING_MODEL", "qwen-embedding-test")
os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "root")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_DATABASE", "interviewace_test")
os.environ.setdefault("MILVUS_HOST", "127.0.0.1")
os.environ.setdefault("MILVUS_PORT", "19530")
