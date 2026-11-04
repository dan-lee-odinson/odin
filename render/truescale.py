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


PULLBACK_START_LENS_MM = 85.0
PULLBACK_END_LENS_MM = 40.0
PULLBACK_PHASE_DEG = 55.0
PULLBACK_DISC_FRACTION = 0.84
SENSOR_WIDTH_MM = 36.0


def _norm(vec):
    length = math.sqrt(_dot(vec, vec))
    return tuple(v / length for v in vec)


def _smootherstep(u):
    """6u^5 - 15u^4 + 10u^3: still at both ends, smooth between."""
    u = max(0.0, min(1.0, u))
    return u * u * u * (u * (u * 6.0 - 15.0) + 10.0)


def _slerp(a, b, t):
    """Spherical interpolation between two unit vectors."""
    dot = max(-1.0, min(1.0, _dot(a, b)))
    angle = math.acos(dot)
    if angle < 1e-9:
        return a
    sin_angle = math.sin(angle)
    return tuple((math.sin((1.0 - t) * angle) * a[i]
                  + math.sin(t * angle) * b[i]) / sin_angle
                 for i in range(3))


def _half_fov_rad(lens_mm, aspect=16.0 / 9.0):
    """Half the vertical field of view for a full-frame-width sensor."""
    return math.atan((SENSOR_WIDTH_MM / aspect / 2.0) / lens_mm)


def pullback_camera(u, start_location, earth_center, sun_local,
                    aspect=16.0 / 9.0):
    """Camera pose for the pull-back cut at clip progress u (0 to 1).

    At u=0 the pose is the clean cut's own: start_location, looking
    at the spacecraft at the origin, 85 mm. From there the camera
    backs away at a log pace (each frame a small factor farther, so
    no frame jumps), eased at both ends, holding the limb in frame
    through the middle and swinging to face Earth's center only in
    the last third, while the lens widens to 40 mm. The last frame
    sits
    PULLBACK_PHASE_DEG from the Sun direction, tilted toward zenith:
    the sunlit face toward us with the terminator in view, the Sun
    itself far outside the frame, and the whole disc filling
    PULLBACK_DISC_FRACTION of the frame height with black space
    around it. The spacecraft stays at true scale and vanishes; no
    marker replaces it. Clip distances track the subject distances
    so nothing crosses a clipping plane on the way out.

    Returns location, target, up_reference, view_dir (unit tuples in
    meters / direction), lens and clip distances in mm / meters, and
    the framing facts the tests check."""
    zenith = (0.0, 0.0, 1.0)
    north = (0.0, 1.0, 0.0)
    sun = _norm(sun_local)
    center = tuple(float(v) for v in earth_center)
    start = tuple(float(v) for v in start_location)
    eased = _smootherstep(u)
    # Final direction from Earth's center: off the Sun direction by
    # the phase angle, in the Sun/zenith plane, toward zenith.
    phase = math.radians(PULLBACK_PHASE_DEG)
    toward_zenith = _norm(tuple(zenith[i] - sun[i] * _dot(sun, zenith)
                                for i in range(3)))
    final_dir = _norm(tuple(sun[i] * math.cos(phase)
                            + toward_zenith[i] * math.sin(phase)
                            for i in range(3)))
    alpha = PULLBACK_DISC_FRACTION * _half_fov_rad(
        PULLBACK_END_LENS_MM, aspect)
    center_distance_end = EARTH_RADIUS_M / math.sin(alpha)
    final_pos = tuple(center[i] + final_dir[i] * center_distance_end
                      for i in range(3))
    r0 = math.sqrt(_dot(start, start))
    r1 = math.sqrt(_dot(final_pos, final_pos))
    distance = math.exp(math.log(r0) + (math.log(r1) - math.log(r0))
                        * eased)
    direction = _slerp(_norm(start), _norm(final_pos), eased)
    location = tuple(direction[i] * distance for i in range(3))
    center_distance = math.sqrt(sum(
        (location[i] - center[i]) ** 2 for i in range(3)))
    lens = math.exp(math.log(PULLBACK_START_LENS_MM)
                    + (math.log(PULLBACK_END_LENS_MM)
                       - math.log(PULLBACK_START_LENS_MM)) * eased)
    # Look direction: hold the limb in frame through the middle,
    # then swing to Earth's center only in the last third (A9C).
    # Offsetting the view from the center direction by delta puts
    # the disc's top edge (alpha - delta) above the axis; hold that
    # at 0.35 of the half-frame, so the curve of the Earth and
    # black space stay in the picture instead of a straight-down
    # field of magnified cloud. Screen-up stays zenith while the
    # horizon is held (the horizon reads level), then rolls to
    # north with the centering swing for the final disc.
    centering = _smootherstep((u - 2.0 / 3.0) * 3.0)
    up_reference = _norm(tuple(zenith[i] * (1.0 - centering)
                               + north[i] * centering for i in range(3)))
    to_center = _norm(tuple(center[i] - location[i] for i in range(3)))
    alpha_now = math.asin(min(1.0, EARTH_RADIUS_M / center_distance))
    beta_now = _half_fov_rad(lens, aspect)
    delta = max(0.0, alpha_now - 0.35 * beta_now) * (1.0 - centering)
    side_up = _norm(tuple(up_reference[i]
                          - to_center[i] * _dot(up_reference, to_center)
                          for i in range(3)))
    horizon_view = _norm(tuple(
        to_center[i] * math.cos(delta) + side_up[i] * math.sin(delta)
        for i in range(3)))
    if u <= 0.0:
        view_dir = _norm(tuple(-v for v in location))
        target = (0.0, 0.0, 0.0)
    else:
        # Blend off the clean cut's own view (at the spacecraft)
        # over the opening frames, so frame 1 is exactly the clean
        # framing and no frame jumps.
        clean_view = _norm(tuple(-v for v in location))
        view_dir = _slerp(clean_view, horizon_view,
                          _smootherstep(u / 0.05))
        target = tuple(location[i] + view_dir[i] * center_distance
                       for i in range(3))
    nearest = min(distance, max(center_distance - EARTH_RADIUS_M, 1.0))
    sun_angle = math.degrees(math.acos(
        max(-1.0, min(1.0, _dot(view_dir, sun)))))
    from_center = _norm(tuple(location[i] - center[i] for i in range(3)))
    phase_now = math.degrees(math.acos(
        max(-1.0, min(1.0, _dot(from_center, sun)))))
    return {
        "location": location, "target": target,
        "up_reference": up_reference, "view_dir": view_dir,
        "lens_mm": 85.0 if u <= 0.0 else lens,
        "distance_m": distance, "center_distance_m": center_distance,
        "clip_start_m": max(0.05, 0.001 * nearest),
        "clip_end_m": center_distance + 2.0 * EARTH_RADIUS_M,
        "disc_fraction": (math.asin(min(1.0, EARTH_RADIUS_M
                                         / center_distance))
                          / _half_fov_rad(lens, aspect)),
        "sun_view_angle_deg": sun_angle, "phase_deg": phase_now}


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
