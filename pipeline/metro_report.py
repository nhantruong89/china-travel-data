"""In tóm tắt metro.json để duyệt trong log CI (artifact không tải được từ mọi nơi).

python -m pipeline.metro_report review/shanghai-*-metro.json
"""
from __future__ import annotations

import heapq
import json
import sys
from collections import defaultdict


def shortest_km(net: dict, a: str, b: str) -> float | None:
    adj = defaultdict(list)
    for e in net["edges"]:
        adj[e["a"]].append((e["b"], e["km"]))
        adj[e["b"]].append((e["a"], e["km"]))
    dist = {a: 0.0}
    q = [(0.0, a)]
    while q:
        d, u = heapq.heappop(q)
        if u == b:
            return d
        if d > dist.get(u, 1e18):
            continue
        for v, w in adj[u]:
            if d + w < dist.get(v, 1e18):
                dist[v] = d + w
                heapq.heappush(q, (d + w, v))
    return None


def components(net: dict) -> int:
    adj = defaultdict(set)
    for e in net["edges"]:
        adj[e["a"]].add(e["b"])
        adj[e["b"]].add(e["a"])
    seen, n = set(), 0
    for s in net["stations"]:
        if s["id"] in seen:
            continue
        n += 1
        stack = [s["id"]]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(adj[u] - seen)
    return n


def report(net: dict, pairs: list[tuple[str, str]]) -> list[str]:
    out = []
    by_zh = {s["name_zh"]: s for s in net["stations"]}
    st = {s["id"]: s for s in net["stations"]}
    per_line = defaultdict(set)
    for e in net["edges"]:
        per_line[e["line"]].update((e["a"], e["b"]))
    out.append(f"tuyến {len(net['lines'])} · ga {len(net['stations'])} · cạnh {len(net['edges'])} · nhóm liên thông {components(net)}")
    for l in net["lines"]:
        out.append(f"  {l['id']:>6} {l['name_zh']:<10} {l['name_vi']:<12} {len(per_line[l['id']]):>3} ga  {l.get('colour') or '-'}")
    km = sorted(net["edges"], key=lambda e: -e["km"])
    out.append("cạnh dài nhất: " + ", ".join(f"{st[e['a']]['name_zh']}–{st[e['b']]['name_zh']} ({e['line']}) {e['km']:.1f}km" for e in km[:8]))
    short = [e for e in net["edges"] if e["km"] < 0.3]
    out.append(f"cạnh < 0,3 km: {len(short)}")
    no_hv = [s["name_zh"] for s in net["stations"] if not s.get("hanviet")]
    out.append(f"ga thiếu Hán-Việt: {len(no_hv)} {no_hv[:15]}")
    import re
    partial = [s["hanviet"] for s in net["stations"] if s.get("hanviet") and re.search(r"[\u3400-\u9fff]", s["hanviet"])]
    out.append(f"Hán-Việt còn chữ Hán: {len(partial)} {partial[:15]}")
    out.append(f"ga thiếu tên Anh: {sum(1 for s in net['stations'] if not s.get('name_en'))}")
    for a, b in pairs:
        if a in by_zh and b in by_zh:
            d = shortest_km(net, by_zh[a]["id"], by_zh[b]["id"])
            out.append(f"{a} → {b}: {'không nối' if d is None else f'{d:.1f} km'}")
        else:
            out.append(f"{a} → {b}: thiếu ga {[x for x in (a, b) if x not in by_zh]}")
    return out


SHANGHAI_PAIRS = [("人民广场", "豫园"), ("人民广场", "陆家嘴"), ("虹桥火车站", "人民广场"), ("虹桥火车站", "浦东1号2号航站楼"),
                  ("静安寺", "徐家汇"), ("南京东路", "迪士尼"), ("上海火车站", "人民广场")]

if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(f"== {path}")
        print("\n".join(report(json.load(open(path, encoding="utf-8")), SHANGHAI_PAIRS)))
