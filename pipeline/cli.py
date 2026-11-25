"""Dòng lệnh đường ống dữ liệu.

  python -m pipeline.cli build cities/shanghai.yaml [...] --pbf china-latest.osm.pbf --out dist/
  python -m pipeline.cli catalog dist/ --base-url https://github.com/nhantruong89/china-travel-data/releases/download/packs
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .catalog import build_catalog
from .config import load_city
from .pack import build_pack, next_version, read_manifest, sha256_file, validate_pack

DEFAULT_BASE_URL = "https://github.com/nhantruong89/china-travel-data/releases/download/packs"


def _version_key(v: str) -> tuple[int, int]:
    day, _, n = v.partition(".")
    return int(day), int(n or 0)


def cmd_build(args) -> int:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    failed = False
    for cfg in args.cities:
        city = load_city(Path(cfg))
        version = next_version(Path(args.out), city.slug, day)
        print(f"Đang dựng {city.slug} {version} …", flush=True)
        z = build_pack(city, Path(args.pbf), Path(args.out), version)
        errors = validate_pack(z, city, max_mb=args.max_mb)
        size_mb = z.stat().st_size / (1 << 20)
        if errors:
            failed = True
            for e in errors:
                print(f"  LỖI: {e}", file=sys.stderr)
            z.rename(z.with_suffix(".zip.invalid"))
        else:
            print(f"  ĐẠT: {z.name} ({size_mb:.1f} MB, {read_manifest(z)['place_count']} địa điểm)")
    return 1 if failed else 0


def cmd_catalog(args) -> int:
    dist = Path(args.dist)
    latest: dict[str, tuple[str, Path, dict]] = {}
    for z in dist.glob("*.zip"):
        m = read_manifest(z)
        cur = latest.get(m["slug"])
        if cur is None or _version_key(m["version"]) > _version_key(cur[0]):
            latest[m["slug"]] = (m["version"], z, m)
    manifests = [m for _, _, m in latest.values()]
    infos = {slug: (z.stat().st_size, sha256_file(z)) for slug, (_, z, _) in latest.items()}
    catalog = build_catalog(manifests, infos, args.base_url)
    (dist / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"catalog.json: {len(manifests)} gói")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="dựng gói cho một hoặc nhiều thành phố")
    b.add_argument("cities", nargs="+")
    b.add_argument("--pbf", required=True)
    b.add_argument("--out", default="dist")
    b.add_argument("--max-mb", type=int, default=400)
    b.set_defaults(func=cmd_build)
    c = sub.add_parser("catalog", help="dựng catalog.json từ các gói mới nhất trong thư mục")
    c.add_argument("dist")
    c.add_argument("--base-url", default=DEFAULT_BASE_URL)
    c.set_defaults(func=cmd_catalog)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
