from PIL import Image, ImageDraw, ImageFont
import sys, os
BASE=sys.argv[1]; OUT=sys.argv[2]; LOC=sys.argv[3]
FDIR="/Library/Fonts"
def F(w,s): return ImageFont.truetype(f"{FDIR}/SF-Pro-Display-{w}.otf", s)
TW,TH=1320,2868
img=Image.open(BASE).convert("RGB").resize((TW,TH), Image.LANCZOS)
d=ImageDraw.Draw(img)
# freq -> (accent, side, xfrac, yfrac). Kept out of the figure's arm-spread band.
POS={
174:("#D4A017","L",0.035,0.205),285:("#DC2626","L",0.03,0.35),
396:("#F97316","L",0.03,0.64),417:("#F59E0B","L",0.03,0.755),
528:("#EAB308","R",0.97,0.265),639:("#22C55E","R",0.985,0.375),
741:("#06B6D4","R",0.97,0.645),852:("#8B5CF6","R",0.985,0.745),
963:("#EC4899","R",0.97,0.83)}
NAMES={
"en":{174:"Deep Ease",285:"Renewal",396:"Let Go",417:"New Start",528:"Pure Love",639:"Open Heart",741:"Clear Voice",852:"Inner Sight",963:"Divine Light"},
"es-MX":{174:"Calma Profunda",285:"Renovación",396:"Soltar",417:"Nuevo Comienzo",528:"Amor Puro",639:"Corazón Abierto",741:"Voz Clara",852:"Visión Interior",963:"Luz Divina"},
"pt-BR":{174:"Calma Profunda",285:"Renovação",396:"Deixar Ir",417:"Recomeço",528:"Amor Puro",639:"Coração Aberto",741:"Voz Clara",852:"Visão Interior",963:"Luz Divina"},
"pl":{174:"Głęboki Spokój",285:"Odnowa",396:"Uwolnienie",417:"Nowy Początek",528:"Czysta Miłość",639:"Otwarte Serce",741:"Czysty Głos",852:"Wewnętrzny Wzrok",963:"Boskie Światło"},
"cs":{174:"Hluboký Klid",285:"Obnova",396:"Odpoutání",417:"Nový Začátek",528:"Čistá Láska",639:"Otevřené Srdce",741:"Čistý Hlas",852:"Vnitřní Zrak",963:"Božské Světlo"},
}
hz_sz=64; nm_sz=52; hzsm=40
fhz=F("Bold",hz_sz); fhzs=F("Bold",hzsm); NMW="Semibold"
UL=270      # every underline is exactly this long
DX,DY=82,28 # fixed diagonal kick toward the figure (same for all)
def shadow_text(xy,text,font,fill,anchor):
    x,y=xy
    for dx,dy in [(2,2),(2,-2),(-2,2),(-2,-2),(0,3)]:
        d.text((x+dx,y+dy),text,font=font,fill=(0,0,10),anchor=anchor)
    d.text((x,y),text,font=font,fill=fill,anchor=anchor)
def layout_name(name):
    f=F(NMW,nm_sz)
    if d.textlength(name,font=f)<=UL: return [(name,f)]
    words=name.split()
    if len(words)>=2:
        bk,bm=1,1e9
        for k in range(1,len(words)):
            m=max(d.textlength(" ".join(words[:k]),font=f),d.textlength(" ".join(words[k:]),font=f))
            if m<bm: bm=m; bk=k
        l1=" ".join(words[:bk]); l2=" ".join(words[bk:])
        while max(d.textlength(l1,font=f),d.textlength(l2,font=f))>UL and f.size>34: f=F(NMW,f.size-2)
        return [(l1,f),(l2,f)]
    while d.textlength(name,font=f)>UL and f.size>34: f=F(NMW,f.size-2)
    return [(name,f)]
names=NAMES[LOC]
for fid,(acc,side,xf,yf) in POS.items():
    x=int(xf*TW); y=int(yf*TH); acc_rgb=tuple(int(acc[i:i+2],16) for i in (1,3,5))
    numw=d.textlength(str(fid),font=fhz); hzw=d.textlength("Hz",font=fhzs)
    # number line "174 Hz"
    if side=="L":
        shadow_text((x,y),str(fid),fhz,"white","ls"); shadow_text((x+numw+6,y),"Hz",fhzs,"white","ls")
    else:
        shadow_text((x,y),"Hz",fhzs,"white","rs"); shadow_text((x-hzw-6,y),str(fid),fhz,"white","rs")
    # name (stacked if long)
    lines=layout_name(names[fid]); ny=y+nm_sz+4
    for i,(txt,f) in enumerate(lines):
        shadow_text((x,ny+i*int(nm_sz*1.02)),txt,f,"white","ls" if side=="L" else "rs")
    uy=ny+(len(lines)-1)*int(nm_sz*1.02)+14   # snug under the name block
    if side=="L":
        d.line([(x,uy),(x+UL,uy)],fill=acc_rgb,width=6)               # fixed underline
        d.line([(x+UL,uy),(x+UL+DX,uy-DY)],fill=acc_rgb,width=6)      # fixed diagonal toward figure
    else:
        d.line([(x-UL,uy),(x,uy)],fill=acc_rgb,width=6)
        d.line([(x-UL,uy),(x-UL-DX,uy-DY)],fill=acc_rgb,width=6)
os.makedirs(os.path.dirname(OUT),exist_ok=True)
img.save(OUT); print("saved",OUT,img.size)
