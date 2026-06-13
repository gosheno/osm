from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.poi_import.models import ChainConfig


APOSTROPHES = {"'", "’", "`", "ʼ", "‘", "´", "‛"}
HYPHENS = {"‐", "‑", "‒", "–", "—", "−"}


def normalize_brand_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.lower().replace("ё", "е")
    for apostrophe in APOSTROPHES:
        text = text.replace(apostrophe, "")
    for hyphen in HYPHENS:
        text = text.replace(hyphen, "-")
    text = re.sub(r"[\s_]+", " ", text)
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"[^\w -]+", "", text, flags=re.UNICODE)
    return " ".join(text.split()).strip()


@dataclass(frozen=True)
class BrandMatch:
    canonical_brand: str
    detected_brand: str
    matched_alias: str


class BrandAliasMatcher:
    def __init__(self, chains: list[ChainConfig]) -> None:
        self.chains = chains
        self._alias_to_brand: dict[str, tuple[str, str]] = {}
        for chain in chains:
            aliases = [chain.canonical_brand, *chain.aliases]
            for alias in aliases:
                normalized = normalize_brand_text(alias)
                if normalized:
                    self._alias_to_brand[normalized] = (chain.canonical_brand, alias)

    def detect(self, value: str | None) -> BrandMatch | None:
        normalized = normalize_brand_text(value)
        if not normalized:
            return None
        exact = self._alias_to_brand.get(normalized)
        if exact is not None:
            canonical, alias = exact
            return BrandMatch(canonical, value or alias, alias)

        padded = f" {normalized} "
        best: tuple[str, str, str] | None = None
        for alias_key, (canonical, alias) in self._alias_to_brand.items():
            if len(alias_key) <= 2:
                continue
            if f" {alias_key} " in padded or alias_key in normalized:
                if best is None or len(alias_key) > len(best[0]):
                    best = (alias_key, canonical, alias)
        if best is None:
            return None
        return BrandMatch(best[1], value or best[2], best[2])

    def aliases_for_brand(self, brand: str) -> list[str]:
        return [
            alias
            for alias_key, (canonical, alias) in self._alias_to_brand.items()
            if canonical == brand
        ]
