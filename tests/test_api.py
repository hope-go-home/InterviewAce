"""集成测试：打真实 HTTP 接口（需要 MySQL/Milvus 可用）

与单元测试的区别：这里走完整的 FastAPI 请求链路（鉴权 → 路由 → 服务 → 存储），
依赖不可用时自动 skip，不阻塞纯单测的 CI。

跑法：pytest tests/test_api.py -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _deps_ready() -> bool:
    """Milvus + MySQL 是否可用（不可用就跳过集成测试）"""
    try:
        from pymilvus import connections, utility
        from interviewace.backend.config import MILVUS_HOST, MILVUS_PORT
        connections.connect(alias="ittest", host=MILVUS_HOST, port=MILVUS_PORT, timeout=3)
        ok = utility.has_collection("interview_kb", using="ittest")
        connections.disconnect("ittest")
        if not ok:
            return False
    except Exception:
        return False
    try:
        from sqlalchemy import text

        from interviewace.backend.database.mysql import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(not _deps_ready(), reason="需要 Milvus/MySQL 可用")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from interviewace.backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def token(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    if r.status_code != 200:
        pytest.skip("默认账号不可用，跳过需要鉴权的集成测试")
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- 健康与鉴权 ----------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ready_reports_deps(client):
    r = client.get("/ready")
    assert r.status_code in (200, 503)
    assert "checks" in r.json()


def test_protected_endpoint_requires_token(client):
    assert client.get("/bank/stats").status_code == 401


def test_login_and_me(client, token):
    r = client.get("/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["username"]


# ---------------- 题库 ----------------

def test_bank_stats(client, token):
    r = client.get("/bank/stats", headers=_auth(token))
    assert r.status_code == 200
    d = r.json()
    assert d["total"] > 0
    assert isinstance(d["domains"], list) and len(d["domains"]) >= 5


def test_bank_questions_pagination(client, token):
    r = client.get("/bank/questions", params={"page": 1, "page_size": 5},
                   headers=_auth(token))
    assert r.status_code == 200
    d = r.json()
    assert len(d["items"]) <= 5


# ---------------- 练习 ----------------

def test_practice_batch_returns_items(client, token):
    r = client.get("/practice/batch", params={"n": 5}, headers=_auth(token))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    assert all(it.get("title") for it in items)


def test_practice_next_then_records(client, token):
    r = client.get("/practice/next", headers=_auth(token))
    if r.status_code == 404:
        pytest.skip("没有可用题目")
    assert r.status_code == 200
    assert r.json()["title"]

    rec = client.get("/practice/records", headers=_auth(token))
    assert rec.status_code == 200 and "records" in rec.json()


# ---------------- 缓存 / 并发 ----------------

def test_cache_stats(client, token):
    r = client.get("/cache/stats", headers=_auth(token))
    assert r.status_code == 200
    d = r.json()
    assert d["heavy_concurrency_limit"] >= 1
    assert any(c["name"] == "dense_embedding" for c in d["caches"])


def test_domain_stats(client, token):
    r = client.get("/domains", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["total"] > 0


# ---------------- 长期记忆 ----------------

def test_memory_context_builds(client, token):
    """学习画像能被构造出来（无练习记录时为空串，不报错）"""
    from interviewace.backend.database import mysql as m
    ctx = m.build_memory_context(1)
    assert isinstance(ctx, str)
