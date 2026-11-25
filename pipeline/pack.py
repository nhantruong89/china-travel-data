"""Dựng và kiểm tra gói dữ liệu một thành phố: <slug>-<version>.zip."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import CityConfig
from .places import Place, extract_places, write_places_db

PACK_FILES = ("map.mbtiles", "places.sqlite")
TOOLS = Path.home() / ".cache" / "china-travel"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _bbox_arg(bbox) -> str:
    return ",".join(str(v) for v in bbox)


def osmium_extract(source_pbf: Path, bbox, out_pbf: Path) -> None:
    subprocess.run(
        ["osmium", "extract", "-b", _bbox_arg(bbox), str(source_pbf), "-o", str(out_pbf), "--overwrite"],
        check=True,
    )


def planetiler_command(city_pbf: Path, bbox, out_mbtiles: Path) -> list[str]:
    # --download: lấy các lớp nền (nước, hồ, Natural Earth) mà schema OpenMapTiles cần;
    # lưu ở TOOLS/sources để các lần dựng sau dùng lại.
    return [
        "java", "-Xmx6g", "-jar", str(TOOLS / "planetiler.jar"),
        f"--osm-path={city_pbf}", f"--bounds={_bbox_arg(bbox)}", f"--output={out_mbtiles}",
        "--maxzoom=14", "--languages=zh,en", "--force",
        "--download", f"--download_dir={TOOLS / 'sources'}",
        f"--tmpdir={out_mbtiles.parent / 'planetiler-tmp'}",
    ]


def planetiler_tiles(city_pbf: Path, bbox, out_mbtiles: Path) -> None:
    subprocess.run(planetiler_command(city_pbf, bbox, out_mbtiles), check=True)


def next_version(out_dir: Path, slug: str, day: str) -> str:
    out_dir = Path(out_dir)
    if not (out_dir / f"{slug}-{day}.zip").exists():
        return day
    n = 1
    while (out_dir / f"{slug}-{day}.{n}.zip").exists():
        n += 1
    return f"{day}.{n}"


def build_pack(
    city: CityConfig,
    source_pbf: Path,
    out_dir: Path,
    version: str,
    tiles_builder: Callable[[Path, tuple, Path], None] = planetiler_tiles,
    extractor: Callable[[Path, tuple, Path], None] = osmium_extract,
    places_extractor: Callable[[Path, tuple], list[Place]] = extract_places,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        work = Path(tmp)
        city_pbf = work / "city.osm.pbf"
        extractor(Path(source_pbf), city.bbox, city_pbf)
        tiles_builder(city_pbf, city.bbox, work / "map.mbtiles")
        count = write_places_db(places_extractor(city_pbf, city.bbox), work / "places.sqlite")

        manifest = {
            "schema": 1,
            "slug": city.slug,
            "name_vi": city.name_vi,
            "name_zh": city.name_zh,
            "name_en": city.name_en,
            "region": city.region,
            "region_name_vi": city.region_name_vi,
            "version": version,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bbox": list(city.bbox),
            "has_metro": city.has_metro,
            "place_count": count,
            "files": {
                name: {"bytes": (work / name).stat().st_size, "sha256": sha256_file(work / name)}
                for name in PACK_FILES
            },
        }
        (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        zip_path = out_dir / f"{city.slug}-{version}.zip"
        partial = zip_path.with_suffix(".zip.partial")
        # map.mbtiles đã nén sẵn → STORED; sqlite nén được → DEFLATED
        with zipfile.ZipFile(partial, "w") as zf:
            zf.write(work / "manifest.json", "manifest.json", compress_type=zipfile.ZIP_DEFLATED)
            zf.write(work / "map.mbtiles", "map.mbtiles", compress_type=zipfile.ZIP_STORED)
            zf.write(work / "places.sqlite", "places.sqlite", compress_type=zipfile.ZIP_DEFLATED)
        partial.replace(zip_path)
    return zip_path


def read_manifest(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        return json.loads(zf.read("manifest.json"))


def validate_pack(zip_path: Path, city: CityConfig, max_mb: int = 400) -> list[str]:
    errors: list[str] = []
    zip_path = Path(zip_path)
    size_mb = zip_path.stat().st_size / (1 << 20)
    if size_mb > max_mb:
        errors.append(f"{city.slug}: dung lượng gói {size_mb:.1f} MB vượt giới hạn {max_mb} MB")

    with zipfile.ZipFile(zip_path) as zf, tempfile.TemporaryDirectory() as tmp:
        names = set(zf.namelist())
        missing = {"manifest.json", *PACK_FILES} - names
        if missing:
            return errors + [f"{city.slug}: thiếu file trong gói: {', '.join(sorted(missing))}"]
        manifest = json.loads(zf.read("manifest.json"))
        zf.extractall(tmp)
        for name in PACK_FILES:
            if sha256_file(Path(tmp) / name) != manifest["files"][name]["sha256"]:
                errors.append(f"{city.slug}: sha256 của {name} không khớp manifest")

        con = sqlite3.connect(Path(tmp) / "places.sqlite")
        try:
            count = con.execute("SELECT COUNT(*) FROM places").fetchone()[0]
            min_lon, min_lat, max_lon, max_lat = city.bbox
            outside = con.execute(
                "SELECT COUNT(*) FROM places WHERE lon < ? OR lon > ? OR lat < ? OR lat > ?",
                (min_lon, max_lon, min_lat, max_lat),
            ).fetchone()[0]
            empty = con.execute("SELECT COUNT(*) FROM places WHERE TRIM(name_zh) = ''").fetchone()[0]
        finally:
            con.close()

    if count < city.min_places:
        errors.append(f"{city.slug}: chỉ có {count} địa điểm, cần ít nhất {city.min_places}")
    if outside:
        errors.append(f"{city.slug}: {outside} địa điểm nằm ngoài ranh giới bbox")
    if empty:
        errors.append(f"{city.slug}: {empty} địa điểm có tên chữ Hán rỗng")
    if manifest.get("slug") != city.slug:
        errors.append(f"{city.slug}: slug trong manifest là '{manifest.get('slug')}'")
    return errors
