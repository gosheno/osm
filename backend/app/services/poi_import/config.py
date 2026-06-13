from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.services.poi_import.models import (
    ChainConfig,
    PoiImportConfig,
    RegionBounds,
    RegionConfig,
)


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "poi_chains.yml"


def load_poi_config(path: str | Path | None = None) -> PoiImportConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid POI config: {config_path}")

    region_raw = _dict(raw.get("region"))
    bbox_raw = _dict(region_raw.get("bbox"))
    region = RegionConfig(
        name=str(region_raw.get("name") or "spb_lenobl"),
        default_country=str(region_raw.get("default_country") or "Russia"),
        bounds=RegionBounds(
            min_lat=float(bbox_raw.get("min_lat")),
            max_lat=float(bbox_raw.get("max_lat")),
            min_lon=float(bbox_raw.get("min_lon")),
            max_lon=float(bbox_raw.get("max_lon")),
        ),
        allowed_regions=[str(item) for item in region_raw.get("allowed_regions") or []],
    )

    chains: list[ChainConfig] = []
    for item in raw.get("chains") or []:
        chain = _dict(item)
        canonical_brand = str(chain.get("canonical_brand") or "").strip()
        if not canonical_brand:
            continue
        chains.append(
            ChainConfig(
                canonical_brand=canonical_brand,
                aliases=[str(alias) for alias in chain.get("aliases") or []],
                priority=int(chain.get("priority") or 100),
            )
        )
    if not chains:
        raise ValueError(f"POI config has no chains: {config_path}")
    return PoiImportConfig(region=region, chains=chains)


def _dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Expected mapping in POI config")
    return value

