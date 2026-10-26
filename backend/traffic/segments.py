"""Monitored Bengaluru corridor points for traffic-flow collection.

TomTom's Flow Segment API snaps each point to the nearest road segment and
returns that segment's geometry, which is stored with each observation. These
are *sample points* on major corridors; they do not provide city-wide coverage.
"""

from __future__ import annotations

from typing import Dict, Tuple

# code: (name, lat, lon)
MONITORED_POINTS: Dict[str, Tuple[str, float, float]] = {
    "silk_board": ("Silk Board Junction (ORR/Hosur Rd)", 12.9172, 77.6228),
    "marathahalli_bridge": ("Marathahalli Bridge (ORR)", 12.9566, 77.7010),
    "kr_puram": ("KR Puram (Old Madras Rd/ORR)", 13.0070, 77.6950),
    "hebbal_flyover": ("Hebbal Flyover", 13.0358, 77.5970),
    "whitefield_itpl": ("ITPL Main Road, Whitefield", 12.9860, 77.7310),
    "electronic_city": ("Electronic City Flyover (Hosur Rd)", 12.8452, 77.6602),
    "orr_bellandur": ("ORR near Bellandur", 12.9260, 77.6760),
    "orr_kadubeesanahalli": ("ORR Kadubeesanahalli", 12.9370, 77.6950),
    "orr_hennur": ("ORR Hennur Junction", 13.0349, 77.6411),
    "orr_nagawara": ("ORR Nagawara", 13.0430, 77.6200),
    "tin_factory": ("Tin Factory (Old Madras Rd)", 12.9960, 77.6690),
    "old_airport_rd_hal": ("Old Airport Road (HAL)", 12.9583, 77.6550),
    "domlur_flyover": ("Domlur Flyover", 12.9610, 77.6380),
    "mg_road": ("MG Road (Trinity)", 12.9730, 77.6170),
    "hosur_rd_bommanahalli": ("Hosur Road, Bommanahalli", 12.9020, 77.6290),
    "bannerghatta_rd": ("Bannerghatta Road (Jayadeva)", 12.9170, 77.5990),
    "sarjapur_rd": ("Sarjapur Road (Agara)", 12.9230, 77.6810),
    "tumkur_rd_yeshwanthpur": ("Tumkur Road, Yeshwanthpur", 13.0280, 77.5400),
    "goraguntepalya": ("Goraguntepalya Junction", 13.0300, 77.5280),
    "mysore_rd": ("Mysore Road, Nayandahalli", 12.9440, 77.5250),
    "kanakapura_rd": ("Kanakapura Road", 12.8900, 77.5650),
    "bellary_rd_yelahanka": ("Bellary Road (NH44), Yelahanka", 13.1000, 77.5960),
    "magadi_rd": ("Magadi Road, Vijayanagar", 12.9760, 77.5350),
    "richmond_circle": ("Richmond Circle", 12.9650, 77.5970),
    "koramangala_sony": ("Koramangala (Sony World Jn)", 12.9370, 77.6270),
    "indiranagar_100ft": ("Indiranagar 100 Feet Road", 12.9720, 77.6410),
}
