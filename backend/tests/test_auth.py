from app import deps


def test_signup_returns_session_and_me_works(client, signed_up):
    headers, user = signed_up()
    assert user["email"] == "ada@example.com"
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["email"] == "ada@example.com"


def test_protected_routes_require_a_token(client):
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/quota").status_code == 401
    assert client.post("/api/chat", json={"question": "hi", "document_id": "default-document"}).status_code == 401


def test_duplicate_email_is_rejected(client, signed_up):
    signed_up("dup@example.com")
    response = client.post("/api/auth/signup", json={"email": "DUP@example.com", "password": "another-pass"})
    assert response.status_code == 409


def test_login_and_wrong_password(client, signed_up):
    signed_up("grace@example.com", "a-strong-pass")
    ok = client.post("/api/auth/login", json={"email": "Grace@Example.com", "password": "a-strong-pass"})
    assert ok.status_code == 200 and ok.json()["token"]
    bad = client.post("/api/auth/login", json={"email": "grace@example.com", "password": "wrong-pass"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "Invalid email or password."


def test_logout_revokes_the_session(client, signed_up):
    headers, _ = signed_up("linus@example.com")
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_password_length_and_email_format_are_validated(client):
    assert client.post("/api/auth/signup", json={"email": "a@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/auth/signup", json={"email": "not-an-email", "password": "long-enough"}).status_code == 422


def test_repeated_failed_logins_are_throttled(client, signed_up, monkeypatch):
    signed_up("target@example.com", "a-strong-pass")
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "target@example.com", "password": "nope-nope"},
                    headers={"X-Forwarded-For": "203.0.113.9"})
    blocked = client.post("/api/auth/login", json={"email": "target@example.com", "password": "a-strong-pass"},
                          headers={"X-Forwarded-For": "203.0.113.9"})
    assert blocked.status_code == 429
