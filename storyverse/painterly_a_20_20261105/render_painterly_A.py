"""GUSTAVA A: deterministic painterly 2D story engine, no AI video morphing.
No on-screen brand, episode/shot counters or diagnostic HUD.
One persistent composition per scene; characters/props are rigged 2D drawings
and sounds are later aligned to animation action timestamps.
"""
from PIL import Image,ImageDraw,ImageFont,ImageFilter
from pathlib import Path
import numpy as np,cv2,math,random,json,subprocess,sys,os,time,hashlib
ROOT=Path(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\PAINTERLY_A_NEXT_120_20261105")
OUT_W,OUT_H=540,960
SW,SH=600,1030
ORIGINAL=Image.open(r"C:\Users\alex-\GUSTAVA-AI-HUB\productions\BUS_00_REBUILD_CONTROLLED\PAINTERLY_ORIGINAL_ART.jpg").convert("RGB")
FONTS=Path(r"C:\Windows\Fonts")
def font(sz,bold=True):
    for name in (("arialbd.ttf","segoeuib.ttf","arial.ttf") if bold else ("arial.ttf","segoeui.ttf")):
        try:return ImageFont.truetype(str(FONTS/name),sz)
        except:pass
    return ImageFont.load_default()
FS=font(18);FT=font(26);FL=font(40)
def lerp(a,b,t):return a+(b-a)*t
def mix(a,b,t):return tuple(int(lerp(a[i],b[i],t)) for i in range(3))
def clamp(t):return max(0,min(1,t))
def smooth(t):
    t=clamp(t);return t*t*(3-2*t)
def line(d,pts,fill,width=2):d.line(pts,fill=fill,width=max(1,int(width)),joint="curve")
def circ(d,x,y,r,fill,outline=None,width=1):
    d.ellipse((int(x-r),int(y-r),int(x+r),int(y+r)),fill=fill,outline=outline,width=width)
def box(d,xy,fill,r=5,outline=None,width=2):
    d.rounded_rectangle(tuple(int(q) for q in xy),radius=int(r),fill=fill,outline=outline,width=width)
def mountains(d,rng,top=440):
    for k in range(5):
        x=k*160-170
        points=[(x-110,top+145),(x+20,top+rng.randint(5,110)),(x+80,top+rng.randint(-50,40)),(x+190,top+110)]
        d.polygon(points+[(x+190,top+225),(x-110,top+225)],fill=(36+k*3,54+k*3,94+k*3))
        d.polygon([(x+54,top+35),(x+78,top-9),(x+118,top+59),(x+96,top+48),(x+76,top+30)],fill=(162,176,220))
def grad_sky(seed,inside=False):
    rng=random.Random(seed)
    colors=[(15,27,65),(37,52,104),(88,84,148),(79,106,149),(19,48,90)]
    if inside:colors=[(24,35,57),(36,52,76),(53,64,88),(46,65,88),(19,44,68)]
    arr=np.empty((SH,SW,3),dtype=np.uint8)
    breaks=[0,180,390,700,1030]
    for i in range(4):
        a,b=breaks[i:i+2]
        c1,c2=colors[i:i+2]
        for y in range(a,b):
            h=(y-a)/(b-a)
            arr[y,:,0]=int(lerp(c1[0],c2[0],h))
            arr[y,:,1]=int(lerp(c1[1],c2[1],h))
            arr[y,:,2]=int(lerp(c1[2],c2[2],h))
    im=Image.fromarray(arr,"RGB")
    # Restore recognizable blue-violet brush texture from approved picture.
    reference=ORIGINAL.crop((510,0,1240,336)).resize((SW,440),Image.Resampling.LANCZOS)
    im.paste(Image.blend(im.crop((0,0,SW,440)),reference,.32),(0,0))
    cloud=Image.new("RGBA",(SW,SH),(0,0,0,0));d=ImageDraw.Draw(cloud)
    for i in range(125):
        x=rng.randrange(-100,SW+100);y=rng.randrange(260,640)
        rx=rng.randint(30,145);ry=rng.randint(12,64)
        d.ellipse((x-rx,y-ry,x+rx,y+ry),fill=rng.choice([(176,96,195,6),(91,107,189,11),(71,142,184,10)]))
    im=Image.alpha_composite(im.convert("RGBA"),cloud.filter(ImageFilter.GaussianBlur(25)))
    d=ImageDraw.Draw(im)
    for i in range(205):
        x=rng.randrange(SW);y=rng.randrange(0,580)
        radius=rng.choice([0,0,1,1,2]);a=rng.randint(50,190)
        circ(d,x,y,radius,(223,234,255,a))
    mountains(d,rng,450)
    # Buildings have a physical ground plane, mountains remain behind.
    d.polygon([(0,625),(100,613),(200,642),(325,603),(450,620),(600,600),(600,SH),(0,SH)],fill=(95,126,167,255))
    d.polygon([(0,720),(115,696),(260,725),(365,682),(485,698),(600,650),(600,SH),(0,SH)],fill=(110,139,185,255))
    d.polygon([(0,835),(155,817),(280,841),(450,789),(600,814),(600,SH),(0,SH)],fill=(124,156,196,255))
    for j in range(60):
        y=rng.randrange(700,SH);x=rng.randrange(SW);dx=rng.randrange(4,60)
        line(d,[(x,y),(x+dx,y-rng.randrange(5))],(184,210,238,rng.randint(14,35)),rng.choice([1,2,3]))
    return im
def glow(im,x,y,r,color=(255,198,134),alpha=75):
    layer=Image.new("RGBA",(SW,SH));d=ImageDraw.Draw(layer)
    circ(d,x,y,r,(*color,alpha))
    im.alpha_composite(layer.filter(ImageFilter.GaussianBlur(int(r*.42))))
def house(d,x,y,w,h,seed,bright=False):
    rng=random.Random(seed);roof=y-h
    d.polygon([(x,roof+18),(x+w,roof+18),(x+w-10,y),(x+7,y)],fill=(39,50,74,255))
    d.polygon([(x-8,roof+16),(x+w+10,roof+16),(x+w-2,roof+32),(x,roof+32)],fill=(183,201,228,255))
    # Coherent stacked window grid.
    for ry in range(3):
        for rx in range(3):
            px=int(x+15+rx*(w-27)/3);py=int(roof+48+ry*max(40,(h-80)/3))
            d.rectangle((px,py,px+17,py+27),fill=(16,30,53,255))
            c=(237,180,127,240) if bright or rng.random()>.62 else (41,72,104,220)
            d.rectangle((px+2,py+2,px+15,py+25),fill=c)
            line(d,[(px+8,py+2),(px+8,py+25)],(41,49,69,170),2)
def fir(d,x,y,scale=1,phase=0):
    s=scale;trunk=(34,52,64,235)
    line(d,[(int(x),int(y)),(int(x),int(y-110*s))],trunk,max(2,int(9*s)))
    for k in range(3):
        cy=y-(26+k*32)*s
        w=(54-k*13)*s
        d.polygon([(x-w,cy),(x,cy-(78-k*8)*s),(x+w,cy)],fill=(32+k*3,65+k*4,79+k*6,240))
        line(d,[(x-w*.70,cy-4*s),(x-w*.22,cy-(29+k*10)*s),(x,cy-(39+k*7)*s)],(163,197,208,155),max(1,int(3*s)))
def ground_scene(im,place,seed,action):
    rng=random.Random(seed+777)
    d=ImageDraw.Draw(im)
    indoor={"carriage","cabin","house","hut","greenhouse","hotel","classroom","cinema","post","observatory","museum","mine","tunnel","apartment","school","shed"}
    if place in indoor:
        d.polygon([(0,SH),(0,320),(SW,320),(SW,SH)],fill=(37,50,75,245))
        d.polygon([(0,700),(SW,670),(SW,SH),(0,SH)],fill=(48,67,93,255))
        d.polygon([(0,330),(SW,350),(SW,420),(0,408)],fill=(26,38,57,255))
        for x in (48,SW-185):
            box(d,(x,130,x+135,405),(49,67,95,255),5,outline=(109,126,149,255),width=7)
            d.rectangle((x+12,143,x+123,393),fill=(71,99,143,255))
            d.polygon([(x+13,340),(x+73,295),(x+122,320),(x+122,393),(x+13,393)],fill=(172,187,219,220))
            line(d,[(x+67,143),(x+67,393)],(108,123,146,255),4)
        d.polygon([(0,SH),(210,730),(365,710),(SW,SH)],fill=(29,39,59,235))
        if place in ("carriage","cinema","classroom","hotel","post","museum","library"):
            for k in range(4):
                y=680+k*82;size=80+k*13
                d.rectangle((42,y,42+size,y+20),fill=(74,55,67,255))
                d.rectangle((SW-42-size,y,SW-42,y+20),fill=(74,55,67,255))
    else:
        if place in ("square","village","city","road","market"):
            for j in range(4):
                x=-50+j*184;h=205+12*(j%3)
                house(d,x,640,150,h,seed+j,bright=action in ("people","reveal","lights"))
            # Consistent perspective road under the standing hero.
            d.polygon([(220,650),(385,650),(590,SH),(60,SH)],fill=(37,63,105,240))
            line(d,[(235,667),(75,SH)],(190,205,226,110),4)
            line(d,[(381,667),(581,SH)],(190,205,226,110),4)
        if place in ("forest","hill","garden","lake","shore","river"):
            for i in range(16):
                xx=20+i*42+rng.randrange(-22,25)
                yy=685+rng.randrange(-17,145)
                fir(d,xx,yy,.40+rng.random()*.6)
            if place in ("lake","shore","river"):
                d.polygon([(0,760),(SW,740),(SW,SH),(0,SH)],fill=(45,94,147,236))
                for j in range(18):
                    x=rng.randrange(SW);y=rng.randrange(785,SH)
                    line(d,[(x,y),(x+rng.randint(22,100),y-2)],(181,223,234,130),2)
        if place in ("bridge","station","school","tower"):
            for j in range(5):
                x=j*160-90;house(d,x,704,130,180,seed+34+j)
    # Repeating random marks as an intentional paint texture, not changing per-frame.
    for j in range(90):
        xx=rng.randint(0,SW-1);yy=rng.randint(730,SH-5)
        line(d,[(xx,yy),(xx+rng.randint(4,25),yy-rng.randint(0,4))],(197,214,235,rng.randint(22,65)),1)
    return im
def prop(im,place,act,seed,t,duration):
    p=clamp(t/max(1,duration));u=smooth(p)
    d=ImageDraw.Draw(im)
    cx,cy=410,754
    kw=act.lower()
    if kw in ("arrival","ticket","doors","compartment","clock") and place in ("station","carriage"):
        # One unchanging railcar with actual carriage floor and two grounded wheel assemblies.
        x=int(35+(185*u if kw=="arrival" else 0))
        if place=="station":
            d.polygon([(0,862),(SW,834),(SW,SH),(0,SH)],fill=(44,62,92,240))
            for yy in range(879,SH,45):
                line(d,[(210-int((yy-880)*.75),yy),(405+int((yy-880)*.74),yy)],(170,181,195,155),4)
            box(d,(x,620,x+440,834),(52,98,159,255),24,outline=(28,54,94,255),width=5)
            d.polygon([(x,620),(x+55,575),(x+394,580),(x+440,622)],fill=(154,177,211,245))
            for k in range(5):
                xx=x+48+k*74
                box(d,(xx,640,xx+53,711),(24,47,76,255),7,outline=(178,207,227,255),width=3)
            for xx in (x+110,x+355):
                circ(d,xx,827,30,(22,37,52,255))
                circ(d,xx,827,14,(122,145,172,255))
            # One panel separates from the doorway only when boarding, not across a person.
            if kw=="doors":
                opening=round(80*smooth((p-.30)/.35))
                d.rectangle((x+275-opening,719,x+330-opening,815),fill=(35,77,118,240))
                d.rectangle((x+334+opening,719,x+378+opening,815),fill=(35,77,118,240))
        else:
            # Interior perspective, fixed seats, and window scenery outside.
            for i in range(4):
                y=645+i*72
                box(d,(33,y,166,y+48),(104,76,83,255),7,outline=(203,160,150,150),width=3)
                box(d,(416,y-10,551,y+46),(104,76,83,255),7,outline=(203,160,150,150),width=3)
            if kw=="clock":
                circ(d,300,405,98,(36,42,69,245),(211,195,159,255),5)
                angle=2*math.pi*u*3
                line(d,[(300,405),(300+68*math.sin(angle),405-68*math.cos(angle))],(241,197,128,255),7)
    elif kw in ("radio","signal","receiver","warning","ring","phone") or place in ("tower",):
        # Upright metal radio with permanent frame; dial light animated in place.
        box(d,(340,620,532,838),(52,62,77,255),17,outline=(131,159,175,255),width=5)
        box(d,(362,643,514,697),(24,42,57,255),5,outline=(221,156,101,200),width=3)
        line(d,[(370,677),(370+120*u,663)],(107,231,228,255),5)
        for i in range(4):
            circ(d,374+i*42,739,13,(167,178,182,255),(34,39,49,255),2)
        d.rectangle((381,771,488,815),fill=(24,31,38,255))
        for i in range(7):
            x=388+i*14
            d.rectangle((x,781,x+5,808),fill=(62+i*9,121+i*8,145,255))
    elif kw in ("mailbox","parcel","letters","letter","photo","note","seeds","ticket") or place in ("post",):
        # Real grounded postbox & letter; front hatch shifts on its own pivot.
        box(d,(360,572,520,812),(128,51,69,255),12,outline=(203,113,106,255),width=5)
        d.polygon([(352,577),(380,550),(502,548),(529,577)],fill=(197,212,226,255))
        box(d,(373,628,508,658),(32,42,57,255),5,outline=(217,167,132,255),width=3)
        opening=int(52*smooth((p-.28)/.3))
        d.polygon([(389,632+opening),(498,630+opening),(492,666+opening),(384,667+opening)],fill=(39,58,68,255))
        paper=int(60*smooth((p-.48)/.3))
        d.polygon([(395,640-paper),(494,640-paper),(486,706-paper),(397,706-paper)],fill=(237,223,191,255))
        d.polygon([(395,640-paper),(446,673-paper),(494,640-paper)],fill=(191,173,149,255))
        box(d,(391,812,489,872),(75,79,91,255),4)
    elif kw in ("lantern","lights","light","glass","lamp","rescue") or place in ("square",):
        # A real pole rooted in ground with light cast on snow.
        x=470
        line(d,[(x,849),(x-8,348)],(35,48,65,255),13)
        line(d,[(x-5,350),(x-50,320),(x-114,319)],(48,53,61,255),8)
        circ(d,x-124,324,24,(235,195,121,255),(61,61,67,255),5)
        if p>.15 and kw!="warning":
            strength=.55+.45*math.sin(t*2.8)**2
            for n,a in ((160,30),(110,44),(72,49)):
                circ(d,x-124,324,int(n*strength), (255,196,124,int(a*strength)))
            d.ellipse((175,866,552,917),fill=(247,203,143,80))
    elif kw in ("bridge","break","rails","river","reflection","crack") or place in ("bridge",):
        d.polygon([(120,760),(485,744),(599,866),(38,886)],fill=(80,92,120,255))
        for k in range(7):
            x=105+k*70
            line(d,[(x,795),(x,610)],(80,101,115,255),8)
            line(d,[(x,612),(x+68,612)],(173,194,203,255),4)
        if kw in ("break","crack"):line(d,[(325,778),(350,800),(337,828),(373,863)],(22,51,85,255),6)
    elif kw in ("lever","repair","switch","fire","water") or place in ("shed","greenhouse"):
        box(d,(338,609,536,825),(60,73,78,255),12,outline=(155,182,187,255),width=6)
        for k in range(3):
            x=367+k*65
            circ(d,x,688,20,(31,48,57,255),(160,172,169,255),4)
            ang=-1.0 if k!=1 else (lerp(-.7,.8,smooth((p-.33)/.35)))
            line(d,[(x,684),(x+46*math.sin(ang),684-44*math.cos(ang))],(210,170,115,255),8)
        for k in range(5):
            y=772+k*10;line(d,[(352,y),(513,y)],(36,51,58,255),3)
    elif kw in ("clock","rewind","time","stars","comet","sky") or place in ("observatory",):
        circ(d,418,621,132,(29,45,76,255),(194,200,208,255),9)
        circ(d,418,621,119,(60,83,118,255),(29,44,67,255),5)
        for k in range(12):
            a=2*math.pi*k/12
            x=418+101*math.sin(a);y=621-101*math.cos(a)
            circ(d,x,y,3,(217,205,170,255))
        ang=2*math.pi*(.05+p*.91)
        line(d,[(418,621),(418+93*math.sin(ang),621-93*math.cos(ang))],(239,206,135,255),8)
        line(d,[(418,621),(418+65*math.sin(ang*2),621-65*math.cos(ang*2))],(255,231,190,255),5)
    elif kw in ("camera","screen","photo","film","marquee") or place in ("cinema",):
        box(d,(335,560,548,772),(35,41,57,255),13,outline=(169,149,146,255),width=6)
        box(d,(362,583,523,711),(77,93,117,255),5,outline=(209,210,218,255),width=3)
        # Image screen: snowy city with sunrise warning, not nonsense text.
        d.polygon([(369,700),(409,646),(444,685),(474,617),(516,698)],fill=(160,194,215,255))
        circ(d,481+int(math.sin(t)*4),612,21,(255,184,108,255))
        for k in range(5):circ(d,366+k*33,744,7,(184,144,128,255))
    elif kw in ("birds","feathers","nest") or place in ("garden",):
        fir(d,415,833,1.45)
        if kw in ("birds","feathers","nest"):
            for i in range(9):
                xx=300+70*math.sin(t*.2+i*1.3)
                yy=340+i*39+math.sin(t*1.7+i)*26
                line(d,[(xx-12,yy),(xx,yy-6),(xx+13,yy)],(213,239,251,240),3)
        elif kw=="flowers":
            for i in range(15):
                xx=325+i*13;yy=847-int(math.sin(i*.6)*14)
                circ(d,xx,yy,6,(250,163,191,255))
    else:
        # A consistent piece of visual scene information: a fixed paper map
        # with moving (not morphing) blue light, never random AI glyphs.
        box(d,(350,604,520,819),(89,91,111,255),13,outline=(159,184,197,255),width=4)
        d.polygon([(372,629),(500,617),(504,782),(372,789)],fill=(192,191,171,255))
        for k in range(4):
            xx=385+k*33
            line(d,[(xx,649),(xx+12,764)],(91,121,127,175),3)
        circ(d,409+int(75*p),719,7,(247,177,118,255))
    return im
def actor(im,x,foot,t,seed,color=(210,103,61),pose="stand",s=.92):
    """Connected 2D skeleton. Both eyes and exactly two feet, two hands."""
    d=ImageDraw.Draw(im)
    phase=t*5.8
    move=pose in ("walk","run")
    bob=math.sin(phase*2)*2.5*s if move else math.sin(t*1.3)*1.0*s
    foot+=bob
    dx=23*math.sin(phase) if move else 0
    lifting=11*max(0,math.sin(phase)) if move else 0
    head=(int(x),int(foot-203*s))
    # Ground-contact shadow. Fixed with the physical foot level.
    d.ellipse((int(x-49*s),int(foot-6*s),int(x+51*s),int(foot+10*s)),fill=(24,43,62,140))
    ink=(18,24,32,255);skin=(241,229,211,255)
    for sign in (-1,1):
        hip=(x+sign*19*s,foot-100*s)
        knee=(x+sign*20*s+dx*sign*.25,foot-55*s)
        toe=(x+sign*22*s+dx*sign,foot-(lifting if sign==1 else 11*max(0,-math.sin(phase)))*s)
        line(d,[hip,knee,toe],ink,7*s)
        line(d,[(toe[0]-12*s,toe[1]),(toe[0]+16*s,toe[1])],(21,29,40,255),10*s)
    # Jacket and fixed central zipper, scarf and face black outline.
    box(d,(x-48*s,foot-195*s,x+49*s,foot-97*s),(*color,255),13,outline=ink,width=max(2,int(4*s)))
    for h in (125,151,176):
        line(d,[(x-41*s,foot-h*s),(x+42*s,foot-h*s)],(132,58,49,100),2)
    line(d,[(x,foot-180*s),(x,foot-99*s)],(37,39,49,255),3)
    box(d,(x-23*s,foot-205*s,x+23*s,foot-188*s),(124,65,94,255),5)
    if pose=="point":
        endR=(x+110*s,foot-225*s)
    elif pose=="hold":
        endR=(x+45*s,foot-144*s)
    else:
        endR=(x+76*s+dx*.3,foot-113*s)
    lsh=(x-41*s,foot-182*s);rsh=(x+42*s,foot-182*s)
    le=(x-68*s,foot-147*s);re=(x+68*s,foot-145*s)
    lw=(x-73*s-dx*.35,foot-103*s);rw=endR
    for points in ([lsh,le,lw],[rsh,re,rw]):
        line(d,points,ink,8*s)
        circ(d,points[-1][0],points[-1][1],9*s,skin,ink,2)
    circ(d,head[0],head[1],40*s,ink)
    circ(d,head[0],head[1],36*s,skin)
    # Winter hat and two eyes; coordinates never independently sampled.
    d.pieslice((int(x-39*s),int(head[1]-47*s),int(x+39*s),int(head[1]+17*s)),180,358,fill=(23,31,41,255))
    box(d,(x-38*s,head[1]-44*s,x+38*s,head[1]-31*s),(37,39,56,255),8)
    blink=(t+seed*.17)%4.7<.14
    for k in (-1,1):
        ex=x+k*15*s
        if blink:line(d,[(ex-5*s,head[1]),(ex+5*s,head[1])],ink,2)
        else:circ(d,ex,head[1],3.5*s,ink)
    # Neutral mouth, not lip-synced to narrator.
    line(d,[(x-8*s,head[1]+22*s),(x+8*s,head[1]+22*s)],(55,45,50,255),2)
    return im
def captions(im,txt):
    if not txt:return
    d=ImageDraw.Draw(im)
    f=FT if len(txt)<34 else FS
    lines=[]
    words=txt.split()
    accum=""
    maxw=OUT_W-82
    for w in words:
        cand=(accum+" "+w).strip()
        bbox=d.textbbox((0,0),cand,font=f)
        if bbox[2]>maxw and accum:
            lines.append(accum);accum=w
        else:accum=cand
    if accum:lines.append(accum)
    lines=lines[:2]
    y=850-(len(lines)-1)*16
    for ln in lines:
        d.text((SW/2,y),ln,font=f,anchor="mm",fill=(251,248,242,255),stroke_width=3,stroke_fill=(20,26,43,240))
        y+=34
def moving_snow(im,seed,t):
    """Four fixed-depth snow layers with deterministic positions and no teleport."""
    d=ImageDraw.Draw(im)
    rng=random.Random(seed*712371+1281)
    for layer,n in ((0,40),(1,37),(2,24),(3,17)):
        for i in range(n):
            x0=rng.randint(0,SW-1);y0=rng.randint(-SH,SH)
            sp=[17,27,45,66][layer];wind=[4,8,15,20][layer]
            x=(x0+wind*t)%(SW+65)-25
            y=(y0+sp*t)%(SH+45)-16
            rad=[.8,1.0,1.4,2.2][layer]
            op=[90,125,165,185][layer]
            circ(d,x,y,rad,(221,234,251,op))
    return im
def render_frame(base,story,scene_idx,local,duration,seed):
    scene=story["scenes"][scene_idx]
    place,action=(scene.split(":",1)+[""])[:2]
    im=base.copy()
    p=local/duration
    # Each action is one physically consistent drawing; no prompts, random anatomy or morphing.
    prop(im,place,action,seed,local,duration)
    hero_color=(224,112,65) if scene_idx%3!=1 else (213,151,77)
    hero_x=185+16*math.sin(local*.12+scene_idx)
    hero_foot=845
    walk=action in ("arrival","tracks","climb","run","rescue","approach","warning")
    if walk:
        hero_x=147+142*smooth((p-.12)/.72)
    hero_pose="walk" if walk else ("point" if action in ("lever","light","reveal","rescue") else "hold" if action in ("letter","mailbox","photo","ticket","parcel") else "stand")
    actor(im,hero_x,hero_foot,local,seed,hero_color,hero_pose,.81 if scene_idx in (3,4) else .92)
    moving_snow(im,seed,local)
    # Controlled, minimal dolly and pan, never crop the actor's head or feet.
    drift=9*math.sin(local*.17+seed*.1)
    zoom=1+.020*smooth(p)+.009*math.sin(local*.18)
    crop_h=int(1010/zoom)
    crop_w=int(crop_h*OUT_W/OUT_H)
    center_x=298+drift;center_y=518
    x0=int(max(0,min(SW-crop_w,center_x-crop_w/2)))
    y0=int(max(0,min(SH-crop_h,center_y-crop_h/2)))
    arr=np.asarray(im.convert("RGB"))
    frame=cv2.resize(arr[y0:y0+crop_h,x0:x0+crop_w],(OUT_W,OUT_H),interpolation=cv2.INTER_LINEAR)
    return frame
def encode_preview(story,seconds=3.0):
    """Generate tiny clip for fast visual QA before any full episode."""
    p=ROOT/"episodes"/story["slug"];p.mkdir(parents=True,exist_ok=True)
    seed=sum(ord(c) for c in story["slug"])%100000
    place,action=story["scenes"][0].split(":")
    base=ground_scene(grad_sky(seed,place in {"carriage","cabin","house","hut","greenhouse","hotel","classroom","cinema","post","observatory","museum","mine","tunnel","apartment","school","shed"}),place,seed,action)
    out=p/"PREVIEW_VISUAL_TEST_3SEC.mp4"
    cmd=["ffmpeg","-y","-hide_banner","-loglevel","error","-f","rawvideo","-pixel_format","rgb24",
        "-video_size",f"{OUT_W}x{OUT_H}","-framerate","12","-i","pipe:0",
        "-c:v","libx264","-preset","ultrafast","-crf","21","-pix_fmt","yuv420p",
        "-r","24","-movflags","+faststart",str(out)]
    pr=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for n in range(int(seconds*12)):
            fr=render_frame(base,story,0,n/12,21,seed)
            pr.stdin.write(fr.tobytes())
        pr.stdin.close()
        ret=pr.wait(timeout=90)
        if ret:raise RuntimeError("PREVIEW_ENCODER_FAILED "+pr.stderr.read().decode("utf8","replace")[-900:])
    finally:
        if pr.poll() is None:pr.kill()
    # Screenshot multiple frames to ensure movement, no blank frame.
    for t in (0.4,1.5,2.6):
        fr=render_frame(base,story,0,t,21,seed)
        Image.fromarray(fr).save(p/f"QA_PREVIEW_{t:.1f}.jpg",quality=90)
    print("PREVIEW_READY",str(out),out.stat().st_size,flush=True)
def audio_duration(file):
    pr=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(file)],check=True,capture_output=True,text=True,timeout=20)
    return float(pr.stdout.strip())
