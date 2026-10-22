"""Community submissions → shortcut candidate lifecycle."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from community import service as community
from community.service import CommunityService, TracePoint, clean_trace, decide, mark_stale
from core.errors import AppError
from core.settings import get_settings
from db.models import RouteSubmission, ShortcutCandidate
from db.session import session_scope
from routing.geometry import line_length_m

from conftest import login, make_user
from fakes import FakeTomTom, osrm_route, straight, via

O, D = (12.9352, 77.6245), (12.9600, 77.6500)
SHORT = straight(O, D, n=60)                       # the user's (shorter) path
REF = via(O, (12.9300, 77.6550), D, n=60)          # longer OSRM reference


def trace(coords, minutes=12, end_ago=timedelta(hours=1), accuracy=8.0):
    end = datetime.now(timezone.utc) - end_ago
    start = end - timedelta(minutes=minutes)
    n = len(coords)
    return [TracePoint(c[1], c[0], start + (end - start) * i / (n - 1), accuracy) for i, c in enumerate(coords)]


class MatchOSRM:
    """Map-matches to the submitted path; reference route is REF."""

    def __init__(self, confidence=0.9):
        self.confidence = confidence

    async def match(self, points, timestamps=None, radiuses=None, profile="driving"):
        coords = [[lon, lat] for lat, lon in points]
        return {"code": "Ok", "matchings": [{"confidence": self.confidence, "distance": line_length_m(coords),
                                             "geometry": {"type": "LineString", "coordinates": coords}}]}

    async def route_points(self, points, *, profile="driving", alternatives=0, steps=True, exclude=()):
        if len(points) == 2:
            return {"code": "Ok", "routes": [osrm_route(REF, speed_mps=8)]}
        coords = [[lon, lat] for lat, lon in points]
        return {"code": "Ok", "routes": [osrm_route(coords, speed_mps=8)]}


@pytest.fixture
def service(monkeypatch):
    svc = CommunityService(get_settings(), tomtom=FakeTomTom(speed_mps=7))
    fake = MatchOSRM()
    monkeypatch.setattr(svc, "_client", lambda vehicle: fake)
    return svc


def submit(svc, user_id, points, vehicle="car"):
    with session_scope() as s:
        sub = asyncio.run(svc.submit(s, user_id, vehicle, points, None))
        return sub.id, sub.status, sub.rejection_reason, sub.candidate_id


# --- trace validation ---------------------------------------------------------


def test_trace_sanity_rules():
    ok, v = clean_trace(trace(SHORT), "car")
    assert v.ok and len(ok) == 60
    assert not clean_trace(trace(SHORT[:5]), "car")[1].ok  # too few points
    assert "days ago" in clean_trace(trace(SHORT, end_ago=timedelta(days=10)), "car")[1].reason  # stale
    future = trace(SHORT, end_ago=timedelta(hours=-2))
    assert "future" in clean_trace(future, "car")[1].reason
    outside = trace(straight((28.6, 77.2), (28.7, 77.3)))
    assert "service area" in clean_trace(outside, "car")[1].reason
    too_short = trace(straight(O, (12.9362, 77.6250), n=20), minutes=1)  # 120 m in 1 min
    assert "duration" in clean_trace(too_short, "car")[1].reason


def test_gps_noise_is_removed_or_rejected():
    pts = trace(SHORT)
    pts[10] = TracePoint(13.2, 77.9, pts[10].t, 8.0)  # teleport spike
    kept, v = clean_trace(pts, "car")
    assert v.ok and len(kept) == 59 and v.checks["gps_noise"]["dropped_points"] == 1
    noisy = trace(SHORT, accuracy=200.0)  # every fix too inaccurate
    assert not clean_trace(noisy, "car")[1].ok


def test_vehicle_speed_plausibility():
    # 3.5 km in 12 min is fine by car but impossible on foot.
    assert clean_trace(trace(SHORT), "car")[1].ok
    assert not clean_trace(trace(SHORT), "walk")[1].ok


# --- lifecycle --------------------------------------------------------------


def test_three_independent_confirmations_move_to_review_not_verified(service):
    users = [make_user(f"u{i}@example.com") for i in range(4)]
    _, status, _, cid = submit(service, users[0], trace(SHORT))
    assert status == "accepted" and cid
    with session_scope() as s:
        c = s.get(ShortcutCandidate, cid)
        assert c.classification == "shortcut" and c.state == "candidate" and c.confirmations == 1

    # Same user again: not independent.
    _, status, reason, _ = submit(service, users[0], trace(SHORT, end_ago=timedelta(hours=3)))
    assert status == "rejected" and "independent" in reason

    submit(service, users[1], trace(SHORT, minutes=11))
    _, _, _, cid3 = submit(service, users[2], trace(SHORT, minutes=13))
    assert cid3 == cid
    with session_scope() as s:
        c = s.get(ShortcutCandidate, cid)
        assert c.confirmations == 3
        assert c.state == "under_review"  # never auto-verified
        assert c.checks["consistent"] is True


def test_low_match_confidence_rejected(service, monkeypatch):
    monkeypatch.setattr(service, "_client", lambda vehicle: MatchOSRM(confidence=0.2))
    uid = make_user()
    _, status, reason, cid = submit(service, uid, trace(SHORT))
    assert status == "rejected" and "legal car roads" in reason and cid is None


def test_non_shortcut_trip_accepted_without_candidate(service):
    uid = make_user()
    _, status, _, cid = submit(service, uid, trace(REF))  # same as reference
    assert status == "accepted" and cid is None


def test_admin_decisions_enforce_state_machine(service):
    admin = make_user("admin@example.com", role="admin")
    uid = make_user()
    _, _, _, cid = submit(service, uid, trace(SHORT))
    with session_scope() as s:
        c = s.get(ShortcutCandidate, cid)
        with pytest.raises(AppError):
            decide(s, c, "verify", admin, "too early")  # only 1 confirmation
        c.state, c.confirmations = "under_review", 3
        decide(s, c, "verify", admin, "checked on map")
        assert c.state == "verified" and c.reviewed_by == admin


def test_stale_marking():
    with session_scope() as s:
        c = ShortcutCandidate(signature="x", vehicle="car", origin_lat=12.9, origin_lon=77.6, destination_lat=12.95,
                              destination_lon=77.65, geometry={"type": "LineString", "coordinates": SHORT},
                              distance_m=1000, classification="shortcut", state="verified", confirmations=3,
                              last_confirmed_at=datetime.now(timezone.utc) - timedelta(days=400))
        s.add(c)
        s.flush()
        assert mark_stale(s) == 1
        assert c.state == "stale"


def test_submission_api_and_public_visibility(client, monkeypatch):
    svc_fake = MatchOSRM()
    monkeypatch.setattr(CommunityService, "_client", lambda self, vehicle: svc_fake)
    monkeypatch.setattr(community, "TomTomProvider", lambda settings: FakeTomTom(speed_mps=7))
    make_user()
    headers = login(client)
    body = {"vehicle": "car", "points": [{"lat": p.lat, "lon": p.lon, "t": p.t.isoformat(), "accuracy_m": 8} for p in trace(SHORT)]}
    r = client.post("/v1/community/submissions", headers=headers, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["candidate"]["state"] == "candidate"
    assert client.get("/v1/community/shortcuts").json()["shortcuts"] == []  # unverified never public
    assert client.post("/v1/community/submissions", json=body).status_code == 401
    mine = client.get("/v1/community/submissions/mine", headers=headers).json()["submissions"]
    assert len(mine) == 1 and mine[0]["checks"]["map_match"]["passed"]
