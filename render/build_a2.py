# SPDX-License-Identifier: GPL-3.0-or-later
"""A2: the record drives the scene.

Reads one VERDA timeline (plus the run's orbit file for position) and
keyframes the A1 scene at a fixed MET step: position along the orbit,
sunlight/eclipse on the craft and its arrays, contact link, payload on/off,
mode beacon, load-current limit colors, per-string array brightness, brief
ODIN/BALDUR-0 cue flashes, and space weather only when a feed is handed in.

Run headless from this folder:
    blender -b --factory-startup --python-exit-code 1 -P build_a2.py
    blender -b --factory-startup --python-exit-code 1 -P build_a2.py -- --fixture

Default renders the dev-ph2-p3-open-01 low-resolution preview video plus
out/a2/a2_report.json. --fixture instead renders three check stills from
the made-up test fixture (eclipse, safe mode, deny, made-up feed), which no
real input run carries; the fixture is never drawn over a real run.
Options: --timeline PATH, --feed PATH.
"""

import json
import math
import random
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

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FIXTURE = "--fixture" in ARGS


def arg_value(flag, default=None):
    return ARGS[ARGS.index(flag) + 1] if flag in ARGS else default


MET_STEP_S = 5
FPS = 10
OUT = S.ROOT / "out" / "a2"
CELL_BASE = (0.02, 0.08, 0.35)
MODE_COLORS = {"NOMINAL": (0.2, 0.9, 0.3), "LOW_POWER": (1.0, 0.7, 0.15),
               "SAFE": (1.0, 0.2, 0.15)}
GREEN, AMBER, RED, GRAY = (0.2, 0.9, 0.3), (1.0, 0.32, 0.0), (1.0, 0.2, 0.15), (0.4, 0.4, 0.42)


def limit_color(limit):
    if limit and limit.startswith("YELLOW"):
        return AMBER
    if limit and limit.startswith("RED"):
        return RED
    if limit == "GREEN":
        return GREEN
    return GRAY


def bsdf(mat):
    return mat.node_tree.nodes["Principled BSDF"]


def set_emission(mat, color, strength, frame=None):
    node = bsdf(mat)
    node.inputs["Emission Color"].default_value = (*color, 1.0)
    node.inputs["Base Color"].default_value = (*color, 1.0)
    node.inputs["Emission Strength"].default_value = strength
    if frame is not None:
        for name in ("Emission Color", "Base Color", "Emission Strength"):
            node.inputs[name].keyframe_insert("default_value", frame=frame)


def pose(empty, position, sun_dir):
    """The same drawn pose as A1, recomputed as the craft and Sun move."""
    zenith = Vector(position).normalized()
    sun = Vector(sun_dir)
    axis_y = (sun - zenith * sun.dot(zenith)).normalized()
    axis_x = axis_y.cross(zenith).normalized()
    empty.location = position
    empty.rotation_euler = Matrix((axis_x, axis_y, zenith)).transposed().to_euler()


