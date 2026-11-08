import io
import zipfile

import pytest
from conftest import load_dir
from fastapi.testclient import TestClient

from app.security import RateLimiter, issue_token, token_user


@pytest.fixture
def client():
    from app import main

    main.login_limiter.hits.clear()
    with TestClient(main.app) as c:
        yield c


def login(c):
    r = c.post("/api/login", json={"username": "admin", "password": "test-password"})
    assert r.status_code == 200


def test_requires_login(client):
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/projects", json={"language": "python", "files": {"a.py": "x"}}).status_code == 401


def test_bad_password_and_rate_limit(client):
    codes = [client.post("/api/login", json={"username": "admin", "password": "nope"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[-1] == 429


def test_session_expires():
    tok = issue_token("admin")
    assert token_user(tok) == "admin"
    assert token_user(tok, max_age=-1) is None
    assert token_user(tok + "x") is None


def test_rate_limiter_window():
    t = [0.0]
    rl = RateLimiter(2, clock=lambda: t[0])
    assert rl.allow("a") and rl.allow("a") and not rl.allow("a")
    t[0] = 61
    assert rl.allow("a")


def test_project_lifecycle(client):
    login(client)
    r = client.post("/api/projects", json={"name": "bank", "language": "python", "files": load_dir("py_bank")})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    p = client.get(f"/api/projects/{pid}").json()
    assert p["assessment"]["graph"]["entry"] == "m_main"
    assert p["name"] == "bank" and p["jobs"] == []

    m = p["mappings"]
    m["classes"][0]["notes"] = "keep it simple"
    assert client.put(f"/api/projects/{pid}/mappings", json=m).status_code == 200
    assert client.get(f"/api/projects/{pid}").json()["mappings"]["classes"][0]["notes"] == "keep it simple"
    m["classes"][0]["strategy"] = "nonsense"
    assert client.put(f"/api/projects/{pid}/mappings", json=m).status_code == 422

    assert any(x["id"] == pid for x in client.get("/api/projects").json())
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_upload_zip(client):
    login(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in load_dir("cpp_shapes").items():
            z.writestr(f"shapes/{k}", v)
    r = client.post("/api/projects/upload", files={"files": ("shapes.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 200, r.text
    p = client.get(f"/api/projects/{r.json()['id']}").json()
    assert p["language"] == "cpp" and "main.cpp" in p["files"]


def test_upload_rejects_non_source(client):
    login(client)
    r = client.post("/api/projects/upload", files={"files": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 422


def test_examples_endpoint(client):
    login(client)
    ex = client.get("/api/examples").json()
    assert any(e["kind"] == "project" and e["name"] == "cpp shapes" for e in ex)
