"""Produce original hand-painted 2D cinema storyboards locally via installed ComfyUI.
One coherent character per episode, deterministic prompts and seeds. No images from user PC.
"""
from pathlib import Path
import os,json,time,uuid,urllib.request,urllib.error,re,hashlib,sys
HOME=Path(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\PAINTERLY_A_NEXT_120_20261105")
COMFY=Path(r"C:\Users\alex-\GUSTAVA-LTX-Video\ComfyUI")
API="http://127.0.0.1:8189"
MODEL="sdxl_lightning_4step.safetensors"
CHAR={
"01_last_lantern":"One young boy in worn orange winter parka, black knitted earflap hat, navy scarf and boots, accompanied by one small black cat with yellow eyes, consistent character design",
"02_train_to_nowhere":"Lera, a young woman with yellow wool scarf, dark navy winter coat and chestnut hair, empty old railway station, one old blue passenger train",
"03_frozen_radio":"Misha, a teenager wearing red headphones and dark forest-green parka, isolated frozen radio transmission tower, little sister visible only when needed",
"04_house_of_memories":"Sonya, a young woman wearing violet winter coat and red mittens, snow-covered old family house, warm windows and nostalgic light",
"05_bridge_of_echoes":"Denis, a young man in emerald puffer jacket, white friendly dog, ancient suspension bridge above frozen river",
"06_lake_under_ice":"Anya, an adventurous young woman in cobalt blue winter overalls, transparent frozen lake and abandoned rescue boathouse",
"07_clock_in_the_forest":"Oleg, a man in brown parka, a white fox, grandfather clock deep in snowy spruce forest",
"08_school_bell":"Ilya, a teenage boy in blue knitted beanie and red scarf, abandoned snowy school with glowing windows",
"09_midnight_cinema":"Kirill, young man with green scarf, deserted ornate vintage cinema with art deco marquee",
"10_post_office_snow":"Marina, adult woman wearing burgundy coat and red mittens, abandoned post office in snowy village",
"11_garden_in_frost":"Egor, young man wearing dark brown coat, magical old flowering apple tree and rustic greenhouse in snowy garden",
"12_observatory_stars":"Vera, young woman wearing deep blue cloak and knit hat, abandoned snowy observatory high on a hill",
"13_hotel_room_zero":"Pavel, mature man in elegant grey winter overcoat with travel suitcase, old snowbound mountain hotel",
"14_phone_in_snow":"Nikita, young man in black cap and red backpack, desolate snowy road and mysterious red telephone",
"15_snow_birds":"Nadya, young woman in light blue parka, flock of luminous white birds on a snowy cottage roof",
"16_camera_tomorrow":"Vadim, young man in mustard winter jacket, old analog film camera and snowy town bridge",
"17_bell_under_mountain":"Roman, mountain rescuer wearing green helmet and orange jacket, abandoned snowy mine",
"18_staircase_between_houses":"Katya, girl in yellow knitted cap and dark coat, mysterious staircase connecting snowy Soviet apartment buildings",
"19_museum_of_stars":"Sasha, young woman with violet scarf, museum of glowing meteorites on winter night",
"20_city_not_on_map":"Timur, young man in red parka, impossible secret snow-covered town with warm streetlights",
}
LOC={
"square":"a deserted old town square with snowy European brick houses and warm isolated amber lamps",
"station":"a deserted old railway station with snow-covered tracks, steel canopy and old blue train",
"carriage":"interior of a mysterious night passenger train, mahogany compartments, dim yellow lamps, frosted windows",
"forest":"snowy dark spruce forest, pale lunar beams and blue snow",
"tower":"rusted radio mast above snowbound forest, small red aviation warning lights",
"cabin":"inside old radio cabin, vacuum tube receivers and old equipment, cinematic warm window light",
"house":"inside nostalgic old family home, winding staircase, vintage family photographs and frosted windows",
"village":"a snowbound old village, small wood houses, warm windows",
"bridge":"a narrow old suspension bridge over a frozen river in blue-purple blizzard",
"river":"frozen river with dramatic blue glacier reflections under night sky",
"lake":"wide winter lake with transparent snow-covered ice and mysterious lights below",
"shore":"icy snow-covered shore with old rescue boathouse",
"hut":"old wooden refuge, fireplace and warm lamp in snowy deep forest",
"school":"abandoned old school, snow, window lights and dark stone facade",
"classroom":"interior of vacant retro school classroom with wooden desks and frosted windows",
"cinema":"inside abandoned vintage cinema, beautiful projector light, velvet chairs and screen",
"post":"small old wooden Russian post office with red metal mailbox and snowfall",
"garden":"snow-covered orchard, old apple trees, wooden greenhouse and warm lantern",
"greenhouse":"rustic greenhouse inside winter orchard with small living apple tree",
"observatory":"old hilltop observatory with rotating dome and starry night sky",
"hill":"isolated mountain ridge with magical winter starfield",
"hotel":"elegant old mountain hotel entrance and warmly lit windows under deep snow",
"road":"snow-covered remote roadway under a vast purple night sky",
"tunnel":"dark old road tunnel at snowy mountain",
"market":"a deserted snowy old-town square with an abandoned market stall",
"mine":"deep old mountain mine shaft with icy stalactites, emergency lamps and railway tracks",
"apartment":"snow-covered Soviet residential courtyard, concrete stairwells and warm windows",
"museum":"small museum interior with glass cabinets and glowing meteorites",
"city":"fantastical lost old city, clocktower, mysterious warm shop windows and thick snow",
"shed":"small utility control shack interior with rusty electrical switches, warm practical lamp"
}
ACTION={
"tracks":"wide cinematic over-the-shoulder scene. Mysterious fresh human footprints appear alone in untouched deep snow; young hero and black cat observe them",
"mailbox":"medium close-up. Hero kneels at an old red cast iron mailbox and removes a sealed old letter. Black cat beside him, natural gloved hands",
"lantern":"wide dramatic night view. One solitary glowing golden streetlamp illuminates snow, hero runs toward it with black cat",
"lever":"inside dim frozen electrical service shed, hero reaches to pull one metal power breaker, old copper cables and warm glow",
"people":"in snowbound square, translucent ghostly villagers slowly materialize beside a vintage night bus, hero watches in amazement",
"mother":"intimate emotional cinematic scene. Orange parka boy embraces his mother in a bright blue wool scarf under beautiful golden streetlamp, small black cat watches",
"arrival":"long shot of vintage midnight blue passenger train arriving through snowy fog at deserted station",
"ticket":"woman studies an old paper ticket under an old station lamp, snow falling outside",
"compartment":"inside empty night train compartment, warm tea steaming beside wooden chessboard",
"clock":"close-up on brass clock without hands in mysterious train compartment",
"doors":"snowy night train passenger doors open with warm light spilling onto icy platform",
"reveal":"emotional final scene revealing a lost loved one in the snow, warm sunrise and luminous ambience",
"signal":"hero stands by glowing radio mast as red warning lamp blinks in snow",
"receiver":"close-up vintage shortwave radio receiver glowing with blue green dials in wooden cabin",
"climb":"hero climbs old rusty metal ladder of radio tower while distant snowstorm arrives",
"rescue":"hero rescues a young child from dangerous winter scene, physically believable action, dramatic glowing light",
"bell":"old copper school bell in snowbound empty building, gothic atmosphere",
"photo":"old sepia family photographs lit by warm window light, gloved hands examining one picture",
"stairs":"hero climbs creaking wooden staircase toward softly glowing doorway",
"window":"frosted window with warm mysterious reflections, moonlit snowfall outside",
"light":"magical burst of warm golden practical light illuminating snowy street",
"river":"a dark frozen river beneath ancient bridge and surreal reflections",
"crack":"dangerous crack in wooden old bridge, hero steps away from splintering planks",
"reflection":"mysterious mirror-like icy river reflecting hero as an older version of himself",
"warning":"hero receives a mysterious future warning through a glowing object on snowy night",
"house":"old two-story snowbound family home, nostalgic glowing window light",
"parcel":"worn paper parcel tied with twine on rustic counter beside old mail stamps",
"letters":"a dozen sealed envelopes floating in enchanted abandoned post office interior",
"flower":"bright pink blossoms on a single apple tree in the midst of snowy orchard",
"stars":"old observatory telescope pointed at brilliant northern stars and purple night",
"comet":"silver comet flying across violet-blue snowy mountain sky, star trails",
"phone":"mysterious red telephone uncovered in roadside snow near a dark tunnel",
"ring":"red telephone in snow with faint amber glow and snowflakes",
"fire":"hero warming hands by small lamp and orange fire in rustic wooden room",
"birds":"flock of white luminous snow birds flying above roof in purple night",
"camera":"vintage film camera held by gloved hand against snowy town backdrop",
"rooftop":"view from snowy apartment rooftop between buildings and moonlight",
"sky":"majestic bright starfield above winter town, cold blue and purple nebula",
"map":"a handmade parchment map resting on wood table under warm lamplight",
"light":"one golden lamppost glowing in purple winter snow",
}
STYLE="(beautiful 2D anime feature film frame:1.4), (hand-painted watercolor gouache movie background:1.45), painted cel-animation aesthetic, dreamy twilight with rich deep indigo violet and purple clouds, cozy warm amber streetlamps, sparkling blue snow, painterly delicate brush textures, hand drawn storybook masterpiece, volumetric atmosphere and cinematic detailed environment, vertical composition, no text"
NEG="photograph, photorealistic, CGI, plastic 3d render, text, letterings, captions, logos, watermark, extra limbs, blurry low detail, duplicate limbs, broken anatomy, glitch, synthetic textures, text, poster, UI, infographic"
def scene_prompts(st):
 slug=st["slug"];character=CHAR.get(slug,"one consistent illustrated winter traveler")
 out=[]
 for i,scene in enumerate(st["scenes"]):
  place,act=(scene.split(":",1)+[""])[0:2]
  action=ACTION.get(act, "A dramatic cinematic illustrated story shot: "+act.replace("_"," "))
  env=LOC.get(place,"a beautiful winter fairytale scene")
  if slug=="01_last_lantern" and i==5:
   action=ACTION["mother"]
  if slug=="01_last_lantern":
   plots=[
    "WIDE ESTABLISHING SHOT, camera looks down a long empty snowy old-town street at midnight, cobblestones under thick blue snow, mysterious footprints across foreground toward dark red mailbox, glowing amber lanterns recede into distance, (a small solitary figure wearing bright orange winter parka and black ushanka walking away from camera:1.3), (one tiny black cat beside him:1.1), subject occupies less than 15 percent of composition, highly detailed Victorian brick town, purple indigo cloud sky",
    "WIDE OVER-THE-SHOULDER CINEMATIC SHOT on frost-covered old town street, deep indigo dusk, antique red iron mailbox at roadside in foreground, the same small distant person in bright orange winter coat and black earflap hat opens a yellow sealed letter, one small black cat at his feet, highly detailed snowy buildings and golden lamps fill background, high-angle composition",
    "MASSIVE CINEMATIC WINTER TOWN SQUARE seen from far away at midnight, a single old golden streetlamp shines into deep blue snow and purple night sky, a tiny orange-jacketed figure with a black hat runs toward the glowing lantern with one black cat, dramatic atmospheric lighting, town architecture covers most of scene, wide establishing composition",
    "FILM FRAME showing aged electric switching room interior, rusted electrical distribution box, exposed copper wires, chunky metal breaker lever in foreground, one small orange-coated person reaching to throw the breaker, clean plausible human hands, dark wood wall and warm hanging bulb, mystical cinematic shadows",
    "WIDE 2D-ANIME CINEMATIC TOWN SQUARE at snowy midnight, old brick houses, vintage red passenger bus parked in far background, mysterious softly luminous silhouettes of villagers appear beneath amber lamplights, one orange-jacketed young man and one small black cat watching from behind in foreground, blue violet twilight, beautiful detailed atmosphere",
    "WIDE EMOTIONAL CINEMATIC WINTER PAINTING of old street at night, orange winter parka young man in black ushanka embracing his mother in long blue scarf under a tall glowing golden lamppost, a single small black cat sitting nearby, magical blue snow, deep violet sky, elegant old town architecture in background, perspective, single pair of people"
   ]
   revised=[
    "Wide establishing view of snowy midnight old town. Mysterious footprints across deep blue snow. One distant boy seen from behind wearing BRIGHT ORANGE PARKA and BLACK USHANKA, a small black cat. Detailed Victorian buildings, amber lamps and indigo purple clouds.",
    "Cinematic closeup of an old RED mailbox in a snowy street. ONE orange-gloved hand retrieves a sealed beige letter. Golden street lamp and snow-covered brick buildings behind. No faces.",
    "Wide cinematic view of EMPTY winter town square illuminated by a SINGLE magnificent golden streetlamp. Beautiful snowfall, tall detailed snow covered buildings, blue-violet sky, no closeup people.",
    "Cinematic closeup of old rusty electrical breaker and thick copper wires on dark wooden wall. One orange-gloved hand about to move the metal lever. Warm light from hanging bulb. Correct object geometry.",
    "Wide view of snowy empty brick town square at midnight. Mysterious translucent silhouettes of returning villagers gradually emerge beside one parked old red bus. A small distant boy in bright orange winter coat and black ushanka seen from behind.",
    "Emotional cinematic wide shot: Boy in BRIGHT ORANGE winter parka and BLACK USHANKA embraces his mother wearing a BLUE wool scarf under one tall glowing golden streetlamp. Small black cat sitting next to them. A snowy European old town, indigo-violet winter sky."
   ]
   focused=[
    "(wide establishing shot:1.3), lone small boy in BRIGHT ORANGE winter coat and black hat seen from behind walking through snow covered town, mysterious footprints, one black cat, purple night, cozy glowing lamps",
    "(ANTIQUE RED METAL MAILBOX:1.8) occupying the foreground, (one sealed beige letter sticking out of the open door:1.5), (one ORANGE gloved hand grasping envelope:1.4), deep snowy blue violet night, detailed background",
    "(SINGLE TALL GOLDEN STREETLAMP:1.8) is shining brightly in middle of deserted SNOWY TOWN SQUARE at night, amber light on blue snow, tiny boy in orange parka and black hat running in distance, deep violet sky",
    "(CLOSE UP OLD RUSTY ELECTRICAL BREAKER BOX:1.8), (one big red LEVER and orange gloved hand flipping the switch:1.6), copper cables, wooden wall, warm yellow light, interior, accurate real object",
    "(TRANSLUCENT GHOSTLY CROWD OF PEOPLE:1.6) materializing in snowy town square beside parked vintage red bus, (one little boy in BRIGHT ORANGE parka seen from behind:1.2), purple night, glowing lamps",
    "(TWO PEOPLE HUGGING UNDER STREETLAMP:1.8), young man in BRIGHT ORANGE parka and black ushanka holding his mother in BLUE wool scarf, one black cat, snow falling, dreamy violet blue town"
   ]
   prompt=f"{focused[i]}, masterpiece, (hand-painted two dimensional anime film frame:1.3), cinematic storybook winter animation, detailed architecture and snowy foreground, warm amber light, deep navy violet palette, beautiful matte brushwork, richly textured but not photorealistic, no text."
  else:
   prompt=f"(wide scenic environment occupying 80 percent of image:1.4), {env}, {action}. (small main character only:1.2) {character}. {STYLE}"
  out.append({"index":i,"place":place,"action":act,"prompt":prompt,"negative":NEG})
 return out
def workflow(prompt,negative,seed,prefix):
 return {
  "1":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":MODEL}},
  "2":{"class_type":"CLIPTextEncode","inputs":{"text":prompt,"clip":["1",1]}},
  "3":{"class_type":"CLIPTextEncode","inputs":{"text":negative,"clip":["1",1]}},
  "4":{"class_type":"EmptyLatentImage","inputs":{"width":832,"height":1216,"batch_size":1}},
  "5":{"class_type":"KSampler","inputs":{"seed":seed,"steps":4,"cfg":1.0,"sampler_name":"euler","scheduler":"sgm_uniform","denoise":1.0,"model":["1",0],"positive":["2",0],"negative":["3",0],"latent_image":["4",0]}},
  "6":{"class_type":"VAEDecode","inputs":{"samples":["5",0],"vae":["1",2]}},
  "7":{"class_type":"SaveImage","inputs":{"images":["6",0],"filename_prefix":prefix}}
 }
def req(path,payload=None,timeout=50):
 data=json.dumps(payload).encode("utf8") if payload is not None else None
 with urllib.request.urlopen(urllib.request.Request(API+path,data=data,headers={"Content-Type":"application/json"}),timeout=timeout) as r:
  return json.loads(r.read().decode())
def create(st,idx,timeout=700):
 slug=st["slug"];plan=scene_prompts(st)[idx]
 prefix="storyverse_A_SDXL/"+slug+f"/shot_{idx+1:02d}"
 seed=sum((i+1)*ord(x) for i,x in enumerate(slug))*1000+(idx+1)*10473
 checkpoint=COMFY/"models"/"checkpoints"/MODEL
 if checkpoint.stat().st_size<2000000000:raise RuntimeError("Model not downloaded completely")
 job=req("/prompt",{"prompt":workflow(plan["prompt"],plan["negative"],seed,prefix),"client_id":"GUSTAVA-STORYVERSE-CONTROLLED"},timeout=20)
 pid=job["prompt_id"]
 print("QUEUED_ILLUSTRATION",slug,idx+1,pid,flush=True)
 started=time.monotonic()
 while time.monotonic()-started<timeout:
  hist=req("/history/"+pid,timeout=30)
  if pid in hist:
   info=hist[pid]
   if info.get("status",{}).get("status_str")=="error":
    raise RuntimeError("ComfyUI error "+str(info.get("status",{}).get("messages",[]))[-600:])
   files=info.get("outputs",{}).get("7",{}).get("images",[])
   if files:
    f=files[0];path=COMFY/"output"/f.get("subfolder","")/f["filename"]
    if not path.exists():path=COMFY/"output"/(f.get("subfolder",""))/f["filename"]
    print("COMPLETED_ILLUSTRATION",slug,idx+1,path,path.stat().st_size,flush=True)
    return {"slug":slug,"shot":idx+1,"file":str(path),"seed":seed,"prompt":plan["prompt"],"bytes":path.stat().st_size}
  time.sleep(3)
 raise TimeoutError("COMFY_TIMEOUT "+pid)
if __name__=="__main__":
 sts=json.loads((HOME/"all_20_stories.json").read_text(encoding="utf8"))["items"]
 mode=sys.argv[1] if len(sys.argv)>1 else "pilot"
 index=int(sys.argv[2]) if len(sys.argv)>2 else 0
 if mode=="pilot":targets=[(sts[index],i) for i in range(6)]
 elif mode=="one":targets=[(sts[index],int(sys.argv[3]))]
 elif mode=="batch":targets=[(s,i) for s in sts for i in range(6)]
 else:raise ValueError(mode)
 allrec=[]
 for st,i in targets:
  try:
   rec=create(st,i);allrec.append(rec)
   path=HOME/"episodes"/st["slug"]/"sdxl_art_manifest.json"
   path.parent.mkdir(parents=True,exist_ok=True)
   old=json.loads(path.read_text(encoding="utf8")) if path.exists() else {}
   old[str(i+1)]=rec
   path.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding="utf8")
  except Exception as e:
   print("ART_ERROR",st["slug"],i+1,str(e),flush=True)
   if mode!="batch":raise
 print("LOCAL_ART_READY_COUNT",len(allrec),flush=True)