class Rig:
    """Scene handles the per-frame state application needs."""

    def __init__(self, mats, station, with_weather):
        self.mats = mats
        self.station_xyz = Vector(S.station_xyz(station))
        self.empty = bpy.data.objects["HUGINN"]
        self.camera = bpy.data.objects["CameraHero"]
        self.sun_craft = bpy.data.objects.get("SunCraftLight")
        self.sun_earth = bpy.data.objects.get("SunLight")
        self.fill = bpy.data.objects.get("EarthshineFill")
        self.rim = bpy.data.objects.get("EclipseRim")
        self.link = self.make_link()
        self.odin_cue = self.make_cue("OdinCue", mats["cue_odin"], -0.09)
        self.baldur_cue = self.make_cue("BaldurCue", mats["cue_baldur"], 0.09)
        self.weather = self.make_weather() if with_weather else None

    def make_link(self):
        A1.bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=1.0)
        link = A1.bpy.context.object
        link.name = "ContactLink"
        link.data.materials.append(self.mats["link"])
        A1.no_shadow(link)
        return link

    def make_cue(self, name, mat, x_m):
        collection = bpy.data.collections["Spacecraft"]
        cue = A1.sphere(name, A1.scaled(0.011),
                        (A1.scaled(x_m), 0.0, A1.scaled(0.366) / 2.0
                         + A1.scaled(0.012)),
                        mat=mat, parent=self.empty, collection=collection)
        cue.scale = (0.001, 0.001, 0.001)
        A1.no_shadow(cue)
        return cue

    def make_weather(self):
        """Radiation as it looks in spacecraft camera footage: brief white
        specks and short streaks across the frame itself (Director, A5).
        The streaks ride just in front of the camera; apply_state flashes
        them at fresh spots each frame, at a rate following the flux."""
        stream = bpy.data.objects.new("WeatherStream", None)
        collection = bpy.data.collections["Spacecraft"]
        collection.objects.link(stream)
        stream.parent = self.camera
        stream.location = (0.0, 0.0, 0.0)
        self.camera.data.clip_start = 0.01
        mats = [A1.material("WeatherParticles%d" % i, (1.0, 1.0, 1.0),
                            roughness=0.5, emission=(1.0, 1.0, 1.0),
                            emission_strength=s)
                for i, s in enumerate((1.0, 2.5, 5.0, 9.0))]
        import random as _rng
        pick = _rng.Random(3)
        self.weather_particles = []
        for i in range(24):
            speck = A1.box("WeatherP%02d" % i, (0.00025, 0.00006, 0.00006),
                           (0.0, 0.0, -0.07), mat=pick.choice(mats),
                           parent=stream, collection=collection)
            speck.hide_render = True
            self.weather_particles.append(speck)
        return stream


def split_sunlight(craft_collection):
    """One sun for Earth, one for the craft, so eclipse darkens the craft
    alone. Uses light linking when this Blender has it; the craft sun's
    energy is driven either way."""
    earth_coll = bpy.data.collections.new("EarthOnly")
    bpy.context.scene.collection.children.link(earth_coll)
    for name in ("Earth", "Atmosphere"):
        obj = bpy.data.objects[name]
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        earth_coll.objects.link(obj)
    sun = bpy.data.objects["SunLight"]
    craft_data = bpy.data.lights.new("SunCraftData", "SUN")
    craft_data.energy = sun.data.energy
    craft_data.angle = sun.data.angle
    craft = bpy.data.objects.new("SunCraftLight", craft_data)
    bpy.context.scene.collection.objects.link(craft)
    craft.location = sun.location
    craft.rotation_euler = sun.rotation_euler
    for light, coll in ((sun, earth_coll), (craft, craft_collection)):
        if hasattr(light, "light_linking"):
            light.light_linking.receiver_collection = coll
    return craft


