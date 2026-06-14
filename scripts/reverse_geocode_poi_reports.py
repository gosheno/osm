from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
for candidate in (
    SCRIPT_PATH.parents[1] / "backend",
    Path("/app"),
):
    if (candidate / "app").exists():
        sys.path.insert(0, str(candidate))
        break

from app.scripts.reverse_geocode_poi_reports import main


if __name__ == "__main__":
    raise SystemExit(main())
