# SPDX-License-Identifier: GPL-3.0-or-later
"""True-scale geometry for the A5 look pass.

The follow shot puts the spacecraft at its real size at the origin and
moves Earth around it (the Director's A5 ruling), so nothing jitters at
Earth's scale. The local scene frame is east/north/up at the spacecraft:
+x east, +y north, +z away from Earth's center. Earth (radius 6,371 km)
sits with its center straight down at the orbit row's altitude. All
record geometry (subpoint, station, Sun) is rotated from the
latitude/longitude frame of scene_spec into that local frame here, in
pure Python the tests can check.
"""

import math

import scene_spec as S

EARTH_RADIUS_M = 6371000.0
CLOUD_ALTITUDE_M = 8000.0


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def local_basis(lat_deg, lon_deg):
    """(east, north, up) unit vectors in scene_spec's lat/lon frame."""
    up = S.latlon_to_xyz(lat_deg, lon_deg, 1.0)
    lon = math.radians(lon_deg)
    east = (-math.sin(lon), math.cos(lon), 0.0)
    north = _cross(up, east)
    return east, north, up


def to_local(vec, basis):
    """Components of a lat/lon-frame vector in the east/north/up frame."""
    east, north, up = basis
    return (_dot(vec, east), _dot(vec, north), _dot(vec, up))


def earth_center_m(alt_km):
    """Scene position of Earth's center for a spacecraft at the origin."""
    return (0.0, 0.0, -(EARTH_RADIUS_M + alt_km * 1000.0))


def point_local_m(lat_deg, lon_deg, radius_m, basis, craft_latlon, craft_alt_km):
    """Scene position (meters, crafted at origin) of a lat/lon point."""
    craft_r = EARTH_RADIUS_M + craft_alt_km * 1000.0
    craft = S.latlon_to_xyz(craft_latlon[0], craft_latlon[1], craft_r)
    point = S.latlon_to_xyz(lat_deg, lon_deg, radius_m)
    rel = tuple(p - c for p, c in zip(point, craft))
    return to_local(rel, basis)


def rotation_rows(basis):
    """Rows for the Earth object's rotation matrix in the local frame.

    The Earth mesh is built in the lat/lon frame (its texture is aligned
    there). The matrix whose columns are the local components of the
    lat/lon axes rotates it into the east/north/up frame; returned as the
    row tuples to hand to mathutils.Matrix(...).transposed().
    """
    columns = [to_local(axis, basis) for axis in
               ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))]
    return tuple(columns)
