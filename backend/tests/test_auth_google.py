"""Google sign-in -> first-party session tokens."""
from app.auth import mint_session


def test_auth_config_exposes_modes(client):
    resp = client.get("/v1/auth/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dev_auth"] is True  # env=dev in tests
    assert body["google_client_id"] == ""


def test_google_sign_in_mints_working_session(client):
    resp = client.post(
        "/v1/auth/google",
        json={"credential": "fake:10203:maya@example.com:Maya Rivera"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["uid"] == "g10203"
    assert body["display_name"] == "Maya Rivera"
    assert body["token"].startswith("st1.")

    me = client.get("/v1/users/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "maya@example.com"
    assert me.json()["display_name"] == "Maya Rivera"


def test_repeat_sign_in_keeps_edited_profile(client):
    cred = {"credential": "fake:555:raj@example.com:Raj P"}
    token = client.post("/v1/auth/google", json=cred).json()["token"]
    hdr = {"Authorization": f"Bearer {token}"}
    client.patch("/v1/users/me", json={"display_name": "Raj the Toolman"}, headers=hdr)

    again = client.post("/v1/auth/google", json=cred).json()
    assert again["display_name"] == "Raj the Toolman"


def test_bad_google_credential_rejected(client):
    resp = client.post("/v1/auth/google", json={"credential": "not-a-real-jwt"})
    assert resp.status_code == 401


def test_tampered_session_token_rejected(client):
    good = client.post(
        "/v1/auth/google", json={"credential": "fake:777:x@example.com:X"}
    ).json()["token"]
    forged = mint_session("g777", "wrong-secret")
    assert good != forged
    resp = client.get("/v1/users/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


def test_email_hidden_on_public_profile(client):
    client.post("/v1/auth/google", json={"credential": "fake:888:ana@example.com:Ana"})
    resp = client.get("/v1/users/g888")
    assert resp.status_code == 200
    assert resp.json()["email"] == ""
