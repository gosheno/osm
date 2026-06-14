from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.services.poi_import.address_normalizer import (
    build_address,
    extract_address_fields,
    normalized_known_poi_address,
)
from app.services.poi_import.brand_normalizer import BrandAliasMatcher
from app.services.poi_import.confidence import calculate_confidence
from app.services.poi_import.models import PoiCandidate, PoiImportConfig
from app.services.poi_import.tag_matcher import candidate_brand_match


class OsmiumUnavailableError(RuntimeError):
    pass

class LimitReached(Exception):
    pass

def read_pbf_candidates(
    *,
    pbf_path: str | Path,
    config: PoiImportConfig,
    matcher: BrandAliasMatcher,
    brand: str | None = None,
    limit: int | None = None,
) -> tuple[list[PoiCandidate], dict[str, int]]:
    try:
        import osmium
    except ImportError as exc:
        raise OsmiumUnavailableError(
            "The osmium package is required for .osm.pbf parsing. "
            "Install backend requirements or run inside the backend container."
        ) from exc

    class PoiHandler(osmium.SimpleHandler):
        def __init__(self) -> None:
            super().__init__()
            self.candidates: list[PoiCandidate] = []
            self.stats = {
                "objects_scanned": 0,
                "candidates": 0,
                "skipped": 0,
                "errors": 0,
                "relations_seen": 0,
            }

        def node(self, node: Any) -> None:
            self._scan_object("node", int(node.id), dict(node.tags), _node_point(node))

        def way(self, way: Any) -> None:
            self._scan_object("way", int(way.id), dict(way.tags), _way_point(way.nodes))

        def relation(self, relation: Any) -> None:
            self.stats["objects_scanned"] += 1
            self.stats["relations_seen"] += 1
            tags = dict(relation.tags)
            if candidate_brand_match(tags, matcher) is not None:
                self.stats["skipped"] += 1

        def _scan_object(
            self,
            osm_type: str,
            osm_id: int,
            tags: dict[str, str],
            point: tuple[float, float] | None,
        ) -> None:
            self.stats["objects_scanned"] += 1
            if self.stats["objects_scanned"] % 100000 == 0:
                print(
                    f"Scanned: {self.stats['objects_scanned']}, "
                    f"candidates: {self.stats['candidates']}",
                    flush=True,
                )
            if limit is not None and len(self.candidates) >= limit:
                raise LimitReached()

            match = candidate_brand_match(tags, matcher)
            if match is None:
                return
            if brand and match.canonical_brand != brand:
                return

            self.stats["candidates"] += 1
            if point is None:
                self.stats["skipped"] += 1
                return

            latitude, longitude = point
            if not config.region.bounds.contains(latitude, longitude):
                self.stats["skipped"] += 1
                return

            fields = extract_address_fields(tags, default_country=config.region.default_country)
            address = build_address(fields)
            normalized_address = normalized_known_poi_address(address, default_city=fields.get("city"))
            warnings: list[str] = []
            if not address:
                warnings.append("ADDRESS_MISSING")
            if not tags.get("shop"):
                warnings.append("SHOP_TAG_MISSING")
            if osm_type == "way":
                warnings.append("GEOMETRY_UNCERTAIN")

            candidate = PoiCandidate(
                osm_type=osm_type,
                osm_id=osm_id,
                canonical_brand=match.canonical_brand,
                detected_brand=match.detected_brand,
                name=tags.get("name:ru") or tags.get("name"),
                operator=tags.get("operator:ru") or tags.get("operator"),
                shop_type=tags.get("shop"),
                amenity_type=tags.get("amenity"),
                original_address=address,
                normalized_address=normalized_address,
                country=fields.get("country") or config.region.default_country,
                region=fields.get("region"),
                city=fields.get("city"),
                district=fields.get("district"),
                suburb=fields.get("suburb"),
                street=fields.get("street"),
                house_number=fields.get("house_number"),
                postcode=fields.get("postcode"),
                latitude=latitude,
                longitude=longitude,
                phone=tags.get("contact:phone") or tags.get("phone"),
                website=tags.get("website") or tags.get("contact:website"),
                opening_hours=tags.get("opening_hours"),
                raw_tags=tags,
                warnings=warnings,
            )
            candidate.confidence_score = calculate_confidence(
                brand_matched=True,
                shop_type=candidate.shop_type,
                street=candidate.street,
                house_number=candidate.house_number,
                city=candidate.city,
                region=candidate.region,
                geometry_valid=osm_type == "node",
                warnings=candidate.warnings,
            )
            self.candidates.append(candidate)


    handler = PoiHandler()
    try:
        handler.apply_file(str(pbf_path), locations=True)
    except LimitReached:
        pass

    return handler.candidates, handler.stats


def _node_point(node: Any) -> tuple[float, float] | None:
    try:
        location = node.location
        if not location.valid():
            return None
        return float(location.lat), float(location.lon)
    except Exception:
        return None


def _way_point(nodes: Iterable[Any]) -> tuple[float, float] | None:
    coordinates: list[tuple[float, float]] = []
    for node in nodes:
        try:
            location = node.location
            if location.valid():
                coordinates.append((float(location.lat), float(location.lon)))
        except Exception:
            continue
    if not coordinates:
        return None
    lat = sum(item[0] for item in coordinates) / len(coordinates)
    lon = sum(item[1] for item in coordinates) / len(coordinates)
    return lat, lon