def apply_state(rig, state, position, sun_dir, frame=None, cue_kinds=()):
    """Put one MET's record state into the scene (keyframed when frame)."""
    key = (lambda obj, prop: obj.keyframe_insert(prop, frame=frame)) \
        if frame is not None else (lambda obj, prop: None)
    pose(rig.empty, position, sun_dir)
    key(rig.empty, "location")
    key(rig.empty, "rotation_euler")
    # Follow camera: pulled back from A2's first cut, horizon kept level
    # by building its up from the craft's zenith (Director, A3).
    zenith, sunward, side = A1.spacecraft_axes(position, sun_dir)
    rig.camera.location = (Vector(position) + sunward * 3.4 + side * 4.2
                           + zenith * 2.2)
    forward = (Vector(position) - rig.camera.location).normalized()
    back = -forward
    up = (zenith - back * zenith.dot(back)).normalized()
    right = up.cross(back).normalized()
    rig.camera.rotation_euler = Matrix((right, up, back)).transposed().to_euler()
    key(rig.camera, "location")
    key(rig.camera, "rotation_euler")
    # Both suns track the derived direction.
    for light in (rig.sun_earth, rig.sun_craft):
        if light is not None:
            light.location = Vector(sun_dir) * 40.0
            A1.look_at(light, (0.0, 0.0, 0.0))
            key(light, "location")
            key(light, "rotation_euler")
    # Earthshine is a faint readability fill only; in eclipse the total
    # light on the craft must stay well under sunlight (Director, A4),
    # with a faint rim light in eclipse alone keeping the outline.
    if rig.fill is not None:
        rig.fill.data.energy = 25.0 if state["sunlit"] else 12.0
        if frame is not None:
            rig.fill.data.keyframe_insert("energy", frame=frame)
    if rig.rim is not None:
        rig.rim.data.energy = 0.0 if state["sunlit"] else 5.0
        if frame is not None:
            rig.rim.data.keyframe_insert("energy", frame=frame)
    # Sunlight on the craft only; Earth keeps its own sun.
    if rig.sun_craft is not None:
        energy = 4.5 if state["sunlit"] else 0.04
        if state["sunlit"] is None:
            energy = 4.5
        rig.sun_craft.data.energy = energy
        if frame is not None:
            rig.sun_craft.data.keyframe_insert("energy", frame=frame)
    # Each wing's cells brighten with its own string's current.
    for mat_name, key_name in (("cell_sa1", "sa1_i"), ("cell_sa2", "sa2_i")):
        amps = state[key_name]
        level = 1.0 if amps is None else max(0.0, min(1.0, amps / 1.7))
        color = tuple(c * (0.12 + 0.88 * level) for c in CELL_BASE)
        node = bsdf(rig.mats[mat_name])
        node.inputs["Base Color"].default_value = (*color, 1.0)
        if frame is not None:
            node.inputs["Base Color"].keyframe_insert("default_value",
                                                      frame=frame)
    set_emission(rig.mats["beacon"],
                 MODE_COLORS.get(state["mode"], GRAY), 2.0, frame)
    set_emission(rig.mats["load_bar"], limit_color(state["load_limit"]),
                 1.4, frame)
    lens = bsdf(rig.mats["lens"])
    lens.inputs["Emission Strength"].default_value = \
        1.3 if state["payload_on"] else 0.05
    if frame is not None:
        lens.inputs["Emission Strength"].keyframe_insert("default_value",
                                                         frame=frame)
    # Contact link between craft and station while the record says contact.
    start, end = Vector(position), rig.station_xyz
    direction = end - start
    rig.link.location = (start + end) / 2.0
    rig.link.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    rig.link.scale = (1.0, 1.0, direction.length)
    rig.link.hide_render = not state["in_contact"] or getattr(rig, "clean", False)
    for prop in ("location", "rotation_euler", "scale", "hide_render"):
        key(rig.link, prop)
    # Brief ODIN / BALDUR-0 flashes (VERDA carries the text).
    for cue, kind in ((rig.odin_cue, "odin"), (rig.baldur_cue, "baldur")):
        on = kind in cue_kinds and not getattr(rig, "clean", False)
        cue.scale = (1.0, 1.0, 1.0) if on else (0.001, 0.001, 0.001)
        key(cue, "scale")
    # Space weather: camera strikes, count following the feed's flux.
    if rig.weather is not None:
        flux = (state["weather"] or {}).get("proton_flux_pfu", 0.0)
        level = max(0.0, min(1.0, math.log10(flux + 1.0)))
        count = int(round(len(rig.weather_particles) * level))
        seed = (frame if frame is not None else int(state["met_s"])) * 131
        for i, speck in enumerate(rig.weather_particles):
            rng = random.Random(seed + i)
            speck.location = (rng.uniform(-0.03, 0.03),
                              rng.uniform(-0.017, 0.017), -0.07)
            speck.rotation_euler = (0.0, 0.0, rng.uniform(0.0, math.pi))
            speck.scale = (rng.uniform(0.4, 1.6), 1.0, 1.0)
            speck.hide_render = i >= count
            for prop in ("location", "rotation_euler", "scale",
                         "hide_render"):
                key(speck, prop)


