"""Mạng tàu điện ngầm của thành phố từ OpenStreetMap → metro.json trong gói.

- Tuyến: quan hệ type=route, route ∈ {subway, light_rail, monorail}; gộp theo ref (hai chiều, nhánh).
- Ga: thành viên vai trò stop* (stop_position), gộp theo tên chữ Hán (bỏ chữ 站 ở cuối) trong bán kính 1,5 km
  → ga đổi tuyến là một ga.
- Khoảng cách giữa hai ga liền nhau: đo dọc đường ray (các way của tuyến nối lại), không phải đường thẳng —
  để ước tính giá vé theo quãng đường.
Giá vé (bậc km) do app tính, quy tắc lấy từ file thành phố (metro_fare).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

METRO_ROUTES = {"subway", "light_rail", "monorail"}
GROUP_RADIUS_KM = 1.5


class MetroError(Exception):
    pass


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def station_key(name: str) -> str:
    n = re.sub(r"\s+", "", name)
    return n[:-1] if n.endswith("站") and len(n) > 1 else n


def chain_ways(ways: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    """Nối các đoạn đường ray thành một đường; đảo chiều đoạn nào cần thiết. Đoạn không nối được thì nối thẳng."""
    ways = [w for w in ways if w]
    if not ways:
        return []
    line = list(ways[0])
    # Đoạn đầu lưu ngược (đoạn thứ hai nối vào đầu kia) → đảo đoạn đầu.
    if len(ways) > 1 and line[0] in (ways[1][0], ways[1][-1]) and line[-1] not in (ways[1][0], ways[1][-1]):
        line.reverse()
    for w in ways[1:]:
        if line[-1] == w[0]:
            line += w[1:]
        elif line[-1] == w[-1]:
            line += list(reversed(w))[1:]
        elif haversine_km(line[-1], w[0]) <= haversine_km(line[-1], w[-1]):
            line += w  # chỗ hở (dữ liệu thiếu) — nối thẳng theo đầu gần hơn
        else:
            line += list(reversed(w))
    return line


def _cumulative(line: list[tuple[float, float]]) -> list[float]:
    cum = [0.0]
    for p, q in zip(line, line[1:]):
        cum.append(cum[-1] + haversine_km(p, q))
    return cum


def _nearest_index(line: list[tuple[float, float]], p: tuple[float, float]) -> int:
    return min(range(len(line)), key=lambda i: (line[i][0] - p[0]) ** 2 + (line[i][1] - p[1]) ** 2)


def segment_km(line: list[tuple[float, float]], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Quãng đường dọc `line` giữa hai điểm (chiếu về đỉnh gần nhất). Không có đường ray → đường thẳng × 1,2."""
    if len(line) < 2:
        return haversine_km(a, b) * 1.2
    cum = _cumulative(line)
    i, j = _nearest_index(line, a), _nearest_index(line, b)
    along = abs(cum[j] - cum[i])
    straight = haversine_km(a, b)
    # Chiếu sai (vd đường ray thiếu) → không tin số quá nhỏ/quá lớn.
    if along < straight * 0.9 or along > straight * 3:
        return straight * 1.2
    return along


@dataclass
class _Route:
    line: str
    colour: str | None
    name: str | None
    stops: list[int] = field(default_factory=list)  # node id theo thứ tự
    ways: list[int] = field(default_factory=list)


def _line_names(ref: str) -> tuple[str, str, str]:
    if ref.isdigit():
        return f"{ref}号线", f"Line {ref}", f"Tuyến {ref}"
    return ref, ref, ref


