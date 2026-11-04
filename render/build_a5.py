# SPDX-License-Identifier: GPL-3.0-or-later
"""A5 look pass: one true-scale follow-shot moment, in both cuts.

Visual target (the Director's A5 ruling, with numbers): real footage from
orbit, not a diagram. The spacecraft at its real size at the origin; the
camera about 3 m away on an 85 mm lens; Earth (radius 6,371 km) moved
around it, its center 6,879 km straight down at the MET-900 altitude, so
the horizon is a wide gentle curve with haze. Cycles, one hard sun (real
0.009 rad disk) from the derived direction, true black shadows, soft blue
earthshine from below, AgX, slight bloom, motion blur on. Earth carries
the 21,600-pixel Blue Marble, a cloud shell 8 km up casting shadows, the
Black Marble night lights fading in across the terminator, a water glint
from a mask derived from the Blue Marble itself, and a thin limb glow.
Clouds and night lights are NASA composites, not the run's date (captions
say so). No station ball; in the instrument cut the contact link is a
fine soft beam toward the station.

Modes after --:
  (none)      both cuts at 1920 x 1080 + a5_still_report.json
  --check     one instrument frame at 640 x 360, for tuning the look
  --animate   keyframe the scene across one run's MET range and render
              the clip + sync file (render_clip.py drives this mode)
  --closeup   one still on the Sun's reflection off the arrays
  --busface   one still of the bus face (--lettering plate|paint)
Options: --met, --cut, --output-dir, --width, --height, --samples;
animate adds --timeline, --inputs, --step, --fps, --met-start,
--met-end, --engine, --clip, --feed.
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
from mathutils import Matrix, Vector

import build_a1 as A1
import scene_spec as S
import solar
import sync as Y
import timeline as T
import truescale as TS

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CHECK = "--check" in ARGS
FIXTURE = "--fixture" in ARGS
ANIMATE = "--animate" in ARGS
CLOSEUP = "--closeup" in ARGS
BUSFACE = "--busface" in ARGS
# Instrument-cut annotations that never appear in the clean cut.
CAPTION_NAMES = ("SA1_Caption", "SA2_Caption",
                 "SA1_CaptionLeader", "SA2_CaptionLeader")


def arg(flag, default=None):
    return ARGS[ARGS.index(flag) + 1] if flag in ARGS else default


OUT = Path(arg("--output-dir",
                 S.ROOT / "out" / ("a2" if FIXTURE else "a5"))).resolve()
MET = int(arg("--met", "900"))
WIDTH = int(arg("--width", "640" if CHECK else "960" if (FIXTURE or ANIMATE) else "1920"))
HEIGHT = int(arg("--height", "360" if CHECK else "540" if (FIXTURE or ANIMATE) else "1080"))
SAMPLES = int(arg("--samples", "32" if CHECK else "48" if ANIMATE else "64" if FIXTURE else "128"))
CUTS = ["instrument"] if (CHECK or FIXTURE) else (
    [arg("--cut")] if arg("--cut") else ["clean", "instrument"])
FIXTURE_LABELS = {890: "sunlit", 920: "eclipse_red", 945: "safe_deny"}


def bsdf(mat):
    return mat.node_tree.nodes["Principled BSDF"]


def earth_material(sun_local):
    """Day map + water glint (mask from the day map) + night lights."""
    mat = bpy.data.materials.new("EarthTrue")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = nodes["Material Output"]
    node = bsdf(mat)
    day = nodes.new("ShaderNodeTexImage")
    day.image = bpy.data.images.load(str(S.EARTH_TEXTURE))
    # Haze: toward the horizon (grazing view) the ground fades into blue.
    geo_haze = nodes.new("ShaderNodeLayerWeight")
    geo_haze.inputs["Blend"].default_value = 0.4
    haze_pow = nodes.new("ShaderNodeMath")
    haze_pow.operation = "POWER"
    haze_pow.inputs[1].default_value = 3.0
    links.new(geo_haze.outputs["Fresnel"], haze_pow.inputs[0])
    haze_gain = nodes.new("ShaderNodeMath")
    haze_gain.operation = "MULTIPLY"
    haze_gain.inputs[1].default_value = 0.22
    links.new(haze_pow.outputs["Value"], haze_gain.inputs[0])
    haze_mix = nodes.new("ShaderNodeMixRGB")
    haze_mix.inputs["Color2"].default_value = (0.45, 0.62, 0.88, 1.0)
    links.new(haze_gain.outputs["Value"], haze_mix.inputs["Fac"])
    links.new(day.outputs["Color"], haze_mix.inputs["Color1"])
    links.new(haze_mix.outputs["Color"], node.inputs["Base Color"])
    node.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in node.inputs:
        node.inputs["Specular IOR Level"].default_value = 0.4
    # Water mask from the Blue Marble itself: oceans run blue-dominant.
    separate = nodes.new("ShaderNodeSeparateColor")
    links.new(day.outputs["Color"], separate.inputs["Color"])
    blue_minus_red = nodes.new("ShaderNodeMath")
    blue_minus_red.operation = "SUBTRACT"
    links.new(separate.outputs["Blue"], blue_minus_red.inputs[0])
    links.new(separate.outputs["Red"], blue_minus_red.inputs[1])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.02
    ramp.color_ramp.elements[1].position = 0.12
    links.new(blue_minus_red.outputs["Value"], ramp.inputs["Fac"])
    # Roughness floor stays moderate: mirror-smooth water would reflect
    # black space at side angles and read as a gray slab.
    gain = nodes.new("ShaderNodeMath")  # roughness = 0.92 - 0.55 * water
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = -0.55
    links.new(ramp.outputs["Color"], gain.inputs[0])
    rough = nodes.new("ShaderNodeMath")
    rough.operation = "ADD"
    rough.inputs[1].default_value = 0.92
    links.new(gain.outputs["Value"], rough.inputs[0])
    links.new(rough.outputs["Value"], node.inputs["Roughness"])
    # Night lights, fading in across the terminator (normal . sun).
    geometry = nodes.new("ShaderNodeNewGeometry")
    sun_vec = nodes.new("ShaderNodeCombineXYZ")
    for i, axis in enumerate(("X", "Y", "Z")):
        sun_vec.inputs[axis].default_value = sun_local[i]
    dot = nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    links.new(geometry.outputs["Normal"], dot.inputs[0])
    links.new(sun_vec.outputs["Vector"], dot.inputs[1])
    night_fac = nodes.new("ShaderNodeMapRange")
    night_fac.inputs["From Min"].default_value = 0.08
    night_fac.inputs["From Max"].default_value = -0.18
    night_fac.inputs["To Min"].default_value = 0.0
    night_fac.inputs["To Max"].default_value = 1.6
    night_fac.clamp = True
    links.new(dot.outputs["Value"], night_fac.inputs["Value"])
    night = nodes.new("ShaderNodeTexImage")
    night.image = bpy.data.images.load(
        str(S.INPUTS / "imagery" / "BlackMarble_2016_3km.jpg"))
    emit = nodes.new("ShaderNodeEmission")
    links.new(night.outputs["Color"], emit.inputs["Color"])
    links.new(night_fac.outputs["Result"], emit.inputs["Strength"])
    add = nodes.new("ShaderNodeAddShader")
    links.new(node.outputs["BSDF"], add.inputs[0])
    links.new(emit.outputs["Emission"], add.inputs[1])
    links.new(add.outputs["Shader"], out.inputs["Surface"])
    # The sun-vector node rides along so animation can keyframe the
    # terminator the night lights fade across.
    return mat, sun_vec


def cloud_material():
    mat = bpy.data.materials.new("Clouds")
    mat.use_nodes = True
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    try:
        mat.cycles.use_transparent_shadow = True
    except Exception:
        pass
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(
        str(S.INPUTS / "imagery" / "cloud_combined_8192.tif"))
    ramp = nodes.new("ShaderNodeValToRGB")  # white-on-black = coverage
    # A wide ramp capped below full opacity: soft edges, thin cloud
    # translucent, and no hard-edged white patches.
    ramp.color_ramp.elements[0].position = 0.02
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.7, 0.7, 0.7, 1.0)
    links.new(tex.outputs["Color"], ramp.inputs["Fac"])
    cloud = bsdf(mat)
    # Brightness carries the cloud shape: the texture itself shades the
    # base color, lifted and compressed so thin cloud stays gentle.
    shade = nodes.new("ShaderNodeBrightContrast")
    shade.inputs["Bright"].default_value = 0.45
    shade.inputs["Contrast"].default_value = -0.25
    links.new(tex.outputs["Color"], shade.inputs["Color"])
    links.new(shade.outputs["Color"], cloud.inputs["Base Color"])
    cloud.inputs["Roughness"].default_value = 0.95
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(ramp.outputs["Color"], mix.inputs["Fac"])
    links.new(clear.outputs["BSDF"], mix.inputs[1])
    links.new(cloud.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], nodes["Material Output"].inputs["Surface"])
    return mat


def atmosphere_material():
    """Thin front-face limb glow, the A1 recipe at true scale."""
    mat = bpy.data.materials.new("AtmosphereTrue")
    mat.use_nodes = True
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    geometry = nodes.new("ShaderNodeNewGeometry")
    facing = nodes.new("ShaderNodeLayerWeight")
    facing.inputs["Blend"].default_value = 0.35
    power = nodes.new("ShaderNodeMath")
    power.operation = "POWER"
    power.inputs[1].default_value = 9.0
    # Roll the glow off again right at the silhouette, so it has no hard
    # top edge: fac = f^9 * (1 - f^48), brightest just inside the limb
    # and fading into black (a thinner band: Director, A5 animate).
    rolloff = nodes.new("ShaderNodeMath")
    rolloff.operation = "POWER"
    rolloff.inputs[1].default_value = 48.0
    one_minus = nodes.new("ShaderNodeMath")
    one_minus.operation = "SUBTRACT"
    one_minus.inputs[0].default_value = 1.0
    band = nodes.new("ShaderNodeMath")
    band.operation = "MULTIPLY"
    front = nodes.new("ShaderNodeMath")
    front.operation = "SUBTRACT"
    front.inputs[0].default_value = 1.0
    fac = nodes.new("ShaderNodeMath")
    fac.operation = "MULTIPLY"
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (0.3, 0.55, 1.0, 1.0)
    emit.inputs["Strength"].default_value = 0.85
    links.new(facing.outputs["Fresnel"], power.inputs[0])
    links.new(facing.outputs["Fresnel"], rolloff.inputs[0])
    links.new(rolloff.outputs["Value"], one_minus.inputs[1])
    links.new(power.outputs["Value"], band.inputs[0])
    links.new(one_minus.outputs["Value"], band.inputs[1])
    links.new(geometry.outputs["Backfacing"], front.inputs[1])
    links.new(band.outputs["Value"], fac.inputs[0])
    links.new(front.outputs["Value"], fac.inputs[1])
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(fac.outputs["Value"], mix.inputs["Fac"])
    links.new(clear.outputs["BSDF"], mix.inputs[1])
    links.new(emit.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], nodes["Material Output"].inputs["Surface"])
    return mat


def make_sphere(name, radius, center, rotation, mat, segments=128):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=center,
                                         segments=segments,
                                         ring_count=segments * 3 // 4)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = Matrix(rotation).transposed().to_euler()
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.materials.append(mat)
    return obj


def add_strikes(camera, state):
    """Sensor strikes for the fixture/feed case: 1-3 px white specks of
    varied brightness just in front of the lens, count following flux."""
    import random
    flux = (state.get("weather") or {}).get("proton_flux_pfu", 0.0)
    if flux <= 0:
        return
    level = min(1.0, math.log10(flux + 1.0) / 1.7)
    count = int(round(26 * level))
    mats = []
    for i, strength in enumerate((3.0, 8.0, 16.0, 28.0)):
        mat = bpy.data.materials.new("Strike%d" % i)
        mat.use_nodes = True
        emit = mat.node_tree.nodes.new("ShaderNodeEmission")
        emit.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        emit.inputs["Strength"].default_value = strength
        mat.node_tree.links.new(
            emit.outputs["Emission"],
            mat.node_tree.nodes["Material Output"].inputs["Surface"])
        mats.append(mat)
    rng = random.Random(int(state["met_s"]) * 131)
    for i in range(count):
        length = rng.uniform(0.000035, 0.00008)
        if rng.random() < 0.2:  # now and then a short squiggle
            length = rng.uniform(0.00011, 0.00018)
        speck = A1.box("Strike%02d" % i, (length, 0.000047, 0.000047),
                       (rng.uniform(-0.014, 0.014),
                        rng.uniform(-0.008, 0.008), -0.07),
                       mat=rng.choice(mats), parent=camera)
        speck.rotation_euler = (0.0, 0.0, rng.uniform(0.0, math.pi))
    camera.data.clip_start = 0.01


def detail_materials(mats):
    """The look pass on the drawn spacecraft (shared by still + clip).
    A6 moved the cell grid, brushed metals, glass and faceted foil
    into build_a1's materials; what stays here is the true-scale
    finish: bright silver substrate in the cell gaps."""
    sub = bsdf(bpy.data.materials["PanelSubstrate"])
    sub.inputs["Base Color"].default_value = (0.75, 0.77, 0.8, 1.0)
    sub.inputs["Roughness"].default_value = 0.32
    sub.inputs["Metallic"].default_value = 1.0


def beam_material(name, strength, transparent_fac):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (0.45, 1.0, 0.65, 1.0)
    emit.inputs["Strength"].default_value = strength
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = transparent_fac
    links.new(emit.outputs["Emission"], mix.inputs[1])
    links.new(clear.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"],
              nodes["Material Output"].inputs["Surface"])
    return mat


def make_lights(scene, earth, clouds, glow, craft_coll, empty):
    """Two suns (Earth / craft, light-linked), earthshine, eclipse rim."""
    sun_data = bpy.data.lights.new("SunData", "SUN")
    sun_data.energy = 6.0
    sun_data.angle = 0.0093  # the Sun's real size in the sky, ~0.53 deg
    sun = bpy.data.objects.new("SunLight", sun_data)
    scene.collection.objects.link(sun)
    earth_coll = bpy.data.collections.new("EarthOnly")
    scene.collection.children.link(earth_coll)
    for obj in (earth, clouds, glow):
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        earth_coll.objects.link(obj)
    craft_data = bpy.data.lights.new("SunCraftData", "SUN")
    craft_data.energy = sun_data.energy
    craft_data.angle = sun_data.angle
    craft_sun = bpy.data.objects.new("SunCraftLight", craft_data)
    scene.collection.objects.link(craft_sun)
    for light, coll in ((sun, earth_coll), (craft_sun, craft_coll)):
        if hasattr(light, "light_linking"):
            light.light_linking.receiver_collection = coll
    fill_data = bpy.data.lights.new("EarthshineData", "AREA")
    fill_data.energy = 180.0
    fill_data.shape = "DISK"
    fill_data.size = 8.0
    fill_data.color = (0.45, 0.62, 1.0)
    fill = bpy.data.objects.new("EarthshineFill", fill_data)
    scene.collection.objects.link(fill)
    fill.location = (0.0, 0.0, -7.0)
    fill.rotation_euler = (math.pi, 0.0, 0.0)
    rim_data = bpy.data.lights.new("EclipseRimData", "POINT")
    rim_data.energy = 0.0
    rim_data.color = (0.65, 0.8, 1.0)
    rim_data.use_shadow = False
    rim = bpy.data.objects.new("EclipseRim", rim_data)
    scene.collection.objects.link(rim)
    rim.parent = empty
    rim.location = (0.0, 0.9, 0.5)
    return sun, craft_sun, fill, rim


def geometry_at(epoch, rows, met):
    """(row, basis, sun_local, rotation rows, center) for one MET."""
    row = S.orbit_row_at(rows, float(met))
    basis = TS.local_basis(row["lat_deg"], row["lon_deg"])
    sun_local = TS.to_local(
        S.latlon_to_xyz(*solar.sun_latlon_at(epoch, met), 1.0), basis)
    return (row, basis, sun_local, TS.rotation_rows(basis),
            TS.earth_center_m(row["alt_km"]))


def build_scene(epoch, rows, met, with_cues=False, with_weather=False,
                earth_segments=128):
    """The true-scale follow scene at an initial MET; returns handles."""
    _row, _basis, sun_local, rotation, center = geometry_at(epoch, rows, met)
    scene = A1.reset_scene()
    scene.unit_settings.scale_length = 1.0
    mats = A1.make_materials()
    detail_materials(mats)
    A1.DS = 1.0  # the spacecraft at its real size, in meters
    empty, _bus_obj, craft_coll = A1.build_spacecraft((0.0, 0.0, 10.0), mats)
    empty.location = (0.0, 0.0, 0.0)
    # Two small extras the detail pass adds: a wire antenna, a tracker.
    A1.cylinder("WireAntenna", 0.0012, 0.17, (-0.08, -0.03, -0.26),
                mat=mats["rail"], parent=empty, collection=craft_coll,
                rotation=(0.5, 0.2, 0.0), vertices=8)
    A1.cylinder("StarTracker", 0.012, 0.03, (0.12, 0.0, 0.08),
                mat=mats["payload"], parent=empty, collection=craft_coll,
                rotation=(0.0, math.radians(90.0), 0.0))
    # A second load strip on the top edge, so the instrument cut's load
    # state reads from the sun-side three-quarter view as well.
    A1.box("LoadIndicatorTop", (0.10, 0.012, 0.002), (0.0, 0.04, 0.184),
           mat=mats["load_bar"], parent=empty, collection=craft_coll)
    earth_mat, sun_vec = earth_material(sun_local)
    earth = make_sphere("Earth", TS.EARTH_RADIUS_M, center, rotation,
                        earth_mat, segments=earth_segments)
    shell_segments = max(96, earth_segments * 3 // 4)
    clouds = make_sphere("Clouds", TS.EARTH_RADIUS_M + TS.CLOUD_ALTITUDE_M,
                         center, rotation, cloud_material(),
                         segments=shell_segments)
    glow = make_sphere("Atmosphere", TS.EARTH_RADIUS_M * 1.003, center,
                       rotation, atmosphere_material(),
                       segments=shell_segments)
    A1.no_shadow(glow)
    sun, craft_sun, fill, rim = make_lights(scene, earth, clouds, glow,
                                            craft_coll, empty)
    # Contact link: unit-length cylinders; apply_met stretches them from
    # the patch antenna toward the station each MET.
    beam = A1.leader_line("ContactBeam", (0.0, 0.0, -0.2), (0.0, 0.0, -1.2),
                          0.0025, mat=beam_material("LinkBeam", 1.6, 0.35))
    beam_glow = A1.leader_line("ContactBeamGlow", (0.0, 0.0, -0.2),
                               (0.0, 0.0, -1.2), 0.009,
                               mat=beam_material("LinkBeamGlow", 0.25, 0.93))
    cam_data = bpy.data.cameras.new("FollowCamData")
    cam_data.lens = 85.0
    cam_data.clip_start = 0.05
    cam_data.clip_end = 3.0e7
    camera = bpy.data.objects.new("FollowCam", cam_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    cues = {}
    if with_cues:
        for name, mat_key, x in (("OdinCue", "cue_odin", -0.09),
                                 ("BaldurCue", "cue_baldur", 0.09)):
            cue = A1.sphere(name, 0.011, (x, 0.0, 0.195), mat=mats[mat_key],
                            parent=empty, collection=craft_coll)
            cue.scale = (0.001, 0.001, 0.001)
            A1.no_shadow(cue)
            cues[name] = cue
    specks = []
    if with_weather:
        import random as _random
        pick = _random.Random(3)
        strike_mats = []
        for i, strength in enumerate((3.0, 8.0, 16.0, 28.0)):
            mat = bpy.data.materials.new("Strike%d" % i)
            mat.use_nodes = True
            emit = mat.node_tree.nodes.new("ShaderNodeEmission")
            emit.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
            emit.inputs["Strength"].default_value = strength
            mat.node_tree.links.new(
                emit.outputs["Emission"],
                mat.node_tree.nodes["Material Output"].inputs["Surface"])
            strike_mats.append(mat)
        for i in range(26):
            speck = A1.box("Strike%02d" % i, (0.00005, 0.000047, 0.000047),
                           (0.0, 0.0, -0.07), mat=pick.choice(strike_mats),
                           parent=camera)
            speck.hide_render = True
            specks.append(speck)
        camera.data.clip_start = 0.01
    return {"scene": scene, "mats": mats, "empty": empty,
            "craft_coll": craft_coll, "earth": earth, "clouds": clouds,
            "glow": glow, "sun_vec": sun_vec, "sun": sun,
            "craft_sun": craft_sun, "fill": fill, "rim": rim,
            "beam": beam, "beam_glow": beam_glow, "camera": camera,
            "cues": cues, "specks": specks,
            "station": S.read_station(S.STATION_JSON)}


LOAD_COLORS = {"YELLOW": (1.0, 0.30, 0.0), "RED": (1.0, 0.08, 0.05)}
MODE_COLORS = {"NOMINAL": (0.2, 0.9, 0.3), "LOW_POWER": (1.0, 0.7, 0.15),
               "SAFE": (1.0, 0.2, 0.15)}


def load_color(state):
    limit = state["load_limit"] or ""
    for prefix, color in LOAD_COLORS.items():
        if limit.startswith(prefix):
            return color
    return (0.2, 0.9, 0.3)


def apply_met(H, timeline, epoch, rows, met, feed_reports=(), frame=None,
              cue_kinds=(), clean=False, pullback=None):
    """Put one MET's geometry and record state into the scene.

    With a frame number, everything is keyframed there; transform curves
    interpolate smoothly between frames while record-state curves are
    set CONSTANT afterwards, so state changes land on their record MET.
    Returns the state dict."""
    import build_a2 as A2
    key = (lambda obj, prop: obj.keyframe_insert(prop, frame=frame)) \
        if frame is not None else (lambda obj, prop: None)
    state = T.state_at(timeline, met, feed_reports)
    row, basis, sun_local, rotation, center = geometry_at(epoch, rows, met)
    zenith = Vector((0.0, 0.0, 1.0))
    sun_v = Vector(sun_local)
    sunward = (sun_v - zenith * sun_v.dot(zenith)).normalized()
    axis_x = sunward.cross(zenith).normalized()
    H["empty"].rotation_euler = Matrix(
        (axis_x, sunward, zenith)).transposed().to_euler()
    key(H["empty"], "rotation_euler")
    rot = Matrix(rotation).transposed().to_euler()
    for obj in (H["earth"], H["clouds"], H["glow"]):
        obj.location = Vector(center)
        obj.rotation_euler = rot
        key(obj, "location")
        key(obj, "rotation_euler")
    for i, axis in enumerate(("X", "Y", "Z")):
        H["sun_vec"].inputs[axis].default_value = sun_local[i]
        if frame is not None:
            H["sun_vec"].inputs[axis].keyframe_insert("default_value",
                                                      frame=frame)
    for light in (H["sun"], H["craft_sun"]):
        light.location = sun_v * 1000.0
        A1.look_at(light, (0.0, 0.0, 0.0))
        key(light, "location")
        key(light, "rotation_euler")
    sunlit = state["sunlit"]
    # One hard light, the Sun; the only fill is earthshine from below
    # (a soft blue area light standing in for sunlit Earth, plus the
    # bounce Cycles picks up from the planet itself). Faces turned
    # away from both go nearly black (Director, A6 round two).
    for light, energy in ((H["craft_sun"], 0.05 if sunlit is False else 6.0),
                          (H["fill"], 15.0 if sunlit is False else 85.0),
                          (H["rim"], 0.5 if sunlit is False else 0.0)):
        light.data.energy = energy
        if frame is not None:
            light.data.keyframe_insert("energy", frame=frame)
    # Side light (Director, round three): south of the craft and somewhat
    # sunward; from 508 km this height looks down about 26 degrees. The
    # camera's path is drawn, so it also drifts slowly in azimuth across
    # the run (Director, A6): about 18 degrees from MET 800 to 1225,
    # enough for a Sun glint to sweep the arrays during a clip. The
    # Sun's direction itself stays the derived one.
    perp = Vector((-sunward.y, sunward.x, 0.0))
    if perp.y > 0:
        perp = -perp
    drift = math.radians(-9.0 + 18.0 * max(0.0, min(1.0,
                                                     (met - 800) / 425.0)))
    along = 1.6 * math.cos(drift) - 2.3 * math.sin(drift)
    across = 1.6 * math.sin(drift) + 2.3 * math.cos(drift)
    camera = H["camera"]
    camera.location = sunward * along + perp * across \
        + Vector((0.0, 0.0, 1.35))
    if pullback is not None:
        # A9: from this frame's clean framing, ease out to the whole
        # Earth (truescale.pullback_camera owns the math and its
        # tests). Lens widens and clip distances track the subjects
        # on the way, all keyframed like the move itself.
        pose = TS.pullback_camera(pullback, tuple(camera.location),
                                  center, sun_local,
                                  aspect=WIDTH / HEIGHT)
        camera.location = Vector(pose["location"])
        back = (camera.location - Vector(pose["target"])).normalized()
        up_ref = Vector(pose["up_reference"])
        camera.data.lens = pose["lens_mm"]
        camera.data.clip_start = pose["clip_start_m"]
        camera.data.clip_end = pose["clip_end_m"]
        # No shutter on this move (A9B): it is the one camera move
        # fast enough for motion blur to streak the sunlit Earth
        # into the black sky and across the spacecraft. Other cuts
        # keep set_render_common's motion blur.
        H["scene"].render.use_motion_blur = False
        if frame is not None:
            for prop in ("lens", "clip_start", "clip_end"):
                camera.data.keyframe_insert(prop, frame=frame)
    else:
        back = camera.location.normalized()
        up_ref = zenith
    up = (up_ref - back * up_ref.dot(back)).normalized()
    right = up.cross(back).normalized()
    camera.rotation_euler = Matrix((right, up, back)).transposed().to_euler()
    key(camera, "location")
    key(camera, "rotation_euler")
    for mat_name, key_name in (("SolarCellSA1", "sa1_i"),
                               ("SolarCellSA2", "sa2_i")):
        amps = state[key_name]
        level = 1.0 if amps is None else max(0.0, min(1.0, amps / 1.7))
        color = tuple(c * (0.12 + 0.88 * level)
                      for c in (0.03, 0.035, 0.17))
        A1.set_cell_color(bpy.data.materials[mat_name], color, frame)
    A2.set_emission(H["mats"]["beacon"],
                    MODE_COLORS.get(state["mode"], (0.4, 0.4, 0.42)),
                    2.0, frame)
    A2.set_emission(H["mats"]["load_bar"], load_color(state), 1.0, frame)
    lens = bsdf(H["mats"]["lens"])
    lens.inputs["Emission Strength"].default_value = \
        1.3 if state["payload_on"] else 0.05
    if frame is not None:
        lens.inputs["Emission Strength"].keyframe_insert("default_value",
                                                         frame=frame)
    # The link starts at the patch antenna itself and runs stationward.
    st_local = Vector(TS.point_local_m(
        H["station"]["lat_deg"], H["station"]["lon_deg"],
        TS.EARTH_RADIUS_M, basis, (row["lat_deg"], row["lon_deg"]),
        row["alt_km"]))
    bpy.context.view_layer.update()
    antenna = bpy.data.objects["PatchAntenna"].matrix_world.translation.copy()
    direction = (st_local - antenna).normalized()
    start = antenna + direction * 0.01
    end = antenna + direction * 140.0
    for beam in (H["beam"], H["beam_glow"]):
        beam.location = (start + end) / 2.0
        beam.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
        beam.scale = (1.0, 1.0, (end - start).length)
        beam.hide_render = clean or not state["in_contact"]
        for prop in ("location", "rotation_euler", "scale", "hide_render"):
            key(beam, prop)
    for name, kind in (("OdinCue", "odin"), ("BaldurCue", "baldur")):
        cue = H["cues"].get(name)
        if cue is not None:
            on = kind in cue_kinds and not clean
            cue.scale = (1.0, 1.0, 1.0) if on else (0.001, 0.001, 0.001)
            key(cue, "scale")
    if H["specks"]:
        import random as _random
        flux = (state.get("weather") or {}).get("proton_flux_pfu", 0.0)
        level = min(1.0, math.log10(flux + 1.0) / 1.7) if flux > 0 else 0.0
        count = int(round(len(H["specks"]) * level))
        rng = _random.Random(int(met) * 131)
        for i, speck in enumerate(H["specks"]):
            length = rng.uniform(0.7, 1.6)
            if rng.random() < 0.2:
                length = rng.uniform(2.2, 3.6)
            speck.location = (rng.uniform(-0.014, 0.014),
                              rng.uniform(-0.008, 0.008), -0.07)
            speck.rotation_euler = (0.0, 0.0, rng.uniform(0.0, math.pi))
            speck.scale = (length, 1.0, 1.0)
            speck.hide_render = i >= count
            for prop in ("location", "rotation_euler", "scale",
                         "hide_render"):
                key(speck, prop)
    return state


def set_render_common(scene, engine="CYCLES"):
    """Cycles/AgX/bloom/black-space setup shared by stills and clips."""
    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = SAMPLES
        scene.cycles.use_denoising = True
    else:
        try:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
        except TypeError:
            scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = SAMPLES
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.view_settings.view_transform = "AgX"
    # Exposure set so the shadowed side keeps a little detail while
    # AgX rolls the highlights off (Director, A6 round two).
    scene.view_settings.exposure = 0.25
    world = bpy.data.worlds.new("Space")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bg.inputs["Strength"].default_value = 0.0
    scene.world = world
    try:  # slight bloom on bright glints, where the compositor allows
        tree = bpy.data.node_groups.new("Compositor", "CompositorNodeTree")
        scene.compositing_node_group = tree
        rl = tree.nodes.new("CompositorNodeRLayers")
        glare = tree.nodes.new("CompositorNodeGlare")
        if hasattr(glare, "glare_type"):
            glare.glare_type = "FOG_GLOW"
            glare.threshold = 0.85
        else:  # Blender 5: glare settings live on input sockets
            if "Type" in glare.inputs:
                glare.inputs["Type"].default_value = "Fog Glow"
            if "Threshold" in glare.inputs:
                glare.inputs["Threshold"].default_value = 0.85
        out_node = tree.nodes.new("NodeGroupOutput")
        tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
        tree.links.new(glare.outputs["Image"], out_node.inputs[0])
    except Exception as exc:
        print("bloom skipped:", exc)


def constant_state_curves():
    """Record-state curves hold their value (CONSTANT) so a state change
    lands on its record MET; transforms keep smooth LINEAR travel."""
    def fcurves_of(action):
        found = []
        legacy = getattr(action, "fcurves", None)
        if legacy is not None and not callable(legacy):
            found = list(legacy)
        for layer in getattr(action, "layers", []) or []:
            for strip in layer.strips:
                # Blender 5: one channel bag per slot on the strip.
                for bag in getattr(strip, "channelbags", []) or []:
                    found.extend(bag.fcurves)
        return found
    for action in bpy.data.actions:
        for fcurve in fcurves_of(action):
            smooth = any(k in fcurve.data_path for k in
                         ("location", "rotation_euler"))
            for point in fcurve.keyframe_points:
                point.interpolation = "LINEAR" if smooth else "CONSTANT"


def main():
    if arg("--lettering"):
        A1.NAMEPLATE_STYLE = arg("--lettering")
    feed_reports = ()
    if FIXTURE:
        timeline = T.load_timeline(
            S.ROOT / "tests" / "fixtures" / "made_up_timeline.json")
        feed_reports = T.load_feed(
            S.ROOT / "inputs" / "feeds" / "made-up-feed-timeline.json")
        epoch = solar.read_epoch("dev-ph2-p3-open-01")
    else:
        timeline = T.load_timeline(
            S.INPUTS / "timelines" / "dev-ph2-p3-open-01.js")
        epoch = solar.read_epoch(timeline["id"])
    rows = S.read_orbit()
    row = S.orbit_row_at(rows, float(MET))
    H = build_scene(epoch, rows, MET)
    scene, camera = H["scene"], H["camera"]
    state = apply_met(H, timeline, epoch, rows, MET, feed_reports)

    set_render_common(scene)
    scene.render.image_settings.file_format = "PNG"
    if CLOSEUP:
        # A6 close-up: on the Sun's reflection off the SA2 coverglass,
        # so the arrays catch the light. Clean of text and cues.
        _r, _b, sun_local, _rot, _c = geometry_at(epoch, rows, MET)
        zenith = Vector((0.0, 0.0, 1.0))
        sun_v = Vector(sun_local)
        sunward = (sun_v - zenith * sun_v.dot(zenith)).normalized()
        axis_x = sunward.cross(zenith).normalized()
        target = axis_x * 0.42
        incident = -sun_v.normalized()
        reflected = (incident
                     - 2.0 * incident.dot(sunward) * sunward).normalized()
        # Near the reflection but off its axis, so the glint band sweeps
        # part of the array instead of blowing out the whole frame.
        look = target - axis_x * 0.22
        camera.location = target + reflected * 1.9 + axis_x * 0.20 \
            + zenith * 0.12
        back = (camera.location - look).normalized()
        up = (zenith - back * zenith.dot(back)).normalized()
        right = up.cross(back).normalized()
        camera.rotation_euler = Matrix(
            (right, up, back)).transposed().to_euler()
        for name in ("ModeBeacon", "LoadIndicator", "LoadIndicatorTop",
                     "ContactBeam", "ContactBeamGlow", "NamePlate",
                     "NamePlateBack") + CAPTION_NAMES:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_render = True
        print("A6 CLOSEUP device:", enable_gpu(scene))
        OUT.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(OUT / "a6_closeup.png")
        bpy.ops.render.render(write_still=True)
        print("A6 CLOSEUP OK", scene.render.filepath)
        return
    if BUSFACE:
        # A6 round two: the bus face with its name, one render per
        # lettering style (--lettering plate|paint) for the Director
        # to pick. Camera half a meter off the sunlit face, three-
        # quarter so seams, edges and small parts catch the light.
        bpy.context.view_layer.update()
        matrix = H["empty"].matrix_world
        look = matrix @ Vector((0.0, 0.05, 0.04))
        camera.location = matrix @ Vector((0.26, 0.78, 0.11))
        back = (camera.location - look).normalized()
        zenith = Vector((0.0, 0.0, 1.0))
        up = (zenith - back * zenith.dot(back)).normalized()
        right = up.cross(back).normalized()
        camera.rotation_euler = Matrix(
            (right, up, back)).transposed().to_euler()
        camera.data.clip_start = 0.01
        for name in ("ContactBeam", "ContactBeamGlow") + CAPTION_NAMES:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_render = True
        style = arg("--lettering", "plate")
        print("A6 BUSFACE device:", enable_gpu(scene), "style:", style)
        OUT.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(OUT / ("a6_bus_%s.png" % style))
        bpy.ops.render.render(write_still=True)
        print("A6 BUSFACE OK", scene.render.filepath)
        return

    # (Scene, lights, link and camera are built by build_scene and posed
    # by apply_met above; the still renders the one applied MET.)

    OUT.mkdir(parents=True, exist_ok=True)
    stills = {}
    add_strikes(camera, state)
    for cut in CUTS:
        clean = cut == "clean"
        # The clean cut carries no text at all, painted plates included.
        # The beam's contact-driven hiding from apply_met stands in the
        # instrument cut; the clean cut hides it outright.
        for name in ("ModeBeacon", "LoadIndicator", "LoadIndicatorTop",
                     "NamePlate", "NamePlateBack") + CAPTION_NAMES:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_render = clean
        for name in ("ContactBeam", "ContactBeamGlow"):
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_render = clean or not state["in_contact"]
        if FIXTURE:
            scene.render.filepath = str(
                OUT / ("fixture_%d_%s.png" % (MET, FIXTURE_LABELS[MET])))
        elif CHECK:
            scene.render.filepath = str(OUT / "check_instrument.png")
        else:
            scene.render.filepath = str(OUT / ("a5_met%d_%s.png" % (MET, cut)))
            stills[cut] = Path(scene.render.filepath).name
        bpy.ops.render.render(write_still=True)
        print("A5 STILL", cut, scene.render.filepath)
    if not CHECK and not FIXTURE:
        report = {"milestone": "A5 (one frame, both cuts)", "met_s": MET,
                  "engine": "CYCLES", "samples": SAMPLES,
                  "resolution": [WIDTH, HEIGHT],
                  "camera_distance_m": round(camera.location.length, 2),
                  "alt_km": row["alt_km"], "stills": stills,
                  "sun_latlon": [round(v, 3) for v in
                                 solar.sun_latlon_at(epoch, MET)],
                  "state": {k: state[k] for k in
                            ("sunlit", "mode", "payload_on", "load_i",
                             "load_limit", "in_contact", "sa1_i", "sa2_i")}}
        (OUT / "a5_still_report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("A5 STILL OK check=%s cuts=%s" % (CHECK, CUTS))


def gpu_requirement_error(device, require_gpu):
    """Error text when a GPU was required but none was found, else None.

    Pure logic (no bpy in the body) so the plain-Python tests can call
    it straight out of this file's source."""
    if require_gpu and device == "CPU":
        return ("--require-gpu: no GPU device found for Cycles; "
                "refusing to render on the CPU")
    return None


