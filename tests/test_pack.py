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
