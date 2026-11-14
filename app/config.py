"""Settings read from the environment, with defaults good enough to run locally."""
import os

# Areas smaller than this get a caveat in the /stats response: before 2012 the
# series is MODIS-only, so a handful of hexagons carries much more uncertainty.
# Provisional threshold (section 6.3), hence configurable.
SMALL_AREA_THRESHOLD_KM2 = float(os.getenv("SMALL_AREA_THRESHOLD_KM2", "500"))
