"""/health 存活探针单测（TestClient，不依赖 Milvus/MySQL 运行）"""
from fastapi.testclient import TestClient

from interviewace.backend.main import app


def test_health_ok():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_metrics_endpoint():
    with TestClient(app) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text


def test_auth_required_on_domains():
    with TestClient(app) as client:
        resp = client.get("/domains")
    assert resp.status_code == 401
