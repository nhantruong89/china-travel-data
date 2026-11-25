"""Đọc và kiểm tra file cấu hình thành phố (data/cities/<slug>.yaml)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED = ("slug", "name_vi", "name_zh", "name_en", "region", "region_name_vi", "bbox", "has_metro")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CityConfig:
    slug: str
    name_vi: str
    name_zh: str
    name_en: str
    region: str
    region_name_vi: str
    bbox: tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat (WGS-84)
    has_metro: bool
    min_places: int = 200
    featured: tuple[str, ...] = ()


def load_city(path: Path) -> CityConfig:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path.name}: YAML không hợp lệ: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"{path.name}: nội dung phải là một bảng khóa–giá trị")

    for key in REQUIRED:
        if raw.get(key) in (None, ""):
            raise ConfigError(f"{path.name}: thiếu trường bắt buộc '{key}'")

    if raw["slug"] != path.stem:
        raise ConfigError(f"{path.name}: slug '{raw['slug']}' phải trùng tên file '{path.stem}'")

    bbox = raw["bbox"]
    if not (isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox)):
        raise ConfigError(f"{path.name}: bbox phải là 4 số [min_lon, min_lat, max_lon, max_lat]")
    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise ConfigError(f"{path.name}: bbox sai thứ tự hoặc ngoài phạm vi: {bbox}")

    if not isinstance(raw["has_metro"], bool):
        raise ConfigError(f"{path.name}: has_metro phải là true hoặc false")

    min_places = raw.get("min_places", 200)
    if not isinstance(min_places, int) or min_places < 0:
        raise ConfigError(f"{path.name}: min_places phải là số nguyên không âm")

    return CityConfig(
        slug=raw["slug"],
        name_vi=raw["name_vi"],
        name_zh=raw["name_zh"],
        name_en=raw["name_en"],
        region=raw["region"],
        region_name_vi=raw["region_name_vi"],
        bbox=(min_lon, min_lat, max_lon, max_lat),
        has_metro=raw["has_metro"],
        min_places=min_places,
        featured=tuple(raw.get("featured") or ()),
    )
