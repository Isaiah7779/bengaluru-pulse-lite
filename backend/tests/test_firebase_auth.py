"""Firebase ID-token sign-in, mandatory API access, account linking and isolation.

Tokens are real RS256 JWTs signed by a test key; only the download of Google's public
certificates is replaced, so the Firebase Admin SDK's own signature, issuer, audience,
expiry and subject checks all run.
"""

from __future__ import annotations

import datetime as dt
import time

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from conftest import make_user
from core.settings import get_settings
from db.models import Trip, User
from db.session import session_scope

PROJECT = "demo-pulse-test"


def _key_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-signer")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return pem, cert.public_bytes(serialization.Encoding.PEM).decode()


SIGNING_KEY, SIGNING_CERT = _key_and_cert()
OTHER_KEY, _ = _key_and_cert()


@pytest.fixture(autouse=True)
def firebase_project(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "firebase_project_id", PROJECT)
    monkeypatch.setattr(settings, "api_auth_required", True)
    monkeypatch.setattr("google.oauth2.id_token._fetch_certs", lambda request, url: {"k1": SIGNING_CERT})
    yield settings


def token(uid="uid-a", email="a@pulse.example", verified=True, *, key=None, aud=PROJECT, iss=None, exp_in=3600, auth_age=0, provider="password", **extra):
    now = int(time.time())
    claims = {
        "iss": iss or f"https://securetoken.google.com/{aud}",
        "aud": aud,
        "sub": uid,
        "iat": now - 10,
        "exp": now + exp_in,
        "auth_time": now - auth_age,
        "email": email,
        "email_verified": verified,
        "firebase": {"sign_in_provider": provider, "identities": {}},
        **extra,
    }
    return jwt.encode(claims, key or SIGNING_KEY, algorithm="RS256", headers={"kid": "k1"})


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_health_is_public_but_app_endpoints_need_sign_in(client):
    assert client.get("/health").status_code == 200
    for path in ("/v1/traffic/segments", "/v1/vehicles", "/v1/incidents", "/v1/geocode/search?q=mg", "/v1/forecast/models", "/v1/community/shortcuts", "/v1/me/trips"):
        r = client.get(path)
        assert r.status_code == 401, path
    assert client.post("/v1/routes", json={}).status_code == 401


def test_verified_firebase_user_is_created_as_normal_user(client):
    r = client.get("/v1/auth/me", headers=bearer(token(name="Asha R")))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "user" and body["firebase_linked"] and not body["has_password"]
    assert body["email"] == "a@pulse.example" and body["display_name"] == "Asha R"
    assert client.get("/v1/vehicles", headers=bearer(token())).status_code == 200
    with session_scope() as s:
        assert s.query(User).filter_by(firebase_uid="uid-a").count() == 1


def test_unverified_email_is_refused(client):
    r = client.get("/v1/vehicles", headers=bearer(token(verified=False)))
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified"
    google_unverified = client.get("/v1/vehicles", headers=bearer(token(verified=False, provider="google.com")))
    assert google_unverified.status_code == 403
    with session_scope() as s:
        assert s.query(User).count() == 0


@pytest.mark.parametrize(
    "bad",
    [
        dict(key=OTHER_KEY),  # signature from a key Google did not publish
        dict(aud="someone-elses-project"),
        dict(iss="https://securetoken.google.com/someone-elses-project"),
        dict(uid=""),
    ],
)
def test_forged_or_foreign_tokens_are_rejected(client, bad):
    r = client.get("/v1/vehicles", headers=bearer(token(**bad)))
    assert r.status_code == 401


def test_expired_token_and_unsigned_token(client):
    r = client.get("/v1/vehicles", headers=bearer(token(exp_in=-120)))
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"
    unsigned = jwt.encode({"sub": "x", "aud": PROJECT}, None, algorithm="none")
    assert client.get("/v1/vehicles", headers=bearer(unsigned)).status_code == 401


def test_token_claims_cannot_grant_admin(client):
    t = token(role="admin", admin=True)
    assert client.get("/v1/auth/me", headers=bearer(t)).json()["role"] == "user"
    assert client.get("/v1/admin/users", headers=bearer(t)).status_code == 403


def test_admin_role_from_database_works_with_firebase(client):
    client.get("/v1/auth/me", headers=bearer(token(uid="boss", email="boss@pulse.example")))
    with session_scope() as s:
        s.query(User).filter_by(firebase_uid="boss").one().role = "admin"
    assert client.get("/v1/admin/users", headers=bearer(token(uid="boss", email="boss@pulse.example"))).status_code == 200


def test_existing_email_is_never_linked_automatically(client):
    uid = make_user(email="a@pulse.example", password="Correct-Horse-9", role="admin")
    r = client.get("/v1/vehicles", headers=bearer(token()))
    assert r.status_code == 409 and r.json()["error"]["code"] == "account_link_required"
    with session_scope() as s:
        assert s.get(User, uid).firebase_uid is None


