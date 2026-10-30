# SPDX-License-Identifier: GPL-3.0-or-later
"""The Sun's direction from a run's UTC epoch (A3).

A standard low-precision solar position (the NOAA fractional-year series
for declination and the equation of time), standard library only. It gives
the sub-solar point — the latitude and longitude where the Sun is
overhead — good to a fraction of a degree, which is all a drawing needs.
The epoch comes from ``inputs/epochs.json``: UTC at MET 0, so the UTC at
any moment is epoch + MET seconds. Where the record's ``ADM_ECLIPSE`` and
this geometry disagree, the record wins (inputs/epochs.json); a test
checks that they agree on the P3 runs.
"""

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EPOCHS_JSON = ROOT / "inputs" / "epochs.json"
EARTH_RADIUS_KM = 6371.0


def read_epoch(run_id, path=EPOCHS_JSON):
    """UTC at MET 0 for a run as an aware datetime, or None when it has none."""
    runs = json.loads(Path(path).read_text(encoding="utf-8"))["runs"]
    entry = runs.get(run_id) or {}
    stamp = entry.get("sun_epoch_utc")
    if not stamp:
        return None
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


def subsolar_latlon(utc):
    """(latitude_deg, longitude_deg) of the sub-solar point at a UTC time."""
    start = datetime(utc.year, 1, 1, tzinfo=timezone.utc)
    day_of_year = (utc - start).days + 1
    hour = utc.hour + utc.minute / 60.0 + utc.second / 3600.0
    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1 + (hour - 12.0) / 24.0)
    eqtime_min = 229.18 * (
        0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl_rad = (
        0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    utc_minutes = utc.hour * 60.0 + utc.minute + utc.second / 60.0
    lon = 180.0 - 0.25 * (utc_minutes + eqtime_min)
    lon = (lon + 180.0) % 360.0 - 180.0
    return math.degrees(decl_rad), lon


def sun_latlon_at(epoch, met_s):
    """Sub-solar point at epoch + MET seconds."""
    return subsolar_latlon(epoch + timedelta(seconds=met_s))


def sunlit_cylindrical(position_km, sun_unit, radius_km=EARTH_RADIUS_KM):
    """True when a point is out of Earth's cylindrical shadow."""
    along = sum(p * s for p, s in zip(position_km, sun_unit))
    if along >= 0:
        return True
    perp_sq = sum(p * p for p in position_km) - along * along
    return perp_sq >= radius_km * radius_km
