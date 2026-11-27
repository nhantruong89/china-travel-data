"""Đo tìm địa điểm bằng tiếng Việt trên gói đã dựng, theo đúng cách app tìm (ios/…/PlaceSearch.swift).

python -m pipeline.search_eval dist/*.zip   → in bảng Markdown: mỗi cách gõ có ra đúng nơi trong 5 kết quả đầu không.
Chỉ dùng để duyệt (CI ghi vào PR), không chặn việc đăng gói.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

from .hanviet import fold

# Từ loại tiếng Việt gõ trước tên → hậu tố Hán-Việt (giống PlaceSearch.categoryWords trong app).
CATEGORY_WORDS: list[tuple[list[str], list[str]]] = [
    (["bao", "tang"], ["bac vat quan", "bac vat vien"]), (["cong", "vien"], ["cong vien"]),
    (["quang", "truong"], ["quang truong"]), (["khach", "san"], ["tuu diem", "phan diem", "tan quan"]),
    (["san", "bay"], ["co truong"]), (["benh", "vien"], ["y vien"]), (["nha", "ga"], ["tram"]),
    (["nha", "tho"], ["giao duong"]), (["pho", "co"], ["nhai", "lo"]), (["thi", "tran"], ["tran"]),
    (["co", "tran"], ["co tran"]), (["chua"], ["tu", "am"]), (["den"], ["mieu", "tu"]), (["mieu"], ["mieu"]),
    (["thap"], ["thap"]), (["pho"], ["nhai", "lo"]), (["duong"], ["lo", "nhai"]), (["ga"], ["tram"]),
    (["vuon"], ["vien", "lam"]), (["ho"], ["ho"]), (["cau"], ["kieu"]), (["nui"], ["son"]),
    (["cho"], ["thi truong"]), (["song"], ["giang", "ha"]), (["dao"], ["dao"]), (["lang"], ["thon"]),
    (["dinh"], ["dinh"]),
]

# Cách người Việt hay gõ → chữ Hán phải có trong tên kết quả.
CASES: dict[str, list[tuple[str, str]]] = {
    "hangzhou": [
        ("Tây Hồ", "西湖"), ("hồ Tây", "西湖"), ("Linh Ẩn Tự", "灵隐寺"), ("chùa Linh Ẩn", "灵隐寺"),
        ("Lôi Phong Tháp", "雷峰塔"), ("tháp Lôi Phong", "雷峰塔"), ("Lục Hòa Tháp", "六和塔"), ("Tô Đê", "苏堤"),
        ("Bạch Đê", "白堤"), ("Đoạn Kiều", "断桥"), ("Tam Đàm Ấn Nguyệt", "三潭印月"), ("Hà Phường Nhai", "河坊街"),
        ("phố Hà Phường", "河坊街"), ("Long Tỉnh", "龙井"), ("Tây Khê", "西溪"), ("Nhạc Vương Miếu", "岳王庙"),
        ("Tịnh Từ Tự", "净慈寺"), ("Hoa Cảng Quan Ngư", "花港观鱼"), ("Tống Thành", "宋城"), ("Củng Thần Kiều", "拱宸桥"),
        ("Thành Hoàng Các", "城隍阁"), ("Ngô Sơn", "吴山"), ("Hàng Châu Đông", "杭州东"), ("ga Hàng Châu Đông", "杭州东"),
        ("Bảo Thục Tháp", "保俶塔"), ("Cô Sơn", "孤山"), ("Vũ Lâm Quảng Trường", "武林广场"), ("Hồ Tân", "湖滨"),
    ],
    "suzhou": [
        ("Chuyết Chính Viên", "拙政园"), ("vườn Chuyết Chính", "拙政园"), ("Lưu Viên", "留园"), ("Sư Tử Lâm", "狮子林"),
        ("Võng Sư Viên", "网师园"), ("Thương Lang Đình", "沧浪亭"), ("Hổ Khâu", "虎丘"), ("Hàn Sơn Tự", "寒山寺"),
        ("chùa Hàn Sơn", "寒山寺"), ("Bình Giang Lộ", "平江路"), ("phố Bình Giang", "平江路"), ("Sơn Đường Nhai", "山塘街"),
        ("Quan Tiền Nhai", "观前街"), ("Huyền Diệu Quán", "玄妙观"), ("Kim Kê Hồ", "金鸡湖"), ("hồ Kim Kê", "金鸡湖"),
        ("Tô Châu Bác Vật Quán", "苏州博物馆"), ("bảo tàng Tô Châu", "苏州博物馆"), ("Bàn Môn", "盘门"), ("Đồng Lý", "同里"),
        ("Mộc Độc", "木渎"), ("Phong Kiều", "枫桥"), ("Di Viên", "怡园"), ("Ngẫu Viên", "耦园"), ("Bắc Tự Tháp", "北寺塔"),
        ("Đông Phương Chi Môn", "东方之门"), ("ga Tô Châu", "苏州站"), ("Tô Châu Trạm", "苏州站"),
        ("Tô Châu Bắc Trạm", "苏州北站"),
    ],
    "shanghai": [
        ("Ngoại Than", "外滩"), ("Dự Viên", "豫园"), ("Tĩnh An Tự", "静安寺"), ("chùa Tĩnh An", "静安寺"),
        ("Ngọc Phật Tự", "玉佛寺"), ("chùa Ngọc Phật", "玉佛寺"), ("Nam Kinh Đông Lộ", "南京东路"),
        ("Điền Tử Phường", "田子坊"), ("Tân Thiên Địa", "新天地"), ("Chu Gia Giác", "朱家角"), ("Đông Phương Minh Châu", "东方明珠"),
        ("Hồng Kiều Hỏa Xa Trạm", "虹桥火车站"), ("Phố Đông Cơ Trường", "浦东机场"), ("sân bay Phố Đông", "浦东"),
        ("Nhân Dân Quảng Trường", "人民广场"), ("Long Hoa Tự", "龙华寺"), ("Thượng Hải Bác Vật Quán", "上海博物馆"),
    ],
}


def queries(text: str) -> list[str]:
    """Các truy vấn FTS app thử lần lượt (PlaceSearch.ftsQueries)."""
    raw = re.findall(r"[a-z0-9]+", fold(text).replace(" ", " "))
    words = fold(text).split()
    pre = " ".join(f'"{w}"*' for w in raw)
    out = [f'({{name_zh_chars name_en pinyin}} : ({pre}) OR hanviet : "{" ".join(words)}")']
    for cat, suffixes in CATEGORY_WORDS:
        if len(words) > len(cat) and words[: len(cat)] == cat:
            name = " ".join(words[len(cat):])
            out.append("hanviet : (" + " OR ".join(f'"{name} {s}"' for s in suffixes) + ")")
            out.append(f'hanviet : "{name}"')
            break
    return out


def top(con: sqlite3.Connection, text: str, n: int = 5) -> list[str]:
    for q in queries(text):
        rows = con.execute(
            "SELECT p.name_zh FROM places_fts JOIN places p ON p.id = places_fts.rowid "
            "WHERE places_fts MATCH ? ORDER BY bm25(places_fts) LIMIT ?", (q, n)).fetchall()
        if rows:
            return [r[0] for r in rows]
    return []


def evaluate(places_db: Path, cases: list[tuple[str, str]]) -> list[tuple[str, str, bool, list[str]]]:
    con = sqlite3.connect(places_db)
    out = []
    for typed, want in cases:
        found = top(con, typed)
        out.append((typed, want, any(want in z for z in found), found[:3]))
    return out


def main(zips: list[str]) -> int:
    lines = ["### Tìm bằng tiếng Việt (5 kết quả đầu)", ""]
    for z in zips:
        slug = Path(z).name.split("-")[0]
        if slug not in CASES:
            continue
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(z) as zf:
            zf.extract("places.sqlite", tmp)
            res = evaluate(Path(tmp) / "places.sqlite", CASES[slug])
        ok = sum(r[2] for r in res)
        lines.append(f"**{slug}: {ok}/{len(res)}**")
        misses = [f"`{t}` → {w}: {', '.join(f) or '(không có)'}" for t, w, hit, f in res if not hit]
        lines += [f"- ✗ {m}" for m in misses] + [""]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