def build_metro(osm_path: Path, bbox, min_stations: int, hanviet: Callable[[str], str | None] | None = None) -> dict:
    import osmium

    # Lượt 1: các tuyến và thành viên.
    routes: list[_Route] = []
    for rel in osmium.FileProcessor(str(osm_path), osmium.osm.RELATION):
        tags = dict(rel.tags)
        if tags.get("type") != "route" or tags.get("route") not in METRO_ROUTES:
            continue
        ref = (tags.get("ref") or tags.get("name:zh") or tags.get("name") or "").strip()
        if not ref:
            continue
        r = _Route(line=ref, colour=tags.get("colour"), name=tags.get("name"))
        for m in rel.members:
            if m.type == "n" and m.role.startswith("stop"):
                r.stops.append(m.ref)
            elif m.type == "w" and m.role in ("", "forward", "backward"):
                r.ways.append(m.ref)
        if len(r.stops) >= 2:
            routes.append(r)

    want_nodes = {n for r in routes for n in r.stops}
    want_ways = {w for r in routes for w in r.ways}
    nodes: dict[int, tuple[float, float, dict]] = {}
    ways: dict[int, list[tuple[float, float]]] = {}
    for obj in osmium.FileProcessor(str(osm_path)).with_locations():
        if obj.is_node() and obj.id in want_nodes and obj.location.valid():
            nodes[obj.id] = (obj.location.lat, obj.location.lon, dict(obj.tags))
        elif obj.is_way() and obj.id in want_ways:
            ways[obj.id] = [(n.lat, n.lon) for n in obj.nodes if n.location.valid()]

    # Ga: gộp theo tên trong bán kính.
    stations: list[dict] = []
    node_station: dict[int, int] = {}

    def inside(lat: float, lon: float) -> bool:
        return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]

    for nid, (lat, lon, tags) in nodes.items():
        raw = tags.get("name:zh") or tags.get("name")
        if not raw or not inside(lat, lon):
            continue
        key = station_key(raw)
        match = next((s for s in stations if s["_key"] == key and haversine_km((s["lat"], s["lon"]), (lat, lon)) <= GROUP_RADIUS_KM), None)
        if match is None:
            match = {"_key": key, "_pts": [], "name_zh": key, "name_en": None, "lat": lat, "lon": lon, "lines": set()}
            stations.append(match)
        match["_pts"].append((lat, lon))
        if not match["name_en"] and tags.get("name:en"):
            match["name_en"] = tags["name:en"].strip()
        node_station[nid] = stations.index(match)

    lines: dict[str, dict] = {}
    edge_km: dict[tuple[int, int, str], list[float]] = {}
    seqs: list[dict] = []
    for r in routes:
        track = chain_ways([ways[w] for w in r.ways if w in ways])
        seq: list[int] = []
        pts: list[tuple[float, float]] = []
        for nid in r.stops:
            if nid not in node_station:
                continue
            sidx = node_station[nid]
            if seq and seq[-1] == sidx:
                continue
            seq.append(sidx)
            pts.append(nodes[nid][:2])
        if len(seq) < 2:
            continue
        zh, en, vi = _line_names(r.line)
        line = lines.setdefault(r.line, {"id": r.line, "name_zh": zh, "name_en": en, "name_vi": vi, "colour": None})
        line["colour"] = line["colour"] or r.colour
        for a, b, pa, pb in zip(seq, seq[1:], pts, pts[1:]):
            key = (min(a, b), max(a, b), r.line)
            edge_km.setdefault(key, []).append(segment_km(track, pa, pb))
        for s in seq:
            stations[s]["lines"].add(r.line)
        seqs.append({"line": r.line, "stops": seq})

    used = sorted({s for q in seqs for s in q["stops"]})
    if len(used) < min_stations:
        raise MetroError(f"chỉ có {len(used)} ga tàu điện (cần ít nhất {min_stations}) — dữ liệu OSM thiếu?")
    new_id = {old: f"s{i}" for i, old in enumerate(used)}

    out_stations = []
    for old in used:
        s = stations[old]
        lat = sum(p[0] for p in s["_pts"]) / len(s["_pts"])
        lon = sum(p[1] for p in s["_pts"]) / len(s["_pts"])
        item = {"id": new_id[old], "name_zh": s["name_zh"], "name_en": s["name_en"], "lat": round(lat, 6),
                "lon": round(lon, 6), "lines": sorted(s["lines"], key=_line_sort)}
        if hanviet:
            item["hanviet"] = hanviet(s["name_zh"])
        out_stations.append(item)
    return {
        "schema": 1,
        "lines": sorted(lines.values(), key=lambda l: _line_sort(l["id"])),
        "stations": out_stations,
        "edges": [{"a": new_id[a], "b": new_id[b], "line": line, "km": round(sum(k) / len(k), 3)}
                  for (a, b, line), k in sorted(edge_km.items())],
        "routes": [{"line": q["line"], "stops": [new_id[s] for s in q["stops"]]} for q in seqs],
    }


def _line_sort(ref: str):
    return (0, int(ref), "") if ref.isdigit() else (1, 0, ref)
