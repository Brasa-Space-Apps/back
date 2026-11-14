import os
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent


def _read_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_env = {**_read_env(BACK / ".env"), **os.environ}

DATABASE_URL: str = _env.get("DATABASE_URL", "postgresql://brasa:brasa@localhost:5432/brasa")
FRONT_ORIGINS: list[str] = [o.strip() for o in _env.get("FRONT_ORIGIN", "http://localhost:3000").split(",")]

H3_RES = 7
UNIT_LABEL = "dias com fogo (por área de ~5 km²)"

# Areas smaller than this get a caveat in the /stats response: before 2012 the
# series is MODIS-only, so a handful of hexagons carries much more uncertainty.
# Provisional threshold (section 6.3), hence configurable.
SMALL_AREA_THRESHOLD_KM2 = float(_env.get("SMALL_AREA_THRESHOLD_KM2", 500))