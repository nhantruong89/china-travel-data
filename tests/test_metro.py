import json
from pathlib import Path

import pytest

from pipeline.metro import MetroError, build_metro, chain_ways, haversine_km, segment_km, station_key

FIX = Path(__file__).parent / "fixtures" / "mini_metro.osm"
BBOX = (121.0, 31.0, 122.0, 31.5)


def test_station_key_ignores_station_suffix_and_spaces():
    assert station_key("人民广场站") == station_key(" 人民广场 ") == "人民广场"


def test_chain_ways_orients_and_joins():
    a = [(0.0, 0.0), (0.0, 1.0)]
    b = [(0.0, 2.0), (0.0, 1.0)]  # ngược chiều
    assert chain_ways([a, b]) == [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]


def test_segment_distance_follows_track_not_straight_line():
    line = [(31.2, 121.40), (31.22, 121.425), (31.2, 121.45)]
    along = segment_km(line, (31.2, 121.40), (31.2, 121.45))
    straight = haversine_km((31.2, 121.40), (31.2, 121.45))
    assert along > straight * 1.2


def test_build_metro_from_osm():
    net = build_metro(FIX, BBOX, min_stations=5)
    names = {s["name_zh"] for s in net["stations"]}
    assert names == {"富锦路", "人民广场", "莘庄", "龙阳路", "虹桥"}, "tàu hoả không lấy; 人民广场站 = 人民广场"
    ps = next(s for s in net["stations"] if s["name_zh"] == "人民广场")
    assert sorted(ps["lines"]) == ["1", "2"], "ga đổi tuyến"
    assert ps["name_en"] == "People's Square"
    lines = {l["id"]: l for l in net["lines"]}
    assert lines["1"]["name_vi"] == "Tuyến 1" and lines["1"]["name_zh"] == "1号线" and lines["1"]["colour"] == "#E3002B"
    assert lines["2"]["colour"] == "#8CC220"
    # Cạnh không hướng, gộp hai chiều: 富锦路–人民广场 đi theo đường cong (> đường thẳng ~4,76 km)
    sid = {s["name_zh"]: s["id"] for s in net["stations"]}
    e = next(e for e in net["edges"] if {e["a"], e["b"]} == {sid["富锦路"], sid["人民广场"]})
    assert e["line"] == "1" and e["km"] > 5.5
    assert len([e for e in net["edges"] if e["line"] == "1"]) == 2
    # Hướng chạy: mỗi chiều một dãy ga, giữ ga đầu/cuối
    seqs = [r["stops"] for r in net["routes"] if r["line"] == "2"]
    assert [sid["龙阳路"], sid["人民广场"], sid["虹桥"]] in seqs
    assert [sid["虹桥"], sid["人民广场"], sid["龙阳路"]] in seqs


def test_too_few_stations_fails_build():
    with pytest.raises(MetroError):
        build_metro(FIX, BBOX, min_stations=300)


def test_json_is_compact_and_serialisable():
    net = build_metro(FIX, BBOX, min_stations=5)
    text = json.dumps(net, ensure_ascii=False, separators=(",", ":"))
    assert "人民广场" in text and len(text) < 5000


def test_chain_ways_flips_first_way_when_needed():
    a = [(0.0, 1.0), (0.0, 0.0)]  # đoạn đầu lưu ngược
    b = [(0.0, 1.0), (0.0, 2.0)]
    assert chain_ways([a, b]) == [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
