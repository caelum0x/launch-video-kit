# blender -b --factory-startup -noaudio --python-exit-code 1 -P skills/launch-world/scripts/blender_glass_object.py -- \
#     <out_dir> <frames> [samples] [core_hex] [ring_hex]
# Glass hero object (a bevelled cube with an emissive core and a ring), rendered as RGBA PNGs on a
# transparent film so it composites over any plate. Pass your brand's accent as core_hex and your
# ground or surface as ring_hex (brand/brand.json colors). Emissions run at strength 1.0 under the
# Standard view so they land on their exact hex. The GPU backend is Metal on Apple Silicon; set
# BLENDER_GPU=CUDA or OPTIX elsewhere, or NONE for CPU.
import bpy, math, os, sys
argv = sys.argv[sys.argv.index("--") + 1:]
out, frames = argv[0], int(argv[1])
samples = int(argv[2]) if len(argv) > 2 else 64
CORE = argv[3] if len(argv) > 3 else "#3B5BFD"
RING = argv[4] if len(argv) > 4 else "#FBFAF7"

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
GPU = os.environ.get("BLENDER_GPU", "METAL")
if GPU != "NONE":
    prefs.compute_device_type = GPU
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    sc.cycles.device = "GPU"
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 16
sc.cycles.transmission_bounces = 16
sc.render.film_transparent = True
sc.cycles.film_transparent_glass = True
sc.render.resolution_x = sc.render.resolution_y = 720
sc.render.image_settings.media_type = "IMAGE"  # 5.x: set before file_format
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
# Standard, no look: brand colours land on their exact hex. AgX greys light brand colours
# (a near-white renders about 18 % darker) and crushes dark ones.
sc.view_settings.view_transform = "Standard"
sc.view_settings.look = "None"
sc.frame_start, sc.frame_end = 0, frames - 1
sc.render.fps = 30

world = bpy.data.worlds.new("w")
sc.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.02, 0.02, 0.025, 1)
bg.inputs[1].default_value = 1.0

def mat_glass():
    m = bpy.data.materials.new("glass")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*[0.8 + 0.2 * v for v in lin(CORE)], 1)  # clear glass, a hint of the core
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.04
    b.inputs["IOR"].default_value = 1.47
    b.inputs["Coat Weight"].default_value = 0.4
    return m

def lin(hex_):
    """sRGB hex to linear RGB, so an emission of strength 1.0 renders the exact hex under Standard."""
    c = [int(hex_.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)

def mat_emit(col, strength):
    m = bpy.data.materials.new("emit")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*col, 1)
    e.inputs[1].default_value = strength
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    return m

# Pivot empty carries the rotation for everything.
pivot = bpy.data.objects.new("pivot", None)
sc.collection.objects.link(pivot)

bpy.ops.mesh.primitive_cube_add(size=2.0)
cube = bpy.context.object
bev = cube.modifiers.new("bevel", "BEVEL")
bev.width, bev.segments = 0.2, 8
cube.data.materials.append(mat_glass())
bpy.ops.object.shade_smooth()
cube.parent = pivot

bpy.ops.mesh.primitive_ico_sphere_add(radius=0.42, subdivisions=4)
core = bpy.context.object
core.data.materials.append(mat_emit(lin(CORE), 1.0))  # the brand accent, the 1 colour
bpy.ops.object.shade_smooth()
core.parent = pivot

bpy.ops.mesh.primitive_torus_add(major_radius=0.72, minor_radius=0.035)
ring = bpy.context.object
ring.data.materials.append(mat_emit(lin(RING), 1.0))  # the brand ground or surface
ring.parent = pivot

# Lights: soft white key, a rim tinted by the core colour (it sells the glass edge), cool fill.
def area(name, loc, energy, col, size):
    l = bpy.data.lights.new(name, "AREA")
    l.energy, l.color, l.size = energy, col, size
    o = bpy.data.objects.new(name, l)
    o.location = loc
    sc.collection.objects.link(o)
    c = o.constraints.new("TRACK_TO")
    c.target = pivot
    return o
area("key", (4, -4, 5), 900, (1, 1, 1), 4)
area("rim", (-5, 3, 2), 1400, tuple(0.5 + 0.5 * v for v in lin(CORE)), 3)
area("fill", (0, -6, -2), 250, (0.8, 0.9, 1.0), 6)

cam_d = bpy.data.cameras.new("cam")
cam_d.lens = 70
cam = bpy.data.objects.new("cam", cam_d)
cam.location = (0, -8.2, 3.4)
sc.collection.objects.link(cam)
cam.constraints.new("TRACK_TO").target = pivot
sc.camera = cam

# 3.2 deg per frame on the spin axis, a slow wobble on the tilt; the ring counter-spins.
for f in range(frames):
    pivot.rotation_euler = (math.radians(8 * math.sin(f / 18)), math.radians(-10), math.radians(30 + 3.2 * f))
    pivot.keyframe_insert("rotation_euler", frame=f)
    ring.rotation_euler = (math.radians(70 + f * 4), math.radians(f * 2.5), 0)
    ring.keyframe_insert("rotation_euler", frame=f)
# Blender 5.x removed Action.fcurves; F-curves live in the action slot's channelbag.
from bpy_extras import anim_utils
for ob in (pivot, ring):
    ad = ob.animation_data
    for fc in anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"

sc.render.filepath = f"{out}/hero_"
bpy.ops.render.render(animation=True)
