# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the A1 scene in Blender: the spacecraft and its surroundings.

Run headless from this folder (see README.md for the exact command):
    blender -b --factory-startup --python-exit-code 1 -P build_a1.py
Modes after ``--``:
    (none)       final 1920 x 1080 stills, scene file and scene report
    --preview    half-size stills only, for fast iteration
    --calibrate  one extra still looking straight at the ground station,
                 used to line the Earth texture up with latitude/longitude

All numbers come from scene_spec.py, which the tests check. The script only
reads the ``inputs`` folder and writes under ``out/a1``. It holds no key and
sends nothing anywhere (the brief, rules 4 and 5).
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
from mathutils import Matrix, Vector

import scene_spec as S

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PREVIEW = "--preview" in ARGS or "--calibrate" in ARGS
CALIBRATE = "--calibrate" in ARGS
DS = S.SPACECRAFT_DISPLAY_SCALE  # scene units per meter, spacecraft only


# ---------------------------------------------------------------------------
# Small builders (data API where practical; sizes are full extents)
# ---------------------------------------------------------------------------
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    return scene


def material(name, color, roughness=0.5, metallic=0.0,
             emission=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def box(name, size, location, mat=None, parent=None, collection=None, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("soft edges", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    if mat:
        obj.data.materials.append(mat)
    finish(obj, parent, collection)
    return obj


def cylinder(name, radius, depth, location, mat=None, parent=None,
             collection=None, rotation=(0.0, 0.0, 0.0), vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth,
                                        vertices=vertices, location=location,
                                        rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    finish(obj, parent, collection)
    return obj


def sphere(name, radius, location, mat=None, parent=None, collection=None,
           segments=48, ring_count=32):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location,
                                         segments=segments,
                                         ring_count=ring_count)
    obj = bpy.context.object
    obj.name = name
    for poly in obj.data.polygons:
        poly.use_smooth = True
    if mat:
        obj.data.materials.append(mat)
    finish(obj, parent, collection)
    return obj


def finish(obj, parent, collection):
    if collection is not None:
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent


def no_shadow(obj):
    """Annotations and shells must not cast shadows onto Earth or the craft."""
    if hasattr(obj, "visible_shadow"):
        obj.visible_shadow = False
    return obj


def leader_line(name, start, end, radius, mat=None, collection=None):
    """A thin cylinder from start to end (label leader lines, link lines)."""
    start, end = Vector(start), Vector(end)
    direction = end - start
    obj = cylinder(name, radius, direction.length,
                   (start + end) / 2.0, mat=mat, collection=collection)
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    no_shadow(obj)
    return obj


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def text_label(name, body, size, location, mat=None, parent=None,
               collection=None, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.object.text_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.body = body
    obj.data.size = size
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    if mat:
        obj.data.materials.append(mat)
    finish(obj, parent, collection)
    return obj


# ---------------------------------------------------------------------------
# Earth, orbit, ground station, Sun
# ---------------------------------------------------------------------------
def build_earth():
    # Fine segments so the limb stays smooth at hero-shot range.
    earth = sphere("Earth", S.SCENE_EARTH_RADIUS, (0.0, 0.0, 0.0),
                   segments=160, ring_count=112)
    mat = bpy.data.materials.new("EarthSurface")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (
        0.0, 0.0, math.radians(S.EARTH_TEXTURE_ROTATION_DEG))
    texture = nodes.new("ShaderNodeTexImage")
    image = bpy.data.images.load(str(S.EARTH_TEXTURE))
    image.pack()  # keep the saved scene file self-contained
    texture.image = image
    links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
    links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    earth.data.materials.append(mat)

    # Atmosphere: a soft glow at the limb only. A shell a hair larger than
    # Earth glows on its front faces with a power falloff fading inward
    # over the disk, so there is no outer ring edge (Director, A2). Close
    # shots hide it and draw Earth's clean limb instead.
    glow = sphere("Atmosphere", S.SCENE_EARTH_RADIUS * 1.008, (0.0, 0.0, 0.0),
                  segments=160, ring_count=112)
    no_shadow(glow)
    atmo = bpy.data.materials.new("AtmosphereRim")
    atmo.use_nodes = True
    if hasattr(atmo, "surface_render_method"):
        atmo.surface_render_method = "BLENDED"
    anodes = atmo.node_tree.nodes
    alinks = atmo.node_tree.links
    geometry = anodes.new("ShaderNodeNewGeometry")
    facing = anodes.new("ShaderNodeLayerWeight")
    facing.inputs["Blend"].default_value = 0.35
    power = anodes.new("ShaderNodeMath")
    power.operation = "POWER"
    power.inputs[1].default_value = 4.0
    front_only = anodes.new("ShaderNodeMath")
    front_only.operation = "SUBTRACT"
    front_only.inputs[0].default_value = 1.0
    glow_fac = anodes.new("ShaderNodeMath")
    glow_fac.operation = "MULTIPLY"
    emit = anodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (0.3, 0.55, 1.0, 1.0)
    emit.inputs["Strength"].default_value = 0.8
    alinks.new(facing.outputs["Fresnel"], power.inputs[0])
    alinks.new(geometry.outputs["Backfacing"], front_only.inputs[1])
    alinks.new(power.outputs["Value"], glow_fac.inputs[0])
    alinks.new(front_only.outputs["Value"], glow_fac.inputs[1])
    clear = anodes.new("ShaderNodeBsdfTransparent")
    mix = anodes.new("ShaderNodeMixShader")
    alinks.new(glow_fac.outputs["Value"], mix.inputs["Fac"])
    alinks.new(clear.outputs["BSDF"], mix.inputs[1])
    alinks.new(emit.outputs["Emission"], mix.inputs[2])
    alinks.new(mix.outputs["Shader"],
               anodes["Material Output"].inputs["Surface"])
    glow.data.materials.append(atmo)
    return earth


def build_orbit(rows):
    curve = bpy.data.curves.new("OrbitCurve", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.022
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    points = [S.orbit_xyz(row) for row in rows]
    spline.points.add(len(points) - 1)
    for spline_point, point in zip(spline.points, points):
        spline_point.co = (*point, 1.0)
    obj = bpy.data.objects.new("OrbitPath", curve)
    bpy.context.scene.collection.objects.link(obj)
    no_shadow(obj)
    mat = material("OrbitLine", (0.35, 0.75, 1.0), roughness=0.4,
                   emission=(0.2, 0.6, 1.0), emission_strength=0.9)
    curve.materials.append(mat)
    return obj, points


def build_station(station, materials):
    position = Vector(S.station_xyz(station))
    outward = position.normalized()
    pin = sphere("GroundStation", 0.11, position + outward * 0.05,
                 mat=materials["marker"])
    no_shadow(pin)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.34, minor_radius=0.028,
                                     major_segments=48, minor_segments=10,
                                     location=position + outward * 0.03)
    ring = bpy.context.object
    ring.name = "GroundStationRing"
    ring.rotation_euler = outward.to_track_quat("Z", "Y").to_euler()
    ring.data.materials.append(materials["marker"])
    no_shadow(ring)
    # Label set clear of the marker, over the Atlantic, with a leader line.
    east = Vector((0.0, 0.0, 1.0)).cross(outward).normalized()
    north = outward.cross(east).normalized()
    label_pos = position + outward * 0.5 + east * 2.2 + north * 0.75
    label = text_label("GroundStationLabel", station["name"], 0.34,
                       label_pos, mat=materials["label"])
    # Text faces its local +Z; point that radially outward, toward the viewer.
    label.rotation_euler = label_pos.normalized().to_track_quat(
        "Z", "Y").to_euler()
    leader = leader_line("GroundStationLeader", position + outward * 0.12,
                         label_pos - east * 1.55, 0.014,
                         mat=materials["label"])
    no_shadow(leader)
    no_shadow(label)
    if CALIBRATE:
        label.hide_render = True  # keep the coastline readable in this check
    return pin


def build_sun(materials):
    direction = Vector(S.sun_direction())
    disk = sphere("Sun", S.SUN_DISK_RADIUS, direction * S.SUN_DISTANCE,
                  mat=materials["sun"])
    no_shadow(disk)
    light_data = bpy.data.lights.new("SunLightData", "SUN")
    light_data.energy = 4.5
    light_data.angle = math.radians(0.6)
    light = bpy.data.objects.new("SunLight", light_data)
    bpy.context.scene.collection.objects.link(light)
    light.location = direction * 40.0
    look_at(light, (0.0, 0.0, 0.0))
    return disk


# ---------------------------------------------------------------------------
# The spacecraft: a standard 6U CubeSat with twin solar arrays (drawn look).
# Built in a "Spacecraft" collection under one Empty, in meters times the
# display scale. Local frame (scene_spec): X across, Y thin, Z long;
# the payload faces local -Z and the wings deploy along local +/-X.
# ---------------------------------------------------------------------------
def scaled(value):
    return value * DS


def face_plus_y(obj):
    """Turn a text object to read correctly seen from local +Y, up = +Z."""
    right = Vector((-1.0, 0.0, 0.0))
    up = Vector((0.0, 0.0, 1.0))
    normal = Vector((0.0, 1.0, 0.0))
    obj.rotation_euler = Matrix((right, up, normal)).transposed().to_euler()


def build_wing(empty, collection, mats, prefix, side):
    """One deployable wing. side is +1 (+X, SA2) or -1 (-X, SA1)."""
    bus_x, _bus_y, _bus_z = (scaled(v) for v in S.BUS_DIMS_M)
    panel_w, panel_t, panel_h = (scaled(v) for v in S.PANEL_SIZE_M)
    hinge_x = side * (bus_x / 2.0 + scaled(0.012))
    box(prefix + "_Hinge", (scaled(0.024), scaled(0.03), scaled(0.20)),
        (hinge_x, 0.0, 0.0), mat=mats["rail"], parent=empty,
        collection=collection)
    x = side * (bus_x / 2.0 + scaled(0.024))
    for index in range(1, S.PANELS_PER_WING + 1):
        center_x = x + side * panel_w / 2.0
        panel = box("%s_Panel%d" % (prefix, index),
                    (panel_w, panel_t, panel_h), (center_x, 0.0, 0.0),
                    mat=mats["panel_back"], parent=empty,
                    collection=collection, bevel=scaled(0.002))
        # Solar cells on the +Y face: a 4 x 3 grid of thin glossy tiles.
        cols, tile_rows = 4, 3
        gap = scaled(0.004)
        cell_w = panel_w / cols - gap
        cell_h = panel_h / tile_rows - gap
        cell_y = panel_t / 2.0 + scaled(0.0015)
        count = 0
        for col in range(cols):
            for row_i in range(tile_rows):
                count += 1
                cx = center_x - panel_w / 2.0 + panel_w * (col + 0.5) / cols
                cz = -panel_h / 2.0 + panel_h * (row_i + 0.5) / tile_rows
                box("%s_Panel%d_Cell%02d" % (prefix, index, count),
                    (cell_w, scaled(0.002), cell_h), (cx, cell_y, cz),
                    mat=mats["cell_" + prefix.lower()], parent=empty,
                    collection=collection)
        x += side * (panel_w + scaled(0.006))
    # Wing name plate on the outer panel's cell side.
    outer_x = side * (bus_x / 2.0 + scaled(0.024)
                      + (S.PANELS_PER_WING - 0.5) * panel_w)
    plate = text_label(prefix + "_Label", prefix, scaled(0.05),
                       (outer_x, panel_t / 2.0 + scaled(0.004),
                        -panel_h / 2.0 + scaled(0.035)),
                       mat=mats["plate"], parent=empty, collection=collection)
    face_plus_y(plate)
    return panel


def build_spacecraft(position, mats):
    collection = bpy.data.collections.new("Spacecraft")
    bpy.context.scene.collection.children.link(collection)
    empty = bpy.data.objects.new("HUGINN", None)
    collection.objects.link(empty)
    empty.location = position
    # Drawn pose: local +Z to zenith (payload -Z to nadir), panel normals
    # (+Y) turned as sunward as that allows. The record holds no attitude.
    zenith = Vector(position).normalized()
    sun = Vector(S.sun_direction())
    axis_y = (sun - zenith * sun.dot(zenith)).normalized()
    axis_x = axis_y.cross(zenith).normalized()
    rotation = Matrix((axis_x, axis_y, zenith)).transposed()
    empty.rotation_euler = rotation.to_euler()

    bus_x, bus_y, bus_z = (scaled(v) for v in S.BUS_DIMS_M)
    bus = box("HUGINN_Bus", (bus_x, bus_y, bus_z), (0.0, 0.0, 0.0),
              mat=mats["bus"], parent=empty, collection=collection,
              bevel=scaled(0.003))
    # Aluminum rails along the four long edges.
    for i, (rx, ry) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1)), 1):
        box("Rail%d" % i, (scaled(0.012), scaled(0.012), bus_z * 0.99),
            (rx * bus_x / 2.0, ry * bus_y / 2.0, 0.0), mat=mats["rail"],
            parent=empty, collection=collection)
    # Side panels on the large faces: dark plate +Y, gold foil patch -Y.
    box("SidePanelPlus", (bus_x * 0.88, scaled(0.003), bus_z * 0.9),
        (0.0, bus_y / 2.0 + scaled(0.0015), 0.0), mat=mats["panel_dark"],
        parent=empty, collection=collection)
    box("FoilPatch", (bus_x * 0.8, scaled(0.003), bus_z * 0.55),
        (0.0, -bus_y / 2.0 - scaled(0.0015), scaled(0.03)), mat=mats["gold"],
        parent=empty, collection=collection)
    plate = text_label("NamePlate", "HUGINN", scaled(0.045),
                       (0.0, bus_y / 2.0 + scaled(0.004), scaled(0.10)),
                       mat=mats["plate"], parent=empty, collection=collection)
    face_plus_y(plate)
    # Separation ring and payload on the nadir (-Z) face.
    cylinder("SeparationRing", scaled(0.045), scaled(0.012),
             (0.0, 0.0, -bus_z / 2.0 - scaled(0.004)), mat=mats["rail"],
             parent=empty, collection=collection)
    cylinder("Payload", scaled(0.032), scaled(0.05),
             (scaled(0.045), 0.0, -bus_z / 2.0 - scaled(0.025)),
             mat=mats["payload"], parent=empty, collection=collection)
    cylinder("PayloadLens", scaled(0.024), scaled(0.004),
             (scaled(0.045), 0.0, -bus_z / 2.0 - scaled(0.051)),
             mat=mats["lens"], parent=empty, collection=collection)
    # Patch antenna on the nadir face; stub antenna on the zenith face.
    box("PatchAntenna", (scaled(0.05), scaled(0.05), scaled(0.004)),
        (scaled(-0.05), 0.0, -bus_z / 2.0 - scaled(0.002)),
        mat=mats["plate"], parent=empty, collection=collection)
    cylinder("StubAntenna", scaled(0.0025), scaled(0.09),
             (scaled(-0.07), 0.0, bus_z / 2.0 + scaled(0.045)),
             mat=mats["rail"], parent=empty, collection=collection)
    # A2 state cues on the bus itself: a mode beacon on the zenith face and
    # a load bar on the sunlit face; the A2 driver colors them from record.
    sphere("ModeBeacon", scaled(0.009),
           (scaled(0.06), 0.0, bus_z / 2.0 + scaled(0.006)),
           mat=mats["beacon"], parent=empty, collection=collection)
    box("LoadIndicator", (bus_x * 0.7, scaled(0.004), scaled(0.02)),
        (0.0, bus_y / 2.0 + scaled(0.0035), scaled(-0.13)),
        mat=mats["load_bar"], parent=empty, collection=collection)
    # Corner screws on the +Y face.
    for i, (sx, sz) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1)), 1):
        cylinder("Screw%d" % i, scaled(0.004), scaled(0.003),
                 (sx * bus_x * 0.42, bus_y / 2.0 + scaled(0.003),
                  sz * bus_z * 0.44),
                 mat=mats["rail"], parent=empty, collection=collection,
                 rotation=(math.radians(90.0), 0.0, 0.0), vertices=12)
    build_wing(empty, collection, mats, "SA1", side=-1)
    build_wing(empty, collection, mats, "SA2", side=+1)
    return empty, bus, collection