def build_scene(rows, station, with_weather, settings=None):
    settings = settings or {}
    scene = A1.reset_scene()
    mats = A1.make_materials()
    first_pos = S.orbit_xyz(S.orbit_row_at(rows, 800.0))
    A1.build_earth()
    orbit_obj, _points = A1.build_orbit(rows)
    orbit_obj.hide_render = True  # follow camera: the tube crosses the craft
    A1.build_station(station, mats)
    A1.build_sun(mats)
    empty, _bus, craft_coll = A1.build_spacecraft(first_pos, mats)
    for obj in craft_coll.objects:
        A1.no_shadow(obj)
    split_sunlight(craft_coll)
    # Wide-shot annotations stay out of the follow view. The Sun disk is
    # left out of the preview entirely (Director, A3): Earth hides it or
    # it is not there, never drawn in front of the planet.
    for name in ("Atmosphere", "GroundStationLabel", "GroundStationLeader",
                 "GroundStationRing", "SpacecraftMarker", "SpacecraftLabel",
                 "Sun"):
        obj = bpy.data.objects.get(name)
        if obj is None and name in ("SpacecraftMarker", "SpacecraftLabel"):
            continue
        obj.hide_render = True
    bpy.data.objects["GroundStation"].scale = (0.55, 0.55, 0.55)
    fill_data = bpy.data.lights.new("EarthshineData", "AREA")
    fill_data.energy = 40.0
    fill_data.shape = "DISK"
    fill_data.size = 3.0
    fill_data.color = (0.45, 0.62, 1.0)
    fill = bpy.data.objects.new("EarthshineFill", fill_data)
    bpy.context.scene.collection.objects.link(fill)
    fill.parent = empty
    fill.location = (0.0, 0.0, -0.45)
    # An area light emits along its local -Z; flip it to shine up at the
    # craft from below (A2's first cut had it shining away into Earth).
    fill.rotation_euler = (math.pi, 0.0, 0.0)
    # Faint rim light, eclipse only, sunward and above the craft.
    rim_data = bpy.data.lights.new("EclipseRimData", "POINT")
    rim_data.energy = 0.0
    rim_data.color = (0.65, 0.8, 1.0)
    rim_data.use_shadow = False
    rim = bpy.data.objects.new("EclipseRim", rim_data)
    bpy.context.scene.collection.objects.link(rim)
    rim.parent = empty
    rim.location = (0.0, 0.9, 0.5)
    cameras = A1.build_cameras(first_pos, station)
    A1.set_render(scene)
    scene.render.resolution_x = settings.get("width", 640)
    scene.render.resolution_y = settings.get("height", 360)
    scene.render.resolution_percentage = 100
    scene.render.fps = settings.get("fps", FPS)
    engine = settings.get("engine", "BLENDER_EEVEE")
    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = settings.get("samples", 32)
        scene.cycles.use_denoising = True
    else:
        scene.eevee.taa_render_samples = settings.get("samples", 32)
    scene.camera = cameras["CameraHero"]
    return scene, Rig(mats, station, with_weather)


def cue_frames(cues, start_met, frame_count, step=MET_STEP_S):
    """Map frame number -> cue kinds flashing there (two frames each)."""
    active = {}
    for cue in cues:
        frame = int(round((cue["met_s"] - start_met) / step)) + 1
        for f in (frame, frame + 1):
            if 1 <= f <= frame_count:
                active.setdefault(f, set()).add(cue["kind"])
                if cue["kind"] == "baldur":
                    active[f].add("baldur:" + str(cue.get("decision")))
    return active


