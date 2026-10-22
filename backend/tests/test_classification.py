"""Shortcut / longcut / alternative classification — every case."""

import math

import pytest

from routing.classification import classify

REF_D, REF_T = 10_000.0, 1_200.0


def c(d, t, **kw):
    return classify(d, t, REF_D, REF_T, basis=kw.pop("basis", "traffic_live"), reference_basis=kw.pop("ref_basis", "traffic_live"), **kw)


def test_shortcut_is_shorter_and_faster():
    r = c(9_000, 1_000)
    assert r.type == "shortcut"
    assert r.distance_relation == "shorter" and r.time_relation == "faster"
    assert r.distance_diff_m == -1000 and r.time_diff_s == -200
    assert "shorter" in r.reason and "faster" in r.reason


def test_longcut_is_longer_and_faster():
    r = c(12_000, 1_000)
    assert r.type == "longcut"
    assert r.distance_relation == "longer" and r.time_relation == "faster"


@pytest.mark.parametrize(
    "d,t,dist_rel,time_rel",
    [
        (9_000, 1_400, "shorter", "slower"),  # shorter but slower
        (12_000, 1_400, "longer", "slower"),  # longer and slower
        (10_000, 1_000, "equal", "faster"),  # same distance, faster
        (9_000, 1_200, "shorter", "equal"),  # shorter, same time
        (12_000, 1_200, "longer", "equal"),  # longer, same time
        (10_000, 1_200, "equal", "equal"),  # identical
    ],
)
def test_everything_else_is_alternative(d, t, dist_rel, time_rel):
    r = c(d, t)
    assert r.type == "alternative"
    assert (r.distance_relation, r.time_relation) == (dist_rel, time_rel)


def test_differences_within_threshold_count_as_equal():
    # 40 m shorter (< 50 m / 1%) and 20 s faster (< 30 s / 2%) are noise.
    r = c(REF_D - 40, REF_T - 20)
    assert r.type == "alternative"
    assert r.distance_relation == "equal" and r.time_relation == "equal"


def test_just_beyond_threshold_is_significant():
    r = c(REF_D - 120, REF_T - 40)  # 1.2% shorter, 3.3% faster
    assert r.type == "shortcut"


@pytest.mark.parametrize("bad", [None, 0, -5, math.nan])
def test_missing_or_invalid_metrics_are_unclassified(bad):
    assert c(bad, 1000).type == "unclassified"
    assert c(9000, bad).type == "unclassified"
    assert classify(9000, 1000, bad, REF_T, basis="free_flow", reference_basis="free_flow").type == "unclassified"


def test_mixed_time_basis_is_not_compared():
    r = c(9_000, 1_000, basis="free_flow", ref_basis="traffic_live")
    assert r.type == "unclassified"
    assert "not comparable" in r.reason


def test_reference_route():
    r = classify(None, None, None, None, basis="free_flow", is_reference=True)
    assert r.type == "reference"
