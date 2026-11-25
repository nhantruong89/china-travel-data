"""Gộp manifest các gói thành catalog.json cho app đọc."""
from __future__ import annotations

from datetime import datetime, timezone

CATALOG_KEYS = ("slug", "name_vi", "name_zh", "name_en", "region", "region_name_vi", "version", "bbox", "has_metro")


def build_catalog(manifests: list[dict], zip_infos: dict[str, tuple[int, str]], base_url: str) -> dict:
    base = base_url.rstrip("/")
    packs = []
    for m in sorted(manifests, key=lambda m: (m["region"], m["slug"])):
        size, sha = zip_infos[m["slug"]]
        entry = {k: m[k] for k in CATALOG_KEYS}
        entry.update(bytes=size, sha256=sha, url=f"{base}/{m['slug']}-{m['version']}.zip")
        packs.append(entry)
    return {
        "schema": 1,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "packs": packs,
    }