def run_preview(timeline, timeline_path, rows, station, feed_reports,
                settings=None):
    settings = settings or {}
    # Resolve: Blender treats a relative render path against the blend
    # file's folder, not the caller's, and a headless run has none.
    out_dir = Path(settings.get("output_dir", OUT)).resolve()
    step = settings.get("step", MET_STEP_S)
    fps = settings.get("fps", FPS)
    epochs_path = settings.get("epochs_path", solar.EPOCHS_JSON)
    epoch = solar.read_epoch(timeline["id"], path=epochs_path)
    if epoch is None:
        raise SystemExit("run %s has no UTC epoch in inputs/epochs.json"
                         % timeline["id"])
    scene, rig = build_scene(rows, station, bool(feed_reports), settings)
    if settings.get("cut", "instrument") == "clean":
        # The clean cut is what a camera would see: no data cues at all.
        rig.clean = True
        for name in ("ModeBeacon", "LoadIndicator", "NamePlate",
                     "SA1_Label", "SA2_Label"):
            obj = bpy.data.objects.get(name)
            if obj is not None:
                obj.hide_render = True
    first_sample, _last = T.telemetry_span(timeline)
    start_met = settings.get("met_start")
    if start_met is None:
        start_met = int(first_sample) if first_sample is not None else 800
    end_met = settings.get("met_end")
    if end_met is None:
        end_met = int(rows[-1]["met_s"])
    mets = list(range(start_met, end_met + 1, step))
    scene.frame_start, scene.frame_end = 1, len(mets)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    cues = T.request_cues(timeline)
    active = cue_frames(cues, start_met, len(mets), step)
    frames = []
    for index, met in enumerate(mets, start=1):
        state = T.state_at(timeline, met, feed_reports)
        position = S.orbit_xyz(S.orbit_row_at(rows, float(met)))
        sun_dir = S.latlon_to_xyz(*solar.sun_latlon_at(epoch, met), 1.0)
        kinds = active.get(index, set())
        for kind in kinds:
            if kind.startswith("baldur:"):
                color = GREEN if kind.endswith("ALLOW") else RED
                set_emission(rig.mats["cue_baldur"], color, 3.0, index)
        cue_on = set()
        if kinds & {"odin", "dispatch"}:
            cue_on.add("odin")
        if any(k.startswith("baldur") for k in kinds):
            cue_on.add("baldur")
        apply_state(rig, state, position, sun_dir, frame=index,
                    cue_kinds=cue_on)
        frames.append({
            "frame": index, "met_s": met, "sunlit": state["sunlit"],
            "mode": state["mode"], "payload_on": state["payload_on"],
            "load_i": state["load_i"], "load_limit": state["load_limit"],
            "in_contact": state["in_contact"],
            "weather": None if state["weather"] is None
            else state["weather"].get("proton_flux_pfu"),
            "xyz": [round(v, 5) for v in position]})
    out_dir.mkdir(parents=True, exist_ok=True)
    preview = settings.get("clip") or (timeline["id"] + "_preview.mp4")
    try:
        scene.render.image_settings.file_format = "FFMPEG"
    except TypeError:  # Blender 5 wants the media type switched first
        scene.render.image_settings.media_type = "VIDEO"
        scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.filepath = str(out_dir / preview)
    bpy.ops.render.render(animation=True)
    # A3: the sync file beside the clip, for VERDA's pane.
    sync_name = preview.replace(".mp4", ".sync.json")
    Y.write_sync(out_dir / sync_name,
                 Y.make_sync(timeline["id"], timeline_path,
                             start_met, step, fps))
    report = {
        "milestone": "A2", "run_id": timeline["id"],
        "met_step_s": step, "fps": fps,
        "met_range": [start_met, end_met], "frames": frames,
        "cues": {
            "odin": [{"met_s": c["met_s"]} for c in cues if c["kind"] == "odin"],
            "baldur": [{"met_s": c["met_s"], "decision": c["decision"]}
                       for c in cues if c["kind"] == "baldur"]},
        "preview": preview, "sync": sync_name,
        "resolution": [settings.get("width", 640),
                       settings.get("height", 360)],
        "engine": settings.get("engine", "BLENDER_EEVEE"),
        "samples": settings.get("samples", 32),
        "cut": settings.get("cut", "instrument"),
        "sun": "derived from inputs/epochs.json epoch + MET (solar.py)",
        "note": "Telemetry starts at contact (MET 800); before that the "
                "record holds no spacecraft state, so the preview starts "
                "there. Spacecraft state reads the truth source."}
    (out_dir / "a2_report.json").write_text(json.dumps(report, indent=2) + "\n",
                                            encoding="utf-8")
    print("A2 PREVIEW OK", preview, len(frames), "frames")


