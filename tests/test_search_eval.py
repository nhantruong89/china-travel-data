from pipeline.places import Place, write_places_db
from pipeline.search_eval import evaluate, queries


def test_queries_like_the_app():
    assert queries("Đồng Lý")[0].endswith('hanviet : "dong li")')
    q = queries("chùa Hàn Sơn")
    assert q[1] == 'hanviet : ("han son tu" OR "han son am")' and q[2] == 'hanviet : "han son"'


def test_evaluate_on_a_tiny_pack(tmp_path):
    db = tmp_path / "places.sqlite"
    write_places_db([Place("n1", "see", "寒山寺", None, "hán shān sì", 31.3, 120.6, None, "{}", hanviet="Hàn Sơn Tự")], db)
    res = evaluate(db, [("chùa Hàn Sơn", "寒山寺"), ("Linh Ẩn", "灵隐寺")])
    assert [r[2] for r in res] == [True, False]
