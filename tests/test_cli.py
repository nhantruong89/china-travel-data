import json
import zipfile

from pipeline.cli import main


def _zip(d, slug, version):
    m = {"schema": 1, "slug": slug, "name_vi": slug, "name_zh": "字", "name_en": slug, "region": "r",
         "region_name_vi": "V", "version": version, "bbox": [1, 2, 3, 4], "has_metro": False,
         "place_count": 1, "files": {}}
    with zipfile.ZipFile(d / f"{slug}-{version}.zip", "w") as zf:
        zf.writestr("manifest.json", json.dumps(m))


def test_catalog_command_uses_latest_version(tmp_path):
    _zip(tmp_path, "a", "20261201")
    _zip(tmp_path, "a", "20261201.1")
    _zip(tmp_path, "a", "20261130")
    _zip(tmp_path, "b", "20261201")
    assert main(["catalog", str(tmp_path), "--base-url", "https://x/y"]) == 0
    c = json.loads((tmp_path / "catalog.json").read_text())
    assert [(p["slug"], p["version"]) for p in c["packs"]] == [("a", "20261201.1"), ("b", "20261201")]


def test_build_uses_version_suffix(tmp_path, monkeypatch):
    import pipeline.cli as cli
    from pipeline.cli import main
    calls = []
    monkeypatch.setattr(cli, "build_pack", lambda city, pbf, out, version, **kw: calls.append(version) or (_fake_zip(out, city.slug, version)))
    monkeypatch.setattr(cli, "validate_pack", lambda z, city, max_mb: [])
    monkeypatch.setattr(cli, "read_manifest", lambda z: {"place_count": 1})
    from pathlib import Path
    city = Path(__file__).resolve().parents[1] / "cities" / "zhouzhuang.yaml"
    assert main(["build", str(city), "--pbf", "x.pbf", "--out", str(tmp_path), "--version-suffix", "57"]) == 0
    assert len(calls) == 1 and calls[0].endswith(".57") and len(calls[0]) == len("20261125.57")


def _fake_zip(out, slug, version):
    from pathlib import Path
    p = Path(out) / f"{slug}-{version}.zip"
    p.write_bytes(b"z")
    return p
