"""Trích địa điểm ăn uống / tham quan / lưu trú từ OpenStreetMap vào places.sqlite.

Quy ước tìm kiếm (app Swift phải theo, cũng ghi trong bảng meta):
- Chữ Hán: tách từng ký tự bằng dấu cách, truy vấn dạng cụm: "外 滩"
- Chữ Latin (pinyin, tiếng Anh): từng từ thành tiền tố: wai* tan*
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import astuple, dataclass
from pathlib import Path
from typing import Callable, Literal

from .hanviet import fold, to_hanviet

Kind = Literal["eat", "see", "stay", "transit", "shop", "service"]

EAT_AMENITY = {"restaurant", "cafe", "fast_food", "food_court", "bar", "pub", "ice_cream"}
SEE_TOURISM = {"attraction", "museum", "viewpoint", "gallery", "zoo", "theme_park", "artwork"}
SEE_LEISURE = {"park", "garden"}
STAY_TOURISM = {"hotel", "hostel", "guest_house", "motel", "apartment"}
TRANSIT_RAILWAY = {"station", "halt"}
TRANSIT_AMENITY = {"bus_station", "ferry_terminal"}
TRANSIT_AEROWAY = {"aerodrome", "terminal"}
SHOP_SHOP = {"mall", "department_store", "supermarket", "convenience"}
SERVICE_AMENITY = {"hospital", "clinic", "pharmacy", "toilets", "atm", "bank", "police"}
# Tên mặc định khi đối tượng không có tên (nhà vệ sinh, ATM rất hay không đặt tên trên OSM).
DEFAULT_NAMES = {"toilets": "公共厕所", "atm": "ATM"}
ADDRESS_KEYS = ("addr:city", "addr:district", "addr:street", "addr:housenumber")

SCHEMA_VERSION = "2"  # 2: thêm cột hanviet
QUERY_CONVENTION = "cjk: chars space-separated as phrase; latin: prefix tokens"

_CJK = re.compile(r"[㐀-鿿豈-﫿]")


@dataclass
class Place:
    osm_id: str
    kind: str
    name_zh: str
    name_en: str | None
    pinyin: str
    lat: float
    lon: float
    address_zh: str | None
    tags_json: str
    hanviet: str | None = None


def classify(tags: dict[str, str]) -> Kind | None:
    amenity = tags.get("amenity")
    if amenity in EAT_AMENITY:
        return "eat"
    if (tags.get("railway") in TRANSIT_RAILWAY or tags.get("station") == "subway"
            or tags.get("public_transport") == "station" or amenity in TRANSIT_AMENITY
            or tags.get("aeroway") in TRANSIT_AEROWAY):
        return "transit"
    if tags.get("shop") in SHOP_SHOP or amenity == "marketplace":
        return "shop"
    if amenity in SERVICE_AMENITY:
        return "service"
    tourism = tags.get("tourism")
    if tourism in STAY_TOURISM:
        return "stay"
    if tourism in SEE_TOURISM or "historic" in tags or tags.get("leisure") in SEE_LEISURE:
        return "see"
    # Chùa, đạo quán, nhà thờ: nhiều nơi nổi tiếng (寒山寺, 净慈寺, 玄妙观) chỉ có thẻ này.
    if amenity == "place_of_worship":
        return "see"
    # Phố đi bộ / đê đi bộ (平江路, 白堤). Mỗi tên giữ một đoạn — xem dedupe_streets.
    if tags.get("highway") == "pedestrian":
        return "see"
    return None


def to_pinyin(text: str) -> str:
    from pypinyin import Style, lazy_pinyin

    return " ".join(s for s in lazy_pinyin(text, style=Style.TONE) if s.strip())


def place_from_tags(
    osm_id: str, tags: dict[str, str], lat: float, lon: float, pinyin: Callable[[str], str] = to_pinyin,
    hanviet: Callable[[str], str | None] | None = None,
) -> Place | None:
    kind = classify(tags)
    if kind is None:
        return None
    name_zh = tags.get("name:zh-Hans") or tags.get("name:zh") or tags.get("name")
    if not name_zh:
        default = DEFAULT_NAMES.get(tags.get("amenity", ""))
        if not default:
            return None
        operator = tags.get("operator")
        name_zh = f"{operator} {default}" if operator and default == "ATM" else default
    address = " ".join(tags[k] for k in ADDRESS_KEYS if tags.get(k))
    return Place(
        osm_id=osm_id,
        kind=kind,
        name_zh=name_zh,
        name_en=tags.get("name:en"),
        pinyin=pinyin(name_zh),
        lat=lat,
        lon=lon,
        address_zh=address or None,
        tags_json=json.dumps(tags, ensure_ascii=False, sort_keys=True),
        hanviet=hanviet(name_zh) if hanviet else None,
    )


def _inside(lat: float, lon: float, bbox) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def extract_places(osm_path: Path, bbox, hanviet_table: dict[str, str] | None = None) -> list[Place]:
    import osmium

    places: dict[str, Place] = {}
    fp = osmium.FileProcessor(str(osm_path)).with_locations().with_areas()
    for obj in fp:
        tags = dict(obj.tags)
        if classify(tags) is None:
            continue
        if obj.is_area():
            # vùng từ way đóng đã được xử lý ở nhánh way; chỉ lấy vùng dựng từ quan hệ (multipolygon)
            if obj.from_way():
                continue
            pts = [(n.lat, n.lon) for ring in obj.outer_rings() for n in ring if n.location.valid()]
            if not pts:
                continue
            lat = sum(p[0] for p in pts) / len(pts)
            lon = sum(p[1] for p in pts) / len(pts)
            oid = f"r{obj.orig_id()}"
        elif obj.is_node():
            if not obj.location.valid():
                continue
            lat, lon, oid = obj.location.lat, obj.location.lon, f"n{obj.id}"
        elif obj.is_way():
            pts = [(n.lat, n.lon) for n in obj.nodes if n.location.valid()]
            if not pts:
                continue
            lat = sum(p[0] for p in pts) / len(pts)
            lon = sum(p[1] for p in pts) / len(pts)
            oid = f"w{obj.id}"
        else:
            continue  # relation thô (đã xử lý qua area)
        if not _inside(lat, lon, bbox):
            continue
        hv = (lambda name: to_hanviet(name, hanviet_table)) if hanviet_table else None
        p = place_from_tags(oid, tags, lat, lon, hanviet=hv)
        if p is not None:
            places[oid] = p
    return dedupe_streets(list(places.values()))


def dedupe_streets(places: list[Place]) -> list[Place]:
    """Phố đi bộ trên OSM chia nhiều đoạn cùng tên: chỉ giữ đoạn đầu tiên của mỗi tên."""
    seen: set[str] = set()
    out: list[Place] = []
    for p in places:
        if '"highway": "pedestrian"' in p.tags_json:
            if p.name_zh in seen:
                continue
            seen.add(p.name_zh)
        out.append(p)
    return out


def _zh_chars(text: str) -> str:
    return " ".join(ch for ch in text if not ch.isspace())


def fts_query(text: str) -> str:
    """Biến chuỗi người dùng gõ thành truy vấn FTS5 theo quy ước của places.sqlite."""
    parts: list[str] = []
    cjk = "".join(_CJK.findall(text))
    if cjk:
        parts.append('"' + " ".join(cjk) + '"')
    latin = _CJK.sub(" ", text)
    for word in re.findall(r"\w+", latin.lower()):
        parts.append(f'"{word}"*')
    return " ".join(parts) if parts else '""'


def write_places_db(places: list[Place], out: Path) -> int:
    out = Path(out)
    if out.exists():
        out.unlink()
    con = sqlite3.connect(out)
    try:
        con.executescript(
            """
            CREATE TABLE places(
              id INTEGER PRIMARY KEY, osm_id TEXT UNIQUE, kind TEXT NOT NULL,
              name_zh TEXT NOT NULL, name_en TEXT, pinyin TEXT NOT NULL,
              lat REAL NOT NULL, lon REAL NOT NULL, address_zh TEXT, tags_json TEXT, hanviet TEXT);
            CREATE INDEX places_kind ON places(kind);
            CREATE VIRTUAL TABLE places_fts USING fts5(
              name_zh_chars, name_en, pinyin, hanviet, tokenize='unicode61 remove_diacritics 2');
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
            """
        )
        for p in places:
            cur = con.execute(
                "INSERT INTO places(osm_id, kind, name_zh, name_en, pinyin, lat, lon, address_zh, tags_json, hanviet)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                astuple(p),
            )
            con.execute(
                "INSERT INTO places_fts(rowid, name_zh_chars, name_en, pinyin, hanviet) VALUES (?,?,?,?,?)",
                (cur.lastrowid, _zh_chars(p.name_zh), p.name_en or "", p.pinyin, fold(p.hanviet) if p.hanviet else ""),
            )
        con.executemany(
            "INSERT INTO meta(key, value) VALUES (?,?)",
            [("schema_version", SCHEMA_VERSION), ("query_convention", QUERY_CONVENTION)],
        )
        con.commit()
    finally:
        con.close()
    return len(places)
