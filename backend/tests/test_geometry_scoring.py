from routing import scoring
from routing.geometry import backtrack_length_m, haversine_m, line_length_m, route_similarity
from routing.schemas import RoutePreference as P

from fakes import straight, via


def test_haversine_known_distance():
    # MG Road to Whitefield is ~16-17 km as the crow flies.
    d = haversine_m((77.6070, 12.9750), (77.7500, 12.9698))
    assert 15_000 < d < 16_500


def test_similarity_identical_and_disjoint():
    a = straight((12.90, 77.60), (12.95, 77.65))
    assert route_similarity(a, a) > 0.99
    b = straight((12.90, 77.70), (12.95, 77.75))
    assert route_similarity(a, b) == 0.0


def test_similarity_partial_overlap():
    a = straight((12.90, 77.60), (12.90, 77.64))
    b = via((12.90, 77.60), (12.90, 77.62), (12.93, 77.64))  # shares first half
    sim = route_similarity(a, b)
    assert 0.3 < sim < 0.7


def test_backtrack_detects_u_turn_spur():
    out_and_back = via((12.90, 77.60), (12.90, 77.61), (12.90, 77.60), n=60) + straight((12.90, 77.60), (12.92, 77.60))[1:]
    assert backtrack_length_m(out_and_back) > 500
    assert backtrack_length_m(straight((12.90, 77.60), (12.95, 77.65))) == 0


def test_line_length():
    line = straight((12.90, 77.60), (12.90, 77.61))
    assert abs(line_length_m(line) - haversine_m(line[0], line[-1])) < 1


def test_preference_resolution():
    assert scoring.resolve_preference(P.LEAST_TRAFFIC_NOW, traffic_basis=False, future=False)[0] == P.FASTEST
    assert scoring.resolve_preference(P.LEAST_TRAFFIC_NOW, traffic_basis=True, future=True)[0] == P.LEAST_TRAFFIC_PREDICTED
    assert scoring.resolve_preference(P.LEAST_TRAFFIC_PREDICTED, traffic_basis=True, future=False)[0] == P.LEAST_TRAFFIC_NOW
    assert scoring.resolve_preference(P.BALANCED, traffic_basis=False, future=False) == (P.BALANCED, None)


def m(eta, dist, delay=0.0, severe=0, other=0, comparable=True):
    return scoring.RouteMetrics(eta, dist, delay, severe, other, comparable)


def test_scores_only_comparable_routes():
    out = scoring.score_routes(P.FASTEST, [m(600, 5000), m(500, 6000, comparable=False)])
    assert out[0][0] == 10.0 and out[1][0] is None


def test_balanced_penalises_incidents_and_delay():
    clean = m(600, 5000, delay=0)
    incident = m(600, 5000, delay=0, severe=1)
    delayed = m(600, 5000, delay=300)
    s = [x[0] for x in scoring.score_routes(P.BALANCED, [clean, incident, delayed])]
    assert s[0] < s[1] and s[0] < s[2]


def test_least_traffic_prefers_lower_delay_over_eta():
    out = scoring.score_routes(P.LEAST_TRAFFIC_NOW, [m(600, 5000, delay=300), m(660, 5000, delay=60)])
    assert out[1][0] < out[0][0]