# ---------------------------------------------------------------------------
# Cameras, materials, rendering
# ---------------------------------------------------------------------------
def make_materials():
    return {
        "bus": material("BusBody", (0.16, 0.17, 0.19), roughness=0.45,
                        metallic=0.6),
        "rail": material("AluminumRail", (0.72, 0.74, 0.76), roughness=0.3,
                         metallic=1.0),
        "panel_dark": material("SidePanel", (0.05, 0.05, 0.06),
                               roughness=0.35, metallic=0.4),
        "panel_back": material("PanelSubstrate", (0.55, 0.57, 0.6),
                               roughness=0.4, metallic=0.9),
        "cell_sa1": material("SolarCellSA1", (0.02, 0.08, 0.35),
                             roughness=0.18, metallic=0.25),
        "cell_sa2": material("SolarCellSA2", (0.02, 0.08, 0.35),
                             roughness=0.18, metallic=0.25),
        "gold": material("GoldFoil", (0.85, 0.55, 0.12), roughness=0.32,
                         metallic=1.0),
        "payload": material("PayloadBarrel", (0.08, 0.08, 0.09),
                            roughness=0.3, metallic=0.7),
        "lens": material("PayloadLensMat", (0.05, 0.25, 0.6),
                         roughness=0.05, metallic=0.1,
                         emission=(0.05, 0.2, 0.5), emission_strength=0.4),
        "plate": material("PlateText", (0.9, 0.92, 0.95), roughness=0.5,
                          emission=(0.9, 0.92, 0.95), emission_strength=0.25),
        "marker": material("StationMarker", (1.0, 0.62, 0.1), roughness=0.4,
                           emission=(1.0, 0.55, 0.08), emission_strength=1.6),
        "label": material("StationLabel", (1.0, 0.8, 0.4), roughness=0.5,
                          emission=(1.0, 0.75, 0.35), emission_strength=0.9),
        "sun": material("SunDisk", (1.0, 0.95, 0.85), roughness=1.0,
                        emission=(1.0, 0.93, 0.78), emission_strength=6.0),
        "craft_marker": material("CraftMarker", (0.25, 0.85, 1.0),
                                 roughness=0.4, emission=(0.2, 0.8, 1.0),
                                 emission_strength=2.0),
        "craft_label": material("CraftLabel", (0.5, 0.92, 1.0), roughness=0.5,
                                emission=(0.4, 0.88, 1.0),
                                emission_strength=0.9),
        "beacon": material("ModeBeaconMat", (0.2, 0.9, 0.3), roughness=0.4,
                           emission=(0.2, 0.9, 0.3), emission_strength=2.0),
        "load_bar": material("LoadBarMat", (0.2, 0.9, 0.3), roughness=0.4,
                             emission=(0.2, 0.9, 0.3), emission_strength=1.4),
        "cue_odin": material("OdinCueMat", (0.3, 0.85, 1.0), roughness=0.4,
                             emission=(0.3, 0.85, 1.0), emission_strength=3.0),
        "cue_baldur": material("BaldurCueMat", (0.3, 1.0, 0.4), roughness=0.4,
                               emission=(0.3, 1.0, 0.4),
                               emission_strength=3.0),
        "link": material("LinkLine", (0.5, 0.95, 0.7), roughness=0.4,
                         emission=(0.4, 1.0, 0.6), emission_strength=1.2),
    }


