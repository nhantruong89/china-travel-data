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
