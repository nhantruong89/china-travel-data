from pipeline.catalog import build_catalog

BASE = "https://github.com/nhantruong89/china-travel-data/releases/download/packs"


def _m(slug, region):
    return {"schema": 1, "slug": slug, "name_vi": slug, "name_zh": "字", "name_en": slug, "region": region,
            "region_name_vi": "V", "version": "20261201", "bbox": [1, 2, 3, 4], "has_metro": False,
            "place_count": 5, "files": {}}


def test_catalog_sorted_and_urls():
    c = build_catalog([_m("suzhou", "b"), _m("shanghai", "b"), _m("aaa", "a")],
                      {"suzhou": (10, "s1"), "shanghai": (20, "s2"), "aaa": (30, "s3")}, BASE + "/")
    assert c["schema"] == 1 and "generated" in c
    assert [p["slug"] for p in c["packs"]] == ["aaa", "shanghai", "suzhou"]
    sh = c["packs"][1]
    assert sh["url"] == f"{BASE}/shanghai-20261201.zip"
    assert sh["bytes"] == 20 and sh["sha256"] == "s2"
    assert set(sh) == {"slug", "name_vi", "name_zh", "name_en", "region", "region_name_vi", "version",
                       "bbox", "has_metro", "bytes", "sha256", "url"}