def add_camera(name, location, target, lens=50.0):
    data = bpy.data.cameras.new(name + "Data")
    data.lens = lens
    data.clip_end = 1000.0
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def spacecraft_axes(position, sun_dir=None):
    """(zenith, sunward, side) unit vectors at the spacecraft, as built."""
    zenith = Vector(position).normalized()
    sun = Vector(sun_dir) if sun_dir is not None else Vector(S.sun_direction())
    sunward = (sun - zenith * sun.dot(zenith)).normalized()
    side = sunward.cross(zenith).normalized()
    return zenith, sunward, side


def build_cameras(position, station):
    pos = Vector(position)
    zenith, sunward, side = spacecraft_axes(position)
    sun = Vector(S.sun_direction())
    station_dir = Vector(S.station_xyz(station)).normalized()
    cameras = {}
    # Wide: the whole Earth with the Americas lit, the orbit arc and the
    # station in view. The Sun disk itself is shown in the payload still.
    wide_dir = (station_dir * 1.0 + sun * 0.45
                + Vector((0.0, 0.0, 0.38))).normalized()
    cameras["CameraWide"] = add_camera(
        "CameraWide", wide_dir * 34.0, (0.0, 0.0, 0.0), lens=40.0)
    # Hero: close three-quarter on the sunlit (cell) side, Earth behind.
    # The wingspan is about 2.1 scene units, so sit about 4 units away.
    hero_loc = pos + sunward * 2.1 + side * 2.6 + zenith * 1.5
    cameras["CameraHero"] = add_camera("CameraHero", hero_loc, pos, lens=50.0)
    # Payload (Director's A2 reframe): near craft level on the foil side,
    # looking slightly down so Earth fills the lower frame and the payload
    # barrel on the nadir face points down at it. The Sun stays out of this
    # frame; its disk is drawn smaller now (scene_spec.SUN_DISK_RADIUS).
    payload_loc = pos - sunward * 3.1 + side * 1.8 - zenith * 0.22
    cameras["CameraPayload"] = add_camera(
        "CameraPayload", payload_loc, pos - zenith * 0.32, lens=34.0)
    if CALIBRATE:
        cameras["CameraCalibrate"] = add_camera(
            "CameraCalibrate", station_dir * 17.0,
            S.station_xyz(station), lens=50.0)
    return cameras


