r"""Blender side of the scene toolkit: build a compiled plan and capture it. Runs only inside Blender.

  blender.exe -b --factory-startup --python-exit-code 1 -P blender_run.py -- OUT\job.json

The executor is deliberately dumb: one function per op kind, no decisions, no randomness (the plan holds every
resolved value). After each frame it saves the shaded PNG and a multi-layer EXR, and hands the EXR to
atomic_flix.scenes.layers (pure numpy) to write the layer files. Seconds per frame go to OUT/capture.json.
"""

import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import bmesh
import bpy

ENGINES = {"raster": "BLENDER_EEVEE", "pathtrace": "CYCLES"}
split_frame = None  # atomic_flix.scenes.layers.split_frame, imported in main() from the job's source folder


class Executor:
    def __init__(self, job):
        self.job = job
        self.out = job["out"]
        self.scene = None
        self.meshes = {}
        self.surfaces = {}
        self.collections = {}
        self.camera_rot = {}
        self.pass_meta = None
        self.renderer = "raster"

    # ------------------------------------------------------------ helpers

    def image_path(self, ref):
        if ref.startswith("gen:"):
            return os.path.join(self.job["tex_dir"], ref[4:] + ".png")
        return ref if os.path.isabs(ref) else os.path.join(self.job["scene_dir"], ref)

    def load_image(self, ref):
        return bpy.data.images.load(self.image_path(ref), check_existing=True)

    def mesh(self, shape, sides, rings):
        key = (shape, sides, rings)
        if key in self.meshes:
            return self.meshes[key]
        me = bpy.data.meshes.new(f"{shape}-{sides}-{rings}")
        bm = bmesh.new()
        if shape == "box":
            bmesh.ops.create_cube(bm, size=1.0)
        elif shape == "tube":
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=sides, radius1=0.5, radius2=0.5,
                                  depth=1.0)
            for face in bm.faces:
                face.smooth = abs(face.normal.z) < 0.5
        else:
            bmesh.ops.create_uvsphere(bm, u_segments=sides, v_segments=rings, radius=0.5)
            for face in bm.faces:
                face.smooth = True
        bm.to_mesh(me)
        bm.free()
        me.materials.append(None)
        self.meshes[key] = me
        return me

    def collection(self, kind):
        if kind not in self.collections:
            col = bpy.data.collections.new(kind)
            self.scene.collection.children.link(col)
            self.collections[kind] = col
        return self.collections[kind]

    # ------------------------------------------------------------ ops

    def op_reset(self, op):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene

    def op_settings(self, op):
        sc = self.scene
        sc.render.resolution_x, sc.render.resolution_y = op["w"], op["h"]
        sc.render.resolution_percentage = 100
        fps = op["fps"]
        sc.render.fps = int(round(fps))
        sc.render.fps_base = sc.render.fps / fps
        sc.frame_start, sc.frame_end = op["frame_start"], op["frame_end"]
        sc.view_settings.view_transform = op["view"]
        sc.view_settings.look = "None"
        sc.render.film_transparent = False

    def op_world(self, op):
        w = bpy.data.worlds.new("sky")
        self.scene.world = w
        nt = w.node_tree
        bg = nt.nodes["Background"]
        sky = op["sky"]
        if "image" in sky:
            env = nt.nodes.new("ShaderNodeTexEnvironment")
            env.image = self.load_image(sky["image"])
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(sky["spin"]))
            tc = nt.nodes.new("ShaderNodeTexCoord")
            nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
            nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        else:
            bg.inputs["Color"].default_value = (*sky["color"], 1.0)
        bg.inputs["Strength"].default_value = sky["brightness"]
        w.mist_settings.start = op["mist"]["start"]
        w.mist_settings.depth = op["mist"]["depth"]

    def op_surface(self, op):
        m = bpy.data.materials.new(op["name"])
        nt = m.node_tree
        b = nt.nodes.get("Principled BSDF")
        if b is None:
            b = nt.nodes.new("ShaderNodeBsdfPrincipled")
            out = nt.nodes.get("Material Output") or nt.nodes.new("ShaderNodeOutputMaterial")
            nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
        if op["kind"] == "flat":
            if "color" in op:
                rgb = op["color"]
            else:
                rgb = [c ** 2.2 for c in op["srgb"]]
            rgb = [c * op.get("gain", 1.0) for c in rgb]
            b.inputs["Base Color"].default_value = (*rgb, 1.0)
            if op.get("emit"):
                b.inputs["Emission Color"].default_value = (*rgb, 1.0)
                b.inputs["Emission Strength"].default_value = op["emit"]
        else:
            geo = nt.nodes.new("ShaderNodeNewGeometry")
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = tuple(op["scale"])
            nt.links.new(geo.outputs["Position"], mp.inputs["Vector"])
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = self.load_image(op["image"])
            tex.projection = "BOX"
            tex.projection_blend = op.get("blend", 0.0)
            tex.extension = "REPEAT"
            nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
            nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
            if op.get("emit"):
                nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
                b.inputs["Emission Strength"].default_value = op["emit"]
        b.inputs["Roughness"].default_value = op.get("rough", 0.5)
        b.inputs["Metallic"].default_value = op.get("metal", 0.0)
        b.inputs["Specular IOR Level"].default_value = op.get("specular", 0.5)
        self.surfaces[op["name"]] = m

    def op_prim(self, op):
        me = self.mesh(op["shape"], op.get("sides", 0), op.get("rings", 0))
        ob = bpy.data.objects.new(f"{op['block']}/{op['name']}", me)
        self.collection(op["kind"]).objects.link(ob)
        ob.location = op["pos"]
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = op["quat"]
        ob.scale = op["scale"]
        ob.pass_index = op["mask"]
        slot = ob.material_slots[0]
        slot.link = "OBJECT"
        slot.material = self.surfaces[op["surface"]]
        for f, (pos, quat) in enumerate(op.get("keys", []), start=1):
            ob.location = pos
            ob.rotation_quaternion = quat
            ob.keyframe_insert("location", frame=f)
            ob.keyframe_insert("rotation_quaternion", frame=f)

    def op_rig(self, op):
        pass  # body points are for pose guides, read from plan.json outside Blender

    def op_light(self, op):
        kind = op["kind"].upper()
        data = bpy.data.lights.new(op["name"], kind)
        data.energy = op["power"]
        data.color = op["color"]
        if kind == "SUN":
            data.angle = math.radians(op.get("soft", 3.0))
        else:
            data.shadow_soft_size = op.get("radius", 0.1)
        if kind == "AREA":
            data.size = op.get("size", 1.0)
        ob = bpy.data.objects.new(op["name"], data)
        self.scene.collection.objects.link(ob)
        if "pos" in op:
            ob.location = op["pos"]
        if kind in ("SUN", "AREA"):
            # pitch and yaw as street.py maps the Unreal light rotation
            ob.rotation_euler = (math.radians(90 + op["pitch"]), 0.0, math.radians(op["yaw"] + 90))

    def op_viewpoint(self, op):
        cam = bpy.data.cameras.new("viewpoint")
        cam.lens = op["lens"]
        cam.sensor_width = op["film_mm"]
        cam.sensor_fit = "HORIZONTAL"
        cam.clip_start, cam.clip_end = op["near"], op["far"]
        ob = bpy.data.objects.new("viewpoint", cam)
        self.scene.collection.objects.link(ob)
        self.scene.camera = ob
        ob.rotation_mode = "QUATERNION"
        lenses = {k["lens"] for k in op["keys"]}
        for k in op["keys"]:
            ob.location = k["pos"]
            ob.rotation_quaternion = k["quat"]
            ob.keyframe_insert("location", frame=k["f"])
            ob.keyframe_insert("rotation_quaternion", frame=k["f"])
            if len(lenses) > 1:
                cam.lens = k["lens"]
                cam.keyframe_insert("lens", frame=k["f"])
            self.camera_rot[k["f"]] = k["rot"]

    def op_layers(self, op):
        vl = self.scene.view_layers[0]
        wanted = set(op["list"])
        vl.use_pass_z = "depth" in wanted
        vl.use_pass_normal = "facing" in wanted
        vl.use_pass_mist = "mist" in wanted
        masks = op["masks"] if "mask" in wanted else []
        for m in masks:
            aov = vl.aovs.add()
            aov.name = m["aov"]
            aov.type = "VALUE"
        for mat in bpy.data.materials:
            nt = mat.node_tree
            if nt is None or not masks:
                continue
            info = nt.nodes.new("ShaderNodeObjectInfo")
            for m in masks:
                cmp = nt.nodes.new("ShaderNodeMath")
                cmp.operation = "COMPARE"
                cmp.inputs[1].default_value = m["index"]
                cmp.inputs[2].default_value = 0.1
                nt.links.new(info.outputs["Object Index"], cmp.inputs[0])
                out = nt.nodes.new("ShaderNodeOutputAOV")
                out.aov_name = m["aov"]
                nt.links.new(cmp.outputs[0], out.inputs["Value"])
        self.pass_meta = {"layers": op["list"], "masks": masks, "far": op["far"],
                          "depth_range": op["depth_range"]}

    def op_renderer(self, op):
        sc = self.scene
        self.renderer = op["renderer"]
        sc.render.engine = ENGINES[op["renderer"]]
        if op["renderer"] == "raster":
            sc.eevee.taa_render_samples = op["spp"]
            return
        sc.cycles.samples = op["spp"]
        sc.cycles.use_denoising = True
        sc.cycles.device = "CPU"
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
        if op["device"] == "gpu":
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for backend in ("OPTIX", "CUDA"):
                try:
                    prefs.compute_device_type = backend
                    prefs.get_devices()
                except TypeError:
                    continue
                devices = [d for d in prefs.devices if d.type == backend]
                if devices:
                    for d in prefs.devices:
                        d.use = d.type == backend
                    sc.cycles.device = "GPU"
                    if backend == "OPTIX":
                        sc.cycles.denoiser = "OPTIX"
                    break

    def op_capture(self, op):
        if self.job.get("blend"):
            bpy.ops.wm.save_as_mainfile(filepath=self.job["blend"])
            print("FLIX saved", self.job["blend"], flush=True)
            return
        sc = self.scene
        exr_dir = os.path.join(self.out, "_exr")
        os.makedirs(os.path.join(self.out, "shaded"), exist_ok=True)
        os.makedirs(exr_dir, exist_ok=True)
        records = []
        start = time.perf_counter()
        # the passes of frame n are split on a worker thread while Blender renders frame n + 1
        with ThreadPoolExecutor(max_workers=1) as pool:
            in_flight = None
            for f in op["frames"]:
                sc.frame_set(f)
                t0 = time.perf_counter()
                bpy.ops.render.render(write_still=False)
                t1 = time.perf_counter()
                exr = self.save_frame(f, exr_dir)
                rec = {"f": f, "render_s": round(t1 - t0, 4), "save_s": round(time.perf_counter() - t1, 4)}
                records.append(rec)
                if in_flight is not None:
                    self.finish(in_flight)
                in_flight = (rec, pool.submit(self.split, exr, f))
            if in_flight is not None:
                self.finish(in_flight)
        if not self.job.get("keep_exr"):
            try:
                os.rmdir(exr_dir)
            except OSError:
                pass
        info = {"format": "atomic-flix/capture@1", "renderer": self.renderer, "app_version": bpy.app.version_string, "w": sc.render.resolution_x,
                "h": sc.render.resolution_y, "wall_s": round(time.perf_counter() - start, 3), "frames": records}
        with open(os.path.join(self.out, "capture.json"), "w", encoding="utf-8") as fh:
            json.dump(info, fh, indent=1)

    def save_frame(self, f, exr_dir):
        """Beauty PNG through the view transform, then every pass into one multi-layer EXR."""
        sc = self.scene
        ims = sc.render.image_settings
        result = bpy.data.images["Render Result"]
        ims.media_type = "IMAGE"
        ims.file_format = "PNG"
        ims.color_mode = "RGB"
        ims.color_depth = "8"
        result.save_render(os.path.join(self.out, "shaded", f"{f:04d}.png"), scene=sc)
        ims.media_type = "MULTI_LAYER_IMAGE"
        ims.file_format = "OPEN_EXR_MULTILAYER"
        ims.color_depth = "32"
        ims.exr_codec = self.job.get("exr_codec", "ZIP")
        exr = os.path.join(exr_dir, f"{f:04d}.exr")
        result.save_render(exr, scene=sc)
        return exr

    def split(self, exr, f):
        t = time.perf_counter()
        split_frame(exr, self.out, f, {**self.pass_meta, "cam_rot": self.camera_rot[f]})
        if not self.job.get("keep_exr"):
            os.remove(exr)
        return time.perf_counter() - t

    @staticmethod
    def finish(in_flight):
        rec, future = in_flight
        rec["split_s"] = round(future.result(), 4)
        rec["post_s"] = round(rec["save_s"] + rec["split_s"], 4)
        print("FLIX frame", json.dumps(rec), flush=True)

    def run(self, plan):
        for op in plan["ops"]:
            getattr(self, "op_" + op["op"])(op)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) != 1:
        raise SystemExit("usage: blender -b -P blender_run.py -- JOB.json")
    with open(argv[0], encoding="utf-8") as fh:
        job = json.load(fh)
    with open(job["plan"], encoding="utf-8") as fh:
        plan = json.load(fh)
    global split_frame
    sys.path.insert(0, job["src"])
    from atomic_flix.scenes.layers import split_frame
    t = time.perf_counter()
    executor = Executor(job)
    ops = plan["ops"]
    capture_op = ops[-1]
    executor.run({"ops": ops[:-1]})
    print(f"FLIX built {len(ops) - 1} ops in {time.perf_counter() - t:.2f} s", flush=True)
    executor.op_capture(capture_op)
    print("FLIX done", flush=True)


if __name__ == "__main__":
    main()