def test_explicit_link_needs_old_password_and_keeps_records(client):
    uid = make_user(email="old-admin@pulse.test", password="Correct-Horse-9", role="admin")
    with session_scope() as s:
        s.add(Trip(user_id=uid, vehicle="car", preference="fastest", origin_label="A", destination_label="B",
                   origin_lat=12.9, origin_lon=77.6, destination_lat=12.95, destination_lon=77.62))
    t = token(uid="fb-owner", email="owner@pulse.example")
    wrong = client.post("/v1/auth/link", json={"email": "old-admin@pulse.test", "password": "wrong-Password-1"}, headers=bearer(t))
    assert wrong.status_code == 401
    ok = client.post("/v1/auth/link", json={"email": "old-admin@pulse.test", "password": "Correct-Horse-9"}, headers=bearer(t))
    assert ok.status_code == 200, ok.text
    assert ok.json()["id"] == uid and ok.json()["role"] == "admin" and ok.json()["email"] == "owner@pulse.example"
    assert len(client.get("/v1/me/trips", headers=bearer(t)).json()) == 1
    again = client.post("/v1/auth/link", json={"email": "owner@pulse.example", "password": "Correct-Horse-9"}, headers=bearer(t))
    assert again.status_code == 409
    other = token(uid="intruder", email="x@pulse.example")
    assert client.post("/v1/auth/link", json={"email": "owner@pulse.example", "password": "Correct-Horse-9"}, headers=bearer(other)).status_code == 409


def test_link_requires_verified_firebase_identity(client):
    make_user(email="old@pulse.test", password="Correct-Horse-9")
    r = client.post("/v1/auth/link", json={"email": "old@pulse.test", "password": "Correct-Horse-9"}, headers=bearer(token(verified=False)))
    assert r.status_code == 403
    assert client.post("/v1/auth/link", json={"email": "old@pulse.test", "password": "Correct-Horse-9"}).status_code == 401


def test_users_cannot_see_each_others_trips(client):
    a, b = bearer(token(uid="ua", email="ua@pulse.example")), bearer(token(uid="ub", email="ub@pulse.example"))
    client.get("/v1/auth/me", headers=a)
    client.get("/v1/auth/me", headers=b)
    with session_scope() as s:
        ua = s.query(User).filter_by(firebase_uid="ua").one()
        trip = Trip(user_id=ua.id, vehicle="car", preference="fastest", origin_label="A", destination_label="B",
                    origin_lat=12.9, origin_lon=77.6, destination_lat=12.95, destination_lon=77.62)
        s.add(trip)
        s.flush()
        trip_id = trip.id
    assert len(client.get("/v1/me/trips", headers=a).json()) == 1
    assert client.get("/v1/me/trips", headers=b).json() == []
    assert client.get(f"/v1/me/trips/{trip_id}", headers=b).status_code == 404
    assert client.delete(f"/v1/me/trips/{trip_id}", headers=b).status_code == 404


def test_disabled_account_is_locked_out(client):
    client.get("/v1/auth/me", headers=bearer(token()))
    with session_scope() as s:
        s.query(User).filter_by(firebase_uid="uid-a").one().is_active = False
    assert client.get("/v1/vehicles", headers=bearer(token())).status_code == 401


def test_firebase_account_deletion_is_explicit_and_needs_recent_sign_in(client):
    client.get("/v1/auth/me", headers=bearer(token()))
    assert client.post("/v1/auth/me/delete", json={}, headers=bearer(token())).status_code == 400
    stale = client.post("/v1/auth/me/delete", json={"confirm": True}, headers=bearer(token(auth_age=3600)))
    assert stale.status_code == 403 and stale.json()["error"]["code"] == "recent_sign_in_required"
    assert client.post("/v1/auth/me/delete", json={"confirm": True}, headers=bearer(token())).status_code == 204
    with session_scope() as s:
        assert s.query(User).filter_by(firebase_uid="uid-a").count() == 0


def test_firebase_user_cannot_set_a_local_password(client):
    r = client.patch("/v1/auth/me", json={"new_password": "Another-Pass-77"}, headers=bearer(token()))
    assert r.status_code == 400 and r.json()["error"]["code"] == "password_managed_by_firebase"


def test_legacy_tokens_until_disabled(client, monkeypatch):
    make_user(email="legacy@pulse.test", password="Correct-Horse-9")
    t = client.post("/v1/auth/login", json={"email": "legacy@pulse.test", "password": "Correct-Horse-9"}).json()["access_token"]
    assert client.get("/v1/vehicles", headers=bearer(t)).status_code == 200
    monkeypatch.setattr(get_settings(), "legacy_auth_enabled", False)
    assert client.get("/v1/vehicles", headers=bearer(t)).status_code == 401
    assert client.post("/v1/auth/login", json={"email": "legacy@pulse.test", "password": "Correct-Horse-9"}).status_code == 404
    assert client.post("/v1/auth/register", json={"email": "n@pulse.example", "password": "Strong-Pass-42", "display_name": "N"}).status_code == 404


def test_without_project_id_firebase_tokens_are_refused(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "firebase_project_id", None)
    r = client.get("/v1/vehicles", headers=bearer(token()))
    assert r.status_code == 401 and r.json()["error"]["code"] == "firebase_not_configured"
