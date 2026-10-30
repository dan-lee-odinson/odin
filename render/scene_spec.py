# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared facts and math for the HUGINN animation (milestone A1).

Pure Python (no Blender imports) so the tests can check every number the
Blender build script uses. Everything record-derived is read from the
``inputs`` folder; the few drawn choices the brief allows are named as such.

Sources:
- 6U size 10 x 22.6 x 36.6 cm: ``inputs/spacecraft.md``.
- Orbit rows (MET, sub-satellite latitude/longitude, altitude): ``inputs/orbit/P3-orbit.csv``.
- Ground station site: ``inputs/orbit/station.json``.
- Earth texture: NASA Blue Marble Next Generation (see ``inputs/imagery/SOURCE.md``).

Drawn choices (the record holds no value for these; the brief, rule 2):
- The spacecraft's look: a standard 6U CubeSat with twin solar arrays.
- The spacecraft is enlarged next to Earth so it can be seen at all (see
  ``SPACECRAFT_DISPLAY_SCALE``). It is not to scale with Earth or the orbit.
- The spacecraft's nadir-pointing pose is fixed and illustrative. The
  Sun's direction was drawn in A1/A2; from A3 it is derived from the run's
  UTC epoch (``inputs/epochs.json``, see ``solar.py``) and checked against
  the record's ``ADM_ECLIPSE``. Where they disagree, the record wins.
"""

import csv
import json
import math
from pathlib import Path

import solar as _solar

# ---------------------------------------------------------------------------
# Paths (all relative to this file's folder; never absolute)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"
ORBIT_CSV = INPUTS / "orbit" / "P3-orbit.csv"
STATION_JSON = INPUTS / "orbit" / "station.json"
EARTH_TEXTURE_NAME = "world.topo.bathy.200407.3x21600x10800.jpg"
EARTH_TEXTURE = INPUTS / "imagery" / EARTH_TEXTURE_NAME

OUT_DIR = ROOT / "out" / "a1"
REPORT_JSON = OUT_DIR / "scene_report.json"
STILL_NAMES = ("a1_01_wide.png", "a1_02_hero.png", "a1_03_payload.png")
RENDER_WIDTH = 1920
RENDER_HEIGHT = 1080

# ---------------------------------------------------------------------------
# Spacecraft (inputs/spacecraft.md): 6U = 10 x 22.6 x 36.6 cm.
# Local frame: X across the large face (22.6 cm), Y thin (10 cm),
# Z along the long axis (36.6 cm). Payload aperture faces local -Z (nadir).
# Twin arrays deploy along local +/-X. SA1 is the -X wing, SA2 the +X wing,
# matching the two array strings EPS_SA1_I / EPS_SA2_I.
# ---------------------------------------------------------------------------
BUS_DIMS_M = (0.226, 0.100, 0.366)
PANEL_SIZE_M = (0.300, 0.006, 0.320)  # one drawn panel: width, thickness, height
PANELS_PER_WING = 2                    # drawn: two hinged panels per wing

# ---------------------------------------------------------------------------
# Scene scale. Earth mean radius 6371 km (the standard mean value; the orbit
# file gives altitude above the ellipsoid, so this only sets the drawn orbit
# height ratio). Earth is 10 scene units in radius.
# ---------------------------------------------------------------------------
EARTH_RADIUS_KM = 6371.0
SCENE_EARTH_RADIUS = 10.0

# Spacecraft display scale: scene units per meter for the spacecraft only.
# Chosen so the bus long axis is about half a scene unit and reads clearly at
# 1920 x 1080. Enlargement against the Earth scale is reported, not hidden.
SPACECRAFT_DISPLAY_SCALE = 1.4

# The MET at which A1 places the spacecraft: in contact per the orbit file
# (station_visible = 1 from MET 800 to 1230) and sunlit, as the whole P3 run
# is. A2 will move it along the orbit from the record.
PLACEMENT_MET_S = 1000.0

# The Sun's direction is derived from the run's UTC epoch (A3): the
# low-precision solar formula in solar.py at epoch + MET. The A1 stills use
# the placement MET of the default run below.
DEFAULT_RUN_ID = "dev-ph2-p3-open-01"
SUN_DISTANCE = 90.0   # scene units, for the visible Sun disk
SUN_DISK_RADIUS = 1.5  # drawn disk (Director's A2 ruling: smaller)
_EPOCH = None

# Rotation (degrees about scene Z) applied to the Earth texture so that the
# map lines up with latlon_to_xyz below. Calibrated visually with the build
# script's --calibrate still: at 0 degrees the station marker sits on
# Florida's Cape coast and the MET-1000 orbit marker sits offshore in the
# Atlantic at the right latitude (see README, "Calibration").
EARTH_TEXTURE_ROTATION_DEG = 0.0


# ---------------------------------------------------------------------------
# Coordinate math. Scene frame: Z through the north pole, X toward
# latitude 0 / longitude 0, Y toward latitude 0 / longitude +90 (east).
# ---------------------------------------------------------------------------
def latlon_to_xyz(lat_deg, lon_deg, radius):
    """Scene position of a geodetic point on a sphere of the given radius."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    cos_lat = math.cos(lat)
    return (
        radius * cos_lat * math.cos(lon),
        radius * cos_lat * math.sin(lon),
        radius * math.sin(lat),
    )


