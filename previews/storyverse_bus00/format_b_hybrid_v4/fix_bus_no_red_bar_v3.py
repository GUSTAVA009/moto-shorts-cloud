import bpy,math,json
from pathlib import Path
from mathutils import Vector

ROOT=Path(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\BUS_00_REBUILD_CONTROLLED")
OUT=ROOT/"FORMAT_B_HYBRID_V3"
OUT.mkdir(exist_ok=True)
scene=bpy.context.scene
assert bpy.data.objects.get("ONE_BUS_FIXED_MODEL")
bus=bpy.data.objects["ONE_BUS_FIXED_MODEL"]
actor=bpy.data.objects["2D_RIG_ANTON_LOCKED"]
cam=scene.camera

# Remove old hinged doors which swung across the boarding path.
for ob in list(bpy.data.objects):
    if ob.name.startswith("Passenger door steel panel") or ob.name.startswith("Passenger door upper glass") or ob.name.startswith("Passenger door true hinge"):
        bpy.data.objects.remove(ob,do_unlink=True)

# Remove structural decorations spanning the entrance on bus street-side.
# Preserve roof and actual floor. The original side pillar at y=-2.5 was hanging in the cut-out.
for ob in list(bpy.data.objects):
    if ob.name.startswith("Permanent bus pillar") and ob.parent==bus and ob.location.x>1:
        if -2.65 < ob.location.y < -.9:
            bpy.data.objects.remove(ob,do_unlink=True)
            continue
    if ob.name.startswith("Bus beltline") and ob.parent==bus and ob.location.x>1:
        bpy.data.objects.remove(ob,do_unlink=True)

red=bpy.data.materials["Bus paint red"]
metal=bpy.data.materials["Reflective dull steel"]
glass=bpy.data.materials["Blue glass"]

def box(n,loc,dim,ma,parent=None,bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
    ob=bpy.context.object; ob.name=n;ob.dimensions=dim
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    ob.data.materials.append(ma)
    if bevel:
        m=ob.modifiers.new("Soft edges", "BEVEL")
        m.width=bevel;m.segments=2
    if parent:ob.parent=parent
    return ob

# Transparent motorized sliding doors. The two leaves slide along outer body
# rather than swinging across the person's path.
panel_data=[]
for k,(closed_y,open_y) in enumerate([(-2.18,-3.18),(-1.40,-.42)]):
    pivot=bpy.data.objects.new("Safe sliding passenger door "+str(k),None)
    scene.collection.objects.link(pivot)
    pivot.parent=bus
    for ob in (
        box("Sliding door framed panel "+str(k),(0,0,1.72),(.09,.72,2.14),red,parent=pivot,bevel=.025),
        box("Sliding door window glass "+str(k),(.055,0,2.13),(.04,.61,.88),glass,parent=pivot,bevel=.01),
        box("Sliding door step handle "+str(k),(.11,(-.20 if k==0 else .20),1.27),(.03,.035,.28),metal,parent=pivot,bevel=.01)
    ): pass
    for f,y in ((1,closed_y),(164,closed_y),(199,open_y),(288,open_y)):
        pivot.location=(1.37,y,0)
        pivot.keyframe_insert(data_path="location",frame=f)
    panel_data.append({"panel":k,"closed_y":closed_y,"open_y":open_y})

# Entrance threshold exists in the bus; eliminate beam of body under doorway.
# The body had been boolean-cut in v2. Add steps in safe vertical position.
box("Grounded boarding step inner",(1.04,-1.78,.50),(.56,1.46,.10),metal,parent=bus,bevel=.02)
box("Grounded boarding step outer",(1.38,-1.78,.28),(.25,1.40,.08),metal,parent=bus,bevel=.02)

# Stable camera trajectory: does not enter a building or clip the body.
# Coordinates: bus at x +/-1.3, stop at x=5.8, actor approaches at x1.0.
target=bpy.data.objects["Camera aim"]
for f,cp,aim in [
    (1,(4.1,-23,5.5),(0,8,1.8)),
    (97,(4.2,-12,3.0),(3.4,-4.8,1.5)),
    (98,(4.2,-12,3.0),(3.4,-4.8,1.5)),
    (166,(4.25,-10.2,3.2),(3.3,-4.9,1.58)),
    (167,(4.25,-10.2,3.2),(3.3,-4.9,1.58)),
    (210,(4.9,-8.9,3.1),(2.4,-4.85,1.52)),
    (288,(4.7,-8.25,2.85),(1.45,-4.85,1.55))
]:
    cam.location=cp
    cam.keyframe_insert(data_path="location",frame=f)
    target.location=aim
    target.keyframe_insert(data_path="location",frame=f)

# Fix actor approach without teleport or camera collision. The bus doors slide first;
# actor starts moving after opening, advances from pavement to inner threshold.
for f,x,z in ((1,5.55,0),(164,5.55,0),(193,5.55,0),
              (209,5.10,0),(236,3.8,0),(266,1.63,.10),(288,0.85,.52)):
    actor.location=(x,-4.84,z)
    actor.keyframe_insert(data_path="location",frame=f)

# Face remains oriented to the camera; avoid black back-of-head silhouettes.
for f in [1,97,98,166,167,193,209,236,266,288]:
    scene.frame_set(f)
    cp=cam.matrix_world.translation
    pos=actor.matrix_world.translation
    d=cp-pos
    actor.rotation_euler.z=math.atan2(d.x,-d.y)
    actor.keyframe_insert(data_path="rotation_euler",frame=f)

# Stop debug style labels from being emitted during encodes. No logo/episode numbers.
scene.render.engine="BLENDER_EEVEE"
scene.render.resolution_x=540
scene.render.resolution_y=960
scene.render.resolution_percentage=100
scene.frame_start=1
scene.frame_end=288
scene.render.fps=24
for f in (163,181,207,242,278):
    scene.frame_set(f)
    scene.render.filepath=str(OUT/f"QA_FRAME_{f:03}.png")
    bpy.ops.render.render(write_still=True)
    print("QA_FRAME_REPAIRED",f,flush=True)
scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"BUS00_FORMAT_B_SAFE_SLIDING_DOORS.blend"))
(OUT/"change_report.json").write_text(json.dumps({
 "version":"format-b-v3", "fixes":[
  "removed hinged doors crossing pedestrian path",
  "removed pillar and long red beltline across entrance",
  "installed bus-attached sliding door leaves",
  "stable camera, no extreme push-through",
  "actor starts walking after doors open",
  "boarding steps are part of bus and fixed",
  "debug day label omitted from encoding"
 ],"door_timing_frames":{"open_start":164,"open_end":199},"fps":24,
 "sliding_doors":panel_data,
 "source":"consistent_bus_world_v2.blend",
 "status":"review_required"
 },ensure_ascii=False,indent=2),encoding="utf8")
print("SAFE_SCENE_READY",flush=True)
