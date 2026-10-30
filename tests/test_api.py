"""API surface: source registry validation, auto-pool clamps, settings hygiene.

TestClient reports its client host as "testclient", which the loopback bypass
does not trust, so these tests sign in like a remote caller would.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        login = c.post("/api/login",
                       data={"username": "admin", "password": "test-pass"})
        assert login.status_code == 200, login.text
        yield c


def test_health_endpoints(client):
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/gateway").status_code == 200
    assert client.get("/api/autopool").status_code == 200


def test_sources_listed(client):
    body = client.get("/api/sources").json()
    assert isinstance(body["items"], list)
    assert len(body["items"]) >= 20          # built-in gates are seeded
    assert all({"url", "protocol", "enabled"} <= set(i) for i in body["items"])


def test_source_rejects_bad_scheme(client):
    r = client.post("/api/sources", json={"url": "ftp://x/y.txt", "protocol": "http"})
    assert r.status_code == 400


def test_source_rejects_bad_protocol(client):
    r = client.post("/api/sources", json={"url": "https://example.com/a.txt",
                                          "protocol": "socks9"})
    assert r.status_code == 400


def test_autopool_clamps_and_persists(client):
    r = client.post("/api/autopool", json={"min_alive": 300, "min_tls": 50,
                                           "interval_min": 15, "target": 700,
                                           "enabled": True})
    assert r.status_code == 200
    body = r.json()
    assert body["min_alive"] == 300 and body["target"] == 700

    again = client.get("/api/autopool").json()
    assert again["min_alive"] == 300 and again["min_tls"] == 50


def test_gateway_settings_ignores_unknown_keys(client):
    before = client.get("/api/gateway").json()
    r = client.post("/api/gateway/settings",
                    json={"retries": 3, "not_a_setting": "boom"})
    assert r.status_code == 200
    after = r.json()
    assert "not_a_setting" not in after
    assert after["retries"] == 3
    assert before["socks_port"] == after["socks_port"]


def test_gateway_settings_caps_latency_budget(client):
    body = client.post("/api/gateway/settings",
                       json={"deadline": 2.5, "first_byte_timeout": 1.5,
                             "idle_timeout": 2.0}).json()
    assert body["deadline"] == 2.5
    assert body["first_byte_timeout"] == 1.5
    assert body["idle_timeout"] == 2.0