def scene_radius_for_alt_km(alt_km):
    """Scene distance from Earth's center for a given altitude in km."""
    return SCENE_EARTH_RADIUS * (EARTH_RADIUS_KM + alt_km) / EARTH_RADIUS_KM


def sun_latlon(met_s=PLACEMENT_MET_S):
    """Derived sub-solar (latitude, longitude) at a MET of the default run."""
    global _EPOCH
    if _EPOCH is None:
        _EPOCH = _solar.read_epoch(DEFAULT_RUN_ID)
    return _solar.sun_latlon_at(_EPOCH, met_s)


def sun_direction(met_s=PLACEMENT_MET_S):
    """Unit vector toward the derived Sun at a MET."""
    lat, lon = sun_latlon(met_s)
    return latlon_to_xyz(lat, lon, 1.0)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def read_orbit(path=ORBIT_CSV):
    """All orbit rows as dicts of floats/ints, in file order."""
    rows = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "met_s": float(row["met_s"]),
                    "lat_deg": float(row["lat_deg"]),
                    "lon_deg": float(row["lon_deg"]),
                    "alt_km": float(row["alt_km"]),
                    "sunlit_by_orbit": int(row["sunlit_by_orbit"]),
                    "station_visible": int(row["station_visible"]),
                }
            )
    return rows


def orbit_row_at(rows, met_s):
    """Orbit row linearly interpolated at a MET (clamped to the file span)."""
    if met_s <= rows[0]["met_s"]:
        return dict(rows[0])
    if met_s >= rows[-1]["met_s"]:
        return dict(rows[-1])
    for before, after in zip(rows, rows[1:]):
        if before["met_s"] <= met_s <= after["met_s"]:
            span = after["met_s"] - before["met_s"]
            frac = 0.0 if span == 0 else (met_s - before["met_s"]) / span
            out = {"met_s": float(met_s)}
            for key in ("lat_deg", "lon_deg", "alt_km"):
                out[key] = before[key] + frac * (after[key] - before[key])
            # Flags are step values: keep the earlier row's until the next row.
            out["sunlit_by_orbit"] = before["sunlit_by_orbit"]
            out["station_visible"] = before["station_visible"]
            return out
    raise ValueError("MET outside orbit rows: %r" % (met_s,))


def orbit_xyz(row):
    """Scene position of the spacecraft for one orbit row."""
    return latlon_to_xyz(
        row["lat_deg"], row["lon_deg"], scene_radius_for_alt_km(row["alt_km"])
    )


def read_station(path=STATION_JSON):
    """The ground station's name and site latitude/longitude/elevation."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    site = data["site"]
    return {
        "name": data["name"],
        "lat_deg": float(site["latitude_deg"]),
        "lon_deg": float(site["longitude_deg"]),
        "elevation_m": float(site["elevation_m"]),
    }


def station_xyz(station):
    """Scene position of the station on Earth's surface."""
    return latlon_to_xyz(station["lat_deg"], station["lon_deg"], SCENE_EARTH_RADIUS)


def spacecraft_enlargement():
    """How many times larger than true scale the spacecraft is drawn.

    True scale would put one meter at SCENE_EARTH_RADIUS / (EARTH_RADIUS_KM
    * 1000) scene units. The captions state this factor.
    """
    true_units_per_meter = SCENE_EARTH_RADIUS / (EARTH_RADIUS_KM * 1000.0)
    return SPACECRAFT_DISPLAY_SCALE / true_units_per_meter