def set_render(scene):
    # The EEVEE engine id differs between Blender generations.
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = S.RENDER_WIDTH
    scene.render.resolution_y = S.RENDER_HEIGHT
    scene.render.resolution_percentage = 50 if PREVIEW else 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    world = bpy.data.worlds.new("Space")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.002, 0.003, 0.008, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    scene.world = world


def hide_collection(collection, hidden):
    for obj in collection.objects:
        obj.hide_render = hidden


def render(scene, camera, filename):
    scene.camera = camera
    scene.render.filepath = str(S.OUT_DIR / filename)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", filename)


def main():
    scene = reset_scene()
    S.OUT_DIR.mkdir(parents=True, exist_ok=True)
    mats = make_materials()
    rows = S.read_orbit()
    station = S.read_station()
    placed = S.orbit_row_at(rows, S.PLACEMENT_MET_S)
    position = S.orbit_xyz(placed)

    build_earth()
    orbit_obj, orbit_points = build_orbit(rows)
    build_station(station, mats)
    sun_disk = build_sun(mats)
    empty, bus, craft_collection = build_spacecraft(position, mats)
    # In the wide shot the true-size drawing would swamp Earth, so the
    # spacecraft's position is marked by a small diamond instead (see
    # README, "Scale"). The hero model is what the close stills show.
    marker = sphere("SpacecraftMarker", 0.13, position,
                    mat=mats["craft_marker"])
    no_shadow(marker)
    # The enlarged craft would cast panel-sized shadows on Earth; face
    # shading still reads, so the craft casts none (drawn scale artifact).
    for obj in craft_collection.objects:
        no_shadow(obj)
    # Earthshine: a soft blue fill from below, the way Earth's albedo
    # lights a spacecraft's nadir side. Local and dim; sun stays the key.
    fill_data = bpy.data.lights.new("EarthshineData", "AREA")
    fill_data.energy = 55.0
    fill_data.shape = "DISK"
    fill_data.size = 3.0
    fill_data.color = (0.45, 0.62, 1.0)
    fill = bpy.data.objects.new("EarthshineFill", fill_data)
    bpy.context.scene.collection.objects.link(fill)
    zenith, sunward, side = spacecraft_axes(position)
    fill.location = (Vector(position) - zenith * 0.4
                     - sunward * 0.5 - side * 0.3)
    look_at(fill, position)
    radial = Vector(position).normalized()
    marker.rotation_euler = radial.to_track_quat("Z", "Y").to_euler()
    marker.scale = (1.0, 1.0, 1.9)
    craft_east = Vector((0.0, 0.0, 1.0)).cross(radial).normalized()
    craft_north = radial.cross(craft_east).normalized()
    craft_label = text_label(
        "SpacecraftLabel", "HUGINN", 0.3,
        Vector(position) + radial * 0.48 - craft_north * 0.85
        + craft_east * 0.35,
        mat=mats["craft_label"])
    craft_label.rotation_euler = radial.to_track_quat("Z", "Y").to_euler()
    no_shadow(craft_label)
    cameras = build_cameras(position, station)
    set_render(scene)
    bpy.context.view_layer.update()

    prefix = "preview_" if PREVIEW else ""
    shots = [("CameraWide", S.STILL_NAMES[0], True),
             ("CameraHero", S.STILL_NAMES[1], False),
             ("CameraPayload", S.STILL_NAMES[2], False)]
    if CALIBRATE:
        shots = [("CameraCalibrate", "a1_calibrate.png", True)]
    for camera_name, filename, wide in shots:
        hide_collection(craft_collection, wide)
        marker.hide_render = not wide
        craft_label.hide_render = not wide
        # The orbit tube passes through the craft; at close range it reads
        # as a pillar across the bus, so only the wide shot draws it. The
        # station annotations likewise belong to the wide shot alone.
        orbit_obj.hide_render = not wide
        # The halo reads as a soft glow only from far off; at close range it
        # is a translucent slab, so close shots draw Earth's clean limb.
        bpy.data.objects["Atmosphere"].hide_render = not wide
        for name in ("GroundStation", "GroundStationRing",
                     "GroundStationLabel", "GroundStationLeader"):
            hidden = not wide
            if CALIBRATE and name == "GroundStationLabel":
                hidden = True
            bpy.data.objects[name].hide_render = hidden
        render(scene, cameras[camera_name], prefix + filename)
    hide_collection(craft_collection, False)
    orbit_obj.hide_render = False
    bpy.data.objects["Atmosphere"].hide_render = False
    for name in ("GroundStation", "GroundStationRing",
                 "GroundStationLabel", "GroundStationLeader"):
        bpy.data.objects[name].hide_render = False
    marker.hide_render = True
    craft_label.hide_render = True
    scene.camera = cameras["CameraHero"]

    if not PREVIEW:
        report = {
            "milestone": "A1",
            "render": {"width": S.RENDER_WIDTH, "height": S.RENDER_HEIGHT,
                       "engine": scene.render.engine},
            "earth": {"radius": S.SCENE_EARTH_RADIUS,
                      "texture": S.EARTH_TEXTURE_NAME,
                      "texture_rotation_deg": S.EARTH_TEXTURE_ROTATION_DEG},
            "station": {"name": station["name"],
                        "lat_deg": station["lat_deg"],
                        "lon_deg": station["lon_deg"],
                        "xyz": list(S.station_xyz(station))},
            "spacecraft": {
                "bus_dims_m": list(S.BUS_DIMS_M),
                "bus_dims_scene": [round(v, 6) for v in bus.dimensions],
                "display_scale": S.SPACECRAFT_DISPLAY_SCALE,
                "enlargement_vs_earth_scale": round(
                    S.spacecraft_enlargement(), 1),
                "placement_met_s": S.PLACEMENT_MET_S,
                "placement_row": placed,
                "xyz": list(position)},
            "orbit": {"point_count": len(orbit_points),
                      "met_range": [rows[0]["met_s"], rows[-1]["met_s"]]},
            "sun": {"xyz": [round(v, 6) for v in sun_disk.location],
                    "lat_deg": round(S.sun_latlon()[0], 4),
                    "lon_deg": round(S.sun_latlon()[1], 4),
                    "met_s": S.PLACEMENT_MET_S,
                    "source": "derived: inputs/epochs.json epoch + MET, "
                              "low-precision solar formula (solar.py)"},
            "objects": sorted(obj.name for obj in bpy.data.objects),
            "stills": list(S.STILL_NAMES),
        }
        S.REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n",
                                 encoding="utf-8")
        blend_path = str(S.OUT_DIR / "huginn_a1.blend")
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)
        print("SAVED scene report and blend file")
    print("A1 BUILD OK preview=%s calibrate=%s" % (PREVIEW, CALIBRATE))


if __name__ == "__main__":
    main()
