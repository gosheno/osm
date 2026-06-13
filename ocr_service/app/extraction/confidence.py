from __future__ import annotations


def average_confidence(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None and value >= 0]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 4)


def clamp_confidence(value: float | None, default: float = 0.65) -> float:
    if value is None:
        return default
    return round(max(0.0, min(float(value), 0.99)), 4)