def enable_gpu(scene, require_gpu=False):
    """Use a Cycles GPU when this machine has one; else stay on CPU.

    With require_gpu (the A7 final), a CPU-only machine stops the
    render instead of silently falling back to the CPU. The default
    keeps the old behavior."""
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
            try:
                devices = prefs.get_devices_for_type(kind)
            except Exception:
                continue
            gpus = [d for d in devices if d.type == kind]
            if gpus:
                prefs.compute_device_type = kind
                for device in devices:
                    device.use = device.type == kind
                scene.cycles.device = "GPU"
                return "%s: %s" % (kind, gpus[0].name)
    except Exception as exc:
        print("GPU skipped:", exc)
    error = gpu_requirement_error("CPU", require_gpu)
    if error:
        raise SystemExit(error)
    return "CPU"


def run_animate():
    """--animate: keyframe the follow scene across one run's MET range
    and render the clip with its sync file (driven by render_clip.py)."""
    import build_a2 as A2
    inputs = None
    if arg("--inputs"):
        inputs = A2.apply_inputs(arg("--inputs"))
    timeline_path = arg("--timeline",
                         (inputs or S.INPUTS) / "timelines"
                         / "dev-ph2-p3-open-01.js")
    timeline = T.load_timeline(timeline_path)
    orbit_path = T.orbit_path_for(timeline["id"])
    if orbit_path is None:
        raise SystemExit("run %s has no orbit on record; no orbit animation"
                         % timeline["id"])
    epochs_path = (inputs / "epochs.json") if inputs else solar.EPOCHS_JSON
    S._EPOCH = solar.read_epoch(S.DEFAULT_RUN_ID, path=epochs_path)
    epoch = solar.read_epoch(timeline["id"], path=epochs_path)
    if epoch is None:
        raise SystemExit("run %s has no UTC epoch in epochs.json"
                         % timeline["id"])
    rows = S.read_orbit(orbit_path)
    feed_reports = T.load_feed(arg("--feed"))
    cut = arg("--cut", "instrument")
    clean = cut in ("clean", "pullback")
    step = Y.parse_met_step(arg("--step", "5"))
    fps = int(arg("--fps", "10"))
    first_sample, _last = T.telemetry_span(timeline)
    start_met = arg("--met-start")
    start_met = Y.to_fraction(start_met) if start_met is not None else (
        int(first_sample) if first_sample is not None else 800)
    end_met = arg("--met-end")
    end_met = Y.to_fraction(end_met) if end_met is not None else (
        int(rows[-1]["met_s"]))
    # A probe renders only a span's first frames; the pull-back's
    # progress is measured against the full pull-back span when one
    # is named, so those frames stay at the move's start (A9B).
    pullback_start = arg("--pullback-met-start")
    pullback_start = (Y.to_fraction(pullback_start)
                      if pullback_start is not None else start_met)
    pullback_end = arg("--pullback-met-end")
    pullback_end = (Y.to_fraction(pullback_end)
                    if pullback_end is not None else end_met)
    mets = Y.frame_mets(start_met, end_met, step)
    # The pull-back ends on the whole disc, where a coarser sphere's
    # silhouette would facet; the other cuts keep their tessellation.
    H = build_scene(epoch, rows, float(mets[0]), with_cues=True,
                    with_weather=bool(feed_reports),
                    earth_segments=256 if cut == "pullback" else 128)
    scene = H["scene"]
    if clean:
        for name in ("ModeBeacon", "LoadIndicator", "LoadIndicatorTop",
                     "NamePlate", "NamePlateBack") + CAPTION_NAMES:
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_render = True
    engine = arg("--engine", "CYCLES")
    set_render_common(scene, engine)
    device = enable_gpu(scene, require_gpu="--require-gpu" in ARGS) \
        if engine == "CYCLES" else engine
    print("A5 ANIM device:", device)
    scene.render.fps = fps
    scene.frame_start, scene.frame_end = 1, len(mets)
    cues = T.request_cues(timeline)
    active = A2.cue_frames(cues, start_met, len(mets), step)
    frames = []
    for index, met in enumerate(mets, start=1):
        kinds = active.get(index, set())
        for kind in kinds:
            if kind.startswith("baldur:"):
                color = (0.2, 0.9, 0.3) if kind.endswith("ALLOW") \
                    else (1.0, 0.2, 0.15)
                A2.set_emission(H["mats"]["cue_baldur"], color, 3.0, index)
        cue_on = set()
        if kinds & {"odin", "dispatch"}:
            cue_on.add("odin")
        if any(k.startswith("baldur") for k in kinds):
            cue_on.add("baldur")
        state = apply_met(H, timeline, epoch, rows, float(met),
                          feed_reports, frame=index, cue_kinds=cue_on,
                          clean=clean,
                          pullback=(Y.pullback_progress(
                                        met, pullback_start, pullback_end)
                                    if cut == "pullback" else None))
        row = S.orbit_row_at(rows, float(met))
        entry = {
            "frame": index, "met_s": Y.sync_number(met),
            "sunlit": state["sunlit"],
            "mode": state["mode"], "payload_on": state["payload_on"],
            "load_i": state["load_i"], "load_limit": state["load_limit"],
            "in_contact": state["in_contact"],
            "weather": None if state["weather"] is None
            else state["weather"].get("proton_flux_pfu"),
            "lat_deg": row["lat_deg"], "lon_deg": row["lon_deg"],
            "alt_km": row["alt_km"]}
        if cut == "pullback":
            entry["camera_distance_m"] = H["camera"].location.length
            entry["lens_mm"] = H["camera"].data.lens
        frames.append(entry)
    constant_state_curves()
    OUT.mkdir(parents=True, exist_ok=True)
    clip = arg("--clip") or ("%s_a5_%s.mp4" % (timeline["id"], cut))
    try:
        scene.render.image_settings.file_format = "FFMPEG"
    except TypeError:  # Blender 5 wants the media type switched first
        scene.render.image_settings.media_type = "VIDEO"
        scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    # A7 final only: H.264 at Blender's perceptually lossless setting,
    # since the edit encodes the clip again. Default (no switch) keeps
    # the preview commands' encoding exactly as it was.
    if "--perceptually-lossless" in ARGS:
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "PERC_LOSSLESS"
    scene.render.filepath = str(OUT / clip)
    bpy.ops.render.render(animation=True)
    sync_name = clip.replace(".mp4", ".sync.json")
    Y.write_sync(OUT / sync_name, Y.make_sync(
        timeline["id"], timeline_path, Y.sync_number(start_met),
        Y.sync_number(step), fps))
    report_name = clip.replace(".mp4", "_report.json")
    report = {"milestone": "A5 animate", "run_id": timeline["id"],
              "cut": cut, "resolution": [WIDTH, HEIGHT],
              "engine": engine, "samples": SAMPLES, "device": device,
              "encoding": "H264 PERC_LOSSLESS"
              if "--perceptually-lossless" in ARGS else "default",
              "fps": fps, "met_step_s": Y.sync_number(step),
              "met_range": [Y.sync_number(start_met),
                            Y.sync_number(end_met)],
              "frames": frames,
              "clip": clip, "sync": sync_name,
              "cues": {
                  "odin": [{"met_s": c["met_s"]} for c in cues
                           if c["kind"] in ("odin", "dispatch")],
                  "baldur": [{"met_s": c["met_s"],
                              "decision": c["decision"]}
                             for c in cues if c["kind"] == "baldur"]},
              "sun": "derived from inputs/epochs.json epoch + MET (solar.py)"}
    (OUT / report_name).write_text(json.dumps(report, indent=2) + "\n",
                                   encoding="utf-8")
    print("A5 ANIM OK", clip, len(frames), "frames")


if __name__ == "__main__":
    if ANIMATE:
        run_animate()
    else:
        main()
