"""Geohash encoding and neighborhood-scale radius search helpers.

Self-contained (no external deps). Firestore can't do native geo queries, so
we store a geohash per listing and query by geohash prefix ranges covering the
search circle, then post-filter by true haversine distance.
"""
from __future__ import annotations

import math
import random

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

EARTH_RADIUS_KM = 6371.0


def encode(lat: float, lng: float, precision: int = 9) -> str:
    lat_lo, lat_hi = -90.0, 90.0
    lng_lo, lng_hi = -180.0, 180.0
    bits = 0
    bit_count = 0
    even = True  # alternate lng/lat, starting with lng
    out: list[str] = []
    while len(out) < precision:
        if even:
            mid = (lng_lo + lng_hi) / 2
            if lng >= mid:
                bits = (bits << 1) | 1
                lng_lo = mid
            else:
                bits = bits << 1
                lng_hi = mid
        else:
            mid = (lat_lo + lat_hi) / 2
            if lat >= mid:
                bits = (bits << 1) | 1
                lat_lo = mid
            else:
                bits = bits << 1
                lat_hi = mid
        even = not even
        bit_count += 1
        if bit_count == 5:
            out.append(_BASE32[bits])
            bits = 0
            bit_count = 0
    return "".join(out)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# Geohash cell height in degrees of latitude per precision level. Width varies
# with latitude but is bounded by these at the equator.
_CELL_LAT_DEG = {1: 45.0, 2: 11.25, 3: 1.40625, 4: 0.3515625, 5: 0.0439453125,
                 6: 0.010986328125, 7: 0.001373291015625, 8: 0.000343322753906}


def precision_for_radius(radius_km: float) -> int:
    """Coarsest precision whose cell is still >= the search radius, so a 3x3
    block of cells around the center is guaranteed to cover the circle."""
    radius_deg = radius_km / 111.0
    for p in range(8, 0, -1):
        if _CELL_LAT_DEG[p] >= radius_deg:
            return p
    return 1


def cover_prefixes(lat: float, lng: float, radius_km: float) -> list[str]:
    """Geohash prefixes covering the search circle: the 3x3 grid of cells
    around the center at an appropriate precision."""
    p = precision_for_radius(radius_km)
    step_lat = _CELL_LAT_DEG[p]
    # longitude cell width in degrees at this latitude (avoid pole blowup)
    step_lng = step_lat * 2 / max(math.cos(math.radians(min(abs(lat), 85.0))), 0.05)
    prefixes: set[str] = set()
    for dlat in (-step_lat, 0.0, step_lat):
        for dlng in (-step_lng, 0.0, step_lng):
            la = max(-90.0, min(90.0, lat + dlat))
            ln = ((lng + dlng + 180.0) % 360.0) - 180.0
            prefixes.add(encode(la, ln, p))
    return sorted(prefixes)


def jitter(lat: float, lng: float, meters: float = 150.0) -> tuple[float, float]:
    """Randomly offset a coordinate for privacy-safe public display."""
    r = meters / 1000.0 / EARTH_RADIUS_KM
    theta = random.uniform(0, 2 * math.pi)
    dlat = math.degrees(r * math.cos(theta))
    dlng = math.degrees(r * math.sin(theta) / max(math.cos(math.radians(lat)), 0.05))
    return lat + dlat, lng + dlng
