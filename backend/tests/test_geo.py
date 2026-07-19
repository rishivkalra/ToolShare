from app import geo


def test_encode_known_value():
    # Well-known reference: geohash of (57.64911, 10.40744) is u4pruydqqvj
    assert geo.encode(57.64911, 10.40744, 11) == "u4pruydqqvj"


def test_haversine_sf_to_oakland():
    d = geo.haversine_km(37.7749, -122.4194, 37.8044, -122.2712)
    assert 12 < d < 14


def test_cover_prefixes_include_center_and_find_nearby():
    lat, lng = 37.7749, -122.4194
    prefixes = geo.cover_prefixes(lat, lng, 3.0)
    assert any(geo.encode(lat, lng).startswith(p) for p in prefixes)
    # A point ~2km away must fall in one of the covering prefixes.
    nearby = geo.encode(37.7899, -122.4094)
    assert any(nearby.startswith(p) for p in prefixes)


def test_jitter_stays_close():
    lat, lng = 37.7749, -122.4194
    jlat, jlng = geo.jitter(lat, lng, meters=150)
    assert geo.haversine_km(lat, lng, jlat, jlng) < 0.4
