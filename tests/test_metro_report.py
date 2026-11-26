from pipeline.metro_report import report, shortest_km


NET = {
    "lines": [{"id": "1", "name_zh": "1号线", "name_vi": "Tuyến 1", "colour": None}],
    "stations": [
        {"id": "a", "name_zh": "甲", "hanviet": "Giáp", "name_en": "A"},
        {"id": "b", "name_zh": "乙", "hanviet": None, "name_en": "B"},
        {"id": "c", "name_zh": "丙", "hanviet": "Bính", "name_en": None},
        {"id": "d", "name_zh": "丁", "hanviet": "Đinh", "name_en": "D"},
    ],
    "edges": [{"a": "a", "b": "b", "line": "1", "km": 1.5}, {"a": "b", "b": "c", "line": "1", "km": 2.0}],
}


def test_shortest_km_and_disconnected():
    assert shortest_km(NET, "a", "c") == 3.5
    assert shortest_km(NET, "a", "d") is None


def test_report_flags_gaps():
    text = "\n".join(report(NET, [("甲", "丙"), ("甲", "丁"), ("甲", "戊")]))
    assert "nhóm liên thông 2" in text
    assert "ga thiếu Hán-Việt: 1 ['乙']" in text
    assert "甲 → 丙: 3.5 km" in text
    assert "甲 → 丁: không nối" in text
    assert "thiếu ga ['戊']" in text
