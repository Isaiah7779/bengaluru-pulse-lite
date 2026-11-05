"""Reviewed scope vocabulary (docs/v3/SCOPE_CHECK.md §3).

Each concept lists the exact token sequences it accepts; there is no stemming
(single-word negative forms also accept a plural "s"/"es", see scope.py).
Changing this file is a reviewed change: add a case for it and record the reason in
SCOPE_CHECK.md. Tune only on development sets (scope_cases_v0, scope_dev_v2); never
on docs/v3/eval/heldout_scope_*.jsonl.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

# concept id -> accepted forms
STRONG: Dict[str, Tuple[str, ...]] = {
    "traffic": ("traffic",),
    "congestion": ("congestion",),
    "jam": ("jam", "jams", "jammed", "gridlock", "bumper to bumper", "standstill", "crawling", "choked",
            "hold up", "hold ups", "holdup", "holdups"),
    "route": ("route", "routes", "routing", "routed"),
    "reroute": ("reroute",),
    "detour": ("detour", "detours", "diversion", "diversions", "diverted"),
    "shortcut": ("shortcut", "shortcuts", "longcut", "longcuts", "short cut", "long cut"),
    "travel_time": ("eta", "travel time", "journey time", "commute"),
    "delay": ("delay", "delays", "delayed"),
    "incident": ("incident", "incidents", "accident", "accidents", "crash", "road works", "closure", "closures",
                 "waterlogging", "flooding", "flooded", "pothole", "potholes"),
    # Explicit, reviewed misspellings (no fuzzy matching): scope_dev_v2 A01-A03.
    "misspelt": ("trafic", "trafik", "trafffic", "conjestion", "congestoin", "acident", "accidnet", "accedent"),
    "forecast": ("forecast", "forecasts", "forecasting", "prediction", "predictions", "predicted", "predict"),
    "peak": ("peak hour", "rush hour", "office hours traffic"),
    "free_flow": ("free flow",),
    "route_kind": ("reference route", "recommended route", "alternative route"),
    "provider": ("osrm", "tomtom", "open meteo"),
    "monitored": ("monitored point", "monitored points", "monitored segment"),
    "travel_mode": ("travel mode",),
    "avoid": ("avoid tolls", "toll", "tolls", "expressway", "motorway", "ferry"),
    "departure": ("departure", "depart", "leave at"),
    "navigation": ("navigation", "turn by turn"),
    "pulse_app": ("bengaluru pulse", "pulse app"),
    "app_feature": ("trip history", "verified shortcut", "incident report", "data sources"),
    "way_to": ("best way to", "fastest way to", "quickest way to", "shortest way to", "how to reach",
               "how do i get to", "how to get to", "stuck in"),
    # product and method concepts (SCOPE_CHECK.md §9: added after the first golden-set run)
    "preference": ("preference", "preferences"),
    "ml_method": ("neural network", "gnn", "machine learning", "public dataset"),
    "password_task": ("password rules", "password reset", "reset password", "reset my password",
                      "forgot password", "change password"),
    "trips": ("trip", "trips", "saved trip", "saved trips", "favourites", "favorites"),
}

WEAK: Dict[str, Tuple[str, ...]] = {
    "road": ("road", "roads", "rd", "highway", "lane", "lanes", "street"),
    "drive": ("drive", "driving", "car"),
    "two_wheeler": ("motorcycle", "bike", "two wheeler", "scooter"),
    "bicycle": ("bicycle", "cycling"),
    "walk": ("walk", "walking"),
    "distance": ("distance", "km"),
    "duration": ("minutes", "mins", "hours", "how long"),
    "speed_words": ("fast", "faster", "slow", "slower", "quick", "quicker"),
    "late": ("late",),
    "reach": ("reach",),
    "leave": ("leave",),
    "arrive": ("arrive", "arrival"),
    "road_feature": ("junction", "signal", "flyover", "underpass"),
    "blocked": ("block", "blocked", "closed", "shut"),
    "map": ("map",),
    "location_input": ("gps", "coordinates"),
    "place_name": ("place name",),
    "weather": ("weather", "rain", "raining"),
    "account": ("account", "sign in", "login", "password", "register"),
    "admin": ("admin",),
    "role": ("role",),
    "data": ("data",),
    "dataset": ("dataset",),
    "model": ("model", "accuracy", "accurate"),
    "v1": ("v1",),
    "speed": ("speed",),
    "sensor": ("sensor", "readings"),
    "source": ("source", "sources", "attributed", "attribution"),
    "ui": ("option", "button", "greyed out", "grayed out"),
    "hosted": ("hosted",),
    "request": ("request", "loading"),
    "when": ("today", "tomorrow", "tonight", "now"),
}

# Weak-pair rule (SCOPE_CHECK.md §4 rule 3): two weak concepts make a question in scope
# only if at least one is a travel/road ANCHOR, or at least two are APP concepts.
# Everything else (time words, speed words, leave/late, durations) is GENERIC and can
# never qualify a question on its own, however many appear.
WEAK_ANCHOR: FrozenSet[str] = frozenset({
    "road", "drive", "two_wheeler", "bicycle", "walk", "distance", "reach", "arrive", "road_feature", "blocked",
    "map", "location_input", "place_name",
})
WEAK_APP: FrozenSet[str] = frozenset({
    "weather", "account", "admin", "role", "data", "dataset", "model", "v1", "speed", "sensor", "source", "ui",
    "hosted", "request",
})

NEGATIVE: Dict[str, Tuple[str, ...]] = {
    "food": ("food", "restaurant", "biryani", "dosa", "cafe", "menu", "recipe", "pizza"),
    "entertainment": ("movie", "film", "song", "music", "poem", "story", "joke", "lyrics"),
    "housing": ("hotel", "pg", "rent", "flat", "apartment", "property"),
    "work": ("job", "salary", "interview"),
    "shopping": ("shopping", "buy", "price"),
    "fares": ("metro fare", "bus fare", "auto fare", "cab fare", "fare", "ticket"),
    "transport_admin": ("rto", "licence", "license", "challan", "registration"),
    "health": ("hospital", "doctor", "medicine", "dentist"),
    "education": ("admission", "exam", "college"),
    "sport": ("cricket", "score", "football"),
    "devices": ("wifi", "phone", "laptop", "cable", "router"),
    "travel_leisure": ("holiday", "packing"),
    "writing_code": ("translate", "essay", "homework", "code"),
}

# Travel or follow-up cues (SCOPE_CHECK.md §4 rule 6): they never make a question in
# scope, but a question with a cue and no recognised concept gets the rephrase fallback
# instead of an outright refusal.
TRAVEL_CUES: Tuple[str, ...] = (
    "how far", "far", "ride", "heading to", "head to", "going to", "which way", "the other one", "that one",
    "this one", "instead",
)

# Masked before matching; never counts towards scope. A question that names a place but
# matches no concept gets the rephrase fallback (rule 6), never an answer.
PLACES: Tuple[str, ...] = (
    "silk board", "outer ring road", "old airport road", "hosur road", "mg road", "electronic city", "koramangala",
    "whitefield", "kia", "majestic", "indiranagar", "hebbal", "marathahalli", "yeshwanthpur", "hsr layout",
    "jayanagar", "bannerghatta road", "bengaluru", "bangalore", "blr",
)

NEGATORS = frozenset({"not", "no", "never", "without", "except", "ignore", "forget", "dont", "doesnt", "isnt", "nothing"})
NEGATION_WINDOW = 4
