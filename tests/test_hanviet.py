import sqlite3
from pathlib import Path

from pipeline.hanviet import fold, load_unihan, to_hanviet
from pipeline.places import Place, write_places_db

TABLE = load_unihan(Path(__file__).parent / "fixtures" / "unihan_mini.txt")


def test_load_only_vietnamese_field():
    assert TABLE["外"] == "ngoại"
    assert TABLE["天"] == "thiên"
    assert len(TABLE) == 7


def test_to_hanviet_title_case():
    assert to_hanviet("外滩", TABLE) == "Ngoại Than"
    assert to_hanviet("豫园", TABLE) == "Dự Viên"


def test_keeps_digits_and_unknown_chars():
    assert to_hanviet("7天酒店", TABLE) == "7 Thiên Tửu Điếm"
    assert to_hanviet("外X滩", TABLE) == "Ngoại X Than"
    assert to_hanviet("外滩馆", TABLE) == "Ngoại Than 馆"


def test_none_when_no_reading():
    assert to_hanviet("Starbucks", TABLE) is None
    assert to_hanviet("馆", TABLE) is None


def test_fold():
    assert fold("Dự Viên") == "du vien"
    assert fold("Điếm") == "diem"


def test_places_db_has_hanviet_and_searchable(tmp_path):
    p = Place("n1", "see", "豫园", "Yu Garden", "yù yuán", 31.2, 121.4, None, "{}", hanviet="Dự Viên")
    db = tmp_path / "places.sqlite"
    write_places_db([p], db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT hanviet FROM places").fetchone() == ("Dự Viên",)
    assert con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() == ("2",)
    hit = con.execute("SELECT rowid FROM places_fts WHERE places_fts MATCH ?", ('"du"* "vien"*',)).fetchall()
    assert hit == [(1,)]


FIX = Path(__file__).parent / "fixtures"


def test_simplified_char_borrows_traditional_reading():
    # 馆 (giản thể) không có kVietnamese; 館 (phồn thể) có "quán".
    table = load_unihan(FIX / "unihan_trad_mini.txt", variants=FIX / "unihan_variants_mini.txt")
    assert table["馆"] == "quán"
    assert table["华"] == "hoa"
    assert table["館"] == "quán"


def test_own_reading_wins_over_traditional():
    readings = FIX / "unihan_mini.txt"
    table = load_unihan(readings, variants=FIX / "unihan_variants_mini.txt")
    assert table["滩"] == "than"
    assert len(table) == 7, "phồn thể không có trong tệp âm đọc thì không thêm gì"


def test_extra_readings_fill_only_missing():
    table = load_unihan(FIX / "unihan_mini.txt", extra={"北": "bắc", "外": "SAI"})
    assert table["北"] == "bắc"
    assert table["外"] == "ngoại"


def test_extra_readings_cover_metro_station_gaps():
    from pipeline.hanviet import EXTRA_READINGS
    table = load_unihan(FIX / "unihan_mini.txt", extra=EXTRA_READINGS)
    for name, want in {"张华浜": "Trương Hoa Banh", "龙华": "Long Hoa", "马陆": "Mã Lục", "赵巷": "Triệu Hạng",
                       "北蔡": "Bắc Thái", "颛桥": "Chuyên Kiều", "北桥": "Bắc Kiều", "菉葭": "Lục Gia", "夏桥": "Hạ Kiều"}.items():
        assert to_hanviet(name, table) == want, name


def test_extra_readings_cover_common_place_name_chars():
    # Unihan kVietnamese thiếu cả chữ rất thường gặp trong tên địa điểm (杭 街 寺 塔 酒 …).
    from pipeline.hanviet import EXTRA_READINGS
    table = load_unihan(FIX / "unihan_mini.txt", extra=EXTRA_READINGS)
    for ch, want in {"杭": "hàng", "街": "nhai", "寺": "tự", "塔": "tháp", "酒": "tửu", "浙": "chiết",
                     "湾": "loan", "滨": "tân", "峰": "phong"}.items():
        assert table.get(ch) == want, ch


def test_extra_readings_file_is_clean():
    from pipeline.hanviet import EXTRA_FILE, load_extra
    extra = load_extra(EXTRA_FILE)
    assert len(extra) > 800
    for ch, reading in extra.items():
        assert len(ch) == 1 and reading and reading == reading.lower() and " " not in reading, (ch, reading)


# --- Bảng phiên âm (Hán-Việt một âm mỗi chữ) ưu tiên hơn kVietnamese (thường là âm Nôm) ---

def _phienam(tmp_path, lines):
    p = tmp_path / "phienam.txt"
    p.write_text("﻿" + "\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_phienam_wins_over_nom_reading_from_unihan(tmp_path):
    from pipeline.hanviet import build_table
    ph = _phienam(tmp_path, ["园=viên", "里=lí", "东=đông", "外=ngoại"])
    table = build_table(unihan=None, phienam=ph)
    assert to_hanviet("同里", {**table, "同": "đồng"}) == "Đồng Lí"
    assert table["园"] == "viên"


def test_phienam_skips_entries_that_are_not_vietnamese_syllables(tmp_path):
    from pipeline.hanviet import load_phienam
    ph = _phienam(tmp_path, ["錫=connect", "麪=mian3", "苏=tô", "苏=xxx", "两字=lưỡng tự", "苏州=tô châu"])
    assert load_phienam(ph) == {"苏": "tô"}


def test_overrides_fix_simplified_chars_read_as_their_old_homograph(tmp_path):
    from pipeline.hanviet import build_table
    ph = _phienam(tmp_path, ["广=nghiễm", "台=thai", "厅=thính", "场=trường"])
    table = build_table(unihan=None, phienam=ph)
    assert table["广"] == "quảng" and table["台"] == "đài" and table["厅"] == "sảnh" and table["场"] == "trường"


def test_i_y_spelling_is_folded_the_same_way_for_data_and_query():
    from pipeline.hanviet import fold
    assert fold("Đồng Lý") == fold("Đồng Lí") == "dong li"
    assert fold("Mỹ Kỳ") == "mi ki"
    assert fold("Thuỷ Huy Quy") == "thuy huy quy", "uy/quy giữ nguyên"
    assert fold("Tây") == "tay"


def test_fts_matches_both_spellings(tmp_path):
    p = Place("n1", "see", "同里", None, "tóng lǐ", 31.1, 120.7, None, "{}", hanviet="Đồng Lí")
    db = tmp_path / "places.sqlite"
    write_places_db([p], db)
    con = sqlite3.connect(db)
    for q in ("dong li", "dong ly"):
        from pipeline.hanviet import fold
        hit = con.execute("SELECT rowid FROM places_fts WHERE places_fts MATCH ?", (f'hanviet : "{fold(q)}"',)).fetchall()
        assert hit == [(1,)], q
