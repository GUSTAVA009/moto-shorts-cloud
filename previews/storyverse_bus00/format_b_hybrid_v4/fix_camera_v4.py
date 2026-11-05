import bpy,json
from pathlib import Path
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

BASE=Path(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\BUS_00_REBUILD_CONTROLLED\FORMAT_B_HYBRID_V3")
scene=bpy.context.scene
camera=scene.camera
target=bpy.data.objects["Camera aim"]
actor=bpy.data.objects["2D_RIG_ANTON_LOCKED"]
# The jump into the door shot happens at frame 167. Correct the offscreen crop
# on the character from that shot onward, without changing early story beats.
target.animation_data_clear()
for f,x,y,z in [
 (1,0,8,1.8),(97,3.4,-4.8,1.5),(98,3.4,-4.8,1.5),
 (166,3.3,-4.9,1.58),
 (167,4.15,-4.88,1.52),
 (210,3.75,-4.85,1.5),
 (238,3.2,-4.85,1.5),
 (288,1.70,-4.85,1.5)
]:
 target.location=(x,y,z);target.keyframe_insert(data_path="location",frame=f)
camera.data.lens=19
# Recompute face orientation after changing focus; both eyes must remain visible.
for f in range(167,289,8):
 scene.frame_set(f)
 cam=camera.matrix_world.translation.copy()
 pos=actor.matrix_world.translation.copy()
 import math
 direction=cam-pos
 actor.rotation_euler.z=math.atan2(direction.x,-direction.y)
 actor.keyframe_insert(data_path="rotation_euler",frame=f)
result=[]
for f in [167,179,190,199,207,218,233,245,264,278,288]:
 scene.frame_set(f)
 pos=actor.matrix_world.translation+Vector((0,0,1.4))
 uv=world_to_camera_view(scene,camera,pos)
 result.append({"frame":f,"screen_x":round(float(uv.x),3),"screen_y":round(float(uv.y),3)})
print("ACTOR_CAMERA_BOUNDS",json.dumps(result),flush=True)
# Do not reject subject deliberately out of view in dramatic bus cut, but reject
# visible half-face clipping around the door and walking.
for row in result:
 if row["frame"]>=167 and row["frame"]<288:
  assert 0.03<row["screen_x"]<.97,("ACTOR_CROPPED",row)
out=BASE/"FORMAT_B_V4_SAFE_CAMERA.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out))
for f in (167,181,207,238,278):
 scene.frame_set(f)
 scene.render.filepath=str(BASE/f"QA_CAM_V4_{f:03}.png")
 bpy.ops.render.render(write_still=True)
 print("CAMERA_V4_CHECK",f,flush=True)
print("CAMERA_V4_READY",flush=True)
