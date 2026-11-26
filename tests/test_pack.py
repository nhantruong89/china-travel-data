import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from pipeline.config import CityConfig
from pipeline.pack import build_pack, next_version, validate_pack
from pipeline.places import Place

CITY = CityConfig("testcity", "Thử", "试", "Test", "r", "Vùng", (121.0, 31.0, 122.0, 32.0), False, min_places=2)


def _places(n=3, lat=31.5):
    return [Place(f"n{i}", "eat", f"店{i}", None, f"dian {i}", lat, 121.5, None, "{}") for i in range(n)]


def _build(tmp_path, places=None, city=CITY):
    def extractor(src, bbox, out):
        out.write_bytes(b"pbf")
    def tiles(city_pbf, bbox, out):
        out.write_bytes(b"\0" * 1024)
    return build_pack(city, tmp_path / "china.osm.pbf", tmp_path / "dist", "20261201",
                      tiles_builder=tiles, extractor=extractor,
                      places_extractor=lambda pbf, bbox: places if places is not None else _places())


def test_build_pack_contents(tmp_path):
    z = _build(tmp_path)
    assert z.name == "testcity-20261201.zip"
    with zipfile.ZipFile(z) as zf:
        assert sorted(zf.namelist()) == ["manifest.json", "map.mbtiles", "places.sqlite"]
        m = json.loads(zf.read("manifest.json"))
        for name in ("map.mbtiles", "places.sqlite"):
            assert m["files"][name]["sha256"] == hashlib.sha256(zf.read(name)).hexdigest()
            assert m["files"][name]["bytes"] == len(zf.read(name))
    assert m["slug"] == "testcity" and m["version"] == "20261201" and m["place_count"] == 3
    assert m["bbox"] == [121.0, 31.0, 122.0, 32.0] and m["region_name_vi"] == "Vùng"
    assert validate_pack(z, CITY) == []


def test_validate_too_big(tmp_path):
    z = _build(tmp_path)
    errors = validate_pack(z, CITY, max_mb=0)
    assert any("dung lượng" in e for e in errors)


def test_validate_few_places(tmp_path):
    city = CityConfig(**{**CITY.__dict__, "min_places": 10})
    z = _build(tmp_path, city=city)
    assert any("địa điểm" in e for e in validate_pack(z, city))


def test_validate_out_of_bbox(tmp_path):
    far = Place("n99", "eat", "远店", None, "yuan dian", 40.0, 121.5, None, "{}")
    z = _build(tmp_path, places=_places(2) + [far])
    assert any("ngoài" in e for e in validate_pack(z, CITY))


def test_validate_empty_name_zh(tmp_path):
    bad = _places(2) + [Place("n9", "eat", " ", None, "", 31.5, 121.5, None, "{}")]
    z = _build(tmp_path, places=bad)
    assert any("chữ Hán" in e for e in validate_pack(z, CITY))


def test_validate_checksum_tamper(tmp_path):
    z = _build(tmp_path)
    tampered = tmp_path / "t.zip"
    with zipfile.ZipFile(z) as src, zipfile.ZipFile(tampered, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, b"x" if n == "map.mbtiles" else src.read(n))
    assert any("sha256" in e for e in validate_pack(tampered, CITY))


def test_next_version(tmp_path):
    assert next_version(tmp_path, "a", "20261201") == "20261201"
    (tmp_path / "a-20261201.zip").write_bytes(b"")
    assert next_version(tmp_path, "a", "20261201") == "20261201.1"
    (tmp_path / "a-20261201.1.zip").write_bytes(b"")
    assert next_version(tmp_path, "a", "20261201") == "20261201.2"


def test_planetiler_command_downloads_and_caches_sources(tmp_path):
    from pipeline.pack import TOOLS, planetiler_command
    cmd = planetiler_command(tmp_path / "c.pbf", (1.0, 2.0, 3.0, 4.0), tmp_path / "m.mbtiles")
    assert "--download" in cmd
    assert f"--download_dir={TOOLS / 'sources'}" in cmd
    assert "--bounds=1.0,2.0,3.0,4.0" in cmd


FAKE_NET = {"schema": 1, "lines": [{"id": "1"}], "stations": [{"id": "s0"}, {"id": "s1"}], "edges": [], "routes": []}
FARE = {"base_yuan": 3, "base_km": 4, "steps_km": [4, 4, 4, 7, 7, 10, 10], "then_every_km": 15, "source": "test"}


def test_metro_pack_includes_metro_json_with_fare(tmp_path):
    city = CityConfig(**{**CITY.__dict__, "has_metro": True, "min_metro_stations": 2, "metro_fare": FARE})
    calls = []
    def metro(pbf, bbox, min_stations):
        calls.append(min_stations)
        return dict(FAKE_NET)
    def extractor(src, bbox, out):
        out.write_bytes(b"pbf")
    z = build_pack(city, tmp_path / "china.osm.pbf", tmp_path / "dist", "20261201",
                   tiles_builder=lambda a, b, out: out.write_bytes(b"\0"), extractor=extractor,
                   places_extractor=lambda pbf, bbox: _places(), metro_builder=metro)
    assert calls == [2]
    with zipfile.ZipFile(z) as zf:
        assert "metro.json" in zf.namelist()
        net = json.loads(zf.read("metro.json"))
        m = json.loads(zf.read("manifest.json"))
    assert net["fare"] == FARE and len(net["stations"]) == 2
    with zipfile.ZipFile(z) as zf:
        assert m["files"]["metro.json"]["sha256"] == hashlib.sha256(zf.read("metro.json")).hexdigest()
    assert m["metro_station_count"] == 2


def test_city_without_metro_has_no_metro_json(tmp_path):
    with zipfile.ZipFile(_build(tmp_path)) as zf:
        assert "metro.json" not in zf.namelist()


def _metro_pack(tmp_path):
    city = CityConfig(**{**CITY.__dict__, "has_metro": True, "min_metro_stations": 2, "metro_fare": FARE})
    z = build_pack(city, tmp_path / "china.osm.pbf", tmp_path / "dist", "20261201",
                   tiles_builder=lambda a, b, out: out.write_bytes(b"\0"), extractor=lambda s, b, o: o.write_bytes(b"pbf"),
                   places_extractor=lambda pbf, bbox: _places(), metro_builder=lambda p, b, m: dict(FAKE_NET))
    return city, z


def test_validate_metro_pack_ok(tmp_path):
    city, z = _metro_pack(tmp_path)
    assert validate_pack(z, city) == []


def test_validate_metro_checksum_tamper(tmp_path):
    city, z = _metro_pack(tmp_path)
    with zipfile.ZipFile(z) as zf:
        parts = {n: zf.read(n) for n in zf.namelist()}
    parts["metro.json"] = b'{"stations":[]}'
    with zipfile.ZipFile(z, "w") as zf:
        for n, data in parts.items():
            zf.writestr(n, data)
    assert any("metro.json" in e for e in validate_pack(z, city))


def test_validate_metro_city_missing_metro_json(tmp_path):
    city = CityConfig(**{**CITY.__dict__, "has_metro": True})
    z = _build(tmp_path)  # dựng như thành phố không có metro
    assert any("metro.json" in e for e in validate_pack(z, city))