def run_fixture(station):
    """Made-up fixture stills: eclipse, red limit, safe mode + deny, feed."""
    timeline = T.load_timeline(S.ROOT / "tests" / "fixtures"
                               / "made_up_timeline.json")
    feed = T.load_feed(S.ROOT / "inputs" / "feeds"
                       / "made-up-feed-timeline.json")
    rows = S.read_orbit()  # P3 rows supply placement for the check only
    epoch = solar.read_epoch("dev-ph2-p3-open-01")
    scene, rig = build_scene(rows, station, True)
    scene.render.image_settings.file_format = "PNG"
    for met, label in ((890, "sunlit"), (920, "eclipse_red"),
                       (945, "safe_deny")):
        state = T.state_at(timeline, met, feed)
        position = S.orbit_xyz(S.orbit_row_at(rows, float(met)))
        sun_dir = S.latlon_to_xyz(*solar.sun_latlon_at(epoch, met), 1.0)
        kinds = {"odin", "baldur"} if met == 945 else set()
        if kinds:
            set_emission(rig.mats["cue_baldur"], RED, 3.0)
        apply_state(rig, state, position, sun_dir, cue_kinds=kinds)
        scene.render.filepath = str(OUT / ("fixture_%d_%s.png" % (met, label)))
        bpy.ops.render.render(write_still=True)
        print("FIXTURE", met, state)
    print("A2 FIXTURE OK (made up; never drawn over a real run)")


def int_arg(flag):
    value = arg_value(flag)
    return int(value) if value is not None else None


def apply_inputs(inputs_dir):
    """Point every input path at an inputs folder given on the command line
    (A4: on a cloud run the folder need not sit beside the scripts)."""
    inputs = Path(inputs_dir)
    S.INPUTS = inputs
    S.ORBIT_CSV = inputs / "orbit" / "P3-orbit.csv"
    S.STATION_JSON = inputs / "orbit" / "station.json"
    S.EARTH_TEXTURE = inputs / "imagery" / S.EARTH_TEXTURE_NAME
    T.P3_ORBIT_CSV = S.ORBIT_CSV
    return inputs


def main():
    inputs = None
    if arg_value("--inputs"):
        inputs = apply_inputs(arg_value("--inputs"))
    station = S.read_station(S.STATION_JSON)
    if FIXTURE:
        run_fixture(station)
        return
    default_timeline = (inputs or S.INPUTS) / "timelines" / "dev-ph2-p3-open-01.js"
    timeline_path = arg_value("--timeline", default_timeline)
    timeline = T.load_timeline(timeline_path)
    orbit_path = T.orbit_path_for(timeline["id"])
    if orbit_path is None:
        raise SystemExit("run %s has no orbit on record; no orbit animation"
                         % timeline["id"])
    epochs_path = (inputs / "epochs.json") if inputs else solar.EPOCHS_JSON
    # Seed scene_spec's cached epoch so its Sun uses this inputs folder.
    S._EPOCH = solar.read_epoch(S.DEFAULT_RUN_ID, path=epochs_path)
    settings = {
        "output_dir": arg_value("--output-dir", OUT),
        "width": int_arg("--width") or 640,
        "height": int_arg("--height") or 360,
        "step": int_arg("--step") or MET_STEP_S,
        "fps": int_arg("--fps") or FPS,
        "met_start": int_arg("--met-start"),
        "met_end": int_arg("--met-end"),
        "engine": arg_value("--engine", "BLENDER_EEVEE"),
        "samples": int_arg("--samples") or 32,
        "cut": arg_value("--cut", "instrument"),
        "clip": arg_value("--clip"),
        "epochs_path": epochs_path,
    }
    feed_reports = T.load_feed(arg_value("--feed"))
    run_preview(timeline, timeline_path, S.read_orbit(orbit_path), station,
                feed_reports, settings)


if __name__ == "__main__":
    main()
