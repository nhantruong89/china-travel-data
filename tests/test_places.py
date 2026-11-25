import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.places import Place, classify, fts_query, place_from_tags, write_places_db

FIXTURE = Path(__file__).parent / "fixtures" / "mini.osm"
SHANGHAI_BBOX = (120.85, 30.67, 122.00, 31.88)


def test_classify():
    assert classify({"amenity": "restaurant"}) == "eat"
    assert classify({"tourism": "museum"}) == "see"
    assert classify({"historic": "temple"}) == "see"
    assert classify({"leisure": "park"}) == "see"
    assert classify({"tourism": "hotel"}) == "stay"
    assert classify({"shop": "bakery"}) is None


def test_place_from_tags_prefers_zh_hans_and_builds_address():
    p = place_from_tags(
        "n1",
        {"amenity": "cafe", "name": "Blue Cafe", "name:zh": "蓝咖啡", "name:zh-Hans": "蓝色咖啡",
         "addr:city": "上海市", "addr:street": "南京路", "addr:housenumber": "1"},
        31.2, 121.4, pinyin=lambda s: "py",
    )
    assert p.name_zh == "蓝色咖啡"
    assert p.address_zh == "上海市 南京路 1"
    assert p.kind == "eat"
    assert json.loads(p.tags_json)["amenity"] == "cafe"


def test_place_from_tags_skips_unnamed_and_unclassified():
    assert place_from_tags("n3", {"amenity": "restaurant"}, 31.2, 121.4, pinyin=str) is None
    assert place_from_tags("n4", {"shop": "bakery", "name": "面包"}, 31.2, 121.4, pinyin=str) is None


def test_pinyin():
    pypinyin = pytest.importorskip("pypinyin")
    from pipeline.places import to_pinyin
    assert to_pinyin("外滩") == "wài tān"


def test_extract_from_fixture():
    pytest.importorskip("osmium")
    pytest.importorskip("pypinyin")
    from pipeline.places import extract_places
    places = extract_places(FIXTURE, SHANGHAI_BBOX)
    names = sorted(p.name_zh for p in places)
    assert names == ["上海博物馆", "南翔馒头店", "和平饭店"]
    museum = next(p for p in places if p.name_zh == "上海博物馆")
    assert museum.osm_id == "w100" and museum.kind == "see"
    assert 31.2 < museum.lat < 31.21 and 121.4 < museum.lon < 121.41


def _place(osm_id, name_zh, pinyin, kind="see", name_en=None):
    return Place(osm_id, kind, name_zh, name_en, pinyin, 31.24, 121.49, None, "{}")


def test_fts_search(tmp_path):
    db = tmp_path / "places.sqlite"
    n = write_places_db([_place("n1", "外滩", "wài tān", name_en="The Bund"),
                         _place("n2", "豫园", "yù yuán")], db)
    assert n == 2
    con = sqlite3.connect(db)
    def search(text):
        rows = con.execute(
            "SELECT p.name_zh FROM places_fts f JOIN places p ON p.id = f.rowid WHERE places_fts MATCH ?",
            (fts_query(text),)).fetchall()
        return [r[0] for r in rows]
    assert search("外滩") == ["外滩"]
    assert search("wai") == ["外滩"]
    assert search("bund") == ["外滩"]
    assert search("豫") == ["豫园"]
    assert con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() == ("1",)
