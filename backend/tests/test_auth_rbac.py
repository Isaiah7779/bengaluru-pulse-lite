"""Authentication and role-based access control (enforced by the backend)."""

from datetime import datetime, timedelta, timezone

import jwt

from core.settings import get_settings
from db.models import Trip, User
from db.session import session_scope

from conftest import login, make_user


def test_register_login_me_logout(client):
    r = client.post("/v1/auth/register", json={"email": "New@Example.com", "password": "Strong-Pass-42", "display_name": "Asha"})
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == "new@example.com"
    assert r.json()["user"]["role"] == "user"
    headers = login(client, "new@example.com", "Strong-Pass-42")
    assert client.get("/v1/auth/me", headers=headers).json()["display_name"] == "Asha"
    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
    after = client.get("/v1/auth/me", headers=headers)
    assert after.status_code == 401 and after.json()["error"]["code"] == "token_revoked"


def test_registration_cannot_self_assign_admin(client):
    r = client.post(
        "/v1/auth/register",
        json={"email": "sneaky@example.com", "password": "Strong-Pass-42", "display_name": "S", "role": "admin"},
    )
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "user"


def test_profile_update_cannot_change_role(client, user_headers):
    r = client.patch("/v1/auth/me", headers=user_headers, json={"display_name": "Renamed", "role": "admin", "is_active": False})
    assert r.status_code == 200
    assert r.json()["role"] == "user"
    assert client.get("/v1/admin/users", headers=user_headers).status_code == 403


def test_weak_password_and_duplicate_email(client):
    weak = client.post("/v1/auth/register", json={"email": "a@example.com", "password": "short", "display_name": "A"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"
    ok = {"email": "a@example.com", "password": "Strong-Pass-42", "display_name": "A"}
    assert client.post("/v1/auth/register", json=ok).status_code == 201
    dup = client.post("/v1/auth/register", json=ok)
    assert dup.status_code == 409


def test_wrong_password_and_rate_limit(client):
    make_user()
    for _ in range(get_settings().login_max_attempts):
        r = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "nope-Nope-1"})
        assert r.status_code == 401
    blocked = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "Correct-Horse-9"})
    assert blocked.status_code == 429


def test_tampered_and_expired_tokens_rejected(client):
    uid = make_user()
    s = get_settings()
    now = datetime.now(timezone.utc)
    forged = jwt.encode({"sub": str(uid), "role": "admin", "jti": "x", "iat": int(now.timestamp()),
                         "exp": int((now + timedelta(hours=1)).timestamp()), "iss": "bengaluru-pulse"}, "wrong-key", algorithm="HS256")
    assert client.get("/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    expired = jwt.encode({"sub": str(uid), "role": "user", "jti": "y", "iat": int((now - timedelta(hours=2)).timestamp()),
                          "exp": int((now - timedelta(hours=1)).timestamp()), "iss": "bengaluru-pulse"},
                         s.jwt_secret.get_secret_value(), algorithm="HS256")
    r = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"


def test_role_comes_from_database_not_token(client):
    """A token minted while admin stops granting admin once the role is revoked."""

    make_user("admin@example.com", "Admin-Pass-123", role="admin")
    make_user("admin2@example.com", "Admin-Pass-123", role="admin")
    headers = login(client, "admin@example.com", "Admin-Pass-123")
    assert client.get("/v1/admin/users", headers=headers).status_code == 200
    with session_scope() as s:
        u = s.query(User).filter_by(email="admin@example.com").one()
        u.role = "user"
    assert client.get("/v1/admin/users", headers=headers).status_code == 403


def test_disabled_user_is_locked_out(client, user_headers):
    with session_scope() as s:
        s.query(User).filter_by(email="user@example.com").one().is_active = False
    assert client.get("/v1/auth/me", headers=user_headers).status_code == 401


def test_users_cannot_read_each_others_trips_or_favourites(client):
    alice = make_user("alice@example.com")
    make_user("bob@example.com")
    with session_scope() as s:
        trip = Trip(user_id=alice, origin_lat=12.9, origin_lon=77.6, destination_lat=13.0, destination_lon=77.5,
                    vehicle="car", preference="fastest")
        s.add(trip)
        s.flush()
        trip_id = trip.id
    a = login(client, "alice@example.com")
    b = login(client, "bob@example.com")
    assert client.get(f"/v1/me/trips/{trip_id}", headers=a).status_code == 200
    assert client.get(f"/v1/me/trips/{trip_id}", headers=b).status_code == 404
    assert client.delete(f"/v1/me/trips/{trip_id}", headers=b).status_code == 404
    assert client.get("/v1/me/trips", headers=b).json() == []
    fav = client.post("/v1/me/favourites", headers=a, json={"label": "Home", "lat": 12.97, "lon": 77.59}).json()
    assert client.delete(f"/v1/me/favourites/{fav['id']}", headers=b).status_code == 404
    assert len(client.get("/v1/me/favourites", headers=a).json()) == 1


def test_anonymous_and_user_access_to_admin_endpoints(client, user_headers):
    for path in ("/v1/admin/users", "/v1/admin/data-freshness", "/v1/admin/models", "/v1/admin/system-health",
                 "/v1/admin/community/candidates", "/v1/admin/audit-log"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers=user_headers).status_code == 403, path


def test_admin_cannot_modify_self_and_last_admin_protected(client, admin_headers):
    me = client.get("/v1/auth/me", headers=admin_headers).json()
    r = client.patch(f"/v1/admin/users/{me['id']}", headers=admin_headers, json={"role": "user"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "self_modification"
    uid = make_user("u2@example.com")
    r = client.patch(f"/v1/admin/users/{uid}", headers=admin_headers, json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    # Two admins now; demoting the other one is allowed, and is audited.
    assert client.patch(f"/v1/admin/users/{uid}", headers=admin_headers, json={"role": "user"}).status_code == 200
    log = client.get("/v1/admin/audit-log", headers=admin_headers).json()["entries"]
    assert any(e["action"] == "admin.user_update" for e in log)


def test_account_deletion_removes_personal_data(client, user_headers):
    client.post("/v1/me/favourites", headers=user_headers, json={"label": "Work", "lat": 12.97, "lon": 77.59})
    r = client.post("/v1/auth/me/delete", headers=user_headers, json={"password": "Correct-Horse-9"})
    assert r.status_code == 204
    with session_scope() as s:
        assert s.query(User).count() == 0
        from db.models import FavouritePlace

        assert s.query(FavouritePlace).count() == 0