def build_audio(story):
    slug=story["slug"];p=ROOT/"episodes"/slug
    parts=[p/"audio"/f"part_{j:02}.mp3" for j in range(1,7)]
    if not all(x.exists() and x.stat().st_size>50000 for x in parts):
        raise RuntimeError("INCOMPLETE_REAL_DEEP_VOICE "+slug)
    olddur=[audio_duration(x) for x in parts]
    # Constant speed across scenes prevents jumpy narration pace.
    scale=sum(olddur)/119.1
    newdur=[x/scale for x in olddur]
    boundaries=np.cumsum([0]+newdur).tolist()
    fs=48000;total=int(120*fs)
    audio=np.zeros((total,2),dtype=np.float32)
    for j,file in enumerate(parts):
        proc=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-i",str(file),
            "-af",f"atempo={scale:.5f}","-f","f32le","-ac","1","-ar",str(fs),"-"],capture_output=True,check=True,timeout=90)
        speech=np.frombuffer(proc.stdout,dtype="<f4")
        start=int(boundaries[j]*fs)
        n=min(len(speech),total-start,int(newdur[j]*fs))
        if n>0:
            sound=np.copy(speech[:n])
            fade_len=min(4500,n//4)
            if fade_len>0:
                sound[:fade_len]*=np.linspace(0,1,fade_len,dtype=np.float32)
                sound[n-fade_len:]*=np.linspace(1,0,fade_len,dtype=np.float32)
            audio[start:start+n,0]+=sound*.86
            audio[start:start+n,1]+=sound*.86
    rng=np.random.default_rng(int(sum(ord(c) for c in slug)))
    # Original low-passed winter wind; no unlicensed third-party sound layers.
    n=(total+1599)//1600
    knots=rng.normal(0,1,size=n).astype(np.float32)
    low=np.interp(np.arange(total),np.arange(n)*1600,knots)
    low=np.float32(low/(np.std(low)+1e-8)*.006)
    audio[:,0]+=low
    audio[:,1]+=np.roll(low,630)*.92
    # Sound events tied to the 2D scene's action progression.
    for j,raw in enumerate(story["scenes"]):
        act=raw.split(":")[-1]
        t0=boundaries[j]
        if act in ("lantern","lights","light","reveal","rescue","stars","comet","signal","warning","clock"):
            at=int((t0+newdur[j]*.37)*fs)
            m=min(int(.9*fs),total-at)
            tt=np.arange(m,dtype=np.float32)/fs
            sw=np.sin(2*np.pi*(195+175*tt)*tt)*np.exp(-tt*5)*.016
            audio[at:at+m,0]+=sw
            audio[at:at+m,1]+=sw*.87
        if act in ("tracks","climb","walk","arrival","run","approach"):
            for frac in np.arange(.17,.85,.075):
                at=int((t0+newdur[j]*frac)*fs)
                m=min(int(.17*fs),total-at)
                tt=np.arange(m,dtype=np.float32)/fs
                fx=np.sin(2*np.pi*83*tt)*np.exp(-tt*28)*.012
                audio[at:at+m,0]+=fx
                audio[at:at+m,1]+=fx*.9
    maxv=np.max(np.abs(audio))
    if maxv>.94:audio*=.94/maxv
    import wave
    wav=p/"GUSTAVA_DEEP_STEREO_MIX.wav"
    with wave.open(str(wav),"wb") as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(fs)
        w.writeframes((np.clip(audio,-1,1)*32767).astype("<i2").tobytes())
    return wav,newdur,boundaries
def render_full(story, fps=12,seconds=120.0):
    slug=story["slug"];p=ROOT/"episodes"/slug
    wav,durations,bounds=build_audio(story)
    out=p/("SHORTS_"+slug+"_120s_A.mp4")
    scene_bases=[]
    indoor={"carriage","cabin","house","hut","greenhouse","hotel","classroom","cinema","post","observatory","museum","mine","tunnel","apartment","school","shed"}
    for j,scene in enumerate(story["scenes"]):
        place,act=scene.split(":")
        seed=1003*j+sum(ord(ch) for ch in slug)
        base=ground_scene(grad_sky(seed,place in indoor),place,seed,act)
        scene_bases.append((base,place,act,seed))
    cmd=["ffmpeg","-y","-nostdin","-hide_banner","-loglevel","error",
         "-f","rawvideo","-pixel_format","rgb24","-video_size",f"{OUT_W}x{OUT_H}",
         "-framerate",str(fps),"-i","pipe:0","-i",str(wav),
         "-map","0:v:0","-map","1:a:0",
         "-c:v","h264_nvenc","-preset","p4","-rc","vbr","-cq","21","-b:v","0","-pix_fmt","yuv420p",
         "-r","24","-c:a","aac","-b:a","192k","-ac","2","-ar","48000",
         "-t",str(seconds),"-movflags","+faststart",str(out)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
    firstframes=[]
    start=time.monotonic()
    try:
        frames=int(seconds*fps)
        for n in range(frames):
            t=n/fps
            j=min(5,max(0,int(np.searchsorted(bounds,t,side="right")-1)))
            local=t-bounds[j]
            base,place,act,seed=scene_bases[j]
            fr=render_frame(base,story,j,local,durations[j],seed)
            proc.stdin.write(fr.tobytes())
            # A 6x3 contact sheet, all cuts visually inspectable, no debug overlay inside movie.
            if n in {min(frames-1,int((bounds[j]+durations[j]*part)*fps)) for j in range(6) for part in (.1,.5,.9)}:
                firstframes.append((t,Image.fromarray(fr).resize((180,320))))
            if n%240==0:print("ENCODE_PROGRESS",slug,f"{n/frames*100:.1f}%","elapsed",round(time.monotonic()-start,1),flush=True)
        proc.stdin.close()
        try:ret=proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill();raise
        if ret:raise RuntimeError("FFMPEG_ERROR "+proc.stderr.read().decode("utf8","replace")[-1600:])
    finally:
        if proc.poll() is None:proc.kill()
    canvas=Image.new("RGB",(6*180,3*320),(23,30,45))
    for k,(t,image) in enumerate(firstframes[:18]):
        canvas.paste(image,((k%6)*180,(k//6)*320))
    canvas.save(p/"VISUAL_QA_18_FRAMES.jpg",quality=89)
    probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_type,codec_name,width,height,avg_frame_rate,channels","-of","json",str(out)],check=True,capture_output=True,text=True,timeout=25)
    info=json.loads(probe.stdout)
    assert abs(float(info["format"]["duration"])-120)<.3
    v=next(x for x in info["streams"] if x.get("codec_type")=="video")
    a=next(x for x in info["streams"] if x.get("codec_type")=="audio")
    assert v["width"]==540 and v["height"]==960 and a["channels"]==2
    sha=hashlib.sha256(out.read_bytes()).hexdigest()
    data={"slug":slug,"status":"rendered_needs_artistic_QA","duration":float(info["format"]["duration"]),"parts":len(story["parts"]),"has_deep_voice":True,"frame_rate":"24","bytes":out.stat().st_size,"sha256":sha,"file":str(out),"note":"Frame-based painted 2D rig and separate prop motion. Not generative 3D film."}
    (p/"delivery_manifest.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
    print("VIDEO_READY",json.dumps(data,ensure_ascii=False),flush=True)
    return data
if __name__=="__main__":
    stories=json.loads((ROOT/"all_20_stories.json").read_text(encoding="utf8"))["items"]
    slug=sys.argv[2] if len(sys.argv)>2 else stories[0]["slug"]
    story=next(x for x in stories if x["slug"]==slug)
    if len(sys.argv)>1 and sys.argv[1]=="--preview":encode_preview(story)
    elif len(sys.argv)>1 and sys.argv[1]=="--render":render_full(story)
    else:print("Usage: render_painterly_A.py --preview|--render <story_slug>",flush=True)
