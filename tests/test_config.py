from pathlib import Path

import pytest

from pipeline.config import ConfigError, load_city

CITIES = Path(__file__).resolve().parents[1] / "cities"

VALID = """\
slug: {slug}
name_vi: Thử
name_zh: 试
name_en: Test
region: test-region
region_name_vi: Vùng thử
bbox: [{bbox}]
has_metro: false
"""


def write(tmp_path, name, text):
    p = tmp_path / f"{name}.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_shanghai():
    c = load_city(CITIES / "shanghai.yaml")
    assert c.slug == "shanghai"
    assert c.name_zh == "上海"
    assert c.region == "shanghai-region"
    assert c.region_name_vi == "Thượng Hải & phụ cận"
    assert c.bbox == (120.85, 30.67, 122.00, 31.88)
    assert c.has_metro is True
    assert c.min_places == 200


def test_bbox_order_invalid(tmp_path):
    p = write(tmp_path, "x", VALID.format(slug="x", bbox="121.0, 31.0, 120.0, 32.0"))
    with pytest.raises(ConfigError, match="bbox"):
        load_city(p)


def test_missing_name_zh(tmp_path):
    text = VALID.format(slug="x", bbox="120.0, 31.0, 121.0, 32.0").replace("name_zh: 试\n", "")
    p = write(tmp_path, "x", text)
    with pytest.raises(ConfigError, match="name_zh"):
        load_city(p)


def test_slug_matches_filename(tmp_path):
    p = write(tmp_path, "x", VALID.format(slug="y", bbox="120.0, 31.0, 121.0, 32.0"))
    with pytest.raises(ConfigError, match="slug"):
        load_city(p)


def test_all_city_files_load():
    files = sorted(CITIES.glob("*.yaml"))
    assert {f.stem for f in files} >= {"shanghai", "suzhou", "hangzhou", "zhouzhuang"}
    for f in files:
        load_city(f)


def test_metro_fare_and_min_stations(tmp_path):
    from pipeline.config import load_city
    p = tmp_path / "sh.yaml"
    p.write_text("""slug: sh
name_vi: A
name_zh: B
name_en: C
region: r
region_name_vi: V
bbox: [121, 31, 122, 32]
has_metro: true
min_metro_stations: 300
metro_fare: {base_yuan: 3, base_km: 4, steps_km: [4, 4, 4, 7, 7, 10, 10], then_every_km: 15, source: "x"}
""", encoding="utf-8")
    c = load_city(p)
    assert c.min_metro_stations == 300
    assert c.metro_fare["steps_km"] == [4, 4, 4, 7, 7, 10, 10]


def test_bad_metro_fare_rejected(tmp_path):
    import pytest
    from pipeline.config import ConfigError, load_city
    p = tmp_path / "sh.yaml"
    p.write_text("""slug: sh
name_vi: A
name_zh: B
name_en: C
region: r
region_name_vi: V
bbox: [121, 31, 122, 32]
has_metro: true
metro_fare: {base_yuan: 3}
""", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_city(p)
